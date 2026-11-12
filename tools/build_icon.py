"""Build matching app/print assets. Dev-only: Pillow, fonttools, resvg-py.

Usage: python tools/build_icon.py --font /path/to/DejaVuSans-Bold.ttf
No font or graphics dependencies are added to app startup.
"""
import argparse
from pathlib import Path


def build(font_path):
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    import resvg_py
    from PIL import Image
    root = Path(__file__).resolve().parents[1] / 'Icon'
    root.mkdir(exist_ok=True)
    navy, blue, teal, orange = '#12223D', '#2864F0', '#21D4BF', '#FF8040'
    mark = f'''<rect x="8" y="8" width="240" height="240" rx="52" fill="{navy}"/>
<path d="M32 77Q32 63 46 63H105L124 81H213Q226 81 226 94V180Q226 194 212 194H46Q32 194 32 180Z" fill="{teal}"/>
<path d="M44 96V64Q44 52 56 52H105L129 79H185V112Z" fill="{orange}"/>
<path d="M32 103Q32 89 46 89H211Q225 89 225 103L211 201Q209 214 196 214H46Q32 214 32 200Z" fill="{blue}"/>
<path d="M45 102H210L207 118H42Z" fill="#3D7BFF"/>
<path d="M81 132V181H175M127 151V181" fill="none" stroke="#FFFFFF" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
<rect x="69" y="120" width="24" height="24" rx="5" fill="#FFFFFF"/>
<rect x="115" y="139" width="24" height="24" rx="5" fill="{teal}"/>
<rect x="163" y="169" width="24" height="24" rx="5" fill="{orange}"/>
<path d="M203 37L210 49L224 52L212 59L209 73L202 61L188 58L200 51Z" fill="{orange}"/>'''
    from html import escape
    license_text = (root.parent / "docs" / "WORDMARK_FONT_LICENSE.txt").read_text(encoding="utf-8")
    def svg(body, width, title):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 256" '
                f'width="{width}" height="256" role="img" aria-label="{title}">'
                f'<title>{title}</title><metadata>{escape(license_text)}</metadata>{body}</svg>\n')
    font = TTFont(font_path)
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = 132 / font['head'].unitsPerEm
    cursor, forge_start, paths = 0, 0, []
    for index, char in enumerate('FolderForge'):
        if index == 6:
            forge_start = cursor
        glyph_name = cmap[ord(char)]
        pen = SVGPathPen(glyphs)
        glyphs[glyph_name].draw(pen)
        paths.append(f'<path fill="{navy if index < 6 else blue}" transform="translate({cursor} 0)" d="{pen.getCommands()}"/>')
        cursor += font['hmtx'][glyph_name][0]
    word = f'<g transform="translate(284 175) scale({scale} {-scale})" fill="{navy}">' + ''.join(paths) + '</g>'
    width = round(284 + cursor * scale + 24)
    symbol = svg(mark, 256, 'FolderForge symbol')
    accent = f'<path d="M{284 + forge_start * scale} 202H{width - 24}L{width - 40} 214H{284 + forge_start * scale}Z" fill="{orange}"/>'
    logo = svg(mark + word + accent, width, 'FolderForge')
    # A separate one-ink version preserves the symbol's negative spaces.
    mono_mark = '''<path d="M32 93V65Q32 52 45 52H103L128 80H211Q224 80 224 94L210 201Q208 214 195 214H46Q32 214 32 200Z" fill="none" stroke="#000000" stroke-width="12" stroke-linejoin="round"/>
<path d="M81 128V181H175M127 151V181" fill="none" stroke="#000000" stroke-width="12" stroke-linecap="round"/>
<rect x="69" y="116" width="24" height="24" rx="5"/><rect x="115" y="139" width="24" height="24" rx="5"/><rect x="163" y="169" width="24" height="24" rx="5"/>
<path d="M203 37L210 49L224 52L212 59L209 73L202 61L188 58L200 51Z"/>'''
    assets = {'folderforge-symbol.svg': symbol, 'folderforge-logo.svg': logo,
              'folderforge-logo-inverse.svg': svg(mark + word.replace(navy, '#FFFFFF').replace(blue, teal) + accent, width, 'FolderForge vit'),
              'folderforge-logo-mono.svg': svg(mono_mark + word.replace(navy, '#000000').replace(blue, '#000000') + accent.replace(orange, '#000000'), width, 'FolderForge enfarg')}
    for name, content in assets.items():
        (root / name).write_text(content, encoding='utf-8')
    def raster(content, size):
        import io
        return Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=content, width=size, skip_system_fonts=True))).convert('RGBA')
    master = raster(symbol, 1024)
    master.save(root / 'folderforge-master.png')
    for name, size in [('projektmapp_icon_256.png', 256), ('projektmapp_icon (1).png', 256), ('folderforge-tray.png', 64)]:
        master.resize((size, size), Image.Resampling.LANCZOS).save(root / name)
    master.save(root / 'projektmapp.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    master.save(root / 'folderforge.icns')
    raster(svg(f'<rect width="{width}" height="256" fill="#FFFFFF"/>' + mark + word + accent, width, 'FolderForge'), width * 2).save(root / 'folderforge-logo.png')
    print('Built vector masters, outlined wordmark, PNG, ICO and ICNS in', root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', required=True, type=Path)
    build(parser.parse_args().font)
