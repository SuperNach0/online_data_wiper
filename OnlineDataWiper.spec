# Recette PyInstaller : fabrique OnlineDataWiper.exe (pyinstaller OnlineDataWiper.spec)
a = Analysis(
    ["lancer_wiper.py"],
    datas=[
        ("wiper/templates", "wiper/templates"),
        ("wiper/static", "wiper/static"),
        ("wiper/data", "wiper/data"),
    ],
    hiddenimports=["wiper.views_auto", "wiper.views_decouverte", "wiper.views_reglages"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="OnlineDataWiper",
    console=True,  # la fenêtre noire sert à voir que l'appli tourne et à l'arrêter
    upx=False,
    icon=None,
)
