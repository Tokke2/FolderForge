"""Opt-in, read-only Qt UI experiment. Never imports Tk or production storage.

No project creation, settings/history writes, updater, autostart or global hooks.
Qt types are imported only when this optional module is explicitly selected.
"""
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSystemTrayIcon, QVBoxLayout, QWidget)

ROOT = Path(__file__).resolve().parent


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
        self.setWindowIcon(QIcon(str(ROOT / 'Icon/projektmapp_icon_256.png')))
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


def run():
    import hashlib
    import sys
    from PySide6.QtCore import QLockFile, QStandardPaths
    app = QApplication(sys.argv)
    app.setApplicationName('FolderForge Qt-prototyp')
    app.setQuitOnLastWindowClosed(False)
    # Prototype-only lock in OS temp; never opens or changes production's lock/data.
    key = hashlib.sha256(str(ROOT).encode()).hexdigest()[:16]
    lock = QLockFile(str(Path(QStandardPaths.writableLocation(QStandardPaths.TempLocation)) /
                         ('folderforge-qt-preview-' + key + '.lock')))
    if not lock.tryLock(0):
        return 0
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print('Qt-prototypen kräver ett tillgängligt systemfält. Använd vanliga Tk-startfilen.', file=sys.stderr)
        return 1
    window = PreviewWindow()
    tray = QSystemTrayIcon(window.windowIcon(), window)
    tray.setToolTip('FolderForge · Qt-prototyp (testläge)')
    menu = QMenu()
    menu.addAction('Öppna Qt-prototypen', window.restore)
    menu.addAction(window.exit_action)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: window.restore() if reason == QSystemTrayIcon.Trigger else None)
    window.tray = tray
    tray.show()
    # Remains hidden until an explicit tray action. Never starts Tk in this process.
    result = app.exec()
    tray.hide()
    lock.unlock()
    return result
