import json
from datetime import datetime, timedelta, timezone

from wiper.db import SEED_FILE, get_db, init_db


def nb_seed():
    return len(json.loads(SEED_FILE.read_text(encoding="utf-8")))


def test_catalogue_charge_et_slugs_uniques(app):
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    assert len({c["slug"] for c in data}) == len(data)
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM cible").fetchone()[0] == nb_seed()


def test_reinit_ne_duplique_pas_et_garde_les_statuts(app):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE cible SET statut = 'supprime' WHERE slug = 'acxiom'")
        db.commit()
        assert init_db() == 0
        assert db.execute("SELECT statut FROM cible WHERE slug = 'acxiom'").fetchone()[0] == "supprime"


def test_tableau_de_bord(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Acxiom" in r.get_data(as_text=True)


def test_changement_statut_et_historique(app, client):
    with app.app_context():
        cid = get_db().execute("SELECT id FROM cible WHERE slug = 'spokeo'").fetchone()[0]
    r = client.post(f"/cible/{cid}/statut", data={"statut": "envoyee", "note": "Formulaire rempli"})
    assert r.status_code == 302
    with app.app_context():
        db = get_db()
        c = db.execute("SELECT * FROM cible WHERE id = ?", (cid,)).fetchone()
        assert c["statut"] == "envoyee" and c["date_envoi"]
        ev = db.execute("SELECT * FROM evenement WHERE cible_id = ?", (cid,)).fetchall()
        assert len(ev) == 1 and ev[0]["note"] == "Formulaire rempli"
    assert "Formulaire rempli" in client.get(f"/cible/{cid}").get_data(as_text=True)


def test_statut_invalide(app, client):
    with app.app_context():
        cid = get_db().execute("SELECT id FROM cible LIMIT 1").fetchone()[0]
    assert client.post(f"/cible/{cid}/statut", data={"statut": "nimporte"}).status_code == 400


def test_filtre_a_relancer(app, client):
    vieux = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    with app.app_context():
        db = get_db()
        db.execute("UPDATE cible SET statut = 'envoyee', date_envoi = ? WHERE slug = 'radaris'", (vieux,))
        db.execute("UPDATE cible SET statut = 'envoyee', date_envoi = ? WHERE slug = 'nuwber'",
                   (datetime.now(timezone.utc).isoformat(),))
        db.commit()
    html = client.get("/?statut=a_relancer").get_data(as_text=True)
    assert "Radaris" in html and "Nuwber" not in html


def test_ajout_site_perso(app, client):
    r = client.post("/ajouter", data={"nom": "Vieux forum", "site": "https://forum.example"})
    assert r.status_code == 302
    client.post("/ajouter", data={"nom": "Vieux forum"})
    with app.app_context():
        rows = get_db().execute("SELECT slug FROM cible WHERE personnalisee = 1 ORDER BY id").fetchall()
        assert [r[0] for r in rows] == ["perso-vieux-forum", "perso-vieux-forum-2"]
    assert client.post("/ajouter", data={"nom": " "}).status_code == 400
