from flask import current_app, flash, redirect, render_template, request, url_for

from . import auto, boite, courriers, mailer
from .db import ecrire_reglages, get_db, lire_reglages
from .views import bp, get_profil
from .lanceur import demarrage_windows_actif, demarrage_windows_possible, regler_demarrage_windows


@bp.route("/auto")
def pilote():
    db = get_db()
    plan_auto, _manuel = auto.plan(db)
    r = lire_reglages(db)
    return render_template(
        "auto.html",
        profil_ok=not courriers.profil_incomplet(get_profil()),
        envoi_ok=bool(mailer.config()),
        boite_ok=bool(boite.config()),
        plan_auto=plan_auto,
        comptes=auto.comptes_trouves(db),
        afaire=auto.a_faire(db),
        tache=auto.TACHES.etat,
        journal=db.execute("SELECT * FROM journal ORDER BY id DESC LIMIT 15").fetchall(),
        r=r,
        dernier_scan=r.get("dernier_scan"),
        win_possible=demarrage_windows_possible(),
        win_actif=demarrage_windows_actif(),
    )


def _lancer(nom, fonction):
    if not auto.TACHES.lancer(current_app._get_current_object(), nom, fonction):
        flash("Une tâche est déjà en cours, attends qu'elle se termine.")
    return redirect(url_for("wiper.pilote"))


@bp.post("/auto/scanner")
def auto_scanner():
    def f(db, progression):
        total, nb = auto.scanner_boite(db, progression)
        return f"Boîte mail analysée : {total} e-mails lus, {nb} comptes probables trouvés."
    return _lancer("Analyse de ta boîte mail", f)


@bp.post("/auto/lancer")
def auto_lancer():
    db = get_db()
    ids = [int(x) for x in request.form.getlist("cible") if x.isdigit()]
    envois = []
    for cid in ids:
        c = db.execute("SELECT * FROM cible WHERE id = ? AND statut = 'a_contacter'", (cid,)).fetchone()
        dest = c and auto.contact_pour(c)
        if dest:
            envois.append((cid, dest))
    envois += auto.preparer_comptes(db, request.form.getlist("domaine"))
    if not envois:
        flash("Rien à envoyer : coche au moins une ligne.")
        return redirect(url_for("wiper.pilote"))
    if not mailer.config():
        flash("Configure d'abord l'envoi d'e-mails dans les Réglages.")
        return redirect(url_for("wiper.reglages"))

    def f(db, progression):
        ok, erreurs = auto.envoyer_lot(db, envois, progression=progression)
        msg = f"{ok} demande(s) RGPD envoyée(s)."
        if erreurs:
            msg += f" {len(erreurs)} échec(s), voir le journal."
        return msg
    return _lancer(f"Envoi de {len(envois)} demande(s)", f)


@bp.post("/auto/maintenant")
def auto_maintenant():
    def f(db, progression):
        auto.tache_quotidienne(db)
        return "Vérification terminée : réponses lues, relances envoyées si besoin."
    return _lancer("Vérification quotidienne", f)


@bp.post("/auto/options")
def auto_options():
    db = get_db()
    ecrire_reglages(db, {k: "1" if request.form.get(k) else "0"
                         for k in ("mode_auto", "auto_brokers", "auto_comptes", "auto_relances")})
    if demarrage_windows_possible():
        try:
            regler_demarrage_windows(bool(request.form.get("demarrage_windows")))
        except OSError as e:
            flash(f"Impossible de régler le démarrage avec Windows : {e}")
    flash("Options enregistrées.")
    return redirect(url_for("wiper.pilote"))


@bp.post("/cible/<int:cible_id>/fait")
def marquer_fait(cible_id):
    db = get_db()
    from .db import maintenant
    c = db.execute("SELECT * FROM cible WHERE id = ?", (cible_id,)).fetchone()
    if c:
        db.execute("UPDATE cible SET statut = 'envoyee', date_envoi = ?, maj = ? WHERE id = ?", (maintenant(), maintenant(), cible_id))
        db.execute("INSERT INTO evenement (cible_id, date, statut, note) VALUES (?, ?, 'envoyee', 'Fait à la main')", (cible_id, maintenant()))
        db.commit()
        flash(f"{c['nom']} : noté comme fait.")
    return redirect(request.form.get("retour") or url_for("wiper.pilote"))
