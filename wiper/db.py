"""Base SQLite locale. Elle vit dans instance/, qui est exclu du dépôt."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import click
from flask import current_app, g

STATUTS = {
    "a_contacter": "À contacter",
    "envoyee": "Demande envoyée",
    "reponse": "Réponse reçue",
    "supprime": "Supprimé",
    "refus": "Refus / sans suite",
    "non_concerne": "Non concerné",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS cible (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE,
    nom TEXT NOT NULL,
    categorie TEXT NOT NULL,
    pays TEXT,
    site TEXT,
    optout_url TEXT,
    contact_rgpd TEXT,
    methode TEXT,
    notes TEXT,
    statut TEXT NOT NULL DEFAULT 'a_contacter',
    date_envoi TEXT,
    maj TEXT NOT NULL,
    personnalisee INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS profil (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    prenom TEXT, nom TEXT, emails TEXT, adresse TEXT,
    date_naissance TEXT, telephone TEXT, pseudos TEXT
);
INSERT OR IGNORE INTO profil (id) VALUES (1);
CREATE TABLE IF NOT EXISTS reglage (
    cle TEXT PRIMARY KEY,
    valeur TEXT
);
CREATE TABLE IF NOT EXISTS decouverte_mail (
    domaine TEXT PRIMARY KEY,
    nb INTEGER NOT NULL,
    premier TEXT, dernier TEXT,
    compte INTEGER NOT NULL DEFAULT 0,
    newsletter INTEGER NOT NULL DEFAULT 0,
    objet TEXT
);
CREATE TABLE IF NOT EXISTS evenement (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cible_id INTEGER NOT NULL REFERENCES cible(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    statut TEXT,
    note TEXT
);
"""

SEED_FILE = Path(__file__).parent / "data" / "cibles.json"


def maintenant():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def charger_seed(db):
    """Ajoute les cibles du catalogue absentes de la base, sans toucher aux suivis existants."""
    cibles = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    ajoutees = 0
    for c in cibles:
        cur = db.execute(
            """INSERT OR IGNORE INTO cible
               (slug, nom, categorie, pays, site, optout_url, contact_rgpd, methode, notes, maj)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                c["slug"], c["nom"], c["categorie"], c.get("pays"), c.get("site"),
                c.get("optout_url"), c.get("contact_rgpd"), c.get("methode"),
                c.get("notes"), maintenant(),
            ),
        )
        ajoutees += cur.rowcount
    db.commit()
    return ajoutees


def _slugify(texte):
    import re
    import unicodedata
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") or "cible"


def ajouter_cible(db, nom, categorie, site=None, optout_url=None, contact_rgpd=None, notes=None, slug=None):
    """Ajoute une cible personnalisée et renvoie son id. Si `slug` est imposé et existe déjà, renvoie l'existante."""
    if slug:
        existante = db.execute("SELECT id FROM cible WHERE slug = ?", (slug,)).fetchone()
        if existante:
            return existante["id"]
    else:
        base = slug = "perso-" + _slugify(nom)
        i = 2
        while db.execute("SELECT 1 FROM cible WHERE slug = ?", (slug,)).fetchone():
            slug, i = f"{base}-{i}", i + 1
    cur = db.execute(
        """INSERT INTO cible (slug, nom, categorie, site, optout_url, contact_rgpd, notes, maj, personnalisee)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (slug, nom, categorie, site, optout_url, contact_rgpd, notes, maintenant()),
    )
    return cur.lastrowid


def migrer(db):
    """Ajoute les colonnes apparues après la première version, sans perdre de données."""
    colonnes = {r["name"] for r in db.execute("PRAGMA table_info(cible)")}
    if "date_relance" not in colonnes:
        db.execute("ALTER TABLE cible ADD COLUMN date_relance TEXT")
    if "contenu" not in {r["name"] for r in db.execute("PRAGMA table_info(evenement)")}:
        db.execute("ALTER TABLE evenement ADD COLUMN contenu TEXT")
    db.commit()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    migrer(db)
    return charger_seed(db)


@click.command("init-db")
def init_db_command():
    """Crée la base locale et charge (ou complète) le catalogue de cibles."""
    n = init_db()
    click.echo(f"Base prête. {n} nouvelle(s) cible(s) ajoutée(s).")


@click.command("analyser-mbox")
@click.argument("chemin", type=click.Path(exists=True, dir_okay=False))
def analyser_mbox_command(chemin):
    """Analyse un export .mbox (Google Takeout…) sans passer par le navigateur."""
    from .decouverte import analyser_mbox
    db = get_db()
    total, stats = analyser_mbox(chemin, mes_emails(db))
    enregistrer_analyse_mail(db, stats)
    click.echo(f"{total} e-mails lus, {len(stats)} expéditeurs trouvés. Résultats dans l'onglet Découverte.")


def lire_reglages(db):
    return {r["cle"]: r["valeur"] for r in db.execute("SELECT cle, valeur FROM reglage")}


def ecrire_reglages(db, valeurs):
    for cle, valeur in valeurs.items():
        if valeur:
            db.execute("INSERT OR REPLACE INTO reglage (cle, valeur) VALUES (?, ?)", (cle, valeur))
        else:
            db.execute("DELETE FROM reglage WHERE cle = ?", (cle,))
    db.commit()


def mes_emails(db):
    p = db.execute("SELECT emails FROM profil WHERE id = 1").fetchone()
    return [e.strip() for e in ((p and p["emails"]) or "").splitlines() if e.strip()]


def enregistrer_analyse_mail(db, stats):
    db.execute("DELETE FROM decouverte_mail")
    db.executemany(
        "INSERT INTO decouverte_mail (domaine, nb, premier, dernier, compte, newsletter, objet) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(d, s["nb"], s["premier"], s["dernier"], s["compte"], s["newsletter"], s["objet"]) for d, s in stats.items()],
    )
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(analyser_mbox_command)
    with app.app_context():
        init_db()
