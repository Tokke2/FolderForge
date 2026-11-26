"""Opt-in, read-only Qt UI experiment. Never imports Tk or production storage.

No project creation, settings/history writes, updater, autostart or global hooks.
Qt types are imported only when this optional module is explicitly selected.
"""
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt, QObject, QPointF
from PySide6.QtGui import QAction, QIcon, QWheelEvent, QGuiApplication
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
    QAbstractSpinBox, QPlainTextEdit, QTextEdit, QScrollArea, QSystemTrayIcon, QVBoxLayout, QWidget)

ROOT = Path(__file__).resolve().parent


class FieldWheelGuard(QObject):
    """Wheel belongs to the containing page, never to an input control."""
    def eventFilter(self, watched, event):
        if event.type() != QEvent.Wheel or not isinstance(watched, QWidget):
            return False
        control = watched
        protected = (QComboBox, QLineEdit, QAbstractSpinBox, QPlainTextEdit, QTextEdit)
        while control is not None and not isinstance(control, protected):
            control = control.parentWidget()
        if control is None:
            return False
        # Multiline editors send wheel events to their viewport/scrollbars too.
        # Forward outside the entire input, never to the input's own scroll area.
        parent = control.parentWidget()
        while parent is not None and not isinstance(parent, QScrollArea):
            parent = parent.parentWidget()
        if parent is not None:
            target = parent.viewport()
            local = QPointF(target.mapFromGlobal(event.globalPosition().toPoint()))
            forwarded = QWheelEvent(local, event.globalPosition(), event.pixelDelta(),
                event.angleDelta(), event.buttons(), event.modifiers(), event.phase(),
                event.inverted(), event.source())
            QApplication.sendEvent(target, forwarded)
        event.accept()
        return True


def install_field_wheel_guard(app):
    if not hasattr(app, '_folderforge_wheel_guard'):
        app._folderforge_wheel_guard = FieldWheelGuard(app)
        app.installEventFilter(app._folderforge_wheel_guard)


def fit_to_screen(window, width, height):
    screen = window.screen() or QApplication.primaryScreen()
    if not screen:
        return
    area = screen.availableGeometry().adjusted(12, 12, -12, -12)
    window.resize(min(width, area.width()), min(height, area.height()))
    frame = window.frameGeometry()
    frame.moveCenter(area.center())
    window.move(frame.topLeft())


class ProjectPreview(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Standardprojekt – endast Qt-förhandsvisning')
        self.setModal(True)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QVBoxLayout(content)
        explanation = QLabel('TESTLÄGE · Inga mappar skapas och ingenting sparas.\n'
                             'Prova fokus, Tab-ordning, större text och fönstrets storlek.')
        explanation.setWordWrap(True)
        body.addWidget(explanation)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.name = QLineEdit()
        self.name.setPlaceholderText('Skriv ett projektnamn…')
        self.name.setAccessibleName('Projektnamn')
        self.location = QLineEdit()
        self.location.setAccessibleName('Lokal')
        self.year = QComboBox()
        self.year.setEditable(True)
        # UI sample only: full shared production naming logic is a later step.
        from datetime import date
        year = date.today().year
        self.year.addItems(['—'] + [str(year - n) for n in range(4)])
        self.year.setAccessibleName('År')
        form.addRow('&Projektnamn', self.name)
        form.addRow('&Lokal', self.location)
        form.addRow('&År', self.year)
        body.addLayout(form)
        body.addWidget(QLabel('Enkel namnförhandsvisning (inte produktionsvalidering):'))
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setTextFormat(Qt.PlainText)
        self.preview.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        body.addWidget(self.preview)
        body.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText('Stäng – inget sparas')
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.name.textChanged.connect(self.update_preview)
        self.location.textChanged.connect(self.update_preview)
        self.year.currentTextChanged.connect(self.update_preview)
        QWidget.setTabOrder(self.name, self.location)
        QWidget.setTabOrder(self.location, self.year)
        QWidget.setTabOrder(self.year, buttons.button(QDialogButtonBox.Close))
        self.update_preview()

    def update_preview(self):
        parts = [self.name.text().strip(), self.location.text().strip()]
        if self.year.currentText().strip() != '—':
            parts.append(self.year.currentText().strip())
        self.preview.setText(' '.join(p for p in parts if p) or 'Ditt projektnamn visas här')

    def showEvent(self, event):
        super().showEvent(event)
        fit_to_screen(self, 600, 430)
        QTimer.singleShot(0, self.focus_name)

    def focus_name(self):
        self.name.setFocus(Qt.OtherFocusReason)
        self.name.selectAll()


class PreviewWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('FolderForge · Qt-prototyp · TESTLÄGE')
        self.setWindowIcon(QIcon(str(ROOT / 'Icon/folderforge-symbol.svg')))
        self.dialog = None
        content = QWidget()
        layout = QVBoxLayout(content)
        brand = QLabel('FolderForge / Qt')
        brand.setObjectName('brand')
        layout.addWidget(brand)
        notice = QLabel('SEPARAT PROTOTYP – INGA ÄNDRINGAR SPARAS\n'
                        'Din vanliga Tk-app är fortfarande standard och reserv.\n'
                        'Här provar vi bara det nya gränssnittet. Riktiga projekt,\n'
                        'historik, inställningar och uppdateringar lämnas orörda.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.open_button = QPushButton('Prova standardprojektdialogen')
        self.open_button.clicked.connect(self.open_project)
        layout.addWidget(self.open_button)
        layout.addStretch()
        hint = QLabel('Öppna den vanliga appen med din befintliga startfil.\n'
                      'Det här är inte en ersättare för Tk ännu.\n© Rickard Längkvist')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.setCentralWidget(content)
        help_menu = self.menuBar().addMenu('Hjälp')
        about = help_menu.addAction('Om Qt-prototypen')
        about.triggered.connect(lambda: QMessageBox.information(self, 'Qt-prototyp',
            'Endast en gränssnittsförhandsvisning. Inga projekt skapas.\n'
            'Ingen automatisk migrering, installation eller ändring av Tk-versionen.'))
        self.exit_action = QAction('Avsluta Qt-prototypen', self)
        self.exit_action.triggered.connect(QApplication.instance().quit)
        help_menu.addAction(self.exit_action)
        self.tray = None
        self.setStyleSheet('''
            QMainWindow, QDialog { background: #101c2c; }
            QWidget { background: #101c2c; color: #edf4fa; font-size: 15px; }
            QWidget#qt_scrollarea_viewport, QScrollArea { background: #101c2c; }
            QLabel#brand { color: #59e0d0; font-size: 28px; font-weight: 700; }
            QPushButton { background: #215c95; padding: 12px; border-radius: 7px; }
            QPushButton:hover { background: #2f75b6; }
            QPushButton:focus, QLineEdit:focus, QComboBox:focus { border: 2px solid #ffce66; }
            QLineEdit, QComboBox { background: #203249; padding: 8px; border: 2px solid #52657a; }
            QMenu { background: #203249; }
            QMenu::item:selected { background: #215c95; }
        ''')

    def open_project(self):
        if self.dialog and self.dialog.isVisible():
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        self.dialog = ProjectPreview(self)
        self.dialog.show()

    def restore(self):
        fit_to_screen(self, 700, 480)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.tray and self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and self.isMinimized() and self.tray:
            QTimer.singleShot(0, self.hide)


def run(window_factory=None, production=False):
    import ctypes
    import hashlib
    import logging
    import os
    import sys
    import time
    from PySide6.QtCore import QFileSystemWatcher, QLockFile, QStandardPaths, QUrl
    from PySide6.QtGui import QDesktopServices, QPixmap, QPixmapCache
    if production:
        from qt_diagnostics import install_qt_message_logging
        install_qt_message_logging()
    if QApplication.instance() is None:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    QPixmapCache.setCacheLimit(16384)
    install_field_wheel_guard(app)
    app.setApplicationName('FolderForge' if production else 'FolderForge Qt-prototyp')
    app.setQuitOnLastWindowClosed(False)
    # Prototype-only lock in OS temp; never opens or changes production's lock/data.
    key = hashlib.sha256(str(ROOT).encode()).hexdigest()[:16]
    if production:
        from instance_lock import SingleInstanceLock
        from settings import APP_NAME
        lock = SingleInstanceLock(APP_NAME)
        acquired = lock.acquire()
        if not acquired:
            from updater import recover_unresponsive_instance
            acquired = recover_unresponsive_instance(lock, ROOT / 'folder.pyw')
    else:
        lock = QLockFile(str(Path(QStandardPaths.writableLocation(QStandardPaths.TempLocation)) /
                             ('folderforge-qt-preview-' + key + '.lock')))
        acquired = lock.tryLock(0)
    if not acquired:
        return 0
    release = lock.release if production else lock.unlock
    if production:
        from qt_diagnostics import save_startup_report
        from updater import apply_pending, launch_update_trial, mark_installation_failed, service_instance_health
        save_startup_report(ROOT, 'starting')
        try:
            service_instance_health(lock.lock_dir, ROOT / 'folder.pyw')
        except Exception:
            logging.getLogger('startup.qt').warning('Hälsosignalen kunde inte initieras', exc_info=True)
        try:
            updated = apply_pending(ROOT)
        except Exception as exc:
            logging.getLogger('qt.update').exception('Kunde inte installera uppdatering; aktuell app används')
            mark_installation_failed(ROOT, exc)
            updated = False
        if updated:
            release()
            launch_update_trial(ROOT, sys.executable)
            return 0
    tray_ready = QSystemTrayIcon.isSystemTrayAvailable()
    if not tray_ready and sys.platform == 'win32':
        for _ in range(20):
            app.processEvents()
            time.sleep(0.25)
            if QSystemTrayIcon.isSystemTrayAvailable():
                tray_ready = True
                break
    if not tray_ready:
        tray_msg = 'FolderForge kräver ett tillgängligt systemfält. Se logs/ och reservstarten Starta-FolderForge-Tk.py.'
        logging.getLogger('startup.qt').error(tray_msg)
        if production:
            save_startup_report(ROOT, 'tray-unavailable', tray_msg)
        if os.name == 'nt' and os.environ.get('FOLDERFORGE_QT_SMOKE') != '1':
            ctypes.windll.user32.MessageBoxW(None, tray_msg, 'FolderForge – systemfält saknas', 0x10)
        elif sys.stderr is not None:
            print(tray_msg, file=sys.stderr)
        release()
        return 1
    try:
        window = window_factory(lock) if window_factory else PreviewWindow()
    except Exception:
        release()
        raise
    if sys.platform == 'win32' and (ROOT / 'Icon/projektmapp.ico').is_file():
        win_icon = QIcon(str(ROOT / 'Icon/projektmapp.ico'))
        if not win_icon.isNull():
            window.setWindowIcon(win_icon)
            app.setWindowIcon(win_icon)
    else:
        app.setWindowIcon(window.windowIcon())
    tray_icon = QIcon()
    if sys.platform == 'win32' and (ROOT / 'Icon/projektmapp.ico').is_file():
        tray_icon = QIcon(str(ROOT / 'Icon/projektmapp.ico'))
    tray_png = QPixmap(str(ROOT / 'Icon/folderforge-tray.png'))
    if not tray_png.isNull():
        for px in (16, 20, 24, 32, 48, 64):
            tray_icon.addPixmap(tray_png.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    try:
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer
        svg_symbol = ROOT / 'Icon/folderforge-symbol.svg'
        if svg_symbol.is_file():
            renderer = QSvgRenderer(str(svg_symbol))
            if renderer.isValid():
                for px in (24, 32, 40, 48, 64, 96, 128):
                    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
                    img.fill(Qt.transparent)
                    painter = QPainter(img)
                    painter.setRenderHint(QPainter.Antialiasing, True)
                    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                    renderer.render(painter)
                    painter.end()
                    tray_icon.addPixmap(QPixmap.fromImage(img))
    except Exception:
        pass
    if tray_icon.isNull():
        tray_icon = window.windowIcon()
    tray = QSystemTrayIcon(tray_icon, window)
    tray.setToolTip('FolderForge' if production else 'FolderForge · Qt-prototyp (testläge)')
    menu = QMenu()
    menu.addAction('Öppna FolderForge' if production else 'Öppna Qt-prototypen', window.restore)
    if production:
        menu.addAction('Öppna appens mapp', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT))))
        menu.addAction('Sök uppdatering nu', window.check_updates)
        menu.addAction('Uppdateringsstatus', window.update_status)
    menu.addAction(window.exit_action)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: window.restore()
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
    window.tray = tray
    tray.show()
    # Remains hidden until an explicit tray action. Never starts Tk in this process.
    stop = None
    cleanup = None
    if production:
        from updater import start_updates
        from settings import APP_VERSION
        def poll_instance():
            service_instance_health(lock.lock_dir, ROOT / 'folder.pyw')
            if lock.check_trigger():
                window.restore()
        lock_watcher = None
        try:
            lock_watcher = QFileSystemWatcher([str(lock.lock_dir)], window)
            lock_watcher.directoryChanged.connect(lambda _path: poll_instance())
        except Exception:
            lock_watcher = None
        smoke_mode = os.environ.get('FOLDERFORGE_QT_SMOKE') == '1'
        health = QTimer(window)
        health.setTimerType(Qt.CoarseTimer)
        health.timeout.connect(poll_instance)
        health.start(500 if smoke_mode else (15000 if lock_watcher is not None else 2000))
        if smoke_mode:
            import threading
            stop = threading.Event()
        else:
            stop = start_updates(ROOT, APP_VERSION)
        from cache_cleanup import start_cleanup
        cleanup = start_cleanup(ROOT)
        from updater import confirm_startup, pending_ready_for_restart
        log = logging.getLogger('qt.update')
        attempts = [0]
        def acknowledge():
            try:
                if not tray.isVisible():
                    attempts[0] += 1
                    tray.show()
                    if attempts[0] < 6 and not tray.isVisible():
                        QTimer.singleShot(500, acknowledge)
                        return
                    if not tray.isVisible():
                        raise RuntimeError('Tray-ikonen är inte redo')
                confirm_startup(ROOT)
                try:
                    from logg import resolve_matching_errors
                    resolve_matching_errors(modules=('qt.update', 'updater'))
                except Exception:
                    pass
                save_startup_report(ROOT, 'ready')
                log.info('FolderForge redo i systemfältet (pid=%d)', os.getpid())
            except Exception as exc:
                log.exception('Startbekräftelse misslyckades; backup behålls')
                save_startup_report(ROOT, 'confirmation-failed', str(exc))
        QTimer.singleShot(500, acknowledge)
        restart_timer = QTimer(window)
        restart_timer.setTimerType(Qt.CoarseTimer)
        def restart_if_safe():
            if hasattr(window, 'can_restart') and window.can_restart() and pending_ready_for_restart(ROOT):
                log.info('Uppdatering klar; säker dold Qt-omstart begärd')
                app.exit(71)
        restart_timer.timeout.connect(restart_if_safe)
        restart_timer.start(2000)
        if os.environ.get('FOLDERFORGE_QT_SMOKE') == '1':
            import json
            from historik import atomic_write_json
            status_path = ROOT / 'data/qt-smoke-status.json'
            command_path = ROOT / 'data/qt-smoke-command.json'
            last_command = [None]
            def smoke_tick():
                try:
                    command = json.loads(command_path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    command = {}
                if command.get('pid') == os.getpid() and command.get('id') != last_command[0]:
                    last_command[0] = command.get('id')
                    action = command.get('action')
                    if action == 'restore': window.restore()
                    elif action == 'project-dialog': window.open_project()
                    elif action == 'close-project-dialog' and window.dialog: window.dialog.reject()
                    elif action == 'close-main': window.close()
                    elif action == 'minimize-main': window.showMinimized()
                    elif action == 'exit': app.quit()
                dialog = getattr(window, 'dialog', None)
                atomic_write_json(status_path, dict(pid=os.getpid(), visible=window.isVisible(),
                    tray=tray.isVisible(), gui='qt', tk_loaded='tkinter' in sys.modules,
                    dialog=bool(dialog and dialog.isVisible()),
                    project_focused=bool(dialog and dialog.isVisible() and app.focusWidget() is dialog.name)), backup=False)
            smoke_timer = QTimer(window)
            smoke_timer.timeout.connect(smoke_tick)
            smoke_timer.start(100)
    result = 1
    try:
        result = app.exec()
    finally:
        if stop is not None:
            stop.set()
        if cleanup is not None:
            cleanup.set()
        tray.hide()
        release()
    if production and result == 71:
        import subprocess
        exe = Path(sys.executable)
        if os.name == 'nt' and exe.with_name('pythonw.exe').is_file():
            exe = exe.with_name('pythonw.exe')
        subprocess.Popen([str(exe), str(ROOT / 'folder.pyw'), '--tray'], cwd=ROOT,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)
        return 0
    return result
