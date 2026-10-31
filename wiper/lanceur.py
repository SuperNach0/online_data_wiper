"""Point d'entrée de l'appli installée : démarre le serveur local et ouvre le navigateur."""
import os
import socket
import sys
from pathlib import Path
import threading
import urllib.request
import webbrowser

from werkzeug.serving import make_server

from . import create_app

HOTE = "127.0.0.1"
PORTS = range(5000, 5011)


def _deja_lancee(port):
    try:
        with urllib.request.urlopen(f"http://{HOTE}:{port}/sante", timeout=1) as r:
            return r.read().decode() == "online-data-wiper"
    except Exception:  # noqa: BLE001
        return False


def _port_libre(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOTE, port))
            return True
        except OSError:
            return False


def _raccourci_demarrage():
    dossier = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return dossier / "OnlineDataWiper.bat"


def demarrage_windows_possible():
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def demarrage_windows_actif():
    return demarrage_windows_possible() and _raccourci_demarrage().exists()


def regler_demarrage_windows(actif):
    """Lance l'appli (fenêtre réduite, sans ouvrir le navigateur) à l'ouverture de session Windows."""
    f = _raccourci_demarrage()
    if actif:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f'@echo off\r\nstart "" /min "{sys.executable}" --sans-navigateur\r\n', encoding="utf-8")
    elif f.exists():
        f.unlink()


def main(ouvrir=None):
    if ouvrir is None:
        ouvrir = "--sans-navigateur" not in sys.argv
    for port in PORTS:
        if _deja_lancee(port):
            print(f"Online Data Wiper tourne déjà : http://{HOTE}:{port}")
            if ouvrir:
                webbrowser.open(f"http://{HOTE}:{port}")
            return
        if _port_libre(port):
            break
    else:
        print("Aucun port libre entre 5000 et 5010.")
        sys.exit(1)

    app = create_app()
    serveur = make_server(HOTE, port, app, threaded=True)
    url = f"http://{HOTE}:{port}"
    print("=" * 60)
    print(" Online Data Wiper est lancé.")
    print(f" Adresse : {url}")
    print(f" Tes données : {app.instance_path}")
    print(" Laisse cette fenêtre ouverte. Ferme-la (ou Ctrl+C) pour arrêter.")
    print("=" * 60)
    from .auto import demarrer_pilote

    demarrer_pilote(app)
    print(" Pilote automatique actif : relances et lecture des réponses une fois par jour.")
    if ouvrir:
        threading.Timer(1.0, webbrowser.open, args=(url + "/auto",)).start()
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
