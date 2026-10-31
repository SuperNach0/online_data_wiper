"""Construit wiper/data/annuaire.json à partir de la base Datenanfragen (CC0).

Usage : git clone --depth 1 https://github.com/datenanfragen/data /tmp/dr
        python outils/construire_annuaire.py /tmp/dr
La base recense les contacts « vie privée » de ~3000 organismes : l'appli s'en
sert pour trouver toute seule où envoyer une demande RGPD.
"""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from wiper.decouverte import domaine_principal  # noqa: E402


def score(c):
    pays = c.get("relevant-countries") or []
    s = 0
    if "fr" in pays:
        s += 4
    if "all" in pays:
        s += 2
    if c.get("quality") == "verified":
        s += 1
    return s


def main(source):
    annuaire = {}
    for f in sorted(Path(source, "companies").glob("*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        if not c.get("email") or not c.get("web"):
            continue
        host = urlparse(c["web"]).hostname
        if not host:
            continue
        dom = domaine_principal(host)
        entree = {
            "nom": c["name"],
            "email": c["email"],
            "adresse": c.get("address"),
            "categories": c.get("categories", []),
            "source": f"https://www.datarequests.org/company/{c['slug']}/",
            "_score": score(c),
        }
        if dom not in annuaire or entree["_score"] > annuaire[dom]["_score"]:
            annuaire[dom] = entree
    for e in annuaire.values():
        del e["_score"]
    out = Path(__file__).resolve().parent.parent / "wiper" / "data" / "annuaire.json"
    out.write_text(json.dumps(annuaire, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print(f"{len(annuaire)} domaines -> {out} ({out.stat().st_size // 1024} Ko)")


if __name__ == "__main__":
    main(sys.argv[1])
