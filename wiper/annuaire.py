"""Annuaire des contacts « vie privée » de ~2500 organismes.

Données : base Datenanfragen / datarequests.org (licence CC0), régénérée par
outils/construire_annuaire.py.
"""
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from .decouverte import domaine_principal

FICHIER = Path(__file__).parent / "data" / "annuaire.json"


@lru_cache(maxsize=1)
def _annuaire():
    return json.loads(FICHIER.read_text(encoding="utf-8"))


def chercher(domaine):
    """Entrée de l'annuaire pour un domaine ou une URL, ou None."""
    if not domaine:
        return None
    if "/" in domaine:
        domaine = urlparse(domaine).hostname or ""
    return _annuaire().get(domaine_principal(domaine))
