"""Explicit, local shortcut generation. No installs, autostart or policy bypass."""
from pathlib import Path
import os
import plistlib
import shlex
import sys


def create_shortcut(base, interpreter, system):
    base, interpreter = Path(base).resolve(), Path(interpreter).resolve()
    if system == 'darwin':
        bundle = base / 'FolderForge.app'
        contents = bundle / 'Contents'
        (contents / 'MacOS').mkdir(parents=True, exist_ok=True)
        (contents / 'Resources').mkdir(exist_ok=True)
        executable = contents / 'MacOS/FolderForge'
        executable.write_text('#!/bin/sh\nexec ' + shlex.quote(str(interpreter)) + ' ' +
                              shlex.quote(str(base / 'Starta-FolderForge.py')) + '\n', encoding='utf-8')
        executable.chmod(0o755)
        import shutil
        shutil.copy2(base / 'Icon/folderforge.icns', contents / 'Resources/folderforge.icns')
        with (contents / 'Info.plist').open('wb') as stream:
            plistlib.dump(dict(CFBundleName='FolderForge', CFBundleDisplayName='FolderForge',
                CFBundleIdentifier='se.folderforge.desktop', CFBundleExecutable='FolderForge',
                CFBundlePackageType='APPL', CFBundleIconFile='folderforge.icns',
                CFBundleShortVersionString='0.0.2', NSHighResolutionCapable=True,
                NSHumanReadableCopyright='© Rickard Längkvist'), stream)
        return bundle
    if system.startswith('linux'):
        def desktop_quote(value):
            # Exec is parsed by the desktop specification, NOT by a shell.
            value = str(value).replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
            return '"' + value + '"'
        if any(c in str(base) + str(interpreter) for c in '\n\r'):
            raise ValueError('Genvägens sökväg får inte innehålla radbrytningar')
        target = base / 'FolderForge.desktop'
        command = desktop_quote(interpreter) + ' ' + desktop_quote(base / 'Starta-FolderForge.py')
        # Desktop-entry string values use backslash escaping, including literal backslashes.
        icon = str(base / 'Icon/projektmapp_icon_256.png').replace('\\', '\\\\')
        target.write_text('[Desktop Entry]\nType=Application\nVersion=1.0\nName=FolderForge\n'
                          'Comment=Skapa projektmappar med rätt struktur\nExec=' + command +
                          '\nIcon=' + icon + '\nTerminal=false\nCategories=Utility;\nStartupNotify=false\n', encoding='utf-8')
        target.chmod(0o755)
        return target
    raise ValueError('Windows: använd Starta-FolderForge.vbs och appens inbyggda startprogram.')


if __name__ == '__main__':
    print(create_shortcut(Path(__file__).resolve().parents[1], sys.executable, sys.platform))
