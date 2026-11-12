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
    navy, gold, teal = '#102A43', '#F4BF4F', '#52DCC4'
    mark = f'''<rect x="10" y="10" width="236" height="236" rx="50" fill="{navy}"/>
<rect x="13" y="13" width="230" height="230" rx="47" fill="none" stroke="{gold}" stroke-width="6"/>
<path d="M45 103V73Q45 61 57 61H105L124 83H199Q211 83 211 95V110" fill="none" stroke="{gold}" stroke-width="12" stroke-linejoin="round"/>
<path d="M40 103Q40 95 50 95H206Q216 95 216 105V191Q216 203 204 203H52Q40 203 40 191Z" fill="{gold}"/>
<rect x="63" y="117" width="130" height="66" rx="12" fill="{navy}"/>
<path d="M86 135V163H169M128 145V163" fill="none" stroke="{teal}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
<rect x="76" y="125" width="20" height="20" rx="4" fill="{teal}"/>
<rect x="118" y="135" width="20" height="20" rx="4" fill="{teal}"/>
<rect x="159" y="153" width="20" height="20" rx="4" fill="{teal}"/>'''
    from html import escape
    license_text = (root.parent / "docs" / "WORDMARK_FONT_LICENSE.txt").read_text(encoding="utf-8")
    def svg(body, width, title):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 256" '
                f'width="{width}" height="256" role="img" aria-label="{title}">'
                f'<title>{title}</title><metadata>{escape(license_text)}</metadata>{body}</svg>\n')
    font = TTFont(font_path)
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = 132 / font['head'].unitsPerEm
    cursor, paths = 0, []
    for char in 'FolderForge':
        glyph_name = cmap[ord(char)]
        pen = SVGPathPen(glyphs)
        glyphs[glyph_name].draw(pen)
        paths.append(f'<path transform="translate({cursor} 0)" d="{pen.getCommands()}"/>')
        cursor += font['hmtx'][glyph_name][0]
    word = f'<g transform="translate(284 175) scale({scale} {-scale})" fill="{navy}">' + ''.join(paths) + '</g>'
    width = round(284 + cursor * scale + 24)
    symbol = svg(mark, 256, 'FolderForge symbol')
    logo = svg(mark + word, width, 'FolderForge')
    # A separate one-ink version preserves the symbol's negative spaces.
    mono_mark = '''<path d="M36 95V64Q36 52 48 52H106L128 77H207Q220 77 220 90V196Q220 208 208 208H48Q36 208 36 196Z" fill="none" stroke="#000000" stroke-width="12" stroke-linejoin="round"/>
<path d="M83 121V173H175M129 141V173" fill="none" stroke="#000000" stroke-width="11" stroke-linecap="round"/>
<rect x="72" y="110" width="22" height="22" rx="4"/><rect x="118" y="130" width="22" height="22" rx="4"/><rect x="164" y="162" width="22" height="22" rx="4"/>'''
    assets = {'folderforge-symbol.svg': symbol, 'folderforge-logo.svg': logo,
              'folderforge-logo-inverse.svg': svg(mark + word.replace(navy, '#FFFFFF'), width, 'FolderForge vit'),
              'folderforge-logo-mono.svg': svg(mono_mark + word.replace(navy, '#000000'), width, 'FolderForge enfarg')}
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
    raster(svg(f'<rect width="{width}" height="256" fill="#FFFFFF"/>' + mark + word, width, 'FolderForge'), width * 2).save(root / 'folderforge-logo.png')
    print('Built vector masters, outlined wordmark, PNG, ICO and ICNS in', root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', required=True, type=Path)
    build(parser.parse_args().font)
