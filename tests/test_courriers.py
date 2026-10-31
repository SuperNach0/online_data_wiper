from datetime import datetime, timedelta, timezone

from wiper import mailer
from wiper.db import get_db


def _il_y_a(jours):
    return (datetime.now(timezone.utc) - timedelta(days=jours)).isoformat()


def remplir_profil(client):
    client.post("/profil", data={"prenom": "Camille", "nom": "Martin", "emails": "camille@example.com\nvieux@example.org"})


def test_profil_et_courrier_prerempli(client, cible_id):
    remplir_profil(client)
    html = client.get(f"/cible/{cible_id('acxiom')}/courrier").get_data(as_text=True)
    assert "Camille Martin" in html and "vieux@example.org" in html
    assert "article 17" in html.lower() or "Article 17" in html
    assert "Acxiom" in html


def test_tous_les_modeles_se_rendent(client, cible_id):
    remplir_profil(client)
    for t in ["effacement", "acces", "opposition", "relance", "plainte_cnil"]:
        r = client.get(f"/cible/{cible_id('criteo')}/courrier?type={t}")
        assert r.status_code == 200, t
    assert client.get(f"/cible/{cible_id('criteo')}/courrier?type=xxx").status_code == 400


def test_marquer_envoye_puis_relance_puis_cnil(app, client, cible_id):
    cid = cible_id("radaris")
    client.post(f"/cible/{cid}/courrier", data={"type": "effacement", "objet": "o", "corps": "c", "action": "marquer"})
    with app.app_context():
        db = get_db()
        c = db.execute("SELECT * FROM cible WHERE id = ?", (cid,)).fetchone()
        assert c["statut"] == "envoyee" and c["date_envoi"] and c["date_relance"] is None
        db.execute("UPDATE cible SET date_envoi = ? WHERE id = ?", (_il_y_a(40), cid))
        db.commit()
    assert "Radaris" in client.get("/?statut=a_relancer").get_data(as_text=True)
    # le type proposé par défaut devient la relance
    assert "Relance" in client.get(f"/cible/{cid}/courrier").get_data(as_text=True)

    client.post(f"/cible/{cid}/courrier", data={"type": "relance", "objet": "o", "corps": "c", "action": "marquer"})
    assert "Radaris" not in client.get("/?statut=a_relancer").get_data(as_text=True)
    with app.app_context():
        db = get_db()
        db.execute("UPDATE cible SET date_relance = ? WHERE id = ?", (_il_y_a(20), cid))
        db.commit()
    assert "Radaris" in client.get("/?statut=cnil").get_data(as_text=True)
    with app.app_context():
        notes = [r[0] for r in get_db().execute("SELECT note FROM evenement WHERE cible_id = ? ORDER BY id", (cid,))]
    assert notes[0].startswith("Demande RGPD envoyée") and notes[1].startswith("Relance envoyée")


def test_envoi_smtp(app, client, cible_id, monkeypatch):
    envoyes = []
    monkeypatch.setattr(mailer, "config", lambda: {"host": "smtp.test", "port": 587, "user": "u", "password": "p", "from": "moi@example.com"})
    monkeypatch.setattr(mailer, "envoyer", lambda dest, objet, corps, cfg=None: envoyes.append((dest, objet)))
    cid = cible_id("kantar")
    r = client.post(f"/cible/{cid}/courrier", data={
        "type": "effacement", "objet": "Demande RGPD", "corps": "Bonjour", "destinataire": "dpo@kantar.example", "action": "envoyer"})
    assert r.status_code == 302
    assert envoyes == [("dpo@kantar.example", "Demande RGPD")]
    with app.app_context():
        c = get_db().execute("SELECT statut, contact_rgpd FROM cible WHERE id = ?", (cid,)).fetchone()
        assert c["statut"] == "envoyee" and c["contact_rgpd"] == "dpo@kantar.example"


def test_envoi_sans_smtp_refuse(client, cible_id, monkeypatch):
    monkeypatch.setattr(mailer, "config", lambda: None)
    r = client.post(f"/cible/{cible_id('kantar')}/courrier", data={"type": "effacement", "destinataire": "a@b.c", "action": "envoyer"})
    assert r.status_code == 400
