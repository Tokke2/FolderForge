"""Opt-in functional Qt client. Tk remains the default and full-feature fallback."""
from pathlib import Path
import threading
import logging
import webbrowser

from PySide6.QtCore import QObject, Signal, QRect, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QStackedWidget, QSizePolicy,
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


class ResponsiveTabs(QWidget):
    """All page names remain visible; navigation wraps rather than scrolling away."""
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.header = QGridLayout()
        layout.addLayout(self.header)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.buttons = []
        self.columns = 0

    def addTab(self, widget, title):
        index = self.stack.addWidget(widget)
        control = QPushButton(title)
        control.setCheckable(True)
        control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        control.clicked.connect(lambda checked=False, n=index: self.setCurrentIndex(n))
        self.buttons.append(control)
        self.reflow(force=True)
        self.setCurrentIndex(self.stack.currentIndex())
        return index

    def count(self):
        return self.stack.count()

    def currentIndex(self):
        return self.stack.currentIndex()

    def setCurrentIndex(self, index):
        self.stack.setCurrentIndex(index)
        for n, control in enumerate(self.buttons):
            control.setChecked(n == index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self, force=False):
        needed = max((b.fontMetrics().horizontalAdvance(b.text()) + 48 for b in self.buttons), default=180)
        columns = max(1, min(len(self.buttons), max(1, self.width() - 24) // needed))
        if not force and columns == self.columns:
            return
        while self.header.count():
            self.header.takeAt(0)
        for col in range(max(self.columns, columns)):
            self.header.setColumnStretch(col, 1 if col < columns else 0)
        for index, control in enumerate(self.buttons):
            self.header.addWidget(control, index // columns, index % columns)
        self.columns = columns


class ExportBridge(QObject):
    ready = Signal(str)
    failed = Signal(str)


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
            stat = path.stat()
            self.window._created.append((path, stat.st_dev, stat.st_ino))
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
            logging.getLogger('qt.projects').exception('Projektet kunde inte skapas')
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
        self._hotkeys = None
        self._busy_tasks = 0
        self._export_bridge = ExportBridge(self)
        self._export_bridge.ready.connect(self.export_ready)
        self._export_bridge.failed.connect(self.export_failed)
        self.setWindowTitle(f'FolderForge {APP_VERSION} · Qt')
        self.tabs = ResponsiveTabs()
        self.setCentralWidget(self.tabs)
        create = page(self.tabs, 'Skapa')
        create.addWidget(label('FolderForge · Qt\nSkapa projektmappar med dina mallar.'))
        button(create, 'Sök uppdatering nu', self.check_updates)
        self._created = []
        button(create, 'Ångra senast skapade projekt…', self.undo_last)
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
        help_menu.addAction('Felsökning och fellista…', self.diagnostics)
        help_menu.addAction('Detaljerad loggning i 15 minuter', self.enable_debug)
        help_menu.addAction('Om FolderForge', lambda: QMessageBox.information(self, 'FolderForge',
            f'FolderForge {APP_VERSION} · Qt\n© Rickard Längkvist\n'
            'Explicit Tk-reserv finns via Starta-FolderForge-Tk.py.'))
        self.setAcceptDrops(True)
        self.refresh_history()
        self.apply_accessibility()
        self._placement_timer = QTimer(self)
        self._placement_timer.setSingleShot(True)
        self._placement_timer.timeout.connect(self.save_placement)
        QApplication.instance().aboutToQuit.connect(self.save_placement)

    def restore(self):
        from historik import read_json_safe
        raw = read_json_safe(self.workspace.base / 'data/qt-window-placement.json', {})
        rectangle = None
        if isinstance(raw, dict) and all(isinstance(raw.get(k), int) and not isinstance(raw[k], bool) for k in ('x', 'y', 'width', 'height')):
            if raw['width'] > 0 and raw['height'] > 0:
                rectangle = QRect(raw['x'], raw['y'], raw['width'], raw['height'])
        screens = QApplication.screens()
        screen = self.screen() or QApplication.primaryScreen()
        if rectangle is not None:
            best = max(screens, key=lambda item: item.availableGeometry().intersected(rectangle).width()
                       * item.availableGeometry().intersected(rectangle).height(), default=screen)
            if best.availableGeometry().intersects(rectangle):
                screen = best
        area = screen.availableGeometry().adjusted(12, 12, -12, -12)
        if rectangle is None:
            rectangle = QRect(0, 0, min(760, area.width()), min(560, area.height()))
            rectangle.moveCenter(area.center())
        width = min(max(300, rectangle.width()), area.width())
        height = min(max(250, rectangle.height()), area.height())
        x = max(area.left(), min(rectangle.x(), area.right() - width + 1))
        y = max(area.top(), min(rectangle.y(), area.bottom() - height + 1))
        self.setGeometry(x, y, width, height)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.tabs.reflow(force=True)

    def save_placement(self):
        if not self.workspace.lock.is_primary or not self.isVisible() or self.isMinimized() or self.isMaximized():
            return
        from historik import atomic_write_json
        rect = self.geometry()
        atomic_write_json(self.workspace.base / 'data/qt-window-placement.json',
                          dict(x=rect.x(), y=rect.y(), width=rect.width(), height=rect.height()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_placement_timer'):
            self._placement_timer.start(500)

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, '_placement_timer'):
            self._placement_timer.start(500)

    def closeEvent(self, event):
        self.save_placement()
        super().closeEvent(event)

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
                self.structure.document().setModified(False)
                self.statusBar().showMessage('Mall sparad')
            except (OSError, ValueError, RuntimeError) as exc:
                logging.getLogger('qt.templates').exception('Mall kunde inte sparas')
                QMessageBox.warning(self, 'Kunde inte spara mall', str(exc))
        button(layout, 'Spara som egen mall', save)
        def set_default():
            self.workspace.config.default_template = self.templates.currentText()
            self.save_settings()
        button(layout, 'Använd vald mall som standard', set_default)
        def remove():
            if QMessageBox.question(self, 'Ta bort egen mall?', self.templates.currentText(),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            try:
                if not self.workspace.templates.delete_template(self.templates.currentText()):
                    raise ValueError('Inbyggda mallar kan inte tas bort')
                self.templates.clear()
                self.templates.addItems(list(self.workspace.templates.list_templates()))
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Kunde inte ta bort mall', str(exc))
        button(layout, 'Ta bort vald egen mall…', remove)
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
                self.start_export(Path(folder))
        button(layout, 'Välj mapp', choose)
        layout.addWidget(self.export_text)
        def save():
            path, _ = QFileDialog.getSaveFileName(self, 'Spara struktur', 'struktur.txt', 'Text (*.txt)')
            if path:
                try:
                    Path(path).write_text(self.export_text.toPlainText(), encoding='utf-8')
                except OSError as exc:
                    logging.getLogger('qt.export').exception('Textfilen kunde inte sparas')
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
        self.theme = QComboBox()
        self.theme.addItems(['Dark', 'Light', 'System'])
        self.theme.setCurrentText(self.workspace.config.theme)
        self.text_size = QComboBox()
        self.text_size.addItems(['100%', '110%', '125%', '150%'])
        self.text_size.setCurrentText(self.workspace.config.text_size)
        self.high_contrast = QCheckBox('Hög kontrast')
        self.high_contrast.setChecked(self.workspace.config.high_contrast)
        layout.addWidget(label('Tema'))
        layout.addWidget(self.theme)
        layout.addWidget(label('Textstorlek'))
        layout.addWidget(self.text_size)
        layout.addWidget(self.high_contrast)
        def save():
            if not self.root_edit.text().strip():
                QMessageBox.warning(self, 'Sparplats', 'Välj en sparplats först.')
                return
            self.workspace.config.save_root = self.root_edit.text().strip()
            self.workspace.config.open_after_creation = self.open_after.isChecked()
            self.workspace.config.plate_mode = self.plate_mode.isChecked()
            self.workspace.config.theme = self.theme.currentText()
            self.workspace.config.text_size = self.text_size.currentText()
            self.workspace.config.high_contrast = self.high_contrast.isChecked()
            self.save_settings()
        button(layout, 'Spara inställningar', save)
        def startup(enabled):
            if QMessageBox.question(self, 'Ändra autostart?',
                    ('Aktivera' if enabled else 'Avaktivera') + ' FolderForge vid inloggning?\n'
                    'Följ arbetsgivarens IT-policy. Inga paket installeras.',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            try:
                from os_startup import configure_autostart
                import json
                result = configure_autostart(enabled)
                details = json.dumps(result, ensure_ascii=False, indent=2)
                if not result.get('ok'):
                    raise RuntimeError(details)
                QMessageBox.information(self, 'Autostart', details)
            except Exception as exc:
                import logging
                logging.getLogger('qt.autostart').exception('Ändring av autostart misslyckades')
                QMessageBox.warning(self, 'Autostart misslyckades', str(exc))
        button(layout, 'Starta med operativsystemet…', lambda: startup(True))
        button(layout, 'Stäng av autostart…', lambda: startup(False))
        layout.addWidget(label('Global snabbtangent, till exempel ctrl+alt+m'))
        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText('ctrl+alt+m')
        def save_hotkey():
            try:
                if self._hotkeys is None:
                    raise RuntimeError('Snabbtangentsbryggan är inte startad')
                self._hotkeys.register(self.hotkey_edit.text().split('+'), save=True)
                self.hotkey_edit.setModified(False)
                self.statusBar().showMessage(self._hotkeys.last_status)
            except Exception as exc:
                import logging
                logging.getLogger('qt.hotkey').exception('Kunde inte ändra snabbtangent')
                QMessageBox.warning(self, 'Snabbtangent', str(exc))
        layout.addWidget(self.hotkey_edit)
        button(layout, 'Spara snabbtangent', save_hotkey)
        layout.addStretch()

    def apply_accessibility(self):
        config = self.workspace.config
        factor = int(config.text_size.rstrip('%')) / 100
        dark = config.theme == 'Dark'
        if config.theme == 'System':
            dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        if config.high_contrast:
            background, foreground, field, accent, focus = '#000000', '#FFFFFF', '#000000', '#164B73', '#FFFF00'
        elif dark:
            background, foreground, field, accent, focus = '#101C2C', '#EDF4FA', '#203249', '#215C95', '#FFCE66'
        else:
            background, foreground, field, accent, focus = '#F4F7FB', '#172B42', '#FFFFFF', '#155A94', '#005FCC'
        self.setStyleSheet(f"""
            QWidget {{ background: {background}; color: {foreground}; font-size: {round(15 * factor)}px; }}
            QPushButton {{ background: {accent}; color: white; padding: 12px; border: 2px solid transparent; border-radius: 7px; }}
            QPushButton:checked {{ background: #316FA5; color: white; }}
            QPushButton:focus, QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 2px solid {focus}; }}
            QLineEdit, QComboBox, QPlainTextEdit, QListWidget {{ background: {field}; padding: 6px; border: 2px solid #708090; }}
            QTabBar::tab {{ padding: 10px; }}
            QTabBar::tab:selected, QMenu::item:selected {{ background: {accent}; color: white; }}
        """)
        QTimer.singleShot(0, lambda: self.tabs.reflow(force=True))

    def save_settings(self):
        try:
            self.workspace.save_settings()
            self.apply_accessibility()
            self.statusBar().showMessage('Inställningar sparade')
        except (OSError, RuntimeError) as exc:
            logging.getLogger('qt.settings').exception('Inställningar kunde inte sparas')
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
        layout.addWidget(label('Hämtad uppdatering installeras genom dold omstart när öppna dialoger och osparade ändringar är avslutade.'))
        button(layout, 'Sök uppdatering nu', self.check_updates)
        button(layout, 'Stäng', dialog.reject)
        fit_to_screen(dialog, 620, 600)
        dialog.exec()

    def check_updates(self):
        from updater import check_once
        threading.Thread(target=check_once, args=(BASE_DIR, APP_VERSION),
                         kwargs={'force': True}, daemon=True, name='qt-release-check').start()
        self.statusBar().showMessage('Uppdateringskontroll begärd – se uppdateringsstatus')


    def start_export(self, folder):
        if self._busy_tasks:
            self.statusBar().showMessage('En export pågår redan. Vänta tills den är klar.')
            return
        self._busy_tasks += 1
        self.statusBar().showMessage('Läser mappstruktur i bakgrunden…')
        def worker():
            try:
                self._export_bridge.ready.emit(StructureEngine.generate_tree_string(folder))
            except Exception as exc:
                logging.getLogger('qt.export').exception('Trälexport misslyckades')
                self._export_bridge.failed.emit(str(exc))
        threading.Thread(target=worker, name='qt-tree-export', daemon=True).start()

    def export_ready(self, text):
        self._busy_tasks = max(0, self._busy_tasks - 1)
        self.export_text.setPlainText(text)
        self.statusBar().showMessage('Struktur klar – du kan spara texten')

    def export_failed(self, message):
        self._busy_tasks = max(0, self._busy_tasks - 1)
        QMessageBox.warning(self, 'Export misslyckades', message)

    def can_restart(self):
        if any(isinstance(widget, QDialog) and widget.isVisible() for widget in QApplication.topLevelWidgets()):
            return False
        config = self.workspace.config
        return (self._busy_tasks == 0 and not self.structure.document().isModified()
                and self.root_edit.text().strip() == config.save_root
                and self.open_after.isChecked() == config.open_after_creation
                and self.plate_mode.isChecked() == config.plate_mode
                and self.theme.currentText() == config.theme
                and self.text_size.currentText() == config.text_size
                and self.high_contrast.isChecked() == config.high_contrast
                and (self._hotkeys is None or not self.hotkey_edit.isModified()))

    def start_integrations(self):
        from qt_integrations import HotkeyBridge
        self._hotkeys = HotkeyBridge(self)
        self._hotkeys.status.connect(self.statusBar().showMessage)
        self.hotkey_edit.setText('+'.join(self._hotkeys.keys))
        self.hotkey_edit.setModified(False)
        self._hotkeys.start()
        QApplication.instance().aboutToQuit.connect(self._hotkeys.stop)

    def diagnostics(self):
        from qt_help import DiagnosticsDialog
        dialog = DiagnosticsDialog(self)
        dialog.exec()

    def enable_debug(self):
        from logg import enable_detailed_logging
        enable_detailed_logging(15)
        self.statusBar().showMessage('Detaljerad loggning aktiv i 15 minuter')

    def undo_last(self):
        if not self._created:
            QMessageBox.information(self, 'Ångra', 'Inget projekt har skapats i denna session.')
            return
        path, device, inode = self._created[-1]
        try:
            stat = path.stat()
            if path.is_symlink() or (stat.st_dev, stat.st_ino) != (device, inode):
                raise ValueError('Mappen har ersatts eller flyttats; automatisk radering stoppas')
            if QMessageBox.warning(self, 'Ta bort hela projektet?',
                    f'{path}\n\nALLT innehåll, även filer du lagt till, tas bort permanent. Fortsätt?',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            import shutil
            shutil.rmtree(path)
            self._created.pop()
            self.workspace.history.remove(str(path))
            self.refresh_history()
        except (OSError, ValueError) as exc:
            logging.getLogger('qt.projects').exception('Ångra/radering stoppades')
            QMessageBox.warning(self, 'Ångra stoppades', str(exc))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        folders = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if folders and folders[0].is_dir():
            self.start_export(folders[0])
            self.tabs.setCurrentIndex(3)
            event.acceptProposedAction()


def run():
    from qt_preview import run as run_host

    def build(lock):
        from logg import init_logging, start_log_archiver
        import logg
        if not logg._initierad:
            init_logging()
        start_log_archiver()
        window = QtWindow(Workspace(lock))
        window.start_integrations()
        return window

    return run_host(window_factory=build, production=True)
