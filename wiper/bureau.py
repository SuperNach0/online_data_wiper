"""Couche « application de bureau » Windows : installation, raccourcis, fenêtre, icône près de l'horloge."""
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

NOM = "Online Data Wiper"
EXE = "OnlineDataWiper.exe"
SANS_FENETRE = 0x08000000  # CREATE_NO_WINDOW


def est_windows_installable():
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def dossier_installation():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "Programs" / "OnlineDataWiper"


def exe_installe():
    return dossier_installation() / EXE


def _dossier_menu_demarrer():
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def _bureau():
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"


def dossier_demarrage():
    return _dossier_menu_demarrer() / "Startup"


def creer_raccourci(lnk: Path, cible: Path, arguments=""):
    """Crée un raccourci .lnk via PowerShell (aucune dépendance supplémentaire)."""
    lnk.parent.mkdir(parents=True, exist_ok=True)
    esc = lambda s: str(s).replace("'", "''")  # noqa: E731
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        "$s.TargetPath='{cible}';$s.Arguments='{args}';$s.WorkingDirectory='{dir}';"
        "$s.IconLocation='{cible},0';$s.Description='{nom}';$s.Save()"
    ).format(lnk=esc(lnk), cible=esc(cible), args=esc(arguments), dir=esc(cible.parent), nom=NOM)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True, creationflags=SANS_FENETRE, timeout=60,
    )


def installer(source: Path):
    """Copie l'exe dans le dossier d'installation et crée les raccourcis menu Démarrer + bureau."""
    cible = exe_installe()
    cible.parent.mkdir(parents=True, exist_ok=True)
    for essai in range(20):  # l'ancienne version peut mettre quelques secondes à se fermer
        try:
            shutil.copy2(source, cible)
            break
        except PermissionError:
            time.sleep(0.5)
    else:
        raise PermissionError(f"Impossible de remplacer {cible}")
    for lnk in (_dossier_menu_demarrer() / f"{NOM}.lnk", _bureau() / f"{NOM}.lnk"):
        try:
            creer_raccourci(lnk, cible)
        except Exception:  # noqa: BLE001 : un raccourci manquant n'empêche pas l'appli de marcher
            pass
    # ancien lanceur .bat des versions précédentes
    ancien = dossier_demarrage() / "OnlineDataWiper.bat"
    if ancien.exists():
        ancien.unlink()
        regler_demarrage(True)
    return cible


def regler_demarrage(actif):
    lnk = dossier_demarrage() / f"{NOM}.lnk"
    if actif:
        creer_raccourci(lnk, exe_installe(), "--arriere-plan")
    elif lnk.exists():
        lnk.unlink()


def demarrage_actif():
    return (dossier_demarrage() / f"{NOM}.lnk").exists()


def lancer_detache(exe: Path, *args):
    subprocess.Popen([str(exe), *args], creationflags=0x00000008 | 0x00000200, close_fds=True)  # DETACHED | NEW_GROUP


class Bureau:
    """Fenêtre native + icône près de l'horloge. Repli sur le navigateur si la fenêtre ne peut pas s'ouvrir."""

    def __init__(self, url, icone_png):
        self.url = url
        self.icone_png = icone_png
        self.fenetre = None
        self.tray = None
        self.quitter_demande = False
        self.prevenu = False
        self._arret = threading.Event()

    # --- appelé par les routes /afficher et /quitter, et par le menu de l'icône
    def afficher(self):
        if self.fenetre is not None:
            try:
                self.fenetre.show()
                self.fenetre.restore()
                return
            except Exception:  # noqa: BLE001
                pass
        webbrowser.open(self.url + "/auto")

    def quitter(self):
        self.quitter_demande = True
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:  # noqa: BLE001
                pass
        if self.fenetre is not None:
            try:
                self.fenetre.destroy()
            except Exception:  # noqa: BLE001
                pass
        self._arret.set()
        threading.Timer(2.0, lambda: os._exit(0)).start()

    def notifier(self, message):
        if self.tray is not None:
            self.tray.notify(message, NOM)

    # --- démarrage
    def _demarrer_tray(self):
        try:
            import pystray
            from PIL import Image
        except Exception:  # noqa: BLE001
            return
        menu = pystray.Menu(
            pystray.MenuItem("Ouvrir", lambda: self.afficher(), default=True),
            pystray.MenuItem("Quitter", lambda: self.quitter()),
        )
        self.tray = pystray.Icon("OnlineDataWiper", Image.open(self.icone_png), NOM, menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _en_fermeture(self):
        if self.quitter_demande:
            return True
        # Fermer la fenêtre = la cacher : le pilote automatique continue.
        self.fenetre.hide()
        if not self.prevenu:
            self.prevenu = True
            self.notifier("L'appli continue en arrière-plan. Clic droit sur l'icône près de l'horloge pour la quitter.")
        return False

    def lancer(self, cache=False):
        self._demarrer_tray()
        try:
            import webview
        except Exception:  # noqa: BLE001
            webview = None
        fenetre_ok = False
        if webview is not None:
            try:
                self.fenetre = webview.create_window(
                    NOM, self.url + "/auto", width=1200, height=860, min_size=(820, 600), hidden=cache,
                )
                self.fenetre.events.closing += self._en_fermeture
                fenetre_ok = True
                webview.start(private_mode=False)
            except Exception:  # noqa: BLE001
                fenetre_ok = False
                self.fenetre = None
                if not cache:
                    webbrowser.open(self.url + "/auto")
        elif not cache:
            webbrowser.open(self.url + "/auto")
        # La fenêtre est fermée pour de bon, ou n'a pas pu s'ouvrir.
        self.fenetre = None
        if not self.quitter_demande and (self.tray is not None or not fenetre_ok):
            # On reste actif : icône près de l'horloge, ou mode navigateur (Ctrl+C / fermer pour arrêter).
            try:
                self._arret.wait()
            except KeyboardInterrupt:
                pass
        os._exit(0)
