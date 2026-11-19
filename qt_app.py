"""Default Qt client with an explicit, separately launched Tk reserve."""
from pathlib import Path
import threading
import logging
import webbrowser

from PySide6.QtCore import QObject, Signal, QRect, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QPixmap, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QStackedWidget, QSizePolicy, QKeySequenceEdit,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QFrame,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget)

from app_core import (build_project_name, ExistingProject, StructureEngine, project_year_choices, validate_project_year)
from qt_preview import PreviewWindow, fit_to_screen, install_field_wheel_guard
from settings import (APP_VERSION, BASE_DIR, LOKAL_CHOICES, VEHICLE_CHOICES,
    UI_BACKGROUND, UI_SURFACE, UI_BORDER, UI_TEXT, UI_MUTED, UI_PRIMARY)
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
    scroll.setFrameShape(QFrame.NoFrame)
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(12)
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
        self.hidden_tabs = set()

    def addTab(self, widget, title):
        index = self.stack.addWidget(widget)
        control = QPushButton(title)
        icons = ['create', 'history', 'templates', 'export', 'settings', 'keyboard']
        control.setIcon(QIcon(str(BASE_DIR / ('Icon/nav-' + icons[index] + '-light.png'))))
        control.setObjectName('navigationTab')
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

    def setTabVisible(self, index, visible):
        if visible:
            self.hidden_tabs.discard(index)
        else:
            self.hidden_tabs.add(index)
        if len(self.hidden_tabs) == self.count():
            self.hidden_tabs.discard(0)
        if self.currentIndex() in self.hidden_tabs:
            self.setCurrentIndex(next(n for n in range(self.count()) if n not in self.hidden_tabs))
        self.reflow(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self, force=False):
        visible = [b for n, b in enumerate(self.buttons) if n not in self.hidden_tabs]
        needed = max((b.fontMetrics().horizontalAdvance(b.text()) + 48 for b in visible), default=180)
        columns = max(1, min(len(visible), max(1, self.width() - 24) // needed))
        if not force and columns == self.columns:
            return
        while self.header.count():
            self.header.takeAt(0)
        for col in range(max(self.columns, columns)):
            self.header.setColumnStretch(col, 1 if col < columns else 0)
        for index, control in enumerate(self.buttons):
            control.setVisible(index not in self.hidden_tabs)
        for index, control in enumerate(visible):
            self.header.addWidget(control, index // columns, index % columns)
        self.columns = columns


class ExportBridge(QObject):
    ready = Signal(str)
    failed = Signal(str)


class ProjectDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle('Skapa standardprojekt')
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
                              ('&Lokal', self.location), ('&År', self.year), ('&Profil / mall', self.template)):
            form.addRow(title, widget)
        body.addLayout(form)
        body.addWidget(label('Tillfällig egen struktur (frivilligt, ändrar inte dina sparade mallar):'))
        self.custom = QPlainTextEdit()
        self.custom.setPlaceholderText('Lämna tomt för vald mall, eller klistra in ett indraget mappträd.')
        self.custom.setMaximumHeight(130)
        body.addWidget(self.custom)
        def show_structure():
            dialog = QDialog(self)
            dialog.setWindowTitle('Mappstruktur för projektet')
            preview_layout = QVBoxLayout(dialog)
            text = QPlainTextEdit()
            text.setReadOnly(True)
            structure = self.custom.toPlainText() if self.custom.toPlainText().strip() else (
                self.window.workspace.templates.list_templates().get(self.template.currentText(), ''))
            text.setPlainText(structure)
            preview_layout.addWidget(text)
            button(preview_layout, 'Stäng', dialog.reject)
            fit_to_screen(dialog, 600, 550)
            dialog.exec()
        button(body, 'Visa vald mappstruktur', show_structure)
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
        body.addWidget(actions)
        body.addStretch()
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
            self.preview.setText(f'Slutnamn: {name}\n{folders} mappar, {files} filer\n'
                f'Sparas i: {self.window.workspace.profile_root(self.template.currentText()) / name}')
            self.error.clear()
            self.create_button.setEnabled(True)
        except (ValueError, OSError) as exc:
            self.preview.clear()
            self.error.setText(str(exc))
            self.create_button.setEnabled(False)

    def create(self):
        try:
            name, items = self.prepare()
            path = self.window.workspace.profile_root(self.template.currentText()) / name
            if QMessageBox.question(self, 'Bekräfta skapande',
                    f'Skapa projektet här?\n{path}\n\n{len(items)} strukturposter.',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            path = self.window.workspace.create_project(name, items, self.template.currentText())
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
        install_field_wheel_guard(QApplication.instance())
        self.workspace = workspace
        self._hotkeys = None
        self._busy_tasks = 0
        self._export_bridge = ExportBridge(self)
        self._export_bridge.ready.connect(self.export_ready)
        self._export_bridge.failed.connect(self.export_failed)
        self.setWindowTitle(f'FolderForge {APP_VERSION}')
        self.tabs = ResponsiveTabs()
        shell = QWidget()
        shell.setObjectName('appShell')
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(6)
        header = QFrame()
        header.setObjectName('appHeader')
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 10, 18, 10)
        logo = QLabel('FolderForge')
        logo.setObjectName('appLogo')
        image = QPixmap(str(BASE_DIR / 'Icon/folderforge-logo.png'))
        if not image.isNull():
            logo.setPixmap(image.scaled(220, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAccessibleName('FolderForge')
        header_layout.addWidget(logo)
        header_layout.addWidget(label('v' + APP_VERSION))
        header_layout.addStretch()
        self.theme_toggle = QPushButton('◐')
        self.theme_toggle.setAccessibleName('Växla ljust och mörkt tema')
        self.theme_toggle.setToolTip('Växla ljust och mörkt tema')
        self.theme_toggle.setFixedWidth(42)
        self.theme_toggle.setObjectName('secondaryAction')
        self.theme_toggle.clicked.connect(self.toggle_theme)
        header_layout.addWidget(self.theme_toggle)
        shell_layout.addWidget(header)
        update = QPushButton('Sök uppdatering nu')
        update.setObjectName('secondaryAction')
        update.clicked.connect(self.check_updates)
        shell_layout.addWidget(update)
        shell_layout.addWidget(self.tabs, 1)
        footer = QFrame()
        footer.setObjectName('appFooter')
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(12, 5, 12, 5)
        footer_layout.setSpacing(4)
        footer_layout.addWidget(label('© Rickard Längkvist · Drag & Drop aktiv'))
        minimize = button(footer_layout, 'Minimera till fältet', self.hide)
        minimize.setObjectName('secondaryAction')
        shell_layout.addWidget(footer)
        self.setCentralWidget(shell)
        create = page(self.tabs, 'Skapa')
        heading = label('Skapa ett projekt')
        heading.setObjectName('pageHeading')
        create.addWidget(heading)
        create.addWidget(label('En tydlig struktur. Redo på några sekunder.'))
        self._created = []
        for title, description, caption, callback in [
            ('Använd din standardmall', 'Skapa projekt med din sparade mappstruktur.',
             'Skapa standardprojekt', self.open_project),
            ('Egen struktur', 'Klistra in ett mappträd för ett enstaka projekt. Din standard ändras inte.',
             'Klistra in struktur', self.open_custom_project),
        ]:
            card = QFrame()
            card.setObjectName('projectCard')
            body = QVBoxLayout(card)
            body.setContentsMargins(18, 16, 18, 16)
            body.setSpacing(10)
            card_title = label(title)
            card_title.setObjectName('cardHeading')
            body.addWidget(card_title)
            body.addWidget(label(description))
            if caption == 'Skapa standardprojekt':
                self.default_template_label = label('Profil / mall: ' + workspace.config.default_template)
                body.addWidget(self.default_template_label)
            action = button(body, caption, callback)
            if caption == 'Klistra in struktur':
                action.setObjectName('secondaryAction')
            create.addWidget(card)
        self.save_root_label = label('Profilens sparplats: ' + str(workspace.profile_root()))
        create.addWidget(self.save_root_label)
        button(create, 'Ångra senast skapade projekt…', self.undo_last)
        create.addStretch()
        history = page(self.tabs, 'Historik')
        history.addWidget(label('Senaste projekt'))
        self.history_filter = QLineEdit()
        self.history_filter.setPlaceholderText('Filtrera projektnamn eller sökväg…')
        self.history_filter.textChanged.connect(self.refresh_history)
        history.addWidget(self.history_filter)
        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self.open_history)
        history.addWidget(self.history_list)
        button(history, 'Öppna markerad mapp', lambda: self.open_history(self.history_list.currentItem()))
        button(history, 'Exportera markerad mappstruktur', self.export_history)
        button(history, 'Ta bort markerad historikpost…', lambda: self.remove_history(False))
        button(history, 'Rensa historiken…', lambda: self.remove_history(True))
        button(history, 'Uppdatera listan', self.refresh_history)
        self.template_page()
        self.export_page()
        self.settings_page()
        self.menuBar().clear()
        file_menu = self.menuBar().addMenu('Arkiv')
        file_menu.addAction('Skapa standardprojekt', self.open_project)
        file_menu.addAction('Klistra in struktur', self.open_custom_project)
        file_menu.addAction('Öppna sparplats', lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.workspace.profile_root()))))
        file_menu.addAction('Minimera till systemfältet', self.hide)
        file_menu.addAction(self.exit_action)
        view_menu = self.menuBar().addMenu('Visa')
        self.tab_actions = []
        view_menu.addAction('Visa alla sidor', self.show_all_tabs)
        view_menu.addSeparator()
        for index, title in enumerate(('Skapa', 'Historik', 'Mallar', 'Exportera', 'Inställningar', 'Snabbtangent')):
            action = view_menu.addAction(title)
            action.setCheckable(True)
            visible = self.workspace.config.visible_tabs.get(title, True)
            action.setChecked(visible)
            self.tabs.setTabVisible(index, visible)
            action.triggered.connect(lambda checked, n=index: self.toggle_tab(n, checked))
            self.tab_actions.append(action)
        help_menu = self.menuBar().addMenu('Hjälp')
        self.exit_action.setText('Avsluta FolderForge')
        help_menu.addAction(self.exit_action)
        help_menu.addAction('Donationer – Stöd FolderForge', self.donations)
        help_menu.addAction('Uppdateringsstatus', self.update_status)
        help_menu.addAction('Sök uppdatering nu', self.check_updates)
        help_menu.addAction('Felsökning och fellista…', self.diagnostics)
        help_menu.addAction('Rensa cache (smartfilter)…', self.cache_dialog)
        help_menu.addAction('Detaljerad loggning i 15 minuter', lambda: self.enable_debug(15))
        help_menu.addAction('Återgå till normal loggning', lambda: self.enable_debug(0))
        help_menu.addAction('Öppna fellogg', lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.workspace.base / 'logs/folderforge-errors.log'))))
        help_menu.addAction('Exportera felsökningspaket…', self.export_diagnostics)
        help_menu.addAction('Om FolderForge', lambda: QMessageBox.information(self, 'FolderForge',
            f'FolderForge {APP_VERSION}\n© Rickard Längkvist\n'
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

    def toggle_tab(self, index, visible):
        self.tabs.setTabVisible(index, visible)
        for n, action in enumerate(self.tab_actions):
            shown = n not in self.tabs.hidden_tabs
            action.setChecked(shown)
            self.workspace.config.visible_tabs[action.text()] = shown
        self.save_settings()

    def show_all_tabs(self):
        for n in range(self.tabs.count()):
            self.tabs.setTabVisible(n, True)
        self.toggle_tab(0, True)

    def open_custom_project(self):
        self.open_project()
        self.dialog.custom.setFocus()

    def refresh_history(self):
        selected = self.history_list.currentItem()
        previous = selected.data(Qt.UserRole) if selected else None
        self.history_list.clear()
        query = self.history_filter.text().casefold()
        for entry in self.workspace.history.get_all():
            path = entry['path']
            if query not in path.casefold():
                continue
            item = QListWidgetItem(Path(path).name + '\n' + path + '\n' + str(entry.get('created', '')))
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.history_list.addItem(item)
            if previous == path:
                self.history_list.setCurrentItem(item)

    def open_history(self, item):
        if item and not QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(Qt.UserRole))):
            QMessageBox.warning(self, 'Kunde inte öppna', 'Kontrollera att mappen finns och är tillgänglig.')

    def export_history(self):
        item = self.history_list.currentItem()
        if item:
            self.tabs.setCurrentIndex(3)
            self.start_export(Path(item.data(Qt.UserRole)))

    def remove_history(self, all_entries=False):
        item = self.history_list.currentItem()
        if not all_entries and not item:
            return
        if QMessageBox.question(self, 'Rensa historik' if all_entries else 'Ta bort historikpost',
                'Ta bort alla historikposter? Projektmapparna påverkas inte.' if all_entries else
                'Ta bort denna historikpost? Projektmappen påverkas inte.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.workspace.require_lock()
            if all_entries:
                self.workspace.history.clear()
            else:
                self.workspace.history.remove(item.data(Qt.UserRole))
            self.refresh_history()
        except (OSError, RuntimeError) as exc:
            logging.getLogger('qt.history').exception('Historiken kunde inte ändras')
            QMessageBox.warning(self, 'Historik', str(exc))

    def cache_dialog(self):
        from cache_cleanup import status_text, clean_cache
        dialog = QDialog(self)
        dialog.setWindowTitle('Rensa cache – smartfilter')
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('Daglig automatisk rensning behålls. Smartfiltret skyddar projekt, '
                               'inställningar, historik, uppdateringar och felloggar.'))
        status = label(status_text(self.workspace.base))
        layout.addWidget(status)
        def clean():
            if QMessageBox.question(dialog, 'Rensa cache', 'Rensa gamla filer enligt smartfiltret?',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            try:
                self.workspace.require_lock()
                clean_cache(self.workspace.base, manual=True)
                status.setText(status_text(self.workspace.base))
            except Exception as exc:
                logging.getLogger('qt.cache').exception('Cacherensning misslyckades')
                QMessageBox.warning(dialog, 'Cacherensning', str(exc))
        button(layout, 'Rensa nu med smartfilter', clean)
        button(layout, 'Stäng', dialog.reject)
        fit_to_screen(dialog, 550, 350)
        dialog.exec()

    def template_page(self):
        layout = page(self.tabs, 'Mallar')
        layout.addWidget(label('Profiler – varje mall har en sparplats'))
        layout.addWidget(label('Välj profil vid skapandet så används både strukturen och sparplatsen. '
            'Äldre mallar utan egen sparplats använder den allmänna sparplatsen i Inställningar. '
            'Ge en inbyggd mall ett eget namn för att spara en profil.'))
        self.templates = QComboBox()
        self.templates.addItems(list(self.workspace.templates.list_templates()))
        self.template_name = QLineEdit()
        self.template_name.setPlaceholderText('Profilnamn (nytt namn skapar en egen profil)')
        self.structure = QPlainTextEdit()
        layout.addWidget(self.templates)
        layout.addWidget(self.template_name)
        layout.addWidget(self.structure)
        layout.addWidget(label('Sparplats för profilen'))
        self.profile_root_edit = QLineEdit()
        self.profile_root_edit.setAccessibleName('Profilens sparplats')
        layout.addWidget(self.profile_root_edit)
        def choose_profile_root():
            path = QFileDialog.getExistingDirectory(self, 'Välj profilens sparplats', self.profile_root_edit.text())
            if path:
                self.profile_root_edit.setText(path)
                self.profile_root_edit.setModified(True)
        button(layout, 'Välj profilens sparplats…', choose_profile_root)
        def load(name):
            self.template_name.setText(name)
            self.structure.setPlainText(self.workspace.templates.list_templates().get(name, ''))
            try:
                root = self.workspace.profile_root(name) if name else Path(self.workspace.config.save_root)
                self.profile_root_edit.setText(str(root))
            except ValueError:
                self.profile_root_edit.clear()
            self.profile_root_edit.setModified(False)
            self.template_name.setModified(False)
        self.templates.currentTextChanged.connect(load)
        def save():
            try:
                self.workspace.require_lock()
                name = self.template_name.text().strip()
                self.workspace.save_profile(name, self.structure.toPlainText(), self.profile_root_edit.text())
                self.templates.blockSignals(True)
                self.templates.clear()
                self.templates.addItems(list(self.workspace.templates.list_templates()))
                self.templates.setCurrentText(name)
                self.templates.blockSignals(False)
                load(name)
                self.structure.document().setModified(False)
                self.default_template_label.setText('Profil / mall: ' + self.workspace.config.default_template)
                self.save_root_label.setText('Profilens sparplats: ' + str(self.workspace.profile_root()))
                self.statusBar().showMessage('Profil sparad – struktur och sparplats')
            except (OSError, ValueError, RuntimeError) as exc:
                logging.getLogger('qt.templates').exception('Mall kunde inte sparas')
                QMessageBox.warning(self, 'Kunde inte spara mall', str(exc))
        button(layout, 'Spara profil (mall + sparplats)', save)
        def set_default():
            self.workspace.config.default_template = self.templates.currentText()
            self.save_settings()
        button(layout, 'Använd vald profil som standard', set_default)
        def remove():
            if QMessageBox.question(self, 'Ta bort egen mall?', self.templates.currentText(),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            try:
                if not self.workspace.templates.delete_template(self.templates.currentText()):
                    raise ValueError('Inbyggda mallar kan inte tas bort')
                if self.workspace.config.default_template == self.templates.currentText():
                    self.workspace.config.default_template = 'Skaderapport'
                    self.workspace.save_settings()
                self.templates.clear()
                self.templates.addItems(list(self.workspace.templates.list_templates()))
                self.save_settings()
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Kunde inte ta bort mall', str(exc))
        button(layout, 'Ta bort vald egen mall…', remove)
        load(self.templates.currentText())

    def export_page(self):
        layout = page(self.tabs, 'Exportera')
        layout.addWidget(label('Välj en mapp för säker trälexport. Resultatet kan kopieras eller sparas.'))
        layout.addWidget(label('Dra och släpp en mapp i fönstret, eller välj den nedan.'))
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
        button(layout, 'Kopiera struktur', lambda: QApplication.clipboard().setText(self.export_text.toPlainText()))
        button(layout, 'Spara text…', save)

    def settings_page(self):
        layout = page(self.tabs, 'Inställningar')
        layout.addWidget(label('Allmän sparplats för äldre mallar utan egen profilsparplats. '
            'Profiler med egen sparplats påverkas inte. Ändringar sparas först med Spara.'))
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
        layout.addStretch()
        layout = page(self.tabs, 'Snabbtangent')
        layout.addWidget(label('Global snabbtangent'))
        layout.addWidget(label('Visa FolderForge var du än arbetar. Ange exempelvis ctrl+alt+m.'))
        self.hotkey_status = label('Snabbtangenten registreras vid start…')
        layout.addWidget(self.hotkey_status)
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
        layout.addWidget(label('Eller spela in en tangentkombination nedan och överför den till fältet:'))
        self.hotkey_recorder = QKeySequenceEdit()
        self.hotkey_recorder.setAccessibleName('Spela in snabbtangent')
        layout.addWidget(self.hotkey_recorder)
        def recorded():
            text = self.hotkey_recorder.keySequence().toString(QKeySequence.PortableText)
            if ',' in text:
                QMessageBox.warning(self, 'Snabbtangent', 'Använd en enda kombination, inte en sekvens.')
                return
            text = text.lower().replace('meta', 'cmd')
            self.hotkey_edit.setText(text)
            self.hotkey_edit.setModified(True)
        button(layout, 'Använd inspelad kombination', recorded)
        def reset_hotkey():
            from settings import DEFAULT_HOTKEY
            self.hotkey_edit.setText('+'.join(DEFAULT_HOTKEY))
            self.hotkey_edit.setModified(True)
        button(layout, 'Återställ standardkombination i fältet', reset_hotkey)
        layout.addStretch()

    def toggle_theme(self):
        self.workspace.config.theme = 'Light' if self.workspace.config.theme == 'Dark' else 'Dark'
        self.theme.setCurrentText(self.workspace.config.theme)
        self.save_settings()

    def apply_accessibility(self):
        config = self.workspace.config
        factor = int(config.text_size.rstrip('%')) / 100
        dark = config.theme == 'Dark'
        if config.theme == 'System':
            dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        index = 1 if dark else 0
        background, foreground = UI_BACKGROUND[index], UI_TEXT[index]
        field, border, muted, accent = UI_SURFACE[index], UI_BORDER[index], UI_MUTED[index], UI_PRIMARY[index]
        focus = '#FFCE66' if dark else '#005FCC'
        if config.high_contrast:
            background, foreground, field, border, muted, accent, focus = (
                '#000000', '#FFFFFF', '#000000', '#FFFFFF', '#FFFFFF', '#164B73', '#FFFF00')
        self.setStyleSheet(f"""
            QWidget {{ background: {background}; color: {foreground}; font-size: {round(15 * factor)}px; }}
            QFrame#appHeader, QFrame#appFooter {{ background: {field}; border: none; }}
            QFrame#appHeader QLabel, QFrame#appFooter QLabel {{ background: transparent; color: {muted}; }}
            QLabel#appLogo {{ background: white; color: #172638; border-radius: 8px; padding: 5px; font-weight: bold; }}
            QPushButton {{ background: {accent}; color: white; padding: 10px; border: 2px solid transparent; border-radius: 9px; }}
            QPushButton:hover {{ border-color: {border}; }}
            QPushButton#secondaryAction, QPushButton#navigationTab {{ background: {field}; color: {foreground}; border: 1px solid {border}; }}
            QPushButton#navigationTab:checked {{ background: {accent}; color: white; border: 1px solid {accent}; }}
            QPushButton:focus, QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 2px solid {focus}; }}
            QLineEdit, QComboBox, QPlainTextEdit, QListWidget {{ background: {field}; padding: 6px; border: 1px solid {border}; border-radius: 6px; }}
            QLabel#pageHeading {{ font-size: {round(23 * factor)}px; font-weight: bold; }}
            QLabel#cardHeading {{ font-size: {round(16 * factor)}px; font-weight: bold; }}
            QFrame#projectCard {{ background: {field}; border: 1px solid {border}; border-radius: 14px; }}
            QFrame#projectCard QLabel {{ background: transparent; border: none; }}
            QStatusBar {{ color: {muted}; background: {field}; }}
            QMenu {{ background: {field}; border: 1px solid {border}; }}
            QMenu::item:selected {{ background: {accent}; color: white; }}
        """)
        for n, control in enumerate(self.tabs.buttons):
            names = ['create', 'history', 'templates', 'export', 'settings', 'keyboard']
            control.setIcon(QIcon(str(BASE_DIR / ('Icon/nav-' + names[n] + ('-dark.png' if dark else '-light.png')))))
        QTimer.singleShot(0, lambda: self.tabs.reflow(force=True))

    def save_settings(self):
        try:
            self.workspace.save_settings()
            self.apply_accessibility()
            self.default_template_label.setText('Profil / mall: ' + self.workspace.config.default_template)
            self.save_root_label.setText('Profilens sparplats: ' + str(self.workspace.profile_root()))
            self.statusBar().showMessage('Inställningar sparade')
        except (OSError, RuntimeError) as exc:
            logging.getLogger('qt.settings').exception('Inställningar kunde inte sparas')
            QMessageBox.warning(self, 'Skrivfel', str(exc))

    def donations(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Donationer – Stöd FolderForge')
        dialog.setWindowIcon(self.windowIcon())
        outer = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        hero = label('STÖD FOLDERFORGE\n\nGör vardagen enklare – tillsammans')
        hero.setObjectName('donationHero')
        hero.setStyleSheet('QLabel { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,'
            'stop:0 #145A32,stop:0.65 #176B46,stop:1 #674122); color: white;'
            'border-radius: 14px; padding: 18px; font-weight: bold; }')
        layout.addWidget(hero)
        layout.addWidget(label('Har FolderForge sparat tid åt dig? En frivillig gåva visar '
            'uppskattning och uppmuntrar fortsatt utveckling, testning och förbättringar.\n\n'
            'Du väljer själv belopp. Inga nivåer eller extrafunktioner säljs. '
            'Alla funktioner fungerar precis lika bra utan donation.'))
        layout.addWidget(label('Swish – skanna med Swish-appen'))
        qr = QLabel()
        qr.setObjectName('swishQr')
        qr.setAlignment(Qt.AlignCenter)
        qr.setAccessibleName('Swish QR-kod för gåva till 0721817177, valfritt belopp')
        pixmap = QPixmap(str(BASE_DIR / 'Icon/swish-folderforge.png'))
        if pixmap.isNull():
            logging.getLogger('qt.support').error('Swish QR-bilden saknas eller kunde inte läsas')
            qr.setText('QR-koden kunde inte läsas. Använd Swish-numret nedan.')
            qr.setWordWrap(True)
        else:
            qr.setPixmap(pixmap.scaled(240, 240, Qt.KeepAspectRatio, Qt.FastTransformation))
        layout.addWidget(qr)
        layout.addWidget(label('Swish: 0721817177\n'
            'Ange valfritt belopp i Swish. Kontrollera alltid mottagarens namn '
            'och belopp innan du godkänner betalningen.'))
        paypal = button(layout, 'Stöd via PayPal ↗',
            lambda: webbrowser.open('https://paypal.me/Rickard3dPrint', new=2))
        kofi = button(layout, 'Bjud på en kaffe via Ko-fi ↗',
            lambda: webbrowser.open('https://ko-fi.com/tokke2', new=2))
        for control, color in ((paypal, '#075A91'), (kofi, '#A62F39')):
            control.setMinimumHeight(44)
            control.setStyleSheet('QPushButton { background: ' + color +
                '; color: white; padding: 10px; border: 2px solid transparent; border-radius: 9px;'
                'font-weight: bold; } QPushButton:focus { border: 2px solid #FFD54F; }')
        layout.addWidget(label('Mottagarlänkarna är fasta och kan inte ändras i appen. '
            'Knapparna öppnar din webbläsare först när du klickar. QR-koden finns lokalt; '
            'ingen extern QR-tjänst kontaktas. FolderForge hanterar inte betalningen '
            'och får ingen betalningsbekräftelse.'))
        layout.addWidget(label('Tack för att du använder FolderForge!\n– Rickard Längkvist'))
        button(outer, 'Stäng', dialog.reject)
        fit_to_screen(dialog, 560, 720)
        dialog.exec()

    def update_status(self):
        from updater import get_update_status, pending_ready_for_restart
        existing = getattr(self, '_update_dialog', None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
        dialog = QDialog(self)
        self._update_dialog = dialog
        dialog.setWindowTitle('Uppdateringsstatus')
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        layout.addWidget(text)
        explanation = label('')
        layout.addWidget(explanation)
        def restart():
            if QMessageBox.question(dialog, 'Installera hämtad uppdatering?',
                    'Läs ändringslistan ovan. Appen stängs och startas om dold i systemfältet. '
                    'Projekt, mallar och historik behålls. Fortsätt?',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
                dialog.accept()
                QTimer.singleShot(0, self.restart_update)
        restart_button = button(layout, 'Installera hämtad uppdatering och starta om…', restart)
        restart_button.setObjectName('installUpdate')
        def refresh():
            report = get_update_status(self.workspace.base, APP_VERSION)
            value = '\n\n'.join(f'{key}: {value}' for key, value in report.items())
            if text.toPlainText() != value:
                bar = text.verticalScrollBar()
                position = bar.value()
                text.setPlainText(value)
                bar.setValue(position)
            ready = pending_ready_for_restart(self.workspace.base)
            restart_button.setEnabled(ready)
            explanation.setText('Uppdateringen är hämtad. Stäng detta fönster för automatisk omstart, '
                'eller välj Installera ovan.' if ready else
                'En kontroll hämtar först uppdateringen. Status och eventuella fel visas ovan. '
                'Installationsknappen aktiveras när hämtningen är klar.')
        timer = QTimer(dialog)
        timer.timeout.connect(refresh)
        timer.start(1000)
        refresh()
        button(layout, 'Sök uppdatering nu', lambda: self._check_updates(False))
        button(layout, 'Stäng', dialog.reject)
        fit_to_screen(dialog, 660, 650)
        dialog.exec()
        timer.stop()
        self._update_dialog = None
        dialog.deleteLater()

    def restart_update(self):
        from updater import pending_ready_for_restart
        if not pending_ready_for_restart(self.workspace.base):
            QMessageBox.information(self, 'Uppdatering', 'Ingen verifierad uppdatering är redo att installeras.')
            return
        if not self.can_restart():
            QMessageBox.information(self, 'Omstart väntar',
                'Spara ändrade inställningar, mallar eller snabbtangent och stäng projektdialoger. '
                'Vänta tills eventuell export är klar. Försök sedan igen.')
            return
        QApplication.instance().exit(71)

    def check_updates(self):
        self._check_updates(True)

    def _check_updates(self, show_status):
        from updater import check_once
        worker = getattr(self, '_update_worker', None)
        if worker is None or not worker.is_alive():
            def check():
                try:
                    check_once(self.workspace.base, APP_VERSION, force=True)
                except Exception:
                    logging.getLogger('qt.update').exception('Manuell uppdateringskontroll misslyckades')
            self._update_worker = threading.Thread(target=check, daemon=True, name='qt-release-check')
            self._update_worker.start()
        self.statusBar().showMessage('Söker uppdatering – hämtning och eventuella fel visas i Uppdateringsstatus')
        if show_status:
            self.update_status()

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
                and not self.profile_root_edit.isModified() and not self.template_name.isModified()
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
        self._hotkeys.status.connect(self.hotkey_status.setText)
        self.hotkey_edit.setText('+'.join(self._hotkeys.keys))
        self.hotkey_edit.setModified(False)
        self._hotkeys.start()
        QApplication.instance().aboutToQuit.connect(self._hotkeys.stop)

    def diagnostics(self):
        from qt_help import DiagnosticsDialog
        dialog = DiagnosticsDialog(self)
        dialog.exec()

    def export_diagnostics(self):
        from qt_help import DiagnosticsDialog
        dialog = DiagnosticsDialog(self)
        try:
            dialog.export()
        finally:
            dialog.timer.stop()
            dialog.deleteLater()

    def enable_debug(self, minutes=15):
        from logg import enable_detailed_logging
        enable_detailed_logging(minutes)
        self.statusBar().showMessage('Detaljerad loggning aktiv i 15 minuter' if minutes else 'Normal loggning aktiv')

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
