from datetime import date, timedelta

from wiper import auto, boite, create_app, mailer
from wiper.db import get_db, lire_reglages


def test_redirection_vers_assistant(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "a.sqlite3")})
    c = app.test_client()
    assert c.get("/").headers["Location"].endswith("/bienvenue")
    assert c.get("/auto").headers["Location"].endswith("/bienvenue")
    assert c.get("/reglages").status_code == 200


def test_assistant_complet(tmp_path, monkeypatch):
    app = create_app({"TESTING": True, "AUTO_PAUSE": 0, "DATABASE": str(tmp_path / "a.sqlite3")})
    c = app.test_client()
    monkeypatch.setattr(mailer, "tester", lambda cfg=None: None)

    class FauxImap:
        def logout(self):
            pass
    monkeypatch.setattr(boite, "connexion", lambda cfg: FauxImap())
    lances = []
    monkeypatch.setattr(auto.TACHES, "lancer", lambda app, nom, f: lances.append(nom) or True)

    r = c.post("/bienvenue", data={"etape": "1", "prenom": "Camille", "nom": "Martin", "emails": "camille@gmail.com"})
    assert r.headers["Location"].endswith("etape=2")
    html = c.get("/bienvenue?etape=2").get_data(as_text=True)
    assert "myaccount.google.com/apppasswords" in html and "camille@gmail.com" in html
    r = c.post("/bienvenue", data={"etape": "2", "smtp_user": "camille@gmail.com", "smtp_password": "abcd efgh"})
    assert r.headers["Location"].endswith("etape=3")
    html = c.get("/bienvenue?etape=3").get_data(as_text=True)
    assert "Criteo" in html and "comptes oubliés" in html
    r = c.post("/bienvenue", data={"etape": "3", "auto_brokers": "1", "auto_comptes": "1", "auto_relances": "1"})
    assert r.headers["Location"].endswith("/auto")
    assert lances == ["Premier passage automatique"]
    with app.app_context():
        reg = lire_reglages(get_db())
        assert reg["mode_auto"] == "1" and reg["assistant_fait"] == "1"
    assert c.get("/").status_code == 200


def test_assistant_mauvais_mot_de_passe(client, monkeypatch):
    def refuse(cfg=None):
        raise OSError("535 identifiants refusés")
    monkeypatch.setattr(mailer, "tester", refuse)
    client.post("/bienvenue", data={"etape": "1", "nom": "Martin", "emails": "m@gmail.com"})
    html = client.post("/bienvenue", data={"etape": "2", "smtp_user": "m@gmail.com", "smtp_password": "x"}).get_data(as_text=True)
    assert "535" in html


def test_comptes_oublies_et_envois_auto(app, monkeypatch):
    envoyes = []
    monkeypatch.setattr(mailer, "config", lambda: {"host": "h", "port": 587, "user": "u", "password": "p", "from": "moi@gmail.com"})
    monkeypatch.setattr(mailer, "envoyer", lambda d, o, c, cfg=None, copie_a_moi=True: envoyes.append(d))
    vieux = (date.today() - timedelta(days=800)).isoformat()
    recent = date.today().isoformat()
    with app.app_context():
        db = get_db()
        db.executemany(
            "INSERT INTO decouverte_mail (domaine, nb, premier, dernier, compte, newsletter) VALUES (?, 3, ?, ?, 1, 0)",
            [("netflix.com", vieux, vieux), ("spotify.com", vieux, recent), ("paypal.com", vieux, vieux)],
        )
        db.commit()
        oublies = [c["d"]["domaine"] for c in auto.comptes_oublies(db)]
        assert oublies == ["netflix.com"]  # spotify encore actif, paypal sensible
        app.config["AUTO_MAX_ENVOIS"] = 3
        assert auto.envois_automatiques(db) == 3  # limite par passage
        db.execute("UPDATE reglage SET valeur = '0' WHERE cle = 'auto_brokers'")
        from wiper.db import ecrire_reglages
        ecrire_reglages(db, {"auto_brokers": "0"})
        app.config["AUTO_MAX_ENVOIS"] = 40
        envoyes.clear()
        assert auto.envois_automatiques(db) == 1 and envoyes == ["privacy@netflix.com"]


def test_tache_quotidienne_mode_auto(app, monkeypatch):
    appels = []
    monkeypatch.setattr(auto, "scanner_boite", lambda db, progression=None: appels.append("scan"))
    monkeypatch.setattr(auto, "envois_automatiques", lambda db: appels.append("envois"))
    monkeypatch.setattr(auto, "lire_reponses", lambda db: appels.append("reponses"))
    monkeypatch.setattr(boite, "config", lambda: {"host": "imap", "user": "u", "password": "p"})
    monkeypatch.setattr(mailer, "config", lambda: {"host": "h"})
    monkeypatch.setattr(auto, "relances_auto", lambda db: appels.append("relances"))
    from wiper.db import ecrire_reglages
    with app.app_context():
        db = get_db()
        auto.tache_quotidienne(db)
        assert appels == ["reponses", "relances"]  # mode auto désactivé : ni scan ni envois
        appels.clear()
        ecrire_reglages(db, {"mode_auto": "1"})
        auto.tache_quotidienne(db)
        assert appels == ["scan", "envois", "reponses", "relances"]
