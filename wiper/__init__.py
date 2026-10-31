"""Online Data Wiper : suivi local de l'effacement de son empreinte en ligne."""
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, request

NOM_APPLI = "OnlineDataWiper"


def dossier_donnees():
    """Où ranger la base. Version installée : dossier utilisateur ; depuis le code : instance/."""
    if os.environ.get("WIPER_DATA_DIR"):
        return Path(os.environ["WIPER_DATA_DIR"])
    if not getattr(sys, "frozen", False):
        return None  # Flask utilisera instance/ à côté du code
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / NOM_APPLI


def _cle_secrete(dossier):
    f = Path(dossier) / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip()


def create_app(test_config=None):
    donnees = dossier_donnees()
    app = Flask(__name__, instance_relative_config=True, instance_path=str(donnees) if donnees else None)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("WIPER_SECRET_KEY") or _cle_secrete(app.instance_path),
        DATABASE=os.path.join(app.instance_path, "wiper.sqlite3"),
        RELANCE_JOURS=30,
        CNIL_JOURS=15,
        AUTO_PAUSE=3,
    )
    if test_config:
        app.config.update(test_config)

    @app.before_request
    def _anti_csrf():
        """Refuse les formulaires envoyés par un autre site que l'appli elle-même.

        Sans ça, n'importe quelle page web ouverte dans le navigateur pourrait
        poster vers 127.0.0.1 (par exemple pour envoyer un e-mail en ton nom).
        """
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return
        origine = request.headers.get("Origin") or request.headers.get("Referer")
        if origine is None:
            if app.testing:
                return
            abort(403)
        if urlparse(origine).netloc != request.host:
            abort(403)

    @app.get("/sante")
    def sante():
        return "online-data-wiper"

    from . import db, views, views_auto, views_bilan, views_decouverte, views_reglages  # noqa: F401 : enregistre les routes

    db.init_app(app)
    app.register_blueprint(views.bp)
    return app
