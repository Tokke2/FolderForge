"""Rebuild the FolderForge icon (requires Pillow)."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / 'Icon'
scale = 4
im = Image.new('RGBA', (256 * scale, 256 * scale))
d = ImageDraw.Draw(im)
def box(coords): return tuple(int(c * scale) for c in coords)
d.rounded_rectangle(box((8, 8, 248, 248)), radius=52 * scale, fill='#10283F')
# A folder with a forged-metal tab, plus a bright hammer/creation spark.
d.rounded_rectangle(box((40, 64, 131, 106)), radius=12 * scale, fill='#FFCA66')
d.rounded_rectangle(box((36, 85, 220, 196)), radius=17 * scale, fill='#EBA43D')
d.rounded_rectangle(box((36, 103, 220, 198)), radius=16 * scale, fill='#FFD27B')
d.polygon([box(p) for p in [(108, 169), (121, 182), (172, 131), (159, 118)]], fill='#173E5A')
d.polygon([box(p) for p in [(130, 112), (145, 97), (185, 137), (170, 152)]], fill='#173E5A')
d.line([box((191, 83)), box((191, 101))], fill='#55DCD0', width=6*scale)
d.line([box((204, 108)), box((220, 108))], fill='#55DCD0', width=6*scale)
im = im.resize((256, 256), Image.Resampling.LANCZOS)
im.save(root / 'projektmapp_icon_256.png')
im.save(root / 'projektmapp.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
