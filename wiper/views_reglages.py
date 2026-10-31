import os

from flask import flash, redirect, render_template, request, url_for

from . import boite, mailer
from .db import ecrire_reglages, get_db, lire_reglages
from .views import bp


def cle_hibp():
    if os.environ.get("WIPER_HIBP_API_KEY"):
        return os.environ["WIPER_HIBP_API_KEY"]
    return lire_reglages(get_db()).get("hibp_cle")


@bp.route("/reglages", methods=["GET", "POST"])
def reglages():
    db = get_db()
    r = lire_reglages(db)
    if request.method == "POST":
        user = request.form.get("smtp_user", "").strip()
        valeurs = {
            "smtp_user": user,
            "smtp_host": request.form.get("smtp_host", "").strip(),
            "smtp_port": request.form.get("smtp_port", "").strip(),
            "imap_host": request.form.get("imap_host", "").strip(),
        }
        mdp = request.form.get("smtp_password", "").replace(" ", "")
        if mdp:
            valeurs["smtp_password"] = mdp
        elif not user:
            valeurs["smtp_password"] = ""
        cle = request.form.get("hibp_cle", "").strip()
        if cle or request.form.get("hibp_effacer"):
            valeurs["hibp_cle"] = cle
        ecrire_reglages(db, valeurs)
        if user and not valeurs["smtp_host"] and not mailer.serveur_pour(user):
            flash("Je ne connais pas le serveur d'envoi de cette adresse : renseigne-le dans « Réglages avancés ».")
        else:
            flash("Réglages enregistrés.")
            if user:
                return redirect(url_for("wiper.pilote"))
        return redirect(url_for("wiper.reglages"))

    return render_template(
        "reglages.html", r=r, smtp=mailer.config(), serveur_auto=mailer.serveur_pour(r.get("smtp_user")),
        hibp=bool(cle_hibp()), env_smtp=bool(os.environ.get("WIPER_SMTP_HOST")), imap=boite.config(),
    )


@bp.post("/reglages/test")
def tester_envoi():
    cfg = mailer.config()
    if not cfg:
        flash("Configure d'abord l'envoi d'e-mails.")
        return redirect(url_for("wiper.reglages"))
    try:
        mailer.envoyer(cfg["from"], "Test Online Data Wiper", "L'envoi d'e-mails fonctionne.", cfg, copie_a_moi=False)
    except Exception as e:  # noqa: BLE001 : on montre l'erreur telle quelle
        flash(f"Échec du test : {e}")
    else:
        flash(f"E-mail de test envoyé à {cfg['from']}. Regarde ta boîte de réception.")
    return redirect(url_for("wiper.reglages"))
