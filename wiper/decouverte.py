"""Étape 3 : trouver où l'on apparaît (fuites, recherches, boîte mail)."""
import json
import mailbox
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from email.header import decode_header, make_header
from email.parser import BytesHeaderParser
from email.utils import getaddresses, parsedate_to_datetime

# --------------------------------------------------------------------------
# Have I Been Pwned
# --------------------------------------------------------------------------

HIBP_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{}?truncateResponse=false"


class HibpErreur(Exception):
    pass


def hibp_fuites(email, api_key, opener=urllib.request.urlopen):
    """Liste des fuites contenant cet e-mail (liste vide si aucune)."""
    req = urllib.request.Request(
        HIBP_URL.format(urllib.parse.quote(email)),
        headers={"hibp-api-key": api_key, "user-agent": "online-data-wiper"},
    )
    try:
        with opener(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        if e.code == 401:
            raise HibpErreur("Clé API Have I Been Pwned refusée.") from e
        if e.code == 429:
            raise HibpErreur("Trop de requêtes vers Have I Been Pwned, réessaie dans une minute.") from e
        raise HibpErreur(f"Erreur Have I Been Pwned ({e.code}).") from e
    except urllib.error.URLError as e:
        raise HibpErreur(f"Have I Been Pwned injoignable : {e.reason}") from e


def hibp_tous(emails, api_key, opener=urllib.request.urlopen, pause=6.5):
    """{email: [fuites]} en respectant la limite de débit de l'API (10 requêtes/min)."""
    resultats = {}
    for i, email in enumerate(emails):
        if i and pause:
            time.sleep(pause)
        resultats[email] = hibp_fuites(email, api_key, opener)
    return resultats


# --------------------------------------------------------------------------
# Recherche par nom, e-mail et pseudo
# --------------------------------------------------------------------------

MOTEURS = {
    "Google": "https://www.google.com/search?q={}",
    "DuckDuckGo": "https://duckduckgo.com/?q={}",
    "Bing": "https://www.bing.com/search?q={}",
    "Google Images": "https://www.google.com/search?tbm=isch&q={}",
}

PROFILS = {
    "GitHub": "https://github.com/{}",
    "GitLab": "https://gitlab.com/{}",
    "X / Twitter": "https://x.com/{}",
    "Instagram": "https://www.instagram.com/{}/",
    "Facebook": "https://www.facebook.com/{}",
    "TikTok": "https://www.tiktok.com/@{}",
    "YouTube": "https://www.youtube.com/@{}",
    "Reddit": "https://www.reddit.com/user/{}",
    "Twitch": "https://www.twitch.tv/{}",
    "Pinterest": "https://www.pinterest.com/{}/",
    "Medium": "https://medium.com/@{}",
    "SoundCloud": "https://soundcloud.com/{}",
    "Steam": "https://steamcommunity.com/id/{}",
    "Telegram": "https://t.me/{}",
    "Vimeo": "https://vimeo.com/{}",
    "Flickr": "https://www.flickr.com/people/{}",
    "DeviantArt": "https://www.deviantart.com/{}",
    "Chess.com": "https://www.chess.com/member/{}",
    "Lichess": "https://lichess.org/@/{}",
    "Keybase": "https://keybase.io/{}",
}


def liens_recherche(profil):
    nom = " ".join(x for x in [profil["prenom"], profil["nom"]] if x).strip()
    emails = [e.strip() for e in (profil["emails"] or "").splitlines() if e.strip()]
    pseudos = [p.strip().lstrip("@") for p in (profil["pseudos"] or "").splitlines() if p.strip()]

    requetes = []
    if nom:
        requetes.append(f'"{nom}"')
        if profil["adresse"]:
            ville = profil["adresse"].splitlines()[-1].strip()
            requetes.append(f'"{nom}" {ville}')
    requetes += [f'"{e}"' for e in emails]
    requetes += [f'"{p}"' for p in pseudos]
    recherches = [
        {"requete": q, "liens": {m: u.format(urllib.parse.quote_plus(q)) for m, u in MOTEURS.items()}}
        for q in requetes
    ]
    profils = [
        {"pseudo": p, "liens": {site: u.format(urllib.parse.quote(p)) for site, u in PROFILS.items()}}
        for p in pseudos
    ]
    return recherches, profils


# --------------------------------------------------------------------------
# Analyse d'un export de boîte mail (.mbox, ex. Google Takeout)
# --------------------------------------------------------------------------

FOURNISSEURS_PERSO = {
    "gmail.com", "googlemail.com", "outlook.com", "outlook.fr", "hotmail.com", "hotmail.fr", "live.com",
    "live.fr", "msn.com", "yahoo.com", "yahoo.fr", "icloud.com", "me.com", "mac.com", "orange.fr",
    "wanadoo.fr", "free.fr", "sfr.fr", "neuf.fr", "laposte.net", "bbox.fr", "aol.com", "proton.me",
    "protonmail.com", "gmx.fr", "gmx.com", "yandex.com", "zoho.com",
}
SECOND_NIVEAU = {"co", "com", "org", "net", "gouv", "ac", "gov", "edu", "asso"}

MOTS_COMPTE = re.compile(
    r"bienvenue|welcome|confirm|vérif|verif|activ|inscription|sign[ -]?up|registration|"
    r"mot de passe|password|identifiant|compte|account|connexion|login|log in|code de sécurité|security code",
    re.IGNORECASE,
)


def domaine_principal(domaine):
    parts = domaine.lower().strip(".").split(".")
    if len(parts) >= 3 and parts[-2] in SECOND_NIVEAU and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _decode(valeur):
    if not valeur:
        return ""
    try:
        return str(make_header(decode_header(str(valeur))))
    except Exception:  # noqa: BLE001 : en-têtes mal formés, fréquents dans les vieux mails
        return str(valeur)


def analyser_mbox(chemin, mes_emails=()):
    """Regroupe les expéditeurs par domaine. Ne lit que les en-têtes, rien n'est conservé d'autre."""
    mes_domaines = {e.split("@")[-1].lower() for e in mes_emails}
    stats = defaultdict(lambda: {"nb": 0, "premier": None, "dernier": None, "compte": 0, "newsletter": 0, "objet": ""})
    parser = BytesHeaderParser()
    mb = mailbox.mbox(chemin, create=False)
    total = 0
    try:
        for key in mb.iterkeys():
            with mb.get_file(key) as f:
                h = parser.parse(f, headersonly=True)
            total += 1
            adresses = getaddresses([_decode(h.get("From"))])
            if not adresses or "@" not in adresses[0][1]:
                continue
            dom_complet = adresses[0][1].split("@")[-1].lower().strip(">")
            if dom_complet in FOURNISSEURS_PERSO or dom_complet in mes_domaines:
                continue
            dom = domaine_principal(dom_complet)
            s = stats[dom]
            s["nb"] += 1
            try:
                d = parsedate_to_datetime(h.get("Date")).date().isoformat()
                s["premier"] = min(filter(None, [s["premier"], d]))
                s["dernier"] = max(filter(None, [s["dernier"], d]))
            except Exception:  # noqa: BLE001
                pass
            objet = _decode(h.get("Subject"))
            if MOTS_COMPTE.search(objet):
                s["compte"] += 1
                if not s["objet"]:
                    s["objet"] = objet[:140]
            if h.get("List-Unsubscribe"):
                s["newsletter"] += 1
            if not s["objet"]:
                s["objet"] = objet[:140]
    finally:
        mb.close()
    return total, dict(stats)
