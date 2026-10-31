from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from . import courriers, mailer
from .db import STATUTS, ajouter_cible, get_db, maintenant

bp = Blueprint("wiper", __name__)


def _il_y_a(jours):
    return (datetime.now(timezone.utc) - timedelta(days=jours)).replace(microsecond=0).isoformat()


def _seuil_relance():
    return _il_y_a(current_app.config["RELANCE_JOURS"])


def _seuil_cnil():
    return _il_y_a(current_app.config["CNIL_JOURS"])


SQL_A_RELANCER = "statut = 'envoyee' AND date_relance IS NULL AND date_envoi <= ?"
SQL_CNIL = "statut = 'envoyee' AND date_relance IS NOT NULL AND date_relance <= ?"


def a_relancer(cible):
    return (
        cible["statut"] == "envoyee"
        and cible["date_relance"] is None
        and cible["date_envoi"] is not None
        and cible["date_envoi"] <= _seuil_relance()
    )


def cnil_possible(cible):
    return (
        cible["statut"] == "envoyee"
        and cible["date_relance"] is not None
        and cible["date_relance"] <= _seuil_cnil()
    )


def get_profil():
    return get_db().execute("SELECT * FROM profil WHERE id = 1").fetchone()


@bp.app_context_processor
def _contexte():
    return {"STATUTS": STATUTS, "a_relancer": a_relancer, "cnil_possible": cnil_possible}


@bp.route("/")
def index():
    db = get_db()
    statut = request.args.get("statut", "")
    categorie = request.args.get("categorie", "")
    q = request.args.get("q", "").strip()

    sql = "SELECT * FROM cible WHERE 1=1"
    params = []
    if statut == "a_relancer":
        sql += " AND " + SQL_A_RELANCER
        params.append(_seuil_relance())
    elif statut == "cnil":
        sql += " AND " + SQL_CNIL
        params.append(_seuil_cnil())
    elif statut in STATUTS:
        sql += " AND statut = ?"
        params.append(statut)
    if categorie:
        sql += " AND categorie = ?"
        params.append(categorie)
    if q:
        sql += " AND (nom LIKE ? OR notes LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY categorie, nom"
    cibles = db.execute(sql, params).fetchall()

    compte = {k: 0 for k in STATUTS}
    for row in db.execute("SELECT statut, COUNT(*) n FROM cible GROUP BY statut"):
        compte[row["statut"]] = row["n"]
    total = sum(compte.values())
    nb_relance = db.execute(
        "SELECT COUNT(*) FROM cible WHERE " + SQL_A_RELANCER, (_seuil_relance(),)
    ).fetchone()[0]
    nb_cnil = db.execute("SELECT COUNT(*) FROM cible WHERE " + SQL_CNIL, (_seuil_cnil(),)).fetchone()[0]
    categories = [r[0] for r in db.execute("SELECT DISTINCT categorie FROM cible ORDER BY categorie")]
    fini = compte["supprime"] + compte["non_concerne"]

    return render_template(
        "index.html",
        cibles=cibles, compte=compte, total=total, nb_relance=nb_relance, nb_cnil=nb_cnil, fini=fini,
        profil_incomplet=courriers.profil_incomplet(get_profil()),
        categories=categories, filtre={"statut": statut, "categorie": categorie, "q": q},
    )


def _get_cible(cible_id):
    cible = get_db().execute("SELECT * FROM cible WHERE id = ?", (cible_id,)).fetchone()
    if cible is None:
        abort(404)
    return cible


@bp.route("/cible/<int:cible_id>")
def cible(cible_id):
    c = _get_cible(cible_id)
    evenements = get_db().execute(
        "SELECT * FROM evenement WHERE cible_id = ? ORDER BY date DESC, id DESC", (cible_id,)
    ).fetchall()
    return render_template("cible.html", c=c, evenements=evenements)


@bp.post("/cible/<int:cible_id>/statut")
def changer_statut(cible_id):
    c = _get_cible(cible_id)
    statut = request.form.get("statut", c["statut"])
    note = request.form.get("note", "").strip()
    if statut not in STATUTS:
        abort(400)
    db = get_db()
    date_envoi = c["date_envoi"]
    if statut == "envoyee" and c["statut"] != "envoyee":
        date_envoi = maintenant()
    date_relance = c["date_relance"]
    if statut != "envoyee":
        date_relance = None
    if statut == "a_contacter":
        date_envoi = None
    db.execute(
        "UPDATE cible SET statut = ?, date_envoi = ?, date_relance = ?, maj = ? WHERE id = ?",
        (statut, date_envoi, date_relance, maintenant(), cible_id),
    )
    if statut != c["statut"] or note:
        db.execute(
            "INSERT INTO evenement (cible_id, date, statut, note) VALUES (?, ?, ?, ?)",
            (cible_id, maintenant(), statut if statut != c["statut"] else None, note or None),
        )
    db.commit()
    flash(f"{c['nom']} : {STATUTS[statut]}")
    return redirect(request.form.get("retour") or url_for("wiper.cible", cible_id=cible_id))


@bp.route("/ajouter", methods=["GET", "POST"])
def ajouter():
    if request.method == "POST":
        nom = request.form.get("nom", "").strip()
        if not nom:
            flash("Le nom est obligatoire.")
            return render_template("ajouter.html", form=request.form), 400
        db = get_db()
        cid = ajouter_cible(
            db, nom, request.form.get("categorie", "").strip() or "Site / compte perso",
            site=request.form.get("site", "").strip() or None,
            optout_url=request.form.get("optout_url", "").strip() or None,
            contact_rgpd=request.form.get("contact_rgpd", "").strip() or None,
            notes=request.form.get("notes", "").strip() or None,
        )
        db.commit()
        flash(f"{nom} ajouté au suivi.")
        return redirect(url_for("wiper.cible", cible_id=cid))
    return render_template("ajouter.html", form=request.args)


@bp.route("/profil", methods=["GET", "POST"])
def profil():
    if request.method == "POST":
        champs = ["prenom", "nom", "emails", "adresse", "date_naissance", "telephone", "pseudos"]
        valeurs = [request.form.get(k, "").strip() or None for k in champs]
        db = get_db()
        db.execute(
            "UPDATE profil SET " + ", ".join(f"{k} = ?" for k in champs) + " WHERE id = 1", valeurs
        )
        db.commit()
        flash("Profil enregistré.")
        return redirect(url_for("wiper.profil"))
    return render_template("profil.html", p=get_profil())


def type_par_defaut(c):
    if cnil_possible(c):
        return "plainte_cnil"
    if a_relancer(c) or (c["statut"] == "envoyee" and c["date_envoi"]):
        return "relance"
    return "effacement"


def _destinataire_email(c):
    contact = (c["contact_rgpd"] or "").strip()
    return contact if "@" in contact and " " not in contact else ""


def enregistrer_courrier(c, type_courrier, objet, corps, destinataire, moyen):
    db = get_db()
    now = maintenant()
    if type_courrier == "relance":
        db.execute(
            "UPDATE cible SET statut = 'envoyee', date_envoi = COALESCE(date_envoi, ?), date_relance = ?, maj = ? WHERE id = ?",
            (now, now, now, c["id"]),
        )
        statut_ev, texte = "envoyee", "Relance envoyée"
    elif type_courrier == "plainte_cnil":
        statut_ev, texte = None, "Plainte CNIL déposée"
    else:
        db.execute(
            "UPDATE cible SET statut = 'envoyee', date_envoi = ?, date_relance = NULL, maj = ? WHERE id = ?",
            (now, now, c["id"]),
        )
        statut_ev, texte = "envoyee", "Demande RGPD envoyée"
    if destinataire:
        texte += f" à {destinataire}"
    texte += f" ({moyen})"
    db.execute(
        "INSERT INTO evenement (cible_id, date, statut, note, contenu) VALUES (?, ?, ?, ?, ?)",
        (c["id"], now, statut_ev, texte, f"Objet : {objet}\n\n{corps}"),
    )
    db.commit()


@bp.route("/cible/<int:cible_id>/courrier", methods=["GET", "POST"])
def courrier(cible_id):
    c = _get_cible(cible_id)
    type_courrier = request.values.get("type") or type_par_defaut(c)
    if type_courrier not in courriers.MODELES:
        abort(400)
    smtp = mailer.config()

    if request.method == "POST":
        objet = request.form.get("objet", "").strip()
        corps = request.form.get("corps", "")
        destinataire = request.form.get("destinataire", "").strip()
        action = request.form.get("action")
        if action == "envoyer":
            if not smtp:
                abort(400)
            if "@" not in destinataire:
                flash("Indique une adresse e-mail de destination.")
                return redirect(url_for("wiper.courrier", cible_id=cible_id, type=type_courrier))
            try:
                mailer.envoyer(destinataire, objet, corps, smtp)
            except Exception as exc:  # noqa: BLE001 : on affiche l'erreur SMTP à l'utilisateur
                flash(f"Échec de l'envoi : {exc}")
                return redirect(url_for("wiper.courrier", cible_id=cible_id, type=type_courrier))
            if destinataire != (c["contact_rgpd"] or ""):
                get_db().execute("UPDATE cible SET contact_rgpd = ? WHERE id = ?", (destinataire, cible_id))
            enregistrer_courrier(c, type_courrier, objet, corps, destinataire, "e-mail")
            flash(f"Courrier envoyé à {destinataire}.")
        else:
            enregistrer_courrier(c, type_courrier, objet, corps, destinataire, "envoi manuel")
            flash("Courrier noté comme envoyé.")
        return redirect(url_for("wiper.cible", cible_id=cible_id))

    p = get_profil()
    lettre = courriers.rediger(type_courrier, p, c)
    return render_template(
        "courrier.html", c=c, type_courrier=type_courrier, modeles=courriers.MODELES,
        lettre=lettre, destinataire=_destinataire_email(c), smtp=smtp,
        profil_incomplet=courriers.profil_incomplet(p),
    )
