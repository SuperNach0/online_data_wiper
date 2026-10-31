import csv
import io
from datetime import datetime, timezone

from flask import Response, render_template

from .db import STATUTS, get_db
from .views import bp, get_profil

FINI = ("supprime", "non_concerne")


def _compter(db, motif):
    return db.execute("SELECT COUNT(*) FROM evenement WHERE note LIKE ?", (motif,)).fetchone()[0]


def _jours_depuis(iso):
    try:
        d = datetime.fromisoformat(iso)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days
    except (TypeError, ValueError):
        return None


def donnees_bilan(db):
    statuts = {k: 0 for k in STATUTS}
    for r in db.execute("SELECT statut, COUNT(*) n FROM cible GROUP BY statut"):
        statuts[r["statut"]] = r["n"]
    total = sum(statuts.values())
    chiffres = {
        "contactes": total - statuts["a_contacter"],
        "demandes": _compter(db, "Demande RGPD envoyée%"),
        "relances": _compter(db, "Relance envoyée%"),
        "reponses": db.execute("SELECT COUNT(*) FROM evenement WHERE statut = 'reponse'").fetchone()[0],
        "supprimes": statuts["supprime"],
        "plaintes": _compter(db, "Plainte CNIL déposée%"),
        "manuels": _compter(db, "Fait à la main%"),
        "fuites": db.execute("SELECT COUNT(*) FROM cible WHERE categorie = 'Fuite de données'").fetchone()[0],
        "comptes": db.execute("SELECT COUNT(*) FROM decouverte_mail WHERE compte > 0").fetchone()[0],
    }
    categories = []
    for r in db.execute(
        """SELECT categorie, COUNT(*) total,
                  SUM(statut != 'a_contacter') contactes,
                  SUM(statut IN ('supprime', 'non_concerne')) finis
           FROM cible GROUP BY categorie ORDER BY total DESC"""
    ):
        categories.append(dict(r))
    attente = [
        {"c": c, "jours": _jours_depuis(c["date_envoi"])}
        for c in db.execute("SELECT * FROM cible WHERE statut = 'envoyee' ORDER BY date_envoi")
    ]
    historique = db.execute(
        """SELECT e.date, e.statut, e.note, c.id cible_id, c.nom, c.categorie
           FROM evenement e JOIN cible c ON c.id = e.cible_id
           ORDER BY e.date DESC, e.id DESC"""
    ).fetchall()
    premiere = db.execute("SELECT MIN(date) FROM evenement").fetchone()[0]
    return {
        "statuts": statuts, "total": total, "fini": statuts["supprime"] + statuts["non_concerne"],
        "chiffres": chiffres, "categories": categories, "attente": attente,
        "historique": historique, "premiere": premiere,
    }


@bp.route("/bilan")
def bilan():
    db = get_db()
    return render_template("bilan.html", p=get_profil(), aujourdhui=datetime.now().strftime("%d/%m/%Y"), **donnees_bilan(db))


@bp.route("/bilan.csv")
def bilan_csv():
    db = get_db()
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";")
    w.writerow(["Date", "Organisme", "Catégorie", "Statut", "Action"])
    for h in donnees_bilan(db)["historique"]:
        w.writerow([h["date"][:16].replace("T", " "), h["nom"], h["categorie"], STATUTS.get(h["statut"] or "", ""), h["note"] or ""])
    # BOM pour qu'Excel lise bien les accents
    return Response(
        "﻿" + sortie.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=bilan-online-data-wiper.csv"},
    )
