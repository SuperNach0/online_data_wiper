"""Point d'entrée de l'appli : installation Windows, serveur local, fenêtre, pilote automatique."""
import os
import socket
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

from werkzeug.serving import make_server

from . import bureau, create_app

HOTE = "127.0.0.1"
PORTS = range(5000, 5011)


def _deja_lancee(port):
    try:
        with urllib.request.urlopen(f"http://{HOTE}:{port}/sante", timeout=1) as r:
            return r.read().decode() == "online-data-wiper"
    except Exception:  # noqa: BLE001
        return False


def _instance_existante():
    for port in PORTS:
        if _deja_lancee(port):
            return port
    return None


def _commander(port, action):
    """Demande à l'instance déjà lancée d'afficher sa fenêtre ou de se fermer."""
    req = urllib.request.Request(
        f"http://{HOTE}:{port}/bureau/{action}", data=b"", method="POST",
        headers={"Origin": f"http://{HOTE}:{port}"},
    )
    try:
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:  # noqa: BLE001
        pass


def _port_libre(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOTE, port))
            return True
        except OSError:
            return False


# Utilisés par la page Pilote automatique et l'assistant.
def demarrage_windows_possible():
    return bureau.est_windows_installable()


def demarrage_windows_actif():
    return demarrage_windows_possible() and bureau.demarrage_actif()


def regler_demarrage_windows(actif):
    bureau.regler_demarrage(actif)


def _journal_fichier(app_dir):
    """Sans console (exe fenêtré), les messages vont dans un fichier."""
    if sys.stdout is None or sys.stderr is None:
        Path(app_dir).mkdir(parents=True, exist_ok=True)
        f = open(Path(app_dir) / "appli.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cache = "--arriere-plan" in argv or "--sans-navigateur" in argv

    # 1. Lancé depuis le téléchargement : on installe (ou on met à jour) puis on relance la copie installée.
    if bureau.est_windows_installable() and Path(sys.executable).resolve() != bureau.exe_installe().resolve():
        port = _instance_existante()
        if port:
            _commander(port, "quitter")
        cible = bureau.installer(Path(sys.executable))
        bureau.lancer_detache(cible)
        return

    # 2. Une seule instance : si elle tourne déjà, on affiche sa fenêtre.
    port = _instance_existante()
    if port:
        if not cache:
            _commander(port, "afficher")
        return
    for port in PORTS:
        if _port_libre(port):
            break
    else:
        sys.exit("Aucun port libre entre 5000 et 5010.")

    from . import dossier_donnees

    if dossier_donnees():
        _journal_fichier(dossier_donnees())
    app = create_app()
    url = f"http://{HOTE}:{port}"
    serveur = make_server(HOTE, port, app, threaded=True)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    print(f"Online Data Wiper : {url} — données dans {app.instance_path}")

    from . import auto

    auto.demarrer_pilote(app)
    icone = Path(__file__).parent / "static" / "icone.png"
    b = bureau.Bureau(url, icone)
    app.config["BUREAU"] = b
    auto.notifier = b.notifier

    if os.environ.get("WIPER_SANS_FENETRE"):  # mode serveur seul (tests, CI)
        if not cache:
            webbrowser.open(url + "/auto")
        threading.Event().wait()
    b.lancer(cache=cache)


if __name__ == "__main__":
    main()
