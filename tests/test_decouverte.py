import io
import json
import urllib.error

import pytest

from wiper import decouverte
from wiper.db import get_db
from wiper.views_decouverte import enregistrer_fuites

MBOX = b"""From a@x Mon Jan  1 00:00:00 2018
From: Netflix <info@mailer.netflix.com>
Date: Mon, 1 Jan 2018 10:00:00 +0000
Subject: Bienvenue sur Netflix
List-Unsubscribe: <mailto:u@netflix.com>

corps
From a@x Mon Jan  1 00:00:00 2018
From: Netflix <info@netflix.com>
Date: Tue, 2 Mar 2021 10:00:00 +0000
Subject: =?utf-8?q?R=C3=A9initialisation_du_mot_de_passe?=

corps
From a@x Mon Jan  1 00:00:00 2018
From: Ami <pote@gmail.com>
Date: Tue, 2 Mar 2021 10:00:00 +0000
Subject: Salut

corps
From a@x Mon Jan  1 00:00:00 2018
From: Boutique <news@shop.co.uk>
Date: Tue, 2 Mar 2022 10:00:00 +0000
Subject: Promo

corps
"""


def test_domaine_principal():
    assert decouverte.domaine_principal("mailer.netflix.com") == "netflix.com"
    assert decouverte.domaine_principal("news.shop.co.uk") == "shop.co.uk"
    assert decouverte.domaine_principal("Example.FR") == "example.fr"


def test_analyser_mbox(tmp_path):
    f = tmp_path / "boite.mbox"
    f.write_bytes(MBOX)
    total, stats = decouverte.analyser_mbox(str(f), ["moi@example.com"])
    assert total == 4
    assert set(stats) == {"netflix.com", "shop.co.uk"}  # gmail.com ignoré
    n = stats["netflix.com"]
    assert n["nb"] == 2 and n["compte"] == 2 and n["newsletter"] == 1
    assert (n["premier"], n["dernier"]) == ("2018-01-01", "2021-03-02")
    assert stats["shop.co.uk"]["compte"] == 0


def test_upload_mbox_et_ajout_au_suivi(app, client):
    r = client.post("/decouverte/mbox", data={"mbox": (io.BytesIO(MBOX), "boite.mbox")}, content_type="multipart/form-data")
    assert r.status_code == 302
    html = client.get("/decouverte").get_data(as_text=True)
    assert "netflix.com" in html and "shop.co.uk" not in html  # filtre « comptes probables »
    assert "shop.co.uk" in client.get("/decouverte?mail=tous").get_data(as_text=True)
    client.post("/decouverte/mbox/ajouter", data={"domaine": ["netflix.com"]})
    client.post("/decouverte/mbox/ajouter", data={"domaine": ["netflix.com"]})  # pas de doublon
    with app.app_context():
        rows = get_db().execute("SELECT nom, categorie, notes FROM cible WHERE slug LIKE 'mail-%'").fetchall()
    assert len(rows) == 1 and rows[0]["categorie"] == "Compte en ligne" and "2 e-mail" in rows[0]["notes"]


def test_liens_recherche():
    p = {"prenom": "Camille", "nom": "Martin", "emails": "c@example.com", "pseudos": "@cmartin\n", "adresse": None}
    recherches, profils = decouverte.liens_recherche(p)
    assert [r["requete"] for r in recherches] == ['"Camille Martin"', '"c@example.com"', '"cmartin"']
    assert profils[0]["liens"]["GitHub"] == "https://github.com/cmartin"


class _Rep(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_hibp(app):
    fuite = {"Name": "Adobe", "Title": "Adobe", "Domain": "adobe.com", "BreachDate": "2013-10-04",
             "DataClasses": ["Email addresses", "Passwords"]}

    def opener(req, timeout):
        assert req.get_header("Hibp-api-key") == "cle"
        if "propre" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
        return _Rep(json.dumps([fuite]).encode())

    res = decouverte.hibp_tous(["a@x.fr", "propre@x.fr", "b@x.fr"], "cle", opener, pause=0)
    assert res["propre@x.fr"] == [] and res["a@x.fr"][0]["Name"] == "Adobe"
    with app.app_context():
        db = get_db()
        assert enregistrer_fuites(db, res) == 1
        assert enregistrer_fuites(db, res) == 0
        c = db.execute("SELECT * FROM cible WHERE slug = 'fuite-adobe'").fetchone()
        assert c["categorie"] == "Fuite de données" and "a@x.fr" in c["notes"] and "b@x.fr" in c["notes"]


def test_hibp_cle_refusee():
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "unauth", {}, None)
    with pytest.raises(decouverte.HibpErreur):
        decouverte.hibp_fuites("a@x.fr", "mauvaise", opener)


def test_page_decouverte_sans_cle(client, monkeypatch):
    monkeypatch.delenv("WIPER_HIBP_API_KEY", raising=False)
    client.post("/profil", data={"nom": "Martin", "emails": "c@example.com", "pseudos": "cmartin"})
    html = client.get("/decouverte").get_data(as_text=True)
    assert "haveibeenpwned.com" in html and "github.com/cmartin" in html
    assert client.post("/decouverte/fuites").status_code == 302
