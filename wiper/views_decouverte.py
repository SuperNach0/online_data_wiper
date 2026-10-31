import os
import tempfile
from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, url_for

from . import decouverte
from .db import ajouter_cible, enregistrer_analyse_mail, get_db, maintenant, mes_emails
from .views import bp, get_profil

CAT_FUITE = "Fuite de données"
CAT_COMPTE = "Compte en ligne"


def hibp_cle():
    return os.environ.get("WIPER_HIBP_API_KEY")


def domaines_suivis(db):
    doms = set()
    for (site,) in db.execute("SELECT site FROM cible WHERE site IS NOT NULL"):
        host = urlparse(site).hostname
        if host:
            doms.add(decouverte.domaine_principal(host))
    return doms


@bp.route("/decouverte")
def decouverte_page():
    db = get_db()
    p = get_profil()
    recherches, profils = decouverte.liens_recherche(p)
    fuites = db.execute("SELECT * FROM cible WHERE categorie = ? ORDER BY nom", (CAT_FUITE,)).fetchall()
    filtre = request.args.get("mail", "comptes")
    sql = "SELECT * FROM decouverte_mail"
    if filtre == "comptes":
        sql += " WHERE compte > 0"
    sql += " ORDER BY compte DESC, nb DESC"
    domaines = db.execute(sql).fetchall()
    nb_domaines = db.execute("SELECT COUNT(*) FROM decouverte_mail").fetchone()[0]
    return render_template(
        "decouverte.html", emails=mes_emails(db), hibp=bool(hibp_cle()), fuites=fuites,
        recherches=recherches, profils=profils, domaines=domaines, nb_domaines=nb_domaines,
        suivis=domaines_suivis(db), filtre_mail=filtre,
    )


@bp.post("/decouverte/fuites")
def verifier_fuites():
    db = get_db()
    emails = mes_emails(db)
    if not hibp_cle():
        flash("Aucune clé Have I Been Pwned configurée (voir le README).")
        return redirect(url_for("wiper.decouverte_page"))
    if not emails:
        flash("Ajoute tes adresses e-mail dans ton profil d'abord.")
        return redirect(url_for("wiper.decouverte_page"))
    try:
        resultats = decouverte.hibp_tous(emails, hibp_cle())
    except decouverte.HibpErreur as e:
        flash(str(e))
        return redirect(url_for("wiper.decouverte_page"))
    nouvelles = enregistrer_fuites(db, resultats)
    total = sum(len(v) for v in resultats.values())
    flash(f"{total} fuite(s) trouvée(s) pour {len(emails)} adresse(s), dont {nouvelles} nouvelle(s) dans le suivi.")
    return redirect(url_for("wiper.decouverte_page"))


def enregistrer_fuites(db, resultats):
    nouvelles = 0
    for email, fuites in resultats.items():
        for f in fuites:
            slug = "fuite-" + f["Name"].lower()
            existe = db.execute("SELECT id, notes FROM cible WHERE slug = ?", (slug,)).fetchone()
            if existe:
                if email not in (existe["notes"] or ""):
                    db.execute(
                        "UPDATE cible SET notes = ?, maj = ? WHERE id = ?",
                        ((existe["notes"] or "") + f"\nAdresse concernée : {email}", maintenant(), existe["id"]),
                    )
                continue
            donnees = ", ".join(f.get("DataClasses") or [])
            notes = (
                f"Fuite du {f.get('BreachDate', '?')}. Données exposées : {donnees}.\n"
                f"Change ton mot de passe sur ce site (et partout où tu l'as réutilisé), "
                f"puis demande la suppression du compte.\nAdresse concernée : {email}"
            )
            ajouter_cible(
                db, f.get("Title") or f["Name"], CAT_FUITE,
                site=f"https://{f['Domain']}" if f.get("Domain") else None, notes=notes, slug=slug,
            )
            nouvelles += 1
    db.commit()
    return nouvelles


@bp.post("/decouverte/mbox")
def analyser_mbox():
    fichier = request.files.get("mbox")
    if not fichier or not fichier.filename:
        flash("Choisis un fichier .mbox.")
        return redirect(url_for("wiper.decouverte_page"))
    db = get_db()
    fd, chemin = tempfile.mkstemp(suffix=".mbox")
    try:
        with os.fdopen(fd, "wb") as out:
            fichier.save(out)
        total, stats = decouverte.analyser_mbox(chemin, mes_emails(db))
    except Exception as e:  # noqa: BLE001 : fichier illisible
        flash(f"Impossible de lire ce fichier : {e}")
        return redirect(url_for("wiper.decouverte_page"))
    finally:
        os.unlink(chemin)  # le contenu des mails n'est jamais conservé
    enregistrer_analyse_mail(db, stats)
    flash(f"{total} e-mails lus, {len(stats)} expéditeurs trouvés.")
    return redirect(url_for("wiper.decouverte_page") + "#mail")


@bp.post("/decouverte/mbox/ajouter")
def ajouter_domaines():
    db = get_db()
    suivis = domaines_suivis(db)
    n = 0
    for dom in request.form.getlist("domaine"):
        d = db.execute("SELECT * FROM decouverte_mail WHERE domaine = ?", (dom,)).fetchone()
        if not d or dom in suivis:
            continue
        notes = f"Trouvé dans ta boîte mail : {d['nb']} e-mail(s)"
        if d["premier"]:
            notes += f" du {d['premier']} au {d['dernier']}"
        notes += "."
        if d["objet"]:
            notes += f"\nExemple : « {d['objet']} »"
        ajouter_cible(db, dom, CAT_COMPTE, site=f"https://{dom}", notes=notes, slug=f"mail-{dom}")
        n += 1
    db.commit()
    flash(f"{n} site(s) ajouté(s) au suivi.")
    return redirect(url_for("wiper.decouverte_page") + "#mail")
