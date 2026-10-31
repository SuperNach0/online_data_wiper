import pytest

from wiper import create_app
from wiper.db import get_db


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3")})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def cible_id(app):
    def _get(slug):
        with app.app_context():
            return get_db().execute("SELECT id FROM cible WHERE slug = ?", (slug,)).fetchone()[0]
    return _get
