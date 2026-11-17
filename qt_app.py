"""Opt-in functional Qt client. Tk remains the default and full-feature fallback."""
from pathlib import Path
import threading
import webbrowser

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget)

from app_core import (build_project_name, ExistingProject, StructureEngine, project_year_choices, validate_project_year)
from qt_preview import PreviewWindow, fit_to_screen
from settings import APP_VERSION, BASE_DIR, LOKAL_CHOICES, VEHICLE_CHOICES
from workspace import Workspace


def label(text):
    result = QLabel(text)
    result.setWordWrap(True)
    result.setTextFormat(Qt.PlainText)
    return result


def button(layout, text, callback):
    result = QPushButton(text)
    result.clicked.connect(callback)
    layout.addWidget(result)
    return result


def page(tabs, title):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    widget = QWidget()
    layout = QVBoxLayout(widget)
    scroll.setWidget(widget)
    tabs.addTab(scroll, title)
    return layout


class ProjectDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle('Skapa standardprojekt – Qt')
        self.setModal(True)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QVBoxLayout(content)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.name = QLineEdit()
        self.name.setAccessibleName('Projektnamn')
        self.location = QComboBox()
        self.location.addItems(['—'] + list(LOKAL_CHOICES))
        self.year = QComboBox()
        self.year.setEditable(True)
        self.year.addItems(['—'] + project_year_choices())
        self.vehicle = QComboBox()
        self.vehicle.addItems(['—'] + list(VEHICLE_CHOICES))
        self.template = QComboBox()
        self.template.addItems(list(window.workspace.templates.list_templates()))
        self.template.setCurrentText(window.workspace.config.default_template)
        for title, widget in (('&Projektnamn', self.name), ('&Fordon', self.vehicle),
                              ('&Lokal', self.location), ('&År', self.year), ('&Mall', self.template)):
            form.addRow(title, widget)
        body.addLayout(form)
        body.addWidget(label('Tillfällig egen struktur (frivilligt, ändrar inte dina sparade mallar):'))
        self.custom = QPlainTextEdit()
        self.custom.setPlaceholderText('Lämna tomt för vald mall, eller klistra in ett indraget mappträd.')
        self.custom.setMaximumHeight(130)
        body.addWidget(self.custom)
        self.preview = label('')
        body.addWidget(self.preview)
        self.error = label('')
        body.addWidget(self.error)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        actions = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.create_button = actions.button(QDialogButtonBox.Save)
        self.create_button.setText('Skapa projekt…')
        actions.accepted.connect(self.create)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)
        self.name.textChanged.connect(self.refresh)
        for widget in (self.location, self.year, self.vehicle, self.template):
            widget.currentTextChanged.connect(self.refresh)
        self.custom.textChanged.connect(self.refresh)
        self.refresh()

    def prepare(self):
        year = validate_project_year(self.year.currentText())
        if not self.name.text().strip():
            raise ValueError('Ange ett projektnamn')
        name = build_project_name(self.name.text(), self.location.currentText(), year,
                                 '' if self.vehicle.currentText() == '—' else self.vehicle.currentText())
        return self.window.workspace.prepare_project(name, self.template.currentText(),
            self.custom.toPlainText() if self.custom.toPlainText().strip() else None)

    def refresh(self):
        try:
            name, items = self.prepare()
            folders, files = StructureEngine.count_items(items)
            self.preview.setText(f'Slutnamn: {name}\n{folders} mappar, {files} filer')
            self.error.clear()
            self.create_button.setEnabled(True)
        except (ValueError, OSError) as exc:
            self.preview.clear()
            self.error.setText(str(exc))
            self.create_button.setEnabled(False)

    def create(self):
        try:
            name, items = self.prepare()
            path = Path(self.window.workspace.config.save_root) / name
            if QMessageBox.question(self, 'Bekräfta skapande',
                    f'Skapa projektet här?\n{path}\n\n{len(items)} strukturposter.',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            path = self.window.workspace.create_project(name, items)
            self.window.statusBar().showMessage(f'Skapad: {path}')
            self.window.refresh_history()
            if self.window.workspace.config.open_after_creation:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            self.name.setFocus()
            self.name.selectAll()
        except ExistingProject as exc:
            if QMessageBox.question(self, 'Projektet finns redan',
                    f'Ingenting har slagits ihop eller skrivits över.\nÖppna {exc.path}?',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(exc.path)))
        except (ValueError, OSError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Projektet kunde inte skapas', str(exc))

    def showEvent(self, event):
        super().showEvent(event)
        fit_to_screen(self, 640, 680)
        QTimer.singleShot(0, self.focus_name)

    def focus_name(self):
        self.name.setFocus()
        self.name.selectAll()


class QtWindow(PreviewWindow):
    def __init__(self, workspace):
        super().__init__()
        self.workspace = workspace
        self.setWindowTitle(f'FolderForge {APP_VERSION} · Qt – under övergång')
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        create = page(self.tabs, 'Skapa')
        create.addWidget(label('FolderForge · Qt\nRiktiga projekt och gemensamma data. '
                              'Tk är fortfarande standard och har alla äldre funktioner.'))
        button(create, 'Skapa standardprojekt', self.open_project)
        create.addWidget(label('Sparplats: ' + workspace.config.save_root))
        create.addStretch()
        history = page(self.tabs, 'Historik')
        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self.open_history)
        history.addWidget(self.history_list)
        button(history, 'Öppna markerad mapp', lambda: self.open_history(self.history_list.currentItem()))
        button(history, 'Uppdatera listan', self.refresh_history)
        self.template_page()
        self.export_page()
        self.settings_page()
        self.menuBar().clear()
        help_menu = self.menuBar().addMenu('Hjälp')
        self.exit_action.setText('Avsluta FolderForge Qt')
        help_menu.addAction(self.exit_action)
        help_menu.addAction('Donationer – Stöd FolderForge', self.donations)
        help_menu.addAction('Uppdateringsstatus', self.update_status)
        help_menu.addAction('Sök uppdatering nu', self.check_updates)
        help_menu.addAction('Om övergången / funktioner kvar i Tk', lambda: QMessageBox.information(self,
            'Övergång till Qt', 'Tk är kvar som standard och reserv.\n'
            'Ångra/radering, global snabbtangent, OS-autostart, detaljerad fellista, '
            'diagnostikexport och komplett tillgänglighets-/DPI-paritet är ännu inte migrerade.\n'
            'Qt installerar inte uppdateringar själv; avsluta och använd vanliga startfilen.'))
        self.refresh_history()

    def open_project(self):
        if self.dialog and self.dialog.isVisible():
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        self.dialog = ProjectDialog(self)
        self.dialog.show()

    def refresh_history(self):
        self.history_list.clear()
        for entry in self.workspace.history.get_all():
            self.history_list.addItem(entry['path'])

    def open_history(self, item):
        if item:
            QDesktopServices.openUrl(QUrl.fromLocalFile(item.text()))

    def template_page(self):
        layout = page(self.tabs, 'Mallar')
        self.templates = QComboBox()
        self.templates.addItems(list(self.workspace.templates.list_templates()))
        self.template_name = QLineEdit()
        self.template_name.setPlaceholderText('Mallnamn (nytt namn skapar en egen mall)')
        self.structure = QPlainTextEdit()
        layout.addWidget(self.templates)
        layout.addWidget(self.template_name)
        layout.addWidget(self.structure)
        def load(name):
            self.template_name.setText(name)
            self.structure.setPlainText(self.workspace.templates.list_templates().get(name, ''))
        self.templates.currentTextChanged.connect(load)
        def save():
            try:
                self.workspace.require_lock()
                self.workspace.templates.save_template(self.template_name.text(), self.structure.toPlainText())
                self.templates.clear()
                self.templates.addItems(list(self.workspace.templates.list_templates()))
                self.statusBar().showMessage('Mall sparad')
            except (OSError, ValueError, RuntimeError) as exc:
                QMessageBox.warning(self, 'Kunde inte spara mall', str(exc))
        button(layout, 'Spara som egen mall', save)
        def set_default():
            self.workspace.config.default_template = self.templates.currentText()
            self.save_settings()
        button(layout, 'Använd vald mall som standard', set_default)
        load(self.templates.currentText())

    def export_page(self):
        layout = page(self.tabs, 'Exportera')
        layout.addWidget(label('Välj en mapp för säker trälexport. Resultatet kan kopieras eller sparas.'))
        self.export_text = QPlainTextEdit()
        self.export_text.setReadOnly(True)
        def choose():
            folder = QFileDialog.getExistingDirectory(self, 'Välj mapp')
            if folder:
                # Bounded traversal uses the exact shared Tk engine.
                self.export_text.setPlainText(StructureEngine.generate_tree_string(Path(folder)))
        button(layout, 'Välj mapp', choose)
        layout.addWidget(self.export_text)
        def save():
            path, _ = QFileDialog.getSaveFileName(self, 'Spara struktur', 'struktur.txt', 'Text (*.txt)')
            if path:
                try:
                    Path(path).write_text(self.export_text.toPlainText(), encoding='utf-8')
                except OSError as exc:
                    QMessageBox.warning(self, 'Kunde inte exportera', str(exc))
        button(layout, 'Spara text…', save)

    def settings_page(self):
        layout = page(self.tabs, 'Inställningar')
        layout.addWidget(label('Samma sparplats och inställningsformat som Tk. Ändringar sparas först med Spara.'))
        self.root_edit = QLineEdit(self.workspace.config.save_root)
        layout.addWidget(self.root_edit)
        def choose():
            path = QFileDialog.getExistingDirectory(self, 'Sparplats', self.root_edit.text())
            if path:
                self.root_edit.setText(path)
        button(layout, 'Välj sparplats…', choose)
        self.open_after = QCheckBox('Öppna mappen efter skapande')
        self.open_after.setChecked(self.workspace.config.open_after_creation)
        self.plate_mode = QCheckBox('Normalisera registreringsnummer')
        self.plate_mode.setChecked(self.workspace.config.plate_mode)
        layout.addWidget(self.open_after)
        layout.addWidget(self.plate_mode)
        def save():
            if not self.root_edit.text().strip():
                QMessageBox.warning(self, 'Sparplats', 'Välj en sparplats först.')
                return
            self.workspace.config.save_root = self.root_edit.text().strip()
            self.workspace.config.open_after_creation = self.open_after.isChecked()
            self.workspace.config.plate_mode = self.plate_mode.isChecked()
            self.save_settings()
        button(layout, 'Spara inställningar', save)
        layout.addStretch()

    def save_settings(self):
        try:
            self.workspace.save_settings()
            self.statusBar().showMessage('Inställningar sparade')
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Skrivfel', str(exc))

    def donations(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Donationer – Stöd FolderForge')
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('Gillar du FolderForge?\n\nHar appen gjort din vardag enklare? '
            'En frivillig gåva visar uppskattning och uppmuntrar fortsatt utveckling. '
            'Du väljer själv belopp. Alla funktioner fungerar lika bra utan donation.\n'
            'Tack för att du använder FolderForge!\n– Rickard Längkvist'))
        qr = QLabel()
        qr.setAlignment(Qt.AlignCenter)
        qr.setPixmap(QPixmap(str(BASE_DIR / 'Icon/swish-folderforge.png')).scaled(
            240, 240, Qt.KeepAspectRatio, Qt.FastTransformation))
        layout.addWidget(qr)
        layout.addWidget(label('Swish 0721817177 · välj belopp i Swish. Kontrollera mottagaren innan betalning.'))
        button(layout, 'PayPal', lambda: webbrowser.open('https://paypal.me/Rickard3dPrint', new=2))
        button(layout, 'Ko-fi', lambda: webbrowser.open('https://ko-fi.com/tokke2', new=2))
        button(layout, 'Stäng', dialog.reject)
        fit_to_screen(dialog, 560, 650)
        dialog.exec()

    def update_status(self):
        from updater import get_update_status
        dialog = QDialog(self)
        dialog.setWindowTitle('Uppdateringsstatus – Qt')
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        layout.addWidget(text)
        def refresh():
            text.setPlainText('\n\n'.join(f'{key}: {value}' for key, value in get_update_status(BASE_DIR, APP_VERSION).items()))
        timer = QTimer(dialog)
        timer.timeout.connect(refresh)
        timer.start(1000)
        refresh()
        layout.addWidget(label('Installation görs genom den vanliga Tk-startfilen efter att Qt har avslutats.'))
        button(layout, 'Sök uppdatering nu', self.check_updates)
        button(layout, 'Stäng', dialog.reject)
        fit_to_screen(dialog, 620, 600)
        dialog.exec()

    def check_updates(self):
        from updater import check_once
        threading.Thread(target=check_once, args=(BASE_DIR, APP_VERSION),
                         kwargs={'force': True}, daemon=True, name='qt-release-check').start()
        self.statusBar().showMessage('Uppdateringskontroll begärd – se uppdateringsstatus')


def run():
    from qt_preview import run as run_host
    return run_host(window_factory=lambda lock: QtWindow(Workspace(lock)), production=True)
