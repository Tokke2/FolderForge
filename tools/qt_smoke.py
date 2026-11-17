"""Real optional Qt widget smoke test in an isolated copy, with no Tk process."""
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def main():
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='FolderForge-Qt-test-') as temp:
        root = Path(temp)
        shutil.copy2(source / 'qt_preview.py', root / 'qt_preview.py')
        (root / 'Icon').mkdir()
        shutil.copy2(source / 'Icon/projektmapp_icon_256.png', root / 'Icon/projektmapp_icon_256.png')
        def snapshot():
            return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        before = snapshot()
        sys.path.insert(0, str(root))
        from qt_preview import PreviewWindow, fit_to_screen
        app = QApplication([])
        window = PreviewWindow()
        assert not window.isVisible(), 'Preview must not show at construction/start'
        window.restore()
        QTest.qWait(100)
        assert window.isVisible()
        for width, height in ((420, 400), (900, 650)):
            fit_to_screen(window, width, height)
            QTest.qWait(20)
            assert window.screen().availableGeometry().contains(window.frameGeometry()), window.frameGeometry()
        window.open_project()
        dialog = window.dialog
        dialog.name.setText('Testprojekt')
        dialog.focus_name()
        QTest.qWait(100)
        assert app.focusWidget() is dialog.name, repr(app.focusWidget())
        assert dialog.name.selectedText() == 'Testprojekt'
        QTest.keyClick(dialog.name, Qt.Key_Tab)
        assert app.focusWidget() is dialog.location
        dialog.location.setText('Kista')
        dialog.year.setEditText('2026')
        assert dialog.preview.text() == 'Testprojekt Kista 2026'
        window.open_project()
        assert window.dialog is dialog, 'Do not duplicate a visible dialog'
        QTest.keyClick(dialog, Qt.Key_Escape)
        assert not dialog.isVisible()
        window.close()
        app.processEvents()
        assert snapshot() == before, 'Preview must not write production files'
        assert not (root / 'data').exists()
        print('Qt smoke OK: hidden startup, screen fit, dialog focus/selection, Tab, preview, Escape, no data writes')
        window.deleteLater()
        app.processEvents()


if __name__ == '__main__':
    main()
