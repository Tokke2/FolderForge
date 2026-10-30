"""Rebuild the FolderForge icon (requires Pillow)."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / 'Icon'
scale = 4
im = Image.new('RGBA', (256 * scale, 256 * scale))
d = ImageDraw.Draw(im)
def box(coords): return tuple(int(c * scale) for c in coords)
d.rounded_rectangle(box((8, 8, 248, 248)), radius=52 * scale, fill='#10283F')
# FolderForge mark: gold folder with a high-contrast branching structure.
d.rounded_rectangle(box((38, 57, 126, 103)), radius=13 * scale, fill='#D99835')
d.rounded_rectangle(box((34, 78, 222, 207)), radius=20 * scale, fill='#F2B64F')
d.rounded_rectangle(box((34, 98, 222, 207)), radius=18 * scale, fill='#FFD279')
# Dark inset keeps the structure legible even at small tray sizes.
d.rounded_rectangle(box((64, 115, 192, 185)), radius=14 * scale, fill='#12394B')
d.line([box((91, 135)), box((91, 164)), box((165, 164))], fill='#70F2D4', width=8*scale)
d.line([box((128, 145)), box((128, 164))], fill='#70F2D4', width=8*scale)
for x, y in [(91, 134), (128, 143), (165, 164)]:
    d.rounded_rectangle(box((x-10, y-9, x+10, y+9)), radius=4*scale, fill='#70F2D4')
im = im.resize((256, 256), Image.Resampling.LANCZOS)
im.save(root / 'projektmapp_icon_256.png')
im.save(root / 'projektmapp.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
