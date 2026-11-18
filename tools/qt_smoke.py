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
        root = Path(temp).resolve()
        for name in ('qt_preview.py', 'qt_app.py', 'workspace.py', 'app_core.py', 'instance_lock.py', 'settings.py', 'historik.py', 'qt_help.py', 'qt_diagnostics.py', 'updater.py', 'logg.py', 'qt_integrations.py'):
            shutil.copy2(source / name, root / name)
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
        from instance_lock import SingleInstanceLock
        from workspace import Workspace
        from qt_app import QtWindow
        from unittest.mock import patch
        import uuid
        from PySide6.QtWidgets import QMessageBox
        import historik
        lock = SingleInstanceLock('FolderForge-Qt-CI-' + uuid.uuid4().hex, root / 'test-lock')
        assert lock.acquire()
        try:
            ws = Workspace(lock, root)
            ws.config.save_root = str(root / 'Projects')
            ws.config.open_after_creation = False
            ws.raw['future_key'] = 'preserved'
            ws.save_settings()
            functional = QtWindow(ws)
            functional.restore()
            QTest.qWait(50)
            functional.open_project()
            dialog = functional.dialog
            dialog.name.setText('abc123 vindruta')
            dialog.year.setEditText('2026')
            QTest.qWait(100)
            assert app.focusWidget() is dialog.name
            with patch('qt_app.QMessageBox.question', return_value=QMessageBox.Yes):
                dialog.create()
            entries = ws.history.get_all()
            assert len(entries) == 1, entries
            project = Path(entries[0]['path'])
            assert project.parent == root / 'Projects'
            assert project.name == 'ABC123 VINDRUTA 2026', project
            assert (project / 'Bilder').is_dir()
            assert dialog.name.selectedText() == 'abc123 vindruta'
            assert len(historik.ProjectHistory(root / 'data/history.json').get_all()) == 1
            assert Workspace(lock, root).raw['future_key'] == 'preserved'
            assert functional.tabs.count() == 5
            ws.config.text_size = '150%'
            ws.config.high_contrast = True
            functional.apply_accessibility()
            assert '22px' in functional.styleSheet()
            ws.config.text_size = '100%'
            ws.config.high_contrast = False
            ws.config.theme = 'Light'
            functional.apply_accessibility()
            assert '#F4F7FB' in functional.styleSheet()
            ws.config.theme = functional.theme.currentText()
            ws.config.text_size = functional.text_size.currentText()
            ws.config.high_contrast = functional.high_contrast.isChecked()
            assert not functional.can_restart(), 'An open project dialog must defer restart'
            dialog.reject()
            assert functional.can_restart(), 'Clean UI must allow a ready update'
            functional.structure.insertPlainText('\n    unsaved/')
            assert not functional.can_restart(), 'Unsaved template must defer restart'
            functional.structure.document().setModified(False)
            from qt_help import DiagnosticsDialog
            diagnostics = DiagnosticsDialog(functional)
            diagnostics.system_check()
            assert 'qt_version' in diagnostics.details.toPlainText()
            diagnostics.reject()
            functional.close()
            functional.deleteLater()
            print('Qt functional smoke OK: shared lock, real isolated project, persistent history/settings, templates, five pages')
        finally:
            lock.release()
        app.processEvents()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        detail = traceback.format_exc()
        print('::error title=Qt integration::' + detail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A'), flush=True)
        raise
