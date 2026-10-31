import pytest

from wiper import create_app, mailer
from wiper.db import get_db, lire_reglages
from wiper.views_reglages import cle_hibp


@pytest.fixture(autouse=True)
def _sans_env(monkeypatch):
    for v in ["WIPER_SMTP_HOST", "WIPER_HIBP_API_KEY"]:
        monkeypatch.delenv(v, raising=False)


def test_reglages_gmail_detecte(app, client):
    client.post("/reglages", data={"smtp_user": "moi@gmail.com", "smtp_password": "abcd efgh ijkl mnop", "hibp_cle": "k"})
    with app.test_request_context():
        cfg = mailer.config()
        assert cfg == {"host": "smtp.gmail.com", "port": 587, "user": "moi@gmail.com",
                       "password": "abcdefghijklmnop", "from": "moi@gmail.com"}
        assert cle_hibp() == "k"
    # mot de passe vide = on garde l'ancien
    client.post("/reglages", data={"smtp_user": "moi@gmail.com", "smtp_password": ""})
    with app.app_context():
        r = lire_reglages(get_db())
        assert r["smtp_password"] == "abcdefghijklmnop" and r["hibp_cle"] == "k"
    client.post("/reglages", data={"smtp_user": "moi@gmail.com", "hibp_effacer": "1"})
    with app.app_context():
        assert "hibp_cle" not in lire_reglages(get_db())


def test_serveur_inconnu_demande_reglage_avance(app, client):
    r = client.post("/reglages", data={"smtp_user": "moi@perso.example", "smtp_password": "x"}, follow_redirects=True)
    assert "Réglages avancés" in r.get_data(as_text=True)
    with app.test_request_context():
        assert mailer.config() is None
    client.post("/reglages", data={"smtp_user": "moi@perso.example", "smtp_host": "mail.perso.example", "smtp_port": "465"})
    with app.test_request_context():
        assert mailer.config()["host"] == "mail.perso.example" and mailer.config()["port"] == 465


def test_page_reglages(client):
    assert "non configuré" in client.get("/reglages").get_data(as_text=True)


def test_csrf_refuse_un_autre_site(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "t.sqlite3")})  # pas TESTING : la protection est complète
    c = app.test_client()
    data = {"nom": "x"}
    assert c.post("/profil", data=data).status_code == 403
    assert c.post("/profil", data=data, headers={"Origin": "https://site-malveillant.example"}).status_code == 403
    assert c.post("/profil", data=data, headers={"Origin": "http://localhost"}).status_code == 302


def test_lanceur_detecte_port(monkeypatch):
    from wiper import lanceur
    assert lanceur._deja_lancee(1) is False
