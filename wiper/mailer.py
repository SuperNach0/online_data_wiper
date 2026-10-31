"""Envoi des courriers par SMTP.

Réglé depuis la page Réglages de l'appli. Les variables d'environnement
WIPER_SMTP_HOST, WIPER_SMTP_PORT, WIPER_SMTP_USER, WIPER_SMTP_PASSWORD et
WIPER_SMTP_FROM restent possibles et passent en priorité.
"""
import os
import smtplib
from email.message import EmailMessage

from flask import has_app_context

# Serveurs connus, pour que l'utilisateur n'ait que son e-mail et son mot de passe à saisir.
SERVEURS = {
    "gmail.com": ("smtp.gmail.com", 587),
    "googlemail.com": ("smtp.gmail.com", 587),
    "outlook.com": ("smtp-mail.outlook.com", 587),
    "outlook.fr": ("smtp-mail.outlook.com", 587),
    "hotmail.com": ("smtp-mail.outlook.com", 587),
    "hotmail.fr": ("smtp-mail.outlook.com", 587),
    "live.fr": ("smtp-mail.outlook.com", 587),
    "live.com": ("smtp-mail.outlook.com", 587),
    "yahoo.fr": ("smtp.mail.yahoo.com", 465),
    "yahoo.com": ("smtp.mail.yahoo.com", 465),
    "icloud.com": ("smtp.mail.me.com", 587),
    "me.com": ("smtp.mail.me.com", 587),
    "orange.fr": ("smtp.orange.fr", 465),
    "wanadoo.fr": ("smtp.orange.fr", 465),
    "free.fr": ("smtp.free.fr", 465),
    "sfr.fr": ("smtp.sfr.fr", 465),
    "laposte.net": ("smtp.laposte.net", 465),
    "gmx.fr": ("mail.gmx.com", 587),
    "gmx.com": ("mail.gmx.com", 587),
}


def serveur_pour(email):
    return SERVEURS.get((email or "").split("@")[-1].lower())


def _depuis_env():
    host = os.environ.get("WIPER_SMTP_HOST")
    if not host:
        return None
    user = os.environ.get("WIPER_SMTP_USER")
    return {
        "host": host,
        "port": int(os.environ.get("WIPER_SMTP_PORT", "587")),
        "user": user,
        "password": os.environ.get("WIPER_SMTP_PASSWORD"),
        "from": os.environ.get("WIPER_SMTP_FROM") or user,
    }


def _depuis_reglages():
    if not has_app_context():
        return None
    from .db import get_db, lire_reglages

    r = lire_reglages(get_db())
    user = r.get("smtp_user")
    if not user or not r.get("smtp_password"):
        return None
    host, port = r.get("smtp_host"), r.get("smtp_port")
    if not host:
        connu = serveur_pour(user)
        if not connu:
            return None
        host, port = connu
    return {"host": host, "port": int(port or 587), "user": user, "password": r["smtp_password"], "from": user}


def config():
    return _depuis_env() or _depuis_reglages()


def envoyer(destinataire, objet, corps, cfg=None, copie_a_moi=True):
    cfg = cfg or config()
    if not cfg:
        raise RuntimeError("Envoi d'e-mails non configuré")
    msg = EmailMessage()
    msg["From"] = cfg["from"]
    msg["To"] = destinataire
    if copie_a_moi and cfg["from"] and cfg["from"] != destinataire:
        msg["Bcc"] = cfg["from"]  # garder une preuve d'envoi dans sa propre boîte
    msg["Subject"] = objet
    msg.set_content(corps)
    if cfg["port"] == 465:
        serveur = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=30)
    else:
        serveur = smtplib.SMTP(cfg["host"], cfg["port"], timeout=30)
    with serveur as s:
        if cfg["port"] != 465:
            s.starttls()
        if cfg["user"]:
            s.login(cfg["user"], cfg["password"] or "")
        s.send_message(msg)
