"""Build original, matching navigation vectors. Standard library only; PNGs remain for Tk."""
from pathlib import Path

SHAPES = {
    'create': '<path d="M3 7V5h6l2 2h10v13H3V7Z"/><path d="M9 13h6m-3-3v6"/>',
    'history': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'templates': '<path d="m12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5"/>',
    'export': '<path d="M14 3h7v7m0-7L11 13M10 5H4v15h15v-6"/>',
    'settings': '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
    'keyboard': '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.1M10 9h.1M14 9h.1M18 9h.1M6 12h.1M10 12h.1M14 12h.1M18 12h.1M7 16h10"/>',
}


def build():
    root = Path(__file__).resolve().parents[1] / 'Icon'
    for name, body in SHAPES.items():
        for theme, color in (('light', '#233E5A'), ('dark', '#F2F6FC')):
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
                   f'fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
                   f'stroke-linejoin="round"><title>FolderForge {name}</title>{body}</svg>\n')
            (root / f'nav-{name}-{theme}.svg').write_text(svg, encoding='utf-8')


if __name__ == '__main__':
    build()
