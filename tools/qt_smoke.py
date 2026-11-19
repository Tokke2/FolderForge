"""Real optional Qt widget smoke test in an isolated copy, with no Tk process."""
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt, QTimer, QPoint, QPointF
from PySide6.QtTest import QTest
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QScrollArea, QComboBox, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget


def main():
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='FolderForge-Qt-test-') as temp:
        root = Path(temp).resolve()
        for name in ('qt_preview.py', 'qt_app.py', 'workspace.py', 'app_core.py', 'instance_lock.py', 'settings.py', 'historik.py', 'qt_help.py', 'qt_diagnostics.py', 'updater.py', 'logg.py', 'qt_integrations.py'):
            shutil.copy2(source / name, root / name)
        (root / 'Icon').mkdir()
        shutil.copy2(source / 'Icon/projektmapp_icon_256.png', root / 'Icon/projektmapp_icon_256.png')
        shutil.copy2(source / 'Icon/swish-folderforge.png', root / 'Icon/swish-folderforge.png')
        shutil.copy2(source / 'Icon/folderforge-logo.png', root / 'Icon/folderforge-logo.png')
        for icon in (source / 'Icon').glob('nav-*.png'):
            shutil.copy2(icon, root / 'Icon' / icon.name)
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
            assert functional.findChild(QLabel, 'appLogo').pixmap() is not None
            assert functional.findChild(QWidget, 'appHeader')
            assert functional.findChild(QWidget, 'appFooter')
            if sys.platform == 'win32':
                import builtins
                from qt_integrations import HotkeyBridge, WindowsHotkey
                original_import = builtins.__import__
                def no_pynput(name, *args, **kwargs):
                    if name == 'pynput' or name.startswith('pynput.'):
                        raise AssertionError('Windows native hotkey must not import pynput')
                    return original_import(name, *args, **kwargs)
                bridge = HotkeyBridge(functional)
                with patch('builtins.__import__', side_effect=no_pynput):
                    bridge.register(['ctrl', 'alt', 'shift', 'f23'])
                    assert isinstance(bridge.listener, WindowsHotkey)
                    assert bridge.listener.active
                    bridge.stop()
            # Real wheel dispatch: focused controls stay unchanged; containing page scrolls.
            wheel_page = QScrollArea()
            wheel_page.setWidgetResizable(True)
            wheel_body = QWidget()
            wheel_layout = QVBoxLayout(wheel_body)
            combo = QComboBox()
            combo.addItems(['A', 'B', 'C'])
            combo.setCurrentIndex(1)
            line = QLineEdit('unchanged')
            multi = QPlainTextEdit('\n'.join(str(n) for n in range(100)))
            multi.setFixedHeight(80)
            for control in (combo, line, multi):
                wheel_layout.addWidget(control)
            wheel_layout.addSpacing(2000)
            wheel_page.setWidget(wheel_body)
            wheel_page.resize(400, 280)
            wheel_page.show()
            QTest.qWait(50)
            for control in (combo, line, multi.viewport()):
                wheel_page.verticalScrollBar().setValue(0)
                control.setFocus()
                before_text_scroll = multi.verticalScrollBar().value()
                event = QWheelEvent(QPointF(8, 8), QPointF(control.mapToGlobal(QPoint(8, 8))),
                    QPoint(), QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
                QApplication.sendEvent(control, event)
                assert combo.currentIndex() == 1
                assert line.text() == 'unchanged'
                assert multi.verticalScrollBar().value() == before_text_scroll
                assert wheel_page.verticalScrollBar().value() > 0, 'Wheel must scroll outer page'
            combo.setFocus()
            QTest.keyClick(combo, Qt.Key_Down)
            assert combo.currentIndex() == 2, 'Keyboard selection must remain available'
            wheel_page.close()
            wheel_page.deleteLater()
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
            assert functional.tabs.count() == 6
            assert [b.text() for b in functional.tabs.buttons] == [
                'Skapa', 'Historik', 'Mallar', 'Exportera', 'Inställningar', 'Snabbtangent']
            assert all(not b.icon().isNull() for b in functional.tabs.buttons)
            functional.tabs.setTabVisible(5, False)
            assert 5 in functional.tabs.hidden_tabs
            functional.tabs.setTabVisible(5, True)
            assert 5 not in functional.tabs.hidden_tabs
            assert functional.hotkey_recorder.accessibleName() == 'Spela in snabbtangent'
            functional.history_filter.setText('NO-SUCH-PROJECT')
            assert functional.history_list.count() == 0
            functional.history_filter.clear()
            assert functional.history_list.count() == 1
            functional.history_list.setCurrentRow(0)
            assert functional.history_list.currentItem().data(Qt.UserRole) == str(project)
            with patch('qt_app.QMessageBox.question', return_value=QMessageBox.No):
                functional.remove_history(True)
            assert len(ws.history.get_all()) == 1
            with patch('qt_app.QMessageBox.question', return_value=QMessageBox.Yes):
                functional.remove_history(False)
            assert not ws.history.get_all()
            assert project.is_dir(), 'History removal must never delete a project'
            ws.history.add(project)
            functional.refresh_history()
            ws.config.text_size = '150%'
            ws.config.high_contrast = True
            functional.apply_accessibility()
            assert '22px' in functional.styleSheet()
            ws.config.text_size = '100%'
            ws.config.high_contrast = False
            ws.config.theme = 'Light'
            functional.apply_accessibility()
            assert '#F3F6FA' in functional.styleSheet()
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
            donation_errors = []
            def inspect_donation():
                donation = app.activeModalWidget()
                try:
                    assert isinstance(donation, QDialog)
                    assert donation.windowTitle() == 'Donationer – Stöd FolderForge'
                    qr = donation.findChild(QLabel, 'swishQr')
                    assert qr and not qr.pixmap().isNull(), 'Offline Swish QR not rendered'
                    assert donation.findChild(QScrollArea), 'Small screens need scrolling without clipping'
                    controls = donation.findChildren(QPushButton)
                    assert any('PayPal' in c.text() for c in controls)
                    assert any('Ko-fi' in c.text() for c in controls)
                except Exception as exc:
                    donation_errors.append(str(exc))
                finally:
                    if donation:
                        donation.reject()
            from unittest.mock import patch
            with patch('qt_app.webbrowser.open') as opened:
                QTimer.singleShot(100, inspect_donation)
                functional.donations()
                opened.assert_not_called()
            assert not donation_errors, donation_errors
            update_errors = []
            def inspect_update():
                dialog = app.activeModalWidget()
                try:
                    assert dialog and dialog.windowTitle() == 'Uppdateringsstatus'
                    install = dialog.findChild(QPushButton, 'installUpdate')
                    assert install and not install.isEnabled(), 'No candidate must mean disabled installation'
                except Exception as exc:
                    update_errors.append(str(exc))
                finally:
                    if dialog:
                        dialog.reject()
            with patch('qt_app.threading.Thread'), patch('updater.pending_ready_for_restart', return_value=False):
                QTimer.singleShot(100, inspect_update)
                functional.check_updates()
            assert not update_errors, update_errors
            # Save a profile through the real editor, then create in its own destination.
            functional.tabs.setCurrentIndex(2)
            functional.template_name.setText('CI Profil')
            functional.structure.setPlainText('Bilder/\nUnderlag/\n')
            profile_root = root / 'Profile Projects'
            functional.profile_root_edit.setText(str(profile_root))
            save_profile = next(b for b in functional.findChildren(QPushButton)
                                if b.text() == 'Spara profil (mall + sparplats)')
            save_profile.click()
            assert ws.profile_root('CI Profil') == profile_root
            assert functional.templates.currentText() == 'CI Profil'
            functional.open_project()
            profile_dialog = functional.dialog
            profile_dialog.template.setCurrentText('CI Profil')
            profile_dialog.name.setText('DEF456')
            profile_dialog.year.setEditText('2026')
            assert str(profile_root) in profile_dialog.preview.text()
            with patch('qt_app.QMessageBox.question', return_value=QMessageBox.Yes):
                profile_dialog.create()
            assert (profile_root / 'DEF456 2026/Bilder').is_dir()
            assert (profile_root / 'DEF456 2026/Underlag').is_dir()
            assert not (root / 'Projects/DEF456 2026').exists()
            profile_dialog.reject()
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
