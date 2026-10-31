from wiper.db import get_db


def test_bilan_vide(client):
    html = client.get("/bilan").get_data(as_text=True)
    assert "Bilan de mes démarches" in html and "Aucune démarche" in html


def test_bilan_apres_demarches(app, client, cible_id):
    cid = cible_id("criteo")
    client.post(f"/cible/{cid}/courrier", data={"type": "effacement", "objet": "o", "corps": "c", "action": "marquer"})
    client.post(f"/cible/{cible_id('bloctel')}/fait")
    client.post(f"/cible/{cible_id('acxiom')}/statut", data={"statut": "supprime"})
    html = client.get("/bilan").get_data(as_text=True)
    assert "Criteo" in html and "Bloctel" in html and "Fait à la main" in html
    assert "En attente de réponse (2)" in html
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM evenement").fetchone()[0] == 3
    r = client.get("/bilan.csv")
    texte = r.get_data(as_text=True)
    assert r.mimetype == "text/csv" and texte.startswith("﻿Date;Organisme")
    assert "Criteo;Publicité / ciblage;Demande envoyée;Demande RGPD envoyée" in texte
