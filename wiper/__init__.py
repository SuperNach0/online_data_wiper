"""Online Data Wiper : suivi local de l'effacement de son empreinte en ligne."""
import os

from flask import Flask


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("WIPER_SECRET_KEY", "local-only"),
        DATABASE=os.path.join(app.instance_path, "wiper.sqlite3"),
        RELANCE_JOURS=30,
        CNIL_JOURS=15,
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    from . import db, views, views_decouverte  # noqa: F401 : enregistre les routes

    db.init_app(app)
    app.register_blueprint(views.bp)
    return app
