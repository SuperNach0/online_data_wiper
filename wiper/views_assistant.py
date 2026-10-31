"""Assistant de premier lancement : 3 écrans, puis tout part tout seul."""
from flask import current_app, redirect, render_template, request, url_for

from . import auto, boite, mailer
from .db import ecrire_reglages, get_db, lire_reglages
from .lanceur import demarrage_windows_possible, regler_demarrage_windows
from .views import bp, get_profil

AIDE_MDP = {
    "gmail.com": ("Google", "https://myaccount.google.com/apppasswords",
                  "La validation en deux étapes doit être activée sur ton compte Google. Donne un nom (par ex. « Wiper »), copie le code de 16 lettres."),
    "outlook": ("Microsoft", "https://account.live.com/proofs/AppPassword",
                "La vérification en deux étapes doit être activée sur ton compte Microsoft."),
    "yahoo": ("Yahoo", "https://login.yahoo.com/account/security", "Rubrique « Générer un mot de passe d'application »."),
    "icloud": ("Apple", "https://account.apple.com", "Rubrique « Mots de passe pour app »."),
}


def aide_mdp(email):
    dom = (email or "").split("@")[-1].lower()
    if dom in ("gmail.com", "googlemail.com"):
        return AIDE_MDP["gmail.com"]
    for cle in ("outlook", "hotmail", "live"):
        if cle in dom:
            return AIDE_MDP["outlook"]
    if "yahoo" in dom:
        return AIDE_MDP["yahoo"]
    if dom in ("icloud.com", "me.com"):
        return AIDE_MDP["icloud"]
    return None


@bp.before_app_request
def _vers_assistant():
    if not current_app.config.get("ASSISTANT") or request.endpoint not in ("wiper.index", "wiper.pilote"):
        return None
    if lire_reglages(get_db()).get("assistant_fait") != "1":
        return redirect(url_for("wiper.bienvenue"))
    return None


def tester_connexion():
    """(ok, message). Vérifie l'envoi (SMTP) et la lecture (IMAP) sans rien envoyer."""
    cfg = mailer.config()
    if not cfg:
        return False, "Je ne connais pas le serveur de cette adresse e-mail. Configure-le dans Réglages > Réglages avancés."
    try:
        mailer.tester(cfg)
    except Exception as e:  # noqa: BLE001
        return False, f"Connexion refusée pour l'envoi : {e}. Vérifie le mot de passe d'application."
    icfg = boite.config()
    if icfg:
        try:
            boite.connexion(icfg).logout()
        except Exception as e:  # noqa: BLE001
            return False, f"Connexion refusée pour la lecture de la boîte : {e}."
    return True, "Connexion réussie."


@bp.route("/bienvenue", methods=["GET", "POST"])
def bienvenue():
    db = get_db()
    etape = request.values.get("etape", "1")
    p = get_profil()
    r = lire_reglages(db)
    erreur = None

    if request.method == "POST" and etape == "1":
        emails = request.form.get("emails", "").strip()
        db.execute(
            "UPDATE profil SET prenom = ?, nom = ?, emails = ? WHERE id = 1",
            (request.form.get("prenom", "").strip() or None, request.form.get("nom", "").strip() or None, emails or None),
        )
        db.commit()
        if not request.form.get("nom", "").strip() or not emails:
            erreur = "Il faut au moins ton nom et une adresse e-mail."
        else:
            return redirect(url_for("wiper.bienvenue", etape="2"))

    elif request.method == "POST" and etape == "2":
        user = request.form.get("smtp_user", "").strip()
        mdp = request.form.get("smtp_password", "").replace(" ", "")
        valeurs = {"smtp_user": user}
        if mdp:
            valeurs["smtp_password"] = mdp
        ecrire_reglages(db, valeurs)
        ok, message = tester_connexion()
        if ok:
            return redirect(url_for("wiper.bienvenue", etape="3"))
        erreur = message

    elif request.method == "POST" and etape == "3":
        ecrire_reglages(db, {
            "auto_brokers": "1" if request.form.get("auto_brokers") else "0",
            "auto_comptes": "1" if request.form.get("auto_comptes") else "0",
            "auto_relances": "1" if request.form.get("auto_relances") else "0",
            "mode_auto": "1",
            "assistant_fait": "1",
        })
        if demarrage_windows_possible():
            try:
                regler_demarrage_windows(bool(request.form.get("demarrage_windows")))
            except OSError:
                pass
        auto.TACHES.lancer(current_app._get_current_object(), "Premier passage automatique",
                           lambda db, progression: auto.tache_quotidienne(db, progression))
        return redirect(url_for("wiper.pilote"))

    p = get_profil()
    r = lire_reglages(db)
    emails = [e.strip() for e in (p["emails"] or "").splitlines() if e.strip()]
    compte = r.get("smtp_user") or (emails[0] if emails else "")
    plan_auto, manuel = auto.plan(db) if etape == "3" else ([], [])
    return render_template(
        "bienvenue.html", etape=etape, p=p, r=r, erreur=erreur, compte=compte,
        aide=aide_mdp(compte), plan_auto=plan_auto, nb_manuel=len(manuel),
        win_possible=demarrage_windows_possible(),
    )
