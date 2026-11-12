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
    # Small-size derivative: deliberately flat, thick and uncluttered.
    tray_mark = f'''<rect x="8" y="8" width="240" height="240" rx="50" fill="{navy}"/>
<path d="M28 90V64Q28 50 42 50H105L131 80H214Q230 80 230 96V201Q230 218 213 218H43Q28 218 28 201Z" fill="{blue}"/>
<path d="M28 90V64Q28 50 42 50H105L131 80H214V96H28Z" fill="{orange}"/>
<path d="M77 127V181H180M130 151V181" fill="none" stroke="#FFFFFF" stroke-width="14" stroke-linecap="round"/>
<rect x="63" y="113" width="28" height="28" rx="5" fill="#FFFFFF"/>
<rect x="116" y="137" width="28" height="28" rx="5" fill="{teal}"/>
<rect x="166" y="167" width="28" height="28" rx="5" fill="{orange}"/>'''
    mark = f'''<defs>
<linearGradient id="badge" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#263C67"/><stop offset="1" stop-color="{navy}"/></linearGradient>
<linearGradient id="folder" x1="0" y1="0" x2="0.8" y2="1"><stop stop-color="#4F9DFF"/><stop offset="0.5" stop-color="{blue}"/><stop offset="1" stop-color="#163EC4"/></linearGradient>
<linearGradient id="edge" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#9CFFF1"/><stop offset="1" stop-color="{teal}"/></linearGradient>
<linearGradient id="ember" x1="0" y1="0" x2="0.8" y2="1"><stop stop-color="#FFD174"/><stop offset="0.55" stop-color="{orange}"/><stop offset="1" stop-color="#FF453D"/></linearGradient>
</defs>
<rect x="8" y="8" width="240" height="240" rx="52" fill="url(#badge)"/>
<path d="M30 74V53Q30 30 53 30H146" fill="none" stroke="{teal}" stroke-width="4" stroke-linecap="round" opacity="0.8"/>
<path d="M230 177V203Q230 226 207 226H159" fill="none" stroke="{orange}" stroke-width="4" stroke-linecap="round"/>
<path d="M34 87Q34 72 49 72H102L126 91H216Q231 91 229 106L217 194Q215 207 201 207H46Q32 207 32 193Z" fill="url(#edge)"/>
<path d="M45 97V63Q45 49 59 49H103L131 80H183V112Z" fill="url(#ember)"/>
<path d="M36 110Q36 96 50 96H214Q228 96 225 111L208 205Q206 219 192 219H49Q35 219 35 205Z" fill="#071A3C" opacity="0.45"/>
<path d="M29 103Q29 89 44 89H209Q224 89 221 104L204 199Q202 213 188 213H42Q28 213 28 199Z" fill="url(#folder)"/>
<path d="M43 101H208L205 114H40Z" fill="#A5D7FF" opacity="0.62"/>
<path d="M40 201H191L198 185" fill="none" stroke="#1948D6" stroke-width="5" stroke-linecap="round"/>
<path d="M77 128V178H173M125 148V178" fill="none" stroke="#FFFFFF" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
<rect x="65" y="116" width="24" height="24" rx="5" fill="#FFFFFF"/>
<rect x="113" y="136" width="24" height="24" rx="5" fill="url(#edge)"/>
<rect x="161" y="166" width="24" height="24" rx="5" fill="url(#ember)"/>
<path d="M198 30L174 68H194L183 96L223 51H203L216 30Z" fill="url(#ember)"/>
<path d="M197 34L180 63H196" fill="none" stroke="#FFE9BC" stroke-width="2.5" stroke-linecap="round"/>
<path d="M238 68L241 76L249 79L241 82L238 90L235 82L227 79L235 76Z" fill="#FFFFFF"/>
'''
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
    display_word = word.replace(f'fill="{blue}"', 'fill="url(#folder)"')
    logo = svg(mark + display_word + accent.replace(orange, 'url(#ember)'), width, 'FolderForge')
    # A separate one-ink version preserves the symbol's negative spaces.
    mono_mark = '''<path d="M32 93V65Q32 52 45 52H103L128 80H211Q224 80 224 94L210 201Q208 214 195 214H46Q32 214 32 200Z" fill="none" stroke="#000000" stroke-width="12" stroke-linejoin="round"/>
<path d="M81 128V181H175M127 151V181" fill="none" stroke="#000000" stroke-width="12" stroke-linecap="round"/>
<rect x="69" y="116" width="24" height="24" rx="5"/><rect x="115" y="139" width="24" height="24" rx="5"/><rect x="163" y="169" width="24" height="24" rx="5"/>
<path d="M198 30L174 68H194L183 96L223 51H203L216 30Z"/>'''
    assets = {'folderforge-symbol.svg': symbol, 'folderforge-logo.svg': logo,
              'folderforge-logo-inverse.svg': svg(mark + word.replace(navy, '#FFFFFF').replace(blue, teal) + accent, width, 'FolderForge vit'),
              'folderforge-logo-mono.svg': svg(mono_mark + word.replace(navy, '#000000').replace(blue, '#000000') + accent.replace(orange, '#000000'), width, 'FolderForge enfarg')}
    for name, content in assets.items():
        (root / name).write_text(content, encoding='utf-8')
    def raster(content, size):
        import io
        return Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=content, width=size, skip_system_fonts=True))).convert('RGBA')
    raster(svg(tray_mark, 256, 'FolderForge tray'), 64).save(root / 'folderforge-tray.png')
    master = raster(symbol, 1024)
    master.save(root / 'folderforge-master.png')
    for name, size in [('projektmapp_icon_256.png', 256), ('projektmapp_icon (1).png', 256)]:
        master.resize((size, size), Image.Resampling.LANCZOS).save(root / name)
    master.save(root / 'projektmapp.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    master.save(root / 'folderforge.icns')
    raster(svg(f'<rect width="{width}" height="256" fill="#FFFFFF"/>' + mark + display_word + accent.replace(orange, 'url(#ember)'), width, 'FolderForge'), width * 2).save(root / 'folderforge-logo.png')
    print('Built vector masters, outlined wordmark, PNG, ICO and ICNS in', root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', required=True, type=Path)
    build(parser.parse_args().font)
