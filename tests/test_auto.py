from datetime import datetime, timedelta, timezone

from wiper import auto, boite, mailer
from wiper.db import ecrire_reglages, get_db


def _il_y_a(j):
    return (datetime.now(timezone.utc) - timedelta(days=j)).isoformat()


def _faux_envoi(monkeypatch):
    envoyes = []
    monkeypatch.setattr(mailer, "config", lambda: {"host": "h", "port": 587, "user": "moi@gmail.com", "password": "p", "from": "moi@gmail.com"})
    monkeypatch.setattr(mailer, "envoyer", lambda dest, objet, corps, cfg=None, copie_a_moi=True: envoyes.append((dest, objet)))
    return envoyes


def test_plan_separe_auto_et_manuel(app):
    with app.app_context():
        a, m = auto.plan(get_db())
        auto_slugs = {p["cible"]["slug"]: p["destinataire"] for p in a}
        manuel_slugs = {p["cible"]["slug"] for p in m}
    assert auto_slugs["criteo"] == "dpo@criteo.com"
    assert auto_slugs["acxiom"] == "dataprotection@acxiom.com"
    assert "google-ads" in manuel_slugs and "bloctel" in manuel_slugs  # réglages / inscriptions
    assert "spokeo" in manuel_slugs  # pas de contact e-mail connu


def test_tout_lancer_envoie_et_cree_les_comptes(app, client, monkeypatch, cible_id):
    envoyes = _faux_envoi(monkeypatch)
    app.config["AUTO_PAUSE"] = 0
    client.post("/profil", data={"nom": "Martin", "emails": "moi@gmail.com"})
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO decouverte_mail (domaine, nb, compte, newsletter) VALUES ('netflix.com', 3, 2, 0)")
        db.commit()
    r = client.post("/auto/lancer", data={"cible": [str(cible_id("criteo")), str(cible_id("acxiom"))], "domaine": ["netflix.com"]})
    assert r.status_code == 302
    for _ in range(50):
        if not auto.TACHES.etat["en_cours"]:
            break
        import time; time.sleep(0.05)
    assert sorted(d for d, _ in envoyes) == ["dataprotection@acxiom.com", "dpo@criteo.com", "privacy@netflix.com"]
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT statut FROM cible WHERE slug = 'mail-netflix.com'").fetchone()[0] == "envoyee"
        assert "3 demande(s)" in auto.TACHES.etat["message"]
    assert "Netflix" not in client.get("/auto").get_data(as_text=True).split("2. Comptes")[1].split("3. À faire")[0]


def test_relances_auto(app, monkeypatch, cible_id):
    envoyes = _faux_envoi(monkeypatch)
    app.config["AUTO_PAUSE"] = 0
    with app.app_context():
        db = get_db()
        db.execute("UPDATE cible SET statut = 'envoyee', date_envoi = ? WHERE slug = 'criteo'", (_il_y_a(40),))
        db.execute("UPDATE cible SET statut = 'envoyee', date_envoi = ? WHERE slug = 'epsilon'", (_il_y_a(5),))
        db.commit()
        assert auto.relances_auto(db) == 1
        assert envoyes[0][0] == "dpo@criteo.com" and "Relance" in envoyes[0][1]
        assert db.execute("SELECT date_relance FROM cible WHERE slug = 'criteo'").fetchone()[0]


def test_traiter_reponses_et_rebonds(app):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE cible SET statut = 'envoyee', date_envoi = ? WHERE slug IN ('criteo', 'acxiom')", (_il_y_a(3),))
        db.execute("UPDATE profil SET emails = 'moi@gmail.com' WHERE id = 1")
        db.commit()
        messages = [
            {"message_id": "<1@criteo>", "de": "Criteo DPO <dpo@criteo.com>", "objet": "Votre demande", "date": "", "texte": "Nous avons supprimé vos données."},
            {"message_id": "<2@g>", "de": "Mail Delivery Subsystem <mailer-daemon@googlemail.com>", "objet": "Delivery Status Notification (Failure)",
             "date": "", "texte": "Address not found: dataprotection@acxiom.com"},
            {"message_id": "<3@g>", "de": "moi@gmail.com", "objet": "copie", "date": "", "texte": ""},
        ]
        assert auto.traiter_reponses(db, messages) == (1, 1)
        assert auto.traiter_reponses(db, messages) == (0, 0)  # déjà traités
        c = db.execute("SELECT * FROM cible WHERE slug = 'criteo'").fetchone()
        a = db.execute("SELECT * FROM cible WHERE slug = 'acxiom'").fetchone()
        assert c["statut"] == "reponse"
        assert a["statut"] == "a_contacter" and a["contact_invalide"] == 1
        assert auto.contact_pour(a) is None
        faire = auto.a_faire(db)
        assert [x["slug"] for x in faire["reponses"]] == ["criteo"]
        assert [x["slug"] for x in faire["invalides"]] == ["acxiom"]


class FauxImap:
    def __init__(self, messages):
        self.messages = messages  # {uid: bytes}

    def list(self):
        return "OK", [b'(\\HasNoChildren \\All) "/" "[Gmail]/Tous les messages"']

    def select(self, dossier, readonly=False):
        self.dossier = dossier
        return "OK", [b"1"]

    def uid(self, cmd, *args):
        if cmd == "search":
            return "OK", [b" ".join(self.messages)]
        uids = args[0].split(b",")
        data = []
        for u in uids:
            data.append((b"1 (UID " + u + b" BODY[] {10}", self.messages[u]))
            data.append(b")")
        return "OK", data

    def logout(self):
        pass


def test_scanner_boite_imap(app):
    msgs = {
        b"1": b"From: Netflix <info@mailer.netflix.com>\r\nSubject: Bienvenue sur Netflix\r\nDate: Mon, 1 Jan 2018 10:00:00 +0000\r\n\r\n",
        b"2": b"From: Ami <pote@gmail.com>\r\nSubject: salut\r\n\r\n",
    }
    imap = FauxImap(msgs)
    with app.app_context():
        db = get_db()
        ecrire_reglages(db, {"smtp_user": "moi@gmail.com", "smtp_password": "x"})
        assert boite.config()["host"] == "imap.gmail.com"
        total, nb = auto.scanner_boite(db, imap=imap)
        assert (total, nb) == (2, 1)
        assert imap.dossier == '"[Gmail]/Tous les messages"'
        comptes = auto.comptes_trouves(db)
        assert comptes[0]["contact"] == "privacy@netflix.com"


def test_messages_recents_imap():
    msgs = {b"7": b"From: dpo@criteo.com\r\nSubject: Re: RGPD\r\nMessage-ID: <x@y>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nC'est fait.\r\n"}
    res = boite.messages_recents({}, datetime.now().date(), imap=FauxImap(msgs))
    assert res[0]["message_id"] == "<x@y>" and "fait" in res[0]["texte"]


def test_page_pilote(client):
    html = client.get("/auto").get_data(as_text=True)
    assert "Tout lancer" in html and "À faire par toi" in html and "Criteo" in html


def test_compte_inconnu_cochable_avec_adresse_probable(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO decouverte_mail (domaine, nb, compte, premier, dernier) VALUES (?, ?, ?, ?, ?)",
            ("petit-site-inconnu.fr", 3, 2, "2015-01-01", "2016-01-01"),
        )
        db.commit()
        c = [c for c in auto.comptes_trouves(db) if c["d"]["domaine"] == "petit-site-inconnu.fr"][0]
        assert c["devine"] and c["contact"] == "privacy@petit-site-inconnu.fr"
        assert c not in auto.comptes_oublies(db)  # jamais envoyé sans que tu coches
        envois = auto.preparer_comptes(db, ["petit-site-inconnu.fr"])
        assert envois and envois[0][1] == "privacy@petit-site-inconnu.fr"
