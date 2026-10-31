"""Lecture de la boîte mail par IMAP (même mot de passe d'application que l'envoi).

Sert à trois choses : retrouver les comptes oubliés (en-têtes de tous les
messages), repérer les réponses des organismes et les adresses qui rebondissent.
Rien n'est modifié dans la boîte : tout est lu en lecture seule.
"""
import imaplib
import re
from datetime import date
from email import message_from_bytes
from email.parser import BytesHeaderParser
from email.policy import default as politique

from flask import has_app_context

from .decouverte import Agregateur

SERVEURS_IMAP = {
    "gmail.com": "imap.gmail.com", "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com", "outlook.fr": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com", "hotmail.fr": "outlook.office365.com",
    "live.com": "outlook.office365.com", "live.fr": "outlook.office365.com",
    "yahoo.fr": "imap.mail.yahoo.com", "yahoo.com": "imap.mail.yahoo.com",
    "icloud.com": "imap.mail.me.com", "me.com": "imap.mail.me.com",
    "orange.fr": "imap.orange.fr", "wanadoo.fr": "imap.orange.fr",
    "free.fr": "imap.free.fr", "sfr.fr": "imap.sfr.fr", "laposte.net": "imap.laposte.net",
    "gmx.fr": "imap.gmx.com", "gmx.com": "imap.gmx.com",
}
MOIS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LOT = 250


def config():
    if not has_app_context():
        return None
    from .db import get_db, lire_reglages

    r = lire_reglages(get_db())
    user, mdp = r.get("smtp_user"), r.get("smtp_password")
    if not user or not mdp:
        return None
    host = r.get("imap_host") or SERVEURS_IMAP.get(user.split("@")[-1].lower())
    if not host:
        return None
    return {"host": host, "user": user, "password": mdp}


def connexion(cfg):
    imap = imaplib.IMAP4_SSL(cfg["host"], 993, timeout=60)
    imap.login(cfg["user"], cfg["password"])
    return imap


def _date_imap(d):
    return f"{d.day:02d}-{MOIS[d.month - 1]}-{d.year}"


def dossier_tous_messages(imap):
    """Le dossier qui contient tout (Gmail : « Tous les messages »), sinon la boîte de réception."""
    typ, lignes = imap.list()
    if typ == "OK":
        for ligne in lignes or []:
            texte = ligne.decode("utf-8", "replace") if isinstance(ligne, bytes) else str(ligne)
            if "\\All" in texte:
                m = re.search(r'"([^"]+)"\s*$', texte) or re.search(r"(\S+)\s*$", texte)
                if m:
                    return f'"{m.group(1)}"'
    return "INBOX"


def _uids(imap, depuis=None):
    critere = f"SINCE {_date_imap(depuis)}" if depuis else "ALL"
    typ, data = imap.uid("search", None, critere)
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _fetch(imap, uids, partie):
    """[(uid, octets)] pour un lot d'uids."""
    typ, data = imap.uid("fetch", b",".join(uids), f"(UID {partie})")
    res = []
    if typ != "OK":
        return res
    for item in data:
        if isinstance(item, tuple) and len(item) >= 2:
            m = re.search(rb"UID (\d+)", item[0])
            res.append((m.group(1) if m else None, item[1]))
    return res


def scanner_comptes(cfg, mes_emails=(), progression=None, imap=None):
    """Équivalent de l'analyse .mbox, directement sur la boîte en ligne."""
    imap = imap or connexion(cfg)
    try:
        imap.select(dossier_tous_messages(imap), readonly=True)
        uids = _uids(imap)
        agg = Agregateur(mes_emails)
        parser = BytesHeaderParser()
        for i in range(0, len(uids), LOT):
            for _uid, brut in _fetch(imap, uids[i:i + LOT], "BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE LIST-UNSUBSCRIBE)]"):
                agg.ajouter(parser.parsebytes(brut))
            if progression:
                progression(min(i + LOT, len(uids)), len(uids))
        return agg.resultat()
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass


def _texte(msg):
    try:
        partie = msg.get_body(preferencelist=("plain", "html"))
        contenu = partie.get_content() if partie else ""
    except Exception:  # noqa: BLE001 : message tronqué ou mal formé
        contenu = ""
    if not contenu:
        try:
            contenu = msg.get_payload(decode=True).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            contenu = ""
    contenu = re.sub(r"<[^>]+>", " ", contenu)
    return re.sub(r"[ \t\r]+", " ", contenu).strip()


def messages_recents(cfg, depuis: date, filtre=None, imap=None):
    """Messages reçus depuis `depuis` dans la boîte de réception.

    `filtre(entetes)` décide pour quels messages on télécharge le début du contenu.
    Renvoie des dicts {message_id, de, objet, date, texte}.
    """
    imap = imap or connexion(cfg)
    try:
        imap.select("INBOX", readonly=True)
        uids = _uids(imap, depuis)
        parser = BytesHeaderParser(policy=politique)
        retenus = []
        for i in range(0, len(uids), LOT):
            for uid, brut in _fetch(imap, uids[i:i + LOT], "BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)]"):
                h = parser.parsebytes(brut)
                if filtre is None or filtre(h):
                    retenus.append((uid, h))
        sortie = []
        for uid, h in retenus:
            corps = _fetch(imap, [uid], "BODY.PEEK[]<0.40000>")
            msg = message_from_bytes(corps[0][1], policy=politique) if corps else h
            sortie.append({
                "message_id": str(h.get("Message-ID") or f"uid-{uid.decode() if uid else '?'}").strip(),
                "de": str(h.get("From") or ""),
                "objet": str(h.get("Subject") or ""),
                "date": str(h.get("Date") or ""),
                "texte": _texte(msg)[:3000],
            })
        return sortie
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass
