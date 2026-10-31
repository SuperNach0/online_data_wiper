"""Pilote automatique : envois groupés, relances, lecture des réponses, tâches quotidiennes."""
import re
import threading
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr

from flask import current_app

from . import annuaire, boite, courriers, decouverte, mailer
from .db import ajouter_cible, ecrire_reglages, enregistrer_analyse_mail, get_db, lire_reglages, maintenant, mes_emails
from .views import a_relancer, enregistrer_courrier, get_profil

# Ce qui ne peut pas partir par e-mail : formulaires, réglages de compte, inscriptions.
METHODES_MANUELLES = {"réglage du compte", "outil en ligne", "inscription"}
EMAIL_OK = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)
REBOND = re.compile(
    r"undeliver|delivery status notification|delivery has failed|mail delivery failed|returned mail|"
    r"non remis|échec de (la )?remise|impossible de remettre|adresse introuvable|address not found",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------
# Journal
# --------------------------------------------------------------------------

def journal(db, message, niveau="info"):
    db.execute("INSERT INTO journal (date, niveau, message) VALUES (?, ?, ?)", (maintenant(), niveau, message))
    db.commit()


# --------------------------------------------------------------------------
# Qui contacter, et comment
# --------------------------------------------------------------------------

def contact_pour(c):
    """Adresse e-mail à utiliser pour une cible, ou None si elle doit être traitée à la main."""
    if c["contact_invalide"]:
        return None
    contact = (c["contact_rgpd"] or "").strip()
    if EMAIL_OK.match(contact):
        return contact
    if (c["methode"] or "") in METHODES_MANUELLES:
        return None
    trouve = annuaire.chercher(c["site"]) if c["site"] else None
    return trouve["email"] if trouve else None


def plan(db):
    """Ce que « Tout lancer » va faire, et ce qui reste à faire à la main."""
    auto, manuel = [], []
    for c in db.execute("SELECT * FROM cible WHERE statut = 'a_contacter' ORDER BY categorie, nom"):
        dest = contact_pour(c)
        (auto if dest else manuel).append({"cible": c, "destinataire": dest})
    return auto, manuel


def comptes_trouves(db):
    """Comptes repérés dans la boîte mail, pas encore suivis, avec leur contact si l'annuaire le connaît."""
    from .views_decouverte import domaines_suivis

    suivis = domaines_suivis(db)
    res = []
    for d in db.execute("SELECT * FROM decouverte_mail WHERE compte > 0 ORDER BY compte DESC, nb DESC"):
        if d["domaine"] in suivis:
            continue
        a = annuaire.chercher(d["domaine"])
        res.append({"d": d, "contact": a["email"] if a else None, "nom": a["nom"] if a else d["domaine"]})
    return res


def a_faire(db):
    """Ce que l'utilisateur doit faire lui-même."""
    from .views import cnil_possible

    _auto, manuel = plan(db)
    cibles = db.execute("SELECT * FROM cible WHERE statut IN ('envoyee', 'reponse')").fetchall()
    return {
        "manuel": manuel,
        "reponses": [c for c in cibles if c["statut"] == "reponse"],
        "cnil": [c for c in cibles if cnil_possible(c)],
        "invalides": db.execute("SELECT * FROM cible WHERE contact_invalide = 1 AND statut = 'a_contacter'").fetchall(),
    }


# --------------------------------------------------------------------------
# Envois
# --------------------------------------------------------------------------

def envoyer_un(db, c, destinataire, type_courrier="effacement", cfg=None):
    lettre = courriers.rediger(type_courrier, get_profil(), c)
    mailer.envoyer(destinataire, lettre["objet"], lettre["corps"], cfg)
    if destinataire != (c["contact_rgpd"] or ""):
        db.execute("UPDATE cible SET contact_rgpd = ? WHERE id = ?", (destinataire, c["id"]))
    enregistrer_courrier(c, type_courrier, lettre["objet"], lettre["corps"], destinataire, "envoi automatique")


def envoyer_lot(db, envois, type_courrier="effacement", progression=None):
    """envois = [(cible_id, destinataire)]. Renvoie (nb envoyés, erreurs)."""
    cfg = mailer.config()
    if not cfg:
        raise RuntimeError("Envoi d'e-mails non configuré (onglet Réglages).")
    pause = current_app.config.get("AUTO_PAUSE", 3)
    ok, erreurs = 0, []
    for i, (cid, dest) in enumerate(envois):
        c = db.execute("SELECT * FROM cible WHERE id = ?", (cid,)).fetchone()
        if not c:
            continue
        try:
            envoyer_un(db, c, dest, type_courrier, cfg)
            ok += 1
        except Exception as e:  # noqa: BLE001 : on continue avec les suivants
            erreurs.append(f"{c['nom']} : {e}")
        if progression:
            progression(i + 1, len(envois))
        if pause and i + 1 < len(envois):
            time.sleep(pause)
    journal(db, f"{ok} courrier(s) {'de relance ' if type_courrier == 'relance' else ''}envoyé(s) automatiquement.")
    for e in erreurs:
        journal(db, f"Échec d'envoi : {e}", "erreur")
    return ok, erreurs


def preparer_comptes(db, domaines):
    """Crée les cibles des comptes cochés, renvoie [(cible_id, contact)] pour ceux qu'on peut contacter par e-mail."""
    envois = []
    for dom in domaines:
        d = db.execute("SELECT * FROM decouverte_mail WHERE domaine = ?", (dom,)).fetchone()
        if not d:
            continue
        a = annuaire.chercher(dom)
        notes = f"Trouvé dans ta boîte mail : {d['nb']} e-mail(s)"
        if d["premier"]:
            notes += f" du {d['premier']} au {d['dernier']}"
        notes += "."
        cid = ajouter_cible(
            db, a["nom"] if a else dom, "Compte en ligne", site=f"https://{dom}",
            contact_rgpd=a["email"] if a else None, notes=notes, slug=f"mail-{dom}",
        )
        if a:
            envois.append((cid, a["email"]))
    db.commit()
    return envois


def relances_auto(db):
    envois = []
    for c in db.execute("SELECT * FROM cible WHERE statut = 'envoyee' AND date_relance IS NULL"):
        if a_relancer(c):
            dest = contact_pour(c)
            if dest:
                envois.append((c["id"], dest))
    if not envois:
        return 0
    ok, _ = envoyer_lot(db, envois, "relance")
    return ok


# --------------------------------------------------------------------------
# Lecture des réponses
# --------------------------------------------------------------------------

def _domaine_email(adresse):
    adresse = parseaddr(adresse)[1].lower()
    return decouverte.domaine_principal(adresse.split("@")[-1]) if "@" in adresse else ""


def traiter_reponses(db, messages):
    """Met à jour les cibles à partir des messages reçus. Renvoie (réponses, rebonds)."""
    attente = db.execute("SELECT * FROM cible WHERE statut = 'envoyee'").fetchall()
    par_domaine = {}
    for c in attente:
        for source in [c["contact_rgpd"], c["site"]]:
            if source:
                dom = _domaine_email(source) if "@" in source else decouverte.domaine_principal(
                    re.sub(r"^https?://", "", source).split("/")[0])
                if dom:
                    par_domaine.setdefault(dom, c)
    mes_adresses = {e.lower() for e in mes_emails(db)}
    reponses = rebonds = 0
    for m in messages:
        if db.execute("SELECT 1 FROM message_traite WHERE message_id = ?", (m["message_id"],)).fetchone():
            continue
        db.execute("INSERT INTO message_traite (message_id, date) VALUES (?, ?)", (m["message_id"], maintenant()))
        expediteur = parseaddr(m["de"])[1].lower()
        if expediteur in mes_adresses:
            continue
        local = expediteur.split("@")[0]
        if local in ("mailer-daemon", "postmaster") or REBOND.search(m["objet"]):
            texte = m["texte"].lower()
            for c in attente:
                contact = (c["contact_rgpd"] or "").lower()
                if contact and contact in texte:
                    db.execute(
                        "UPDATE cible SET statut = 'a_contacter', contact_invalide = 1, date_envoi = NULL, maj = ? WHERE id = ?",
                        (maintenant(), c["id"]),
                    )
                    db.execute(
                        "INSERT INTO evenement (cible_id, date, statut, note) VALUES (?, ?, 'a_contacter', ?)",
                        (c["id"], maintenant(), f"L'adresse {contact} a rebondi : il faut trouver un autre contact."),
                    )
                    rebonds += 1
            continue
        c = par_domaine.get(_domaine_email(m["de"]))
        if c:
            db.execute("UPDATE cible SET statut = 'reponse', maj = ? WHERE id = ?", (maintenant(), c["id"]))
            db.execute(
                "INSERT INTO evenement (cible_id, date, statut, note, contenu) VALUES (?, ?, 'reponse', ?, ?)",
                (c["id"], maintenant(), f"Réponse reçue : « {m['objet']} »", f"De : {m['de']}\nDate : {m['date']}\n\n{m['texte']}"),
            )
            reponses += 1
    db.commit()
    return reponses, rebonds


def lire_reponses(db, cfg=None, imap=None):
    cfg = cfg or boite.config()
    if not cfg:
        return None
    envoi_le_plus_ancien = db.execute("SELECT MIN(date_envoi) FROM cible WHERE statut = 'envoyee'").fetchone()[0]
    if not envoi_le_plus_ancien:
        return 0, 0
    depuis = date.fromisoformat(envoi_le_plus_ancien[:10])
    messages = boite.messages_recents(cfg, depuis, imap=imap)
    reponses, rebonds = traiter_reponses(db, messages)
    if reponses or rebonds:
        journal(db, f"Boîte mail : {reponses} réponse(s) d'organismes, {rebonds} adresse(s) invalide(s).")
    return reponses, rebonds


def scanner_boite(db, progression=None, imap=None):
    cfg = boite.config()
    if not cfg:
        raise RuntimeError("Lecture de la boîte mail non configurée (onglet Réglages).")
    total, stats = boite.scanner_comptes(cfg, mes_emails(db), progression, imap=imap)
    enregistrer_analyse_mail(db, stats)
    nb = sum(1 for s in stats.values() if s["compte"])
    journal(db, f"Boîte mail analysée : {total} e-mails, {nb} comptes probables.")
    ecrire_reglages(db, {"dernier_scan": maintenant()})
    return total, nb


# --------------------------------------------------------------------------
# Tâche quotidienne et tâches de fond
# --------------------------------------------------------------------------

def tache_quotidienne(db):
    r = lire_reglages(db)
    try:
        lire_reponses(db)
    except Exception as e:  # noqa: BLE001
        journal(db, f"Lecture de la boîte mail impossible : {e}", "erreur")
    if r.get("auto_relances", "1") == "1" and mailer.config():
        try:
            relances_auto(db)
        except Exception as e:  # noqa: BLE001
            journal(db, f"Relances impossibles : {e}", "erreur")
    from .views_decouverte import enregistrer_fuites
    from .views_reglages import cle_hibp

    derniere_hibp = r.get("derniere_hibp")
    if cle_hibp() and (not derniere_hibp or derniere_hibp < _il_y_a(7)):
        try:
            res = decouverte.hibp_tous(mes_emails(db), cle_hibp())
            n = enregistrer_fuites(db, res)
            ecrire_reglages(db, {"derniere_hibp": maintenant()})
            if n:
                journal(db, f"{n} nouvelle(s) fuite(s) de données trouvée(s).")
        except Exception as e:  # noqa: BLE001
            journal(db, f"Vérification des fuites impossible : {e}", "erreur")
    ecrire_reglages(db, {"derniere_auto": maintenant()})


def _il_y_a(jours=0, heures=0):
    return (datetime.now(timezone.utc) - timedelta(days=jours, hours=heures)).replace(microsecond=0).isoformat()


class Taches:
    """Une seule tâche longue à la fois (scan, envoi groupé), suivie par la page Pilote automatique."""

    def __init__(self):
        self.verrou = threading.Lock()
        self.etat = {"nom": None, "fait": 0, "total": 0, "message": None, "en_cours": False}

    def lancer(self, app, nom, fonction):
        if self.etat["en_cours"]:
            return False
        self.etat = {"nom": nom, "fait": 0, "total": 0, "message": None, "en_cours": True}

        def progression(fait, total):
            self.etat.update(fait=fait, total=total)

        def corps():
            with self.verrou, app.app_context():
                try:
                    self.etat["message"] = fonction(get_db(), progression)
                except Exception as e:  # noqa: BLE001
                    self.etat["message"] = f"Erreur : {e}"
                    traceback.print_exc()
                finally:
                    self.etat["en_cours"] = False

        threading.Thread(target=corps, daemon=True).start()
        return True


TACHES = Taches()


def demarrer_pilote(app, intervalle=3600, delai=60):
    """Thread qui lance la tâche quotidienne au plus une fois toutes les 20 h, tant que l'appli tourne."""

    def boucle():
        time.sleep(delai)
        while True:
            with app.app_context():
                db = get_db()
                derniere = lire_reglages(db).get("derniere_auto")
                if not derniere or derniere < _il_y_a(heures=20):
                    with TACHES.verrou:
                        try:
                            tache_quotidienne(db)
                        except Exception as e:  # noqa: BLE001
                            journal(db, f"Pilote automatique : {e}", "erreur")
            time.sleep(intervalle)

    threading.Thread(target=boucle, daemon=True).start()
