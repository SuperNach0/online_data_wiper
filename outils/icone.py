"""Dessine l'icône de l'appli (wiper/static/icone.png et .ico). Usage : python outils/icone.py"""
from pathlib import Path

from PIL import Image, ImageDraw

T = 512
img = Image.new("RGBA", (T, T), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([16, 16, T - 16, T - 16], radius=110, fill=(47, 91, 211, 255))
# bouclier
d.polygon([(256, 96), (396, 150), (384, 300), (256, 420), (128, 300), (116, 150)], fill=(255, 255, 255, 255))
# gomme qui efface : trait diagonal
d.line([(178, 270), (238, 330), (342, 196)], fill=(47, 91, 211, 255), width=42, joint="curve")
out = Path(__file__).resolve().parent.parent / "wiper" / "static"
img.save(out / "icone.png")
img.save(out / "icone.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ok")
