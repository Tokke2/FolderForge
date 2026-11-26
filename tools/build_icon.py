"""Build matching app/print assets and crisp UI icons. Dev-only: Pillow, fonttools, resvg-py.

Usage: python tools/build_icon.py --font /path/to/DejaVuSans-Bold.ttf
No font or graphics dependencies are added to app startup.
"""
import argparse
from html import escape
import io
from pathlib import Path
import shutil


NAV_SHAPES = {
    'create': (
        '<path d="M3 6a2 2 0 0 1 2-2h4.2l2 2.2H19a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6Z"/>',
        '<path d="M12 10v6M9 13h6" stroke="{accent}"/>',
    ),
    'history': (
        '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 8.5V4.5h4"/>',
        '<path d="M12 7.5v4.8l3.2 2" stroke="{accent}"/>',
    ),
    'templates': (
        '<rect x="3" y="4" width="7" height="6" rx="1.5"/><rect x="14" y="9" width="7" height="5" rx="1.5"/><rect x="14" y="16" width="7" height="5" rx="1.5"/>',
        '<path d="M6.5 10v8.5H14M6.5 11.5H14" stroke="{accent}"/>',
    ),
    'export': (
        '<path d="M4 15.5V18a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2.5"/><path d="M8 8l4-4 4 4"/>',
        '<path d="M12 4v11" stroke="{accent}"/>',
    ),
    'settings': (
        '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1"/>',
        '<circle cx="15" cy="7" r="2" stroke="{accent}"/><circle cx="9" cy="12" r="2" stroke="{accent}"/><circle cx="17" cy="17" r="2" stroke="{accent}"/>',
    ),
    'keyboard': (
        '<rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M6.5 9.5h1.5M11.2 9.5h1.6M16 9.5h1.5M6.5 13h1.5M11.2 13h1.6M16 13h1.5"/>',
        '<path d="M8 16.2h8" stroke="{accent}"/>',
    ),
    'profiles': (
        '<path d="M3 7a2 2 0 0 1 2-2h3.8l1.8 2H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>',
        '<circle cx="12" cy="12.2" r="2" stroke="{accent}"/><path d="M8.8 17c.7-1.5 1.8-2.2 3.2-2.2s2.5.7 3.2 2.2" stroke="{accent}"/>',
    ),
    'folder': (
        '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.3l2 2H19.5A1.5 1.5 0 0 1 21 8.5v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-11Z"/>',
        '<path d="M3.5 10.5h17" stroke="{accent}"/>',
    ),
    'refresh': (
        '<path d="M20 11a8 8 0 0 0-14.3-4.8L4 8M4 4v4h4"/>',
        '<path d="M4 13a8 8 0 0 0 14.3 4.8L20 16M20 20v-4h-4" stroke="{accent}"/>',
    ),
    'copy': (
        '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/>',
        '<path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" stroke="{accent}"/>',
    ),
    'save': (
        '<path d="M5 4h11.5L20 7.5V19a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 19V5.5A1.5 1.5 0 0 1 5.5 4Z"/><path d="M8 4v5h7V4"/>',
        '<rect x="7.5" y="13" width="9" height="7" rx="1" stroke="{accent}"/>',
    ),
    'trash': (
        '<path d="M4.5 7h15M9 7V4.8a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1V7M6.5 7l.8 12a1.5 1.5 0 0 0 1.5 1.4h6.4a1.5 1.5 0 0 0 1.5-1.4L17.5 7"/>',
        '<path d="M10 11v5.5M14 11v5.5" stroke="{accent}"/>',
    ),
    'undo': (
        '<path d="M4 9h10.5a4.5 4.5 0 1 1 0 9H9"/>',
        '<path d="M7.5 5.5 4 9l3.5 3.5" stroke="{accent}"/>',
    ),
    'fit': (
        '<path d="M4 9V5a1 1 0 0 1 1-1h4M20 9V5a1 1 0 0 0-1-1h-4M4 15v4a1 1 0 0 0 1 1h4M20 15v4a1 1 0 0 1-1 1h-4"/>',
        '<rect x="8.5" y="8.5" width="7" height="7" rx="1" stroke="{accent}"/>',
    ),
}


def build(font_path):
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    import resvg_py
    from PIL import Image, ImageFilter

    root = Path(__file__).resolve().parents[1] / 'Icon'
    root.mkdir(exist_ok=True)
    navy, blue, teal, orange = '#12223D', '#2864F0', '#21D4BF', '#FF8040'

    # Small-size tray derivative: bold geometry, thick strokes, maximum contrast at 16-32 px.
    tray_mark = f'''<rect id="tray-bg" x="6" y="6" width="244" height="244" rx="54" fill="{navy}" stroke="#2A436E" stroke-width="4"/>
<path id="tray-tab" d="M30 88V60Q30 44 46 44H106L132 72H214Q228 72 228 88V102H30Z" fill="{orange}"/>
<path id="tray-folder" d="M26 94Q26 80 40 80H216Q230 80 228 94L216 202Q214 216 200 216H52Q38 216 36 202Z" fill="{blue}"/>
<path id="tray-rim" d="M38 92H218" fill="none" stroke="#9AD0FF" stroke-width="6" stroke-linecap="round"/>
<path id="tray-tree" d="M78 124V184H180M78 152H134" fill="none" stroke="#FFFFFF" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>
<rect id="tray-node-1" x="62" y="108" width="32" height="32" rx="7" fill="#FFFFFF"/>
<rect id="tray-node-2" x="122" y="136" width="32" height="32" rx="7" fill="{teal}"/>
<rect id="tray-node-3" x="166" y="168" width="32" height="32" rx="7" fill="{orange}"/>'''

    # Crisp vector symbol with named editable shape IDs for print & design tools.
    mark = f'''<defs>
<linearGradient id="badge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1E355E"/><stop offset="1" stop-color="{navy}"/></linearGradient>
<linearGradient id="folder" x1="0" y1="0" x2="0.85" y2="1"><stop offset="0" stop-color="#4DA1FF"/><stop offset="0.52" stop-color="{blue}"/><stop offset="1" stop-color="#1842C6"/></linearGradient>
<linearGradient id="edge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7CFFF0"/><stop offset="1" stop-color="{teal}"/></linearGradient>
<linearGradient id="ember" x1="0" y1="0" x2="0.85" y2="1"><stop offset="0" stop-color="#FFCA68"/><stop offset="0.55" stop-color="{orange}"/><stop offset="1" stop-color="#F04E37"/></linearGradient>
</defs>
<rect id="symbol-badge" x="8" y="8" width="240" height="240" rx="52" fill="url(#badge)"/>
<rect id="symbol-badge-rim" x="12" y="12" width="232" height="232" rx="48" fill="none" stroke="#35558A" stroke-width="2" opacity="0.55"/>
<path id="symbol-accent-top" d="M36 62V50Q36 34 52 34H142" fill="none" stroke="{teal}" stroke-width="4" stroke-linecap="round" opacity="0.85"/>
<path id="symbol-accent-bottom" d="M224 182V204Q224 222 206 222H162" fill="none" stroke="{orange}" stroke-width="4" stroke-linecap="round"/>
<path id="symbol-back-plate" d="M36 82Q36 66 52 66H104L128 86H214Q228 86 226 100L214 196Q212 208 198 208H48Q34 208 34 194Z" fill="url(#edge)"/>
<path id="symbol-forge-tab" d="M46 92V60Q46 46 60 46H104L130 74H184V104Z" fill="url(#ember)"/>
<path id="symbol-folder-shadow" d="M34 106Q34 92 48 92H214Q228 92 225 106L210 206Q208 218 194 218H50Q36 218 34 206Z" fill="#081631" opacity="0.46"/>
<path id="symbol-folder-front" d="M28 98Q28 84 42 84H210Q224 84 221 98L206 198Q204 212 190 212H44Q30 212 28 198Z" fill="url(#folder)"/>
<path id="symbol-folder-bevel" d="M40 96H210L208 106H38Z" fill="#B8E0FF" opacity="0.55"/>
<path id="symbol-tree-lines" d="M74 124V180H168M74 152H124" fill="none" stroke="#FFFFFF" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
<rect id="symbol-node-root" x="60" y="110" width="28" height="28" rx="6" fill="#FFFFFF"/>
<rect id="symbol-node-mid" x="112" y="138" width="28" height="28" rx="6" fill="url(#edge)"/>
<rect id="symbol-node-leaf" x="156" y="166" width="28" height="28" rx="6" fill="url(#ember)"/>
<path id="symbol-forge-bolt" d="M196 28L172 66H192L182 94L222 50H202L214 28Z" fill="url(#ember)"/>
<path id="symbol-forge-spark" d="M227 72L230 79L237 82L230 85L227 92L224 85L217 82L224 79Z" fill="#FFFFFF"/>
'''

    license_text = (root.parent / 'docs' / 'WORDMARK_FONT_LICENSE.txt').read_text(encoding='utf-8')

    def svg(body, width, title):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 256" '
                f'width="{width}" height="256" shape-rendering="geometricPrecision" role="img" aria-label="{title}">'
                f'<title>{title}</title><metadata>{escape(license_text)}</metadata>{body}</svg>\n')

    font = TTFont(font_path)
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = 134 / font['head'].unitsPerEm
    tracking = round(font['head'].unitsPerEm * 0.015)
    cursor, forge_start, paths = 0, 0, []
    for index, char in enumerate('FolderForge'):
        if index == 6:
            forge_start = cursor
        glyph_name = cmap[ord(char)]
        pen = SVGPathPen(glyphs)
        glyphs[glyph_name].draw(pen)
        paths.append(
            f'<path id="glyph-{index}-{char}" fill="{navy if index < 6 else blue}" '
            f'transform="translate({cursor} 0)" d="{pen.getCommands()}"/>'
        )
        cursor += font['hmtx'][glyph_name][0] + tracking

    word = f'<g id="wordmark-folderforge" transform="translate(284 166) scale({scale} {-scale})" fill="{navy}">' + ''.join(paths) + '</g>'
    width = round(284 + cursor * scale + 28)
    symbol = svg(mark, 256, 'FolderForge symbol')
    bar_x = round(284 + forge_start * scale)
    accent = f'<path id="wordmark-underline" d="M{bar_x} 212H{width - 28}L{width - 40} 224H{bar_x}Z" fill="{orange}"/>'
    display_word = word.replace(f'fill="{blue}"', 'fill="url(#folder)"')
    logo = svg(mark + display_word + accent.replace(orange, 'url(#ember)'), width, 'FolderForge')

    # Dedicated one-ink vector master preserving open negative spaces.
    mono_mark = '''<path id="mono-folder-outline" d="M30 92V62Q30 48 44 48H104L130 76H212Q226 76 224 90L210 200Q208 214 194 214H46Q32 214 30 200Z" fill="none" stroke="#000000" stroke-width="12" stroke-linejoin="round"/>
<path id="mono-tree-lines" d="M76 124V180H170M76 152H126" fill="none" stroke="#000000" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
<rect id="mono-node-root" x="62" y="110" width="28" height="28" rx="6" fill="#000000"/>
<rect id="mono-node-mid" x="114" y="138" width="28" height="28" rx="6" fill="#000000"/>
<rect id="mono-node-leaf" x="158" y="166" width="28" height="28" rx="6" fill="#000000"/>
<path id="mono-forge-bolt" d="M198 28L174 66H194L184 94L224 50H204L216 28Z" fill="#000000"/>'''

    # Editable-text vector print original with clean Illustrator/Inkscape layer groups.
    editable_print = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 256" width="{width}" height="256" '
        f'shape-rendering="geometricPrecision" role="img" aria-label="FolderForge redigerbart tryckoriginal">\n'
        f'<title>FolderForge – redigerbart vektororiginal för tryck</title>\n'
        f'<metadata>{escape(license_text)} | Färger sRGB: Navy {navy}, Blue {blue}, Teal {teal}, Orange {orange}</metadata>\n'
        f'<g id="Layer-1-Symbol">{mark}</g>\n'
        f'<g id="Layer-2-Redigerbar-Text" font-family="DejaVu Sans, Segoe UI, Inter, Arial, sans-serif" font-weight="700" font-size="134" letter-spacing="1.5">\n'
        f'  <text id="Text-Folder" x="284" y="166" fill="{navy}">Folder</text>\n'
        f'  <text id="Text-Forge" x="{bar_x}" y="166" fill="url(#folder)">Forge</text>\n'
        f'</g>\n'
        f'<g id="Layer-3-Accent">{accent.replace(orange, "url(#ember)")}</g>\n'
        f'</svg>\n'
    )

    assets = {
        'folderforge-symbol.svg': symbol,
        'folderforge-logo.svg': logo,
        'folderforge-logo-inverse.svg': svg(
            mark + word.replace(navy, '#FFFFFF').replace(blue, teal) + accent,
            width, 'FolderForge vit',
        ),
        'folderforge-logo-mono.svg': svg(
            mono_mark + word.replace(navy, '#000000').replace(blue, '#000000') + accent.replace(orange, '#000000'),
            width, 'FolderForge enfarg',
        ),
        'folderforge-print-editable.svg': editable_print,
    }
    for name, content in assets.items():
        (root / name).write_text(content, encoding='utf-8')

    def raster(content, size):
        return Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=content, width=size, skip_system_fonts=True))).convert('RGBA')

    # Crisp navigation & action vector icons (light & dark) + matching PNGs for Tk reserve.
    for icon_name, (primary_paths, accent_paths) in NAV_SHAPES.items():
        for theme, stroke, accent_col in (
            ('light', '#17324D', '#2768AF'),
            ('dark', '#F1F6FD', '#21D4BF'),
        ):
            icon_svg = (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                f'stroke="{stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
                f'shape-rendering="geometricPrecision"><title>FolderForge {icon_name}</title>'
                f'{primary_paths}{accent_paths.format(accent=accent_col)}</svg>\n'
            )
            svg_path = root / f'nav-{icon_name}-{theme}.svg'
            svg_path.write_text(icon_svg, encoding='utf-8')
            if icon_name in {'create', 'history', 'templates', 'export', 'settings', 'keyboard'}:
                raster(icon_svg, 48).save(root / f'nav-{icon_name}-{theme}.png')

    tray_img = raster(svg(tray_mark, 256, 'FolderForge tray'), 64)
    tray_img.save(root / 'folderforge-tray.png')

    master = raster(symbol, 1024)
    master.save(root / 'folderforge-master.png')
    for name, size in [('projektmapp_icon_256.png', 256), ('projektmapp_icon (1).png', 256)]:
        resized = master.resize((size, size), Image.Resampling.LANCZOS)
        resized = resized.filter(ImageFilter.UnsharpMask(radius=0.8, percent=90, threshold=2))
        resized.save(root / name)

    # Build crisp multi-size ICO directly from size-appropriate renders.
    master.save(root / 'projektmapp.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    master.save(root / 'folderforge.icns')
    bundle_icon = root.parent / 'Starta-FolderForge.app/Contents/Resources/folderforge.icns'
    if bundle_icon.parent.is_dir():
        shutil.copy2(root / 'folderforge.icns', bundle_icon)
    raster(
        svg(f'<rect width="{width}" height="256" fill="#FFFFFF"/>' + mark + display_word + accent.replace(orange, 'url(#ember)'), width, 'FolderForge'),
        width * 2,
    ).save(root / 'folderforge-logo.png')
    print('Built vector masters, editable print SVG, crisp UI icons, PNG, ICO and ICNS in', root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', required=True, type=Path)
    build(parser.parse_args().font)
