import re
import unicodedata
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from .db import STATUTS, get_db, maintenant

bp = Blueprint("wiper", __name__)


def _seuil_relance():
    jours = current_app.config["RELANCE_JOURS"]
    return (datetime.now(timezone.utc) - timedelta(days=jours)).replace(microsecond=0).isoformat()


def a_relancer(cible):
    return (
        cible["statut"] == "envoyee"
        and cible["date_envoi"] is not None
        and cible["date_envoi"] <= _seuil_relance()
    )


def _slugify(texte):
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") or "cible"


@bp.app_context_processor
def _contexte():
    return {"STATUTS": STATUTS, "a_relancer": a_relancer}


@bp.route("/")
def index():
    db = get_db()
    statut = request.args.get("statut", "")
    categorie = request.args.get("categorie", "")
    q = request.args.get("q", "").strip()

    sql = "SELECT * FROM cible WHERE 1=1"
    params = []
    if statut == "a_relancer":
        sql += " AND statut = 'envoyee' AND date_envoi <= ?"
        params.append(_seuil_relance())
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
        "SELECT COUNT(*) FROM cible WHERE statut = 'envoyee' AND date_envoi <= ?",
        (_seuil_relance(),),
    ).fetchone()[0]
    categories = [r[0] for r in db.execute("SELECT DISTINCT categorie FROM cible ORDER BY categorie")]
    fini = compte["supprime"] + compte["non_concerne"]

    return render_template(
        "index.html",
        cibles=cibles, compte=compte, total=total, nb_relance=nb_relance, fini=fini,
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
    if statut == "a_contacter":
        date_envoi = None
    db.execute(
        "UPDATE cible SET statut = ?, date_envoi = ?, maj = ? WHERE id = ?",
        (statut, date_envoi, maintenant(), cible_id),
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
        base = slug = "perso-" + _slugify(nom)
        i = 2
        while db.execute("SELECT 1 FROM cible WHERE slug = ?", (slug,)).fetchone():
            slug, i = f"{base}-{i}", i + 1
        cur = db.execute(
            """INSERT INTO cible (slug, nom, categorie, site, optout_url, contact_rgpd, notes, maj, personnalisee)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                slug, nom, request.form.get("categorie", "").strip() or "Site / compte perso",
                request.form.get("site", "").strip() or None,
                request.form.get("optout_url", "").strip() or None,
                request.form.get("contact_rgpd", "").strip() or None,
                request.form.get("notes", "").strip() or None, maintenant(),
            ),
        )
        db.commit()
        flash(f"{nom} ajouté au suivi.")
        return redirect(url_for("wiper.cible", cible_id=cur.lastrowid))
    return render_template("ajouter.html", form={})
