# Recette PyInstaller : fabrique OnlineDataWiper.exe (pyinstaller OnlineDataWiper.spec)
a = Analysis(
    ["lancer_wiper.py"],
    datas=[
        ("wiper/templates", "wiper/templates"),
        ("wiper/static", "wiper/static"),
        ("wiper/data", "wiper/data"),
    ],
    hiddenimports=["pystray._win32", "webview.platforms.edgechromium", "wiper.bureau", "wiper.views_assistant", "wiper.views_auto", "wiper.views_bilan", "wiper.views_decouverte", "wiper.views_reglages"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="OnlineDataWiper",
    console=False,  # vraie appli : pas de fenêtre noire
    upx=False,
    icon="wiper/static/icone.ico",
)
