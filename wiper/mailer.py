"""Envoi des courriers par SMTP, configuré par variables d'environnement.

WIPER_SMTP_HOST, WIPER_SMTP_PORT (587 par défaut), WIPER_SMTP_USER,
WIPER_SMTP_PASSWORD, WIPER_SMTP_FROM (par défaut = WIPER_SMTP_USER).
Pour Gmail : un « mot de passe d'application » (pas ton vrai mot de passe).
"""
import os
import smtplib
from email.message import EmailMessage


def config():
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


def envoyer(destinataire, objet, corps, cfg=None, copie_a_moi=True):
    cfg = cfg or config()
    if not cfg:
        raise RuntimeError("SMTP non configuré")
    msg = EmailMessage()
    msg["From"] = cfg["from"]
    msg["To"] = destinataire
    if copie_a_moi and cfg["from"]:
        msg["Bcc"] = cfg["from"]  # garder une preuve d'envoi dans sa propre boîte
    msg["Subject"] = objet
    msg.set_content(corps)
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as s:
        s.starttls()
        if cfg["user"]:
            s.login(cfg["user"], cfg["password"] or "")
        s.send_message(msg)
