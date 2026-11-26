"""Default Qt client with an explicit, separately launched Tk reserve."""
from pathlib import Path
import threading
import logging
import webbrowser
import sys
from functools import lru_cache

from PySide6.QtCore import QObject, Signal, QRect, QTimer, QUrl, Qt, QSize
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtGui import QDesktopServices, QPixmap, QIcon, QKeySequence, QFontDatabase, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QGridLayout, QHeaderView, QStackedWidget, QSizePolicy,
    QKeySequenceEdit, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QFrame,
    QProgressBar, QStyle, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from app_core import (
    build_project_name, ExistingProject, StructureEngine,
    project_year_choices, validate_project_year,
)
from qt_preview import PreviewWindow, fit_to_screen, install_field_wheel_guard
from settings import (
    APP_VERSION, BASE_DIR, DAMAGE_TYPE_CHIPS, RUTA_CHOICES, LOKAL_CHOICES,
    VEHICLE_CHOICES, UI_BACKGROUND, UI_SURFACE, UI_BORDER, UI_TEXT, UI_MUTED,
    UI_PRIMARY,
)
from workspace import Workspace


@lru_cache(maxsize=32)
def navigation_icon(name, variant):
    """Bounded cache: share SVG engines without retaining widgets or raster copies."""
    return QIcon(str(BASE_DIR / ('Icon/nav-' + name + variant)))


def toggle_damage_word(current_text: str, chip: str) -> str:
    """Slår ruta-/skadeordet av/på i projektnamnet (SIDORUTA/BAKRUTA utesluter varandra)."""
    upp = chip.upper()
    words = (current_text or '').split()
    if any(w.upper() == upp for w in words):
        words = [w for w in words if w.upper() != upp]
    else:
        if upp in RUTA_CHOICES:
            words = [w for w in words if w.upper() not in RUTA_CHOICES]
        words.append(upp)
    return ' '.join(words)


def label(text, object_name=None):
    result = QLabel(text)
    result.setWordWrap(True)
    result.setTextFormat(Qt.PlainText)
    if object_name:
        result.setObjectName(object_name)
    return result


def button(layout, text, callback, icon_name=None, icon_registry=None):
    result = QPushButton(text)
    result.setObjectName('secondaryAction')
    result.clicked.connect(callback)
    layout.addWidget(result)
    if icon_name and icon_registry is not None:
        icon_registry.append((result, icon_name))
    return result


def card_frame():
    frame = QFrame()
    frame.setObjectName('projectCard')
    body = QVBoxLayout(frame)
    body.setContentsMargins(14, 12, 14, 12)
    body.setSpacing(8)
    return frame, body


def monospace_font(factor=1.0):
    mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    families = set(QFontDatabase.families())
    for candidate in ('Cascadia Mono', 'Consolas', 'SF Mono', 'JetBrains Mono', 'DejaVu Sans Mono'):
        if candidate in families:
            mono.setFamily(candidate)
            break
    mono.setPointSizeF(10.5 * factor)
    mono.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
    return mono


def page(tabs, title):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(10)
    scroll.setWidget(widget)
    tabs.addTab(scroll, title)
    return layout


class ResponsiveTabs(QWidget):
    """All page names remain visible; navigation wraps rather than scrolling away."""
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 0)
        layout.setSpacing(6)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.header = QGridLayout()
        self.header.setSpacing(6)
        layout.addLayout(self.header)
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        layout.addWidget(self.stack, 1)
        self.buttons = []
        self.columns = 0
        self.hidden_tabs = set()

    def addTab(self, widget, title):
        index = self.stack.addWidget(widget)
        control = QPushButton(title)
        icons = ['create', 'history', 'templates', 'export', 'settings', 'keyboard']
        control.setIcon(navigation_icon(icons[index], '-light.svg'))
        control.setObjectName('navigationTab')
        control.setCheckable(True)
        control.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
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
            names = ['create', 'history', 'templates', 'export', 'settings', 'keyboard']
            variant = '-dark.svg' if n == index or getattr(self, 'dark_theme', False) else '-light.svg'
            control.setIcon(navigation_icon(names[n], variant))

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
        needed = max((b.fontMetrics().horizontalAdvance(b.text()) + 68 for b in visible), default=170)
        columns = max(1, min(len(visible), max(1, self.width() - 20) // needed))
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
        self.setWindowIcon(window.windowIcon())
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(4, 2, 4, 4)
        body.setSpacing(8)

        name_card, name_layout = card_frame()
        name_title = label('&Projektnamn / registreringsnummer', 'cardHeading')
        self.name = QLineEdit()
        self.name.setAccessibleName('Projektnamn')
        self.name.setPlaceholderText('T.ex. ABC123 eller kund-/projektnamn…')
        name_title.setBuddy(self.name)
        name_layout.addWidget(name_title)
        name_layout.addWidget(self.name)

        # Val av ruta / skadetyp (precis som i Tk/ttk-versionen, med ömsesidigt uteslutande SIDORUTA/BAKRUTA)
        chips_caption = label('Ruta / skadetyp · valfria snabbval (klicka för att lägga till eller ta bort)', 'mutedText')
        name_layout.addWidget(chips_caption)
        chips_grid = QGridLayout()
        chips_grid.setSpacing(6)
        self.damage_buttons = {}
        for idx, chip in enumerate(DAMAGE_TYPE_CHIPS):
            chip_btn = QPushButton(chip)
            chip_btn.setObjectName('damageChip')
            chip_btn.setCheckable(True)
            chip_btn.setFocusPolicy(Qt.TabFocus)
            chip_btn.clicked.connect(lambda _checked=False, c=chip: self.toggle_damage(c))
            chips_grid.addWidget(chip_btn, 0, idx)
            chips_grid.setColumnStretch(idx, 1)
            self.damage_buttons[chip] = chip_btn
        name_layout.addLayout(chips_grid)
        body.addWidget(name_card)

        # Kompakt 2-kolumnskort för Fordon, Profil, Lokal och År (minimerar scroll)
        details_card, details_layout = card_frame()
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.vehicle = QComboBox()
        self.vehicle.addItems(['—'] + list(VEHICLE_CHOICES))
        self.template = QComboBox()
        self.template.addItems(list(window.workspace.templates.list_templates()))
        self.template.setCurrentText(window.home_profile.currentText())
        self.location = QComboBox()
        self.location.addItems(['—'] + list(LOKAL_CHOICES))
        self.year = QComboBox()
        self.year.setEditable(True)
        self.year.addItems(['—'] + project_year_choices())

        for row, col, caption, widget in (
            (0, 0, '&Fordon', self.vehicle),
            (0, 1, '&Profil / mall', self.template),
            (2, 0, '&Lokal', self.location),
            (2, 1, '&År (välj eller skriv)', self.year),
        ):
            lbl = label(caption, 'mutedText')
            lbl.setBuddy(widget)
            grid.addWidget(lbl, row, col)
            grid.addWidget(widget, row + 1, col)
        details_layout.addLayout(grid)
        body.addWidget(details_card)

        custom_card, custom_layout = card_frame()
        custom_header = QHBoxLayout()
        custom_header.addWidget(label('Tillfällig egen struktur (frivilligt – ändrar inte sparade profiler)', 'mutedText'), 1)

        def show_structure():
            dialog = QDialog(self)
            dialog.setWindowTitle('Mappstruktur för projektet')
            dialog.setWindowIcon(self.windowIcon())
            preview_layout = QVBoxLayout(dialog)
            text = QPlainTextEdit()
            text.setReadOnly(True)
            text.setFont(monospace_font())
            structure = self.custom.toPlainText() if self.custom.toPlainText().strip() else (
                self.window.workspace.templates.list_templates().get(self.template.currentText(), ''))
            text.setPlainText(structure)
            preview_layout.addWidget(text)
            button(preview_layout, 'Stäng', dialog.reject)
            fit_to_screen(dialog, 620, 560)
            dialog.exec()
            dialog.deleteLater()

        def save_custom_over_profile():
            custom_text = self.custom.toPlainText().strip()
            target = self.template.currentText().strip()
            if not custom_text:
                QMessageBox.information(
                    self,
                    'Ingen ny struktur angiven',
                    'Skriv eller klistra in den nya mappstrukturen i rutan nedan för att spara över vald profil, '
                    'eller klicka på "Hantera profiler…" för att redigera sparplats, skapa eller ta bort profiler.',
                )
                return
            if QMessageBox.question(
                self,
                'Spara över profil?',
                f'Vill du spara över mappstrukturen i profilen "{target}"?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            ) != QMessageBox.Yes:
                return
            try:
                root_path = self.window.workspace.profile_root(target)
                self.window.workspace.save_profile(target, custom_text + '\n', str(root_path))
                self.custom.clear()
                self.window._sync_all_template_lists(target)
                self.window._load_template_into_editor(target)
                if hasattr(self.window, '_load_settings_profile'):
                    self.window._load_settings_profile(target)
                self.refresh()
                self.window.statusBar().showMessage(f'Profilen "{target}" uppdaterades (sparades över)')
            except (OSError, ValueError, RuntimeError) as exc:
                QMessageBox.warning(self, 'Kunde inte spara över profil', str(exc))

        def manage_profiles():
            self.window.open_profiles_subtab(self.template.currentText())

        inspect_btn = QPushButton('Visa struktur…')
        inspect_btn.setObjectName('secondaryAction')
        inspect_btn.clicked.connect(show_structure)
        custom_header.addWidget(inspect_btn)
        overwrite_btn = QPushButton('Spara över profil…')
        overwrite_btn.setObjectName('secondaryAction')
        overwrite_btn.clicked.connect(save_custom_over_profile)
        custom_header.addWidget(overwrite_btn)
        manage_btn = QPushButton('Hantera profiler…')
        manage_btn.setObjectName('secondaryAction')
        manage_btn.clicked.connect(manage_profiles)
        custom_header.addWidget(manage_btn)
        custom_layout.addLayout(custom_header)
        self.custom = QPlainTextEdit()
        self.custom.setFont(monospace_font())
        self.custom.setPlaceholderText('Lämna tomt för vald profil, eller klistra in ett indraget mappträd.')
        self.custom.setMaximumHeight(96)
        custom_layout.addWidget(self.custom)
        body.addWidget(custom_card)
        body.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # Alltid synlig nederdel utan rullning: live-förhandsvisning + Skapa/Avbryt
        footer_card, footer_layout = card_frame()
        self.preview = label('')
        self.preview.setObjectName('previewBox')
        footer_layout.addWidget(self.preview)
        self.error = label('', 'errorText')
        footer_layout.addWidget(self.error)
        actions = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.create_button = actions.button(QDialogButtonBox.Save)
        self.create_button.setText('Skapa projekt…')
        actions.accepted.connect(self.create)
        actions.rejected.connect(self.reject)
        footer_layout.addWidget(actions)
        outer.addWidget(footer_card)

        self.name.textChanged.connect(self.on_name_changed)
        for widget in (self.location, self.year, self.vehicle, self.template):
            widget.currentTextChanged.connect(self.refresh)
        self.custom.textChanged.connect(self.refresh)
        self.template.currentTextChanged.connect(window.select_profile)
        self.sync_damage_chips()
        self.refresh()

    def toggle_damage(self, chip):
        updated = toggle_damage_word(self.name.text(), chip)
        self.name.setText(updated)
        self.name.setFocus()
        self.name.setCursorPosition(len(updated))

    def sync_damage_chips(self):
        words = {w.upper() for w in self.name.text().split()}
        for chip, btn in self.damage_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(chip.upper() in words)
            btn.blockSignals(False)

    def on_name_changed(self):
        self.sync_damage_chips()
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
            self.preview.setText(f'Slutnamn: {name}\n{folders} mappar · {files} filer · '
                f'Sparas i: {self.window.workspace.profile_root(self.template.currentText()) / name}')
            self.preview.setVisible(True)
            self.error.clear()
            self.error.setVisible(False)
            self.create_button.setEnabled(True)
        except (ValueError, OSError) as exc:
            self.preview.clear()
            self.preview.setVisible(False)
            self.error.setText(str(exc))
            self.error.setVisible(True)
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
            try:
                from logg import resolve_matching_errors
                resolve_matching_errors(modules=('qt.projects',))
            except Exception:
                pass
            self.window.select_profile(self.template.currentText())
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
        fit_to_screen(self, 700, 620)
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
        self._action_icons = []
        self._mono_editors = []
        self._last_update_mtime = None
        self._export_bridge = ExportBridge(self)
        self._export_bridge.ready.connect(self.export_ready)
        self._export_bridge.failed.connect(self.export_failed)
        self.setWindowTitle(f'FolderForge {APP_VERSION}')
        self.setMinimumSize(300, 250)
        self.tabs = ResponsiveTabs()

        shell = QWidget()
        shell.setObjectName('appShell')
        shell.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(2)

        # Kompakt, knivskarp toppanel (sparar höjd på alla sidor och växlar vektor-logotyp efter tema)
        header = QFrame()
        header.setObjectName('appHeader')
        header.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        header_layout = QGridLayout(header)
        self._header_layout = header_layout
        header_layout.setContentsMargins(14, 6, 14, 6)
        header_layout.setSpacing(8)
        logo_path = BASE_DIR / 'Icon/folderforge-logo.svg'
        logo = QSvgWidget(str(logo_path))
        if logo.renderer().isValid():
            logo.renderer().setAspectRatioMode(Qt.KeepAspectRatio)
            self._logo_svg = logo
        else:
            logo.deleteLater()
            logo = QLabel('FolderForge')
            self._logo_svg = None
        logo.setObjectName('appLogo')
        logo.setFixedSize(196, 40)
        logo.setAccessibleName('FolderForge')
        self._logo_widget = logo
        self._version_badge = label('v' + APP_VERSION, 'versionBadge')

        self.update_summary = label('Kontrollerar lokal uppdateringsstatus…', 'updateSummary')
        self.update_summary.setMinimumWidth(0)
        self.update_summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        update = QPushButton('Sök uppdatering nu')
        update.setObjectName('secondaryAction')
        update.clicked.connect(self.check_updates)
        self._global_update_button = update

        self.fit_screen_button = QPushButton('Maxhöjd')
        self.fit_screen_button.setObjectName('secondaryAction')
        self.fit_screen_button.setToolTip('Anpassa fönstret till skärmens fulla höjd och optimala bredd')
        self.fit_screen_button.clicked.connect(self.fit_window_to_screen)
        self._action_icons.append((self.fit_screen_button, 'fit'))

        self.theme_toggle = QPushButton('◐')
        self.theme_toggle.setAccessibleName('Växla ljust och mörkt tema')
        self.theme_toggle.setToolTip('Växla ljust och mörkt tema')
        self.theme_toggle.setFixedWidth(42)
        self.theme_toggle.setObjectName('secondaryAction')
        self.theme_toggle.clicked.connect(self.toggle_theme)
        self._header_wide = None
        self._reflow_header(force=True)
        shell_layout.addWidget(header)

        shell_layout.addWidget(self.tabs, 1)

        footer = QFrame()
        footer.setObjectName('appFooter')
        footer.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        footer_layout = QGridLayout(footer)
        self._footer_layout = footer_layout
        footer_layout.setContentsMargins(14, 4, 14, 4)
        footer_layout.setSpacing(4)
        footer_layout.setColumnStretch(0, 1)
        footer_note = label('© Rickard Längkvist · Släpp valfri mapp i fönstret för snabb trälexport', 'mutedText')
        footer_note.setMinimumWidth(0)
        footer_note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        footer_layout.addWidget(footer_note, 0, 0)
        minimize = QPushButton('Minimera till fältet')
        minimize.clicked.connect(self.hide)
        footer_layout.addWidget(minimize, 1, 0)
        minimize.setObjectName('secondaryAction')
        self._minimize_button = minimize
        shell_layout.addWidget(footer)
        self.setCentralWidget(shell)

        # ── Sida 0: Skapa (kompakt, noll scroll på normala skärmar) ──
        create = page(self.tabs, 'Skapa')
        hero_row = QHBoxLayout()
        hero_texts = QVBoxLayout()
        hero_texts.setSpacing(2)
        heading = label('Skapa ett projekt', 'pageHeading')
        hero_texts.addWidget(heading)
        subtitle = label('En tydlig struktur – skapad och organiserad på några sekunder.', 'mutedText')
        hero_texts.addWidget(subtitle)
        hero_row.addLayout(hero_texts, 1)
        undo_btn = QPushButton('Ångra senast skapade projekt…')
        undo_btn.setObjectName('secondaryAction')
        undo_btn.clicked.connect(self.undo_last)
        self._action_icons.append((undo_btn, 'undo'))
        hero_row.addWidget(undo_btn, 0, Qt.AlignTop)
        create.addLayout(hero_row)

        self._home_grid = QGridLayout()
        self._home_grid.setSpacing(12)
        self._project_cards = []
        self._home_columns = 0
        create.addLayout(self._home_grid)
        self._created = []
        for title, description, caption, callback in [
            ('Använd din standardmall', 'Skapa projekt med sparad mappstruktur, ruta/skadetyp, fordon, lokal och år.',
             'Skapa projekt', self.open_project),
            ('Egen struktur', 'Klistra in ett mappträd för ett enstaka projekt. Dina sparade profiler ändras inte.',
             'Klistra in struktur', self.open_custom_project),
        ]:
            card, body = card_frame()
            card_title = label(title, 'cardHeading')
            body.addWidget(card_title)
            description_label = label(description, 'mutedText')
            body.addWidget(description_label)
            if caption == 'Skapa projekt':
                self.default_template_label = label('Aktiv profil', 'mutedText')
                body.addWidget(self.default_template_label)
                self.home_profile = QComboBox()
                self.home_profile.setAccessibleName('Aktiv profil på startsidan')
                self.home_profile.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                self.home_profile.setMinimumContentsLength(16)
                self.home_profile.addItems(list(workspace.templates.list_templates()))
                self.home_profile.setCurrentText(workspace.selected_profile())
                body.addWidget(self.home_profile)
                self.save_root_label = label('', 'mutedText')
                body.addWidget(self.save_root_label)
            else:
                quick_note = label('Tips: Du kan också skapa nya permanenta profiler under Inställningar → Profiler.', 'mutedText')
                body.addWidget(quick_note)
            body.addStretch()
            action = button(body, caption, callback)
            action.setObjectName('primaryAction' if caption == 'Skapa projekt' else 'secondaryAction')
            self._action_icons.append((action, 'create' if caption == 'Skapa projekt' else 'templates'))
            self._project_cards.append(card)
        self.reflow_home(force=True)
        self.home_profile.currentTextChanged.connect(self.select_profile)
        self.refresh_profile_path()
        create.addStretch()

        # ── Sida 1: Historik (2 tydliga kolumner: lista + detaljpanel) ──
        history = page(self.tabs, 'Historik')
        hist_grid = QGridLayout()
        hist_grid.setSpacing(12)
        hist_grid.setColumnStretch(0, 3)
        hist_grid.setColumnStretch(1, 2)

        hist_left, hist_left_body = card_frame()
        hist_left_body.addWidget(label('Senaste projekt', 'cardHeading'))
        hist_left_body.addWidget(label('Klicka på kolumnrubrik för att sortera eller dra rubriker för att flytta kolumner.', 'mutedText'))
        self.history_filter = QLineEdit()
        self.history_filter.setPlaceholderText('Filtrera projektnamn eller sökväg…')
        self.history_filter.textChanged.connect(self.refresh_history)
        hist_left_body.addWidget(self.history_filter)

        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(['Projekt', 'Skapad', 'Status', 'Sökväg'])
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.verticalHeader().setVisible(False)
        hist_hdr = self.history_table.horizontalHeader()
        hist_hdr.setSectionsMovable(True)
        hist_hdr.setSectionsClickable(True)
        hist_hdr.setStretchLastSection(True)
        for col in range(3):
            hist_hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.history_table.setSortingEnabled(True)
        self._restore_history_columns()
        hist_hdr.sectionMoved.connect(lambda *_: self._save_history_columns())
        hist_hdr.sortIndicatorChanged.connect(lambda *_: self._save_history_columns())
        self.history_table.itemSelectionChanged.connect(self._on_history_table_selected)
        self.history_table.cellDoubleClicked.connect(lambda _r, _c: self.open_history(self.history_list.currentItem()))
        hist_left_body.addWidget(self.history_table, 1)

        # Synkad QListWidget för programmatisk kompatibilitet
        self.history_list = QListWidget()
        self.history_list.setVisible(False)
        self.history_list.itemDoubleClicked.connect(self.open_history)
        self.history_list.currentItemChanged.connect(self._update_history_detail)
        hist_left_body.addWidget(self.history_list)
        hist_grid.addWidget(hist_left, 0, 0)

        hist_right, hist_right_body = card_frame()
        hist_right_body.addWidget(label('Detaljer & åtgärder', 'cardHeading'))
        self.history_detail = label('Markera ett projekt i listan för att se sökväg och status.', 'mutedText')
        hist_right_body.addWidget(self.history_detail)
        button(hist_right_body, 'Öppna markerad mapp', lambda: self.open_history(self.history_list.currentItem()), 'folder', self._action_icons)
        button(hist_right_body, 'Exportera markerad mappstruktur', self.export_history, 'export', self._action_icons)
        button(hist_right_body, 'Uppdatera listan', self.refresh_history, 'refresh', self._action_icons)
        button(hist_right_body, 'Ta bort markerad historikpost…', lambda: self.remove_history(False), 'trash', self._action_icons)
        button(hist_right_body, 'Rensa historiken…', lambda: self.remove_history(True), 'trash', self._action_icons)
        hist_right_body.addStretch(1)
        hist_grid.addWidget(hist_right, 0, 1)
        history.addLayout(hist_grid, 1)

        self.template_page()
        self.export_page()
        self.settings_page()

        self.menuBar().clear()
        file_menu = self.menuBar().addMenu('Arkiv')
        file_menu.addAction('Skapa standardprojekt', self.open_project)
        file_menu.addAction('Klistra in struktur', self.open_custom_project)
        file_menu.addAction('Hantera profiler…', self.open_profiles_subtab)
        file_menu.addAction('Öppna sparplats', lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.workspace.profile_root(self.home_profile.currentText())))))
        file_menu.addAction('Minimera till systemfältet', self.hide)
        file_menu.addAction(self.exit_action)

        view_menu = self.menuBar().addMenu('Visa')
        self.tab_actions = []
        view_menu.addAction('Anpassa till skärm (maxhöjd)', self.fit_window_to_screen)
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
        self._update_summary_timer = QTimer(self)
        self._update_summary_timer.timeout.connect(self.refresh_update_summary)
        self._update_summary_timer.setInterval(2000)
        self._update_summary_timer.setTimerType(Qt.CoarseTimer)
        self.refresh_update_summary(force=True)
        QApplication.styleHints().colorSchemeChanged.connect(self.system_theme_changed)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() and Path(u.toLocalFile()).is_dir() for u in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                folder = Path(url.toLocalFile())
                if folder.is_dir():
                    self.tabs.setCurrentIndex(3)
                    self.start_export(folder)
                    event.acceptProposedAction()
                    return

    def open_profiles_subtab(self, profile_name=None):
        self.tabs.setCurrentIndex(4)
        if hasattr(self, 'settings_subtabs'):
            self.settings_subtabs.setCurrentIndex(1)
        if isinstance(profile_name, str) and profile_name in self.workspace.templates.list_templates():
            if hasattr(self, 'settings_profile_picker'):
                self.settings_profile_picker.setCurrentText(profile_name)
                self._load_settings_profile(profile_name)
        if not self.isVisible():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, '_screen_hooked', False) and self.windowHandle() is not None:
            self._screen_hooked = True
            self.windowHandle().screenChanged.connect(self._on_screen_changed)
        if hasattr(self, '_update_summary_timer'):
            self.refresh_update_summary(force=True)
            self._update_summary_timer.start()

    def _on_screen_changed(self, _screen):
        # Vid skärmflytt mellan olika DPI/upplösningar återskapas vektorikoner, logotyp och ramklämning direkt.
        self.apply_accessibility()
        self._clamp_frame_to_screen()
        self._reflow_header(force=True)
        self.reflow_home(force=True)

    def hideEvent(self, event):
        # A hidden tray window does not need UI status polling.
        if hasattr(self, '_update_summary_timer'):
            self._update_summary_timer.stop()
        if hasattr(self, '_placement_timer'):
            self._placement_timer.stop()
        super().hideEvent(event)

    def system_theme_changed(self, scheme):
        if self.workspace.config.theme == 'System':
            self.apply_accessibility()

    def _screen_work_area(self, screen):
        self.winId()
        margins = self.windowHandle().frameMargins()
        top_frame = max(32, margins.top())
        return screen.availableGeometry().adjusted(
            4 + margins.left(),
            4 + top_frame,
            -4 - margins.right(),
            -4 - margins.bottom(),
        )

    def _default_screen_geometry(self, area):
        factor = int(self.workspace.config.text_size.rstrip('%')) / 100
        # Starta i maxhöjd beroende på skärm och anpassa bredden efter skärmens storlek och textskala.
        ratio = 0.88 if area.width() < 1440 else (0.78 if area.width() < 2100 else 0.68)
        preferred_width = min(round(1460 * factor), max(round(860 * factor), round(area.width() * ratio)))
        width = min(preferred_width, area.width())
        height = area.height()
        rect = QRect(0, 0, width, height)
        rect.moveCenter(area.center())
        rect.moveTop(area.top())
        return rect

    def _reflow_header(self, force=False):
        if not hasattr(self, '_header_layout'):
            return
        wide = self.width() >= 960
        if not force and wide == self._header_wide:
            return
        grid = self._header_layout
        while grid.count():
            grid.takeAt(0)
        for col in range(6):
            grid.setColumnStretch(col, 0)
        if wide:
            self.update_summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(self._logo_widget, 0, 0)
            grid.addWidget(self._version_badge, 0, 1)
            grid.addWidget(self.update_summary, 0, 2)
            grid.addWidget(self._global_update_button, 0, 3)
            grid.addWidget(self.fit_screen_button, 0, 4)
            grid.addWidget(self.theme_toggle, 0, 5)
            grid.setColumnStretch(2, 1)
        else:
            self.update_summary.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            grid.addWidget(self._logo_widget, 0, 0)
            grid.addWidget(self._version_badge, 0, 1)
            grid.addWidget(self.fit_screen_button, 0, 3)
            grid.addWidget(self.theme_toggle, 0, 4)
            grid.addWidget(self.update_summary, 1, 0, 1, 3)
            grid.addWidget(self._global_update_button, 1, 3, 1, 2)
            grid.setColumnStretch(2, 1)
        self._header_wide = wide

    def _clamp_frame_to_screen(self, screen):
        avail = screen.availableGeometry()
        fg = self.frameGeometry()
        if avail.contains(fg):
            return
        cg = self.geometry()
        dx = max(0, fg.width() - cg.width())
        dy = max(0, fg.height() - cg.height())
        left_frame = max(0, cg.x() - fg.x())
        top_frame = max(0, cg.y() - fg.y())
        w = max(260, min(cg.width(), avail.width() - dx))
        h = max(220, min(cg.height(), avail.height() - dy))
        fx = max(avail.left(), min(fg.x(), avail.left() + avail.width() - (w + dx)))
        fy = max(avail.top(), min(fg.y(), avail.top() + avail.height() - (h + dy)))
        self.setGeometry(fx + left_frame, fy + top_frame, w, h)

    def fit_window_to_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        area = self._screen_work_area(screen)
        rect = self._default_screen_geometry(area)
        self.setGeometry(rect)
        self._clamp_frame_to_screen(screen)
        self._reflow_header()
        self.tabs.reflow(force=True)
        self.reflow_home(force=True)
        self.save_placement()

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
        area = self._screen_work_area(screen)
        if rectangle is None:
            rectangle = self._default_screen_geometry(area)
        width = min(max(300, rectangle.width()), area.width())
        height = min(max(250, rectangle.height()), area.height())
        x = max(area.left(), min(rectangle.x(), area.right() - width + 1))
        y = max(area.top(), min(rectangle.y(), area.bottom() - height + 1))
        self.setGeometry(x, y, width, height)
        self.showNormal()
        self._clamp_frame_to_screen(screen)
        self.raise_()
        self.activateWindow()
        self._reflow_header()
        self.tabs.reflow(force=True)
        self.reflow_home(force=True)

    def save_placement(self):
        if not self.workspace.lock.is_primary or not self.isVisible() or self.isMinimized() or self.isMaximized():
            return
        from historik import atomic_write_json
        rect = self.geometry()
        atomic_write_json(self.workspace.base / 'data/qt-window-placement.json',
                          dict(x=rect.x(), y=rect.y(), width=rect.width(), height=rect.height()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_header()
        if hasattr(self, '_footer_layout') and hasattr(self, '_minimize_button'):
            compact = self.width() >= 650
            if compact != getattr(self, '_footer_compact', None):
                self._footer_layout.addWidget(self._minimize_button, 0 if compact else 1, 1 if compact else 0)
                self._footer_compact = compact
        if hasattr(self, '_project_cards'):
            self.reflow_home()
        if hasattr(self, '_placement_timer'):
            self._placement_timer.start(500)

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, '_placement_timer'):
            self._placement_timer.start(500)

    def closeEvent(self, event):
        self.save_placement()
        super().closeEvent(event)

    def reflow_home(self, force=False):
        factor = int(self.workspace.config.text_size.rstrip('%')) / 100
        columns = 2 if self.width() >= round(980 * factor) else 1
        if not force and columns == self._home_columns:
            return
        while self._home_grid.count():
            self._home_grid.takeAt(0)
        self._home_grid.setColumnStretch(0, 3 if columns == 2 else 1)
        self._home_grid.setColumnStretch(1, 2 if columns == 2 else 0)
        for n, card in enumerate(self._project_cards):
            self._home_grid.addWidget(card, n // columns, n % columns)
        self._home_columns = columns

    def refresh_profile_path(self):
        try:
            root = self.workspace.profile_root(self.home_profile.currentText())
            self.save_root_label.setText('Sparplats: ' + str(root))
            self.save_root_label.setToolTip(str(root))
        except ValueError as exc:
            self.save_root_label.setText(str(exc))

    def select_profile(self, name):
        if not name:
            return
        try:
            self.workspace.remember_profile(name)
        except (OSError, ValueError, RuntimeError) as exc:
            logging.getLogger('qt.profiles').exception('Profilvalet kunde inte sparas')
            QMessageBox.warning(self, 'Profilvalet sparades inte', str(exc))
            self.home_profile.blockSignals(True)
            self.home_profile.setCurrentText(self.workspace.selected_profile())
            self.home_profile.blockSignals(False)
            self.refresh_profile_path()
            return
        self.home_profile.blockSignals(True)
        self.home_profile.setCurrentText(name)
        self.home_profile.blockSignals(False)
        self.refresh_profile_path()

    def refresh_profile_choices(self):
        names = list(self.workspace.templates.list_templates())
        active = self.home_profile.currentText()
        active = active if active in names else self.workspace.selected_profile()
        combos = [(self.home_profile, active), (self.default_profile, self.default_profile.currentText())]
        if hasattr(self, 'settings_profile_picker'):
            combos.append((self.settings_profile_picker, self.settings_profile_picker.currentText()))
        for combo, selected in combos:
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            combo.setCurrentText(selected if selected in names else self.workspace.config.default_template)
            combo.blockSignals(False)
        self.refresh_profile_path()

    def refresh_update_summary(self, force=False):
        from updater import get_update_status
        state_file = self.workspace.base / 'data/update-state.json'
        mtime = None
        try:
            mtime = state_file.stat().st_mtime_ns
        except OSError:
            pass
        if not force and mtime is not None and mtime == self._last_update_mtime:
            return
        self._last_update_mtime = mtime
        try:
            state = get_update_status(self.workspace.base, APP_VERSION)
            text = 'Uppdatering: ' + state['Status']
            tooltip = ('Senaste kontroll: ' + state['Senaste kontrollförsök'] +
                '\n' + state['Hämtning'] + '\n' + state.get('Verifierade filändringar', '') +
                '\n' + state['Senaste fel'])
            if self.update_summary.text() != text:
                self.update_summary.setText(text)
            if self.update_summary.toolTip() != tooltip:
                self.update_summary.setToolTip(tooltip)
        except (OSError, ValueError) as exc:
            self.update_summary.setText('Uppdateringsstatus kunde inte läsas: ' + str(exc))

    def open_project(self):
        if self.dialog and self.dialog.isVisible():
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        if self.dialog is not None:
            self.dialog.deleteLater()
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

    def _update_history_detail(self, current, _previous=None):
        if not hasattr(self, 'history_detail'):
            return
        if current is None:
            self.history_detail.setText('Markera ett projekt i listan för att se sökväg och status.')
            return
        raw_path = current.data(Qt.UserRole)
        created = current.data(Qt.UserRole + 1) or 'Okänt datum'
        folder = Path(raw_path)
        if folder.is_dir():
            try:
                children = list(folder.iterdir())
                dirs = sum(1 for p in children if p.is_dir())
                files = sum(1 for p in children if p.is_file())
                state_str = f'Finns på disk ({dirs} undermappar, {files} filer i roten)'
            except OSError:
                state_str = 'Finns på disk'
        else:
            state_str = 'Mappen hittas inte på angiven sökväg'
        self.history_detail.setText(f'Projekt: {folder.name}\nSökväg: {folder}\nSkapad: {created}\nStatus: {state_str}')

    def _restore_history_columns(self):
        from historik import read_json_safe
        raw = read_json_safe(self.workspace.base / 'data/qt-history-columns.json', {})
        if not isinstance(raw, dict):
            return
        hdr = self.history_table.horizontalHeader()
        order = raw.get('visual_order')
        if isinstance(order, list) and sorted(order) == [0, 1, 2, 3]:
            for target_visual, logical in enumerate(order):
                current_visual = hdr.visualIndex(logical)
                if current_visual != target_visual:
                    hdr.moveSection(current_visual, target_visual)
        sort_col = raw.get('sort_column')
        sort_desc = raw.get('sort_desc', False)
        if isinstance(sort_col, int) and 0 <= sort_col < 4:
            self.history_table.sortByColumn(sort_col, Qt.DescendingOrder if sort_desc else Qt.AscendingOrder)

    def _save_history_columns(self):
        if not self.workspace.lock.is_primary or not hasattr(self, 'history_table'):
            return
        from historik import atomic_write_json
        hdr = self.history_table.horizontalHeader()
        order = [hdr.logicalIndex(v) for v in range(hdr.count())]
        atomic_write_json(
            self.workspace.base / 'data/qt-history-columns.json',
            dict(
                visual_order=order,
                sort_column=hdr.sortIndicatorSection(),
                sort_desc=hdr.sortIndicatorOrder() == Qt.DescendingOrder,
            ),
        )

    def _on_history_table_selected(self):
        if getattr(self, '_syncing_history', False):
            return
        row = self.history_table.currentRow()
        if row < 0:
            return
        item = self.history_table.item(row, 0)
        path = item.data(Qt.UserRole) if item else None
        if not path:
            return
        self._syncing_history = True
        try:
            for i in range(self.history_list.count()):
                li = self.history_list.item(i)
                if li and li.data(Qt.UserRole) == path:
                    self.history_list.setCurrentRow(i)
                    break
        finally:
            self._syncing_history = False

    def refresh_history(self):
        selected = self.history_list.currentItem()
        previous = selected.data(Qt.UserRole) if selected else None
        self._syncing_history = True
        try:
            self.history_list.clear()
            sorting = self.history_table.isSortingEnabled()
            self.history_table.setSortingEnabled(False)
            self.history_table.setRowCount(0)
            query = self.history_filter.text().casefold()
            rows = []
            for entry in self.workspace.history.get_all():
                path = entry['path']
                if query not in path.casefold():
                    continue
                created = str(entry.get('created', ''))
                item = QListWidgetItem(f'{Path(path).name}  ·  {created}\n{path}')
                item.setData(Qt.UserRole, path)
                item.setData(Qt.UserRole + 1, created)
                item.setToolTip(path)
                self.history_list.addItem(item)
                if previous == path:
                    self.history_list.setCurrentItem(item)
                folder = Path(path)
                status = 'Finns' if folder.is_dir() else 'Saknas'
                rows.append((folder.name, created, status, path))

            self.history_table.setRowCount(len(rows))
            for r, (name, created, status, path) in enumerate(rows):
                c0 = QTableWidgetItem(name)
                c0.setData(Qt.UserRole, path)
                c1 = QTableWidgetItem(created)
                c2 = QTableWidgetItem(status)
                c3 = QTableWidgetItem(path)
                for col, cell in enumerate((c0, c1, c2, c3)):
                    cell.setToolTip(path)
                    self.history_table.setItem(r, col, cell)
            self.history_table.setSortingEnabled(sorting)

            if self.history_list.count() and self.history_list.currentItem() is None:
                self.history_list.setCurrentRow(0)
            active_path = self.history_list.currentItem().data(Qt.UserRole) if self.history_list.currentItem() else None
            if active_path:
                for r in range(self.history_table.rowCount()):
                    cell = self.history_table.item(r, 0)
                    if cell and cell.data(Qt.UserRole) == active_path:
                        self.history_table.selectRow(r)
                        break
        finally:
            self._syncing_history = False
        self._update_history_detail(self.history_list.currentItem())

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
        dialog.setWindowTitle('Rensa cache & loggarkiv – smartfilter')
        dialog.setWindowIcon(self.windowIcon())
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('Daglig automatisk rensning behålls. Smartfiltret skyddar projekt, '
                               'inställningar, historik, uppdateringar och aktiva felloggar. '
                               'Arkiverade loggar äldre än 7 dagar rensas automatiskt.'))
        status = label(status_text(self.workspace.base))
        layout.addWidget(status)

        def clean():
            if QMessageBox.question(dialog, 'Rensa cache', 'Rensa gamla filer och loggarkiv äldre än 7 dagar enligt smartfiltret?',
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
        fit_to_screen(dialog, 560, 360)
        dialog.exec()
        dialog.deleteLater()

    def _sync_all_template_lists(self, selected_name=None):
        names = list(self.workspace.templates.list_templates())
        for combo in (self.templates, getattr(self, 'settings_profile_picker', None)):
            if combo is not None:
                current = selected_name or combo.currentText()
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(names)
                if current in names:
                    combo.setCurrentText(current)
                elif self.workspace.selected_profile() in names:
                    combo.setCurrentText(self.workspace.selected_profile())
                combo.blockSignals(False)
        self.refresh_profile_choices()
        if getattr(self, 'dialog', None) is not None:
            try:
                dlg_current = selected_name or self.dialog.template.currentText()
                self.dialog.template.blockSignals(True)
                self.dialog.template.clear()
                self.dialog.template.addItems(names)
                target_dlg = dlg_current if dlg_current in names else self.workspace.selected_profile()
                self.dialog.template.setCurrentText(target_dlg)
                self.dialog.template.blockSignals(False)
                self.dialog.refresh()
            except RuntimeError:
                pass

    def template_page(self):
        layout = page(self.tabs, 'Mallar')
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 3)

        left_card, left_body = card_frame()
        left_body.addWidget(label('Mallar & profiler', 'cardHeading'))
        left_body.addWidget(label('Välj en profil för att redigera och spara över den direkt, '
            'eller ange ett nytt namn för att skapa en ny profil.', 'mutedText'))
        left_body.addWidget(label('Befintlig mall / profil', 'mutedText'))
        self.templates = QComboBox()
        self.templates.addItems(list(self.workspace.templates.list_templates()))
        self.templates.setCurrentText(self.workspace.selected_profile())
        left_body.addWidget(self.templates)
        left_body.addWidget(label('Profilnamn', 'mutedText'))
        self.template_name = QLineEdit()
        self.template_name.setPlaceholderText('Behåll namnet för att spara över, eller skriv nytt namn')
        left_body.addWidget(self.template_name)
        left_body.addWidget(label('Sparplats för profilen', 'mutedText'))
        self.profile_root_edit = QLineEdit()
        self.profile_root_edit.setAccessibleName('Profilens sparplats')
        left_body.addWidget(self.profile_root_edit)

        def choose_profile_root():
            path = QFileDialog.getExistingDirectory(self, 'Välj profilens sparplats', self.profile_root_edit.text())
            if path:
                self.profile_root_edit.setText(path)
                self.profile_root_edit.setModified(True)

        button(left_body, 'Välj profilens sparplats…', choose_profile_root, 'folder', self._action_icons)
        button(left_body, 'Spara profil (mall + sparplats)', self._save_template_page_profile, 'save', self._action_icons)

        def set_default():
            self.default_profile.setCurrentText(self.templates.currentText())
            self.tabs.setCurrentIndex(4)
            if hasattr(self, 'settings_subtabs'):
                self.settings_subtabs.setCurrentIndex(0)
            self.statusBar().showMessage('Välj standardprofil och tryck Spara inställningar')

        button(left_body, 'Välj standardprofil i Inställningar…', set_default, 'settings', self._action_icons)
        button(left_body, 'Ta bort vald profil…', self._remove_template_page_profile, 'trash', self._action_icons)
        left_body.addStretch(1)
        grid.addWidget(left_card, 0, 0)

        right_card, right_body = card_frame()
        right_body.addWidget(label('Mappstruktur (indrag med 4 mellanslag per nivå)', 'cardHeading'))
        self.structure = QPlainTextEdit()
        self._mono_editors.append(self.structure)
        right_body.addWidget(self.structure, 1)
        grid.addWidget(right_card, 0, 1)
        layout.addLayout(grid, 1)

        self.templates.currentTextChanged.connect(self._load_template_into_editor)
        self._load_template_into_editor(self.templates.currentText())

    def _load_template_into_editor(self, name):
        self.template_name.setText(name)
        self.structure.setPlainText(self.workspace.templates.list_templates().get(name, ''))
        try:
            root = self.workspace.profile_root(name) if name else Path(self.workspace.config.save_root)
            self.profile_root_edit.setText(str(root))
        except ValueError:
            self.profile_root_edit.clear()
        self.profile_root_edit.setModified(False)
        self.template_name.setModified(False)
        self.structure.document().setModified(False)

    def _save_template_page_profile(self):
        try:
            self.workspace.require_lock()
            name = self.template_name.text().strip()
            overwrote = self.workspace.save_profile(name, self.structure.toPlainText(), self.profile_root_edit.text())
            self._sync_all_template_lists(name)
            self._load_template_into_editor(name)
            if hasattr(self, '_load_settings_profile'):
                self._load_settings_profile(name)
            action_msg = 'uppdaterades (sparades över)' if overwrote else 'skapades'
            try:
                from logg import resolve_matching_errors
                resolve_matching_errors(modules=('qt.profiles', 'qt.templates'))
            except Exception:
                pass
            self.statusBar().showMessage(f'Profilen "{name}" {action_msg}')
        except (OSError, ValueError, RuntimeError) as exc:
            logging.getLogger('qt.templates').exception('Mall kunde inte sparas')
            QMessageBox.warning(self, 'Kunde inte spara mall', str(exc))

    def _remove_template_page_profile(self):
        typed = self.template_name.text().strip()
        templates = self.workspace.templates.list_templates()
        target = next((k for k in templates if k.casefold() == typed.casefold()), None) or self.templates.currentText()
        if not target:
            return
        if QMessageBox.question(self, 'Ta bort profil?',
                f'Vill du ta bort profilen "{target}"?\nRedan skapade projektmappar på disken påverkas inte.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            fallback = self.workspace.delete_profile(target)
            self._sync_all_template_lists(fallback)
            self.select_profile(fallback)
            self._load_template_into_editor(self.templates.currentText())
            if hasattr(self, '_load_settings_profile'):
                self._load_settings_profile(self.settings_profile_picker.currentText())
            self.statusBar().showMessage(f'Profilen "{target}" togs bort. Aktiv profil: "{fallback}".')
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Kunde inte ta bort profil', str(exc))

    def export_page(self):
        layout = page(self.tabs, 'Exportera')
        card, body = card_frame()
        top_bar = QHBoxLayout()
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        info_col.addWidget(label('Exportera mappstruktur', 'cardHeading'))
        info_col.addWidget(label('Dra och släpp en mapp i fönstret eller välj den nedan för säker trälexport.', 'mutedText'))
        top_bar.addLayout(info_col, 1)

        def choose():
            folder = QFileDialog.getExistingDirectory(self, 'Välj mapp')
            if folder:
                self.start_export(Path(folder))

        def save():
            path, _ = QFileDialog.getSaveFileName(self, 'Spara struktur', 'struktur.txt', 'Text (*.txt)')
            if path:
                try:
                    Path(path).write_text(self.export_text.toPlainText(), encoding='utf-8')
                except OSError as exc:
                    logging.getLogger('qt.export').exception('Textfilen kunde inte sparas')
                    QMessageBox.warning(self, 'Kunde inte exportera', str(exc))

        button(top_bar, 'Välj mapp', choose, 'folder', self._action_icons)
        button(top_bar, 'Kopiera struktur', lambda: QApplication.clipboard().setText(self.export_text.toPlainText()), 'copy', self._action_icons)
        button(top_bar, 'Spara text…', save, 'save', self._action_icons)
        body.addLayout(top_bar)
        self.export_text = QPlainTextEdit()
        self.export_text.setReadOnly(True)
        self._mono_editors.append(self.export_text)
        body.addWidget(self.export_text, 1)
        layout.addWidget(card, 1)

    def settings_page(self):
        layout = page(self.tabs, 'Inställningar')
        self.settings_subtabs = QTabWidget()
        self.settings_subtabs.setObjectName('settingsSubtabs')
        self.settings_subtabs.setUsesScrollButtons(True)
        self.settings_subtabs.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

        # ── Underflik 1: Allmänt & Utseende (2 kolumner, noll scroll) ──
        general_tab = QWidget()
        general_outer = QVBoxLayout(general_tab)
        general_outer.setContentsMargins(8, 8, 8, 8)
        general_outer.setSpacing(10)
        gen_grid = QGridLayout()
        gen_grid.setSpacing(12)
        gen_grid.setColumnStretch(0, 1)
        gen_grid.setColumnStretch(1, 1)

        storage_card, storage_body = card_frame()
        storage_body.addWidget(label('Sparplats & projektflöde', 'cardHeading'))
        storage_body.addWidget(label('Standardprofil (reserv om senaste profil tagits bort)', 'mutedText'))
        self.default_profile = QComboBox()
        self.default_profile.setAccessibleName('Standardprofil')
        self.default_profile.addItems(list(self.workspace.templates.list_templates()))
        self.default_profile.setCurrentText(self.workspace.config.default_template)
        storage_body.addWidget(self.default_profile)
        storage_body.addWidget(label('Allmän sparplats (för äldre mallar utan egen profilsparplats)', 'mutedText'))
        root_row = QHBoxLayout()
        self.root_edit = QLineEdit(self.workspace.config.save_root)
        root_row.addWidget(self.root_edit, 1)

        def choose():
            path = QFileDialog.getExistingDirectory(self, 'Sparplats', self.root_edit.text())
            if path:
                self.root_edit.setText(path)

        button(root_row, 'Välj sparplats…', choose, 'folder', self._action_icons)
        storage_body.addLayout(root_row)
        self.open_after = QCheckBox('Öppna mappen efter skapande')
        self.open_after.setChecked(self.workspace.config.open_after_creation)
        self.plate_mode = QCheckBox('Normalisera registreringsnummer (t.ex. abc 123 → ABC123)')
        self.plate_mode.setChecked(self.workspace.config.plate_mode)
        storage_body.addWidget(self.open_after)
        storage_body.addWidget(self.plate_mode)
        button(storage_body, 'Skapa eller redigera profiler i underfliken Profiler →',
               lambda: self.settings_subtabs.setCurrentIndex(1), 'profiles', self._action_icons)
        storage_body.addStretch(1)
        gen_grid.addWidget(storage_card, 0, 0)

        display_card, display_body = card_frame()
        display_body.addWidget(label('Utseende, DPI-skärpa & autostart', 'cardHeading'))
        form_grid = QGridLayout()
        form_grid.setSpacing(8)
        form_grid.setColumnStretch(0, 1)
        form_grid.setColumnStretch(1, 1)
        self.theme = QComboBox()
        self.theme.addItems(['Dark', 'Light', 'System'])
        self.theme.setCurrentText(self.workspace.config.theme)
        self.text_size = QComboBox()
        self.text_size.addItems(['100%', '110%', '125%', '150%'])
        self.text_size.setCurrentText(self.workspace.config.text_size)
        form_grid.addWidget(label('Tema', 'mutedText'), 0, 0)
        form_grid.addWidget(label('Text- och UI-skala', 'mutedText'), 0, 1)
        form_grid.addWidget(self.theme, 1, 0)
        form_grid.addWidget(self.text_size, 1, 1)
        display_body.addLayout(form_grid)
        self.high_contrast = QCheckBox('Hög kontrast (7:1 tillgänglighetsläge)')
        self.high_contrast.setChecked(self.workspace.config.high_contrast)
        display_body.addWidget(self.high_contrast)

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
                logging.getLogger('qt.autostart').exception('Ändring av autostart misslyckades')
                QMessageBox.warning(self, 'Autostart misslyckades', str(exc))

        auto_row = QHBoxLayout()
        button(auto_row, 'Starta med operativsystemet…', lambda: startup(True))
        button(auto_row, 'Stäng av autostart…', lambda: startup(False))
        display_body.addLayout(auto_row)
        button(display_body, 'Fellista & loggar (rensa åtgärdade fel)…', self.diagnostics, 'refresh', self._action_icons)
        display_body.addStretch(1)
        gen_grid.addWidget(display_card, 0, 1)
        general_outer.addLayout(gen_grid, 1)

        def save():
            if not self.root_edit.text().strip():
                QMessageBox.warning(self, 'Sparplats', 'Välj en sparplats först.')
                return
            self.workspace.config.default_template = self.default_profile.currentText()
            self.workspace.config.save_root = self.root_edit.text().strip()
            self.workspace.config.open_after_creation = self.open_after.isChecked()
            self.workspace.config.plate_mode = self.plate_mode.isChecked()
            self.workspace.config.theme = self.theme.currentText()
            self.workspace.config.text_size = self.text_size.currentText()
            self.workspace.config.high_contrast = self.high_contrast.isChecked()
            self.save_settings()

        button(general_outer, 'Spara inställningar', save, 'save', self._action_icons)
        self.settings_subtabs.addTab(general_tab, 'Allmänt & Utseende')

        # ── Underflik 2: Profiler (egen dedikerad underflik i Inställningar) ──
        profiles_tab = QWidget()
        prof_grid = QGridLayout(profiles_tab)
        prof_grid.setContentsMargins(8, 8, 8, 8)
        prof_grid.setSpacing(12)
        prof_grid.setColumnStretch(0, 2)
        prof_grid.setColumnStretch(1, 3)

        prof_left, prof_left_body = card_frame()
        prof_left_body.addWidget(label('Skapa & hantera profiler', 'cardHeading'))
        prof_left_body.addWidget(label('Redigera och spara över befintliga profiler, skapa nya eller ta bort profiler du inte använder.', 'mutedText'))
        prof_left_body.addWidget(label('Utgå från befintlig profil / mall', 'mutedText'))
        self.settings_profile_picker = QComboBox()
        self.settings_profile_picker.setAccessibleName('Välj profil i Inställningar')
        self.settings_profile_picker.addItems(list(self.workspace.templates.list_templates()))
        self.settings_profile_picker.setCurrentText(self.workspace.selected_profile())
        prof_left_body.addWidget(self.settings_profile_picker)

        def start_blank_profile():
            self.settings_profile_name.clear()
            self.settings_profile_name.setPlaceholderText('Ange namn på ny profil, t.ex. Verkstad Örebro')
            self.settings_profile_root.setText(self.workspace.config.save_root)
            self.settings_profile_structure.setPlainText('Bilder/\nUnderlag/\nDokument/\n')
            self.settings_profile_name.setModified(True)
            self.settings_profile_name.setFocus()

        button(prof_left_body, 'Ny tom profil', start_blank_profile, 'create', self._action_icons)
        prof_left_body.addWidget(label('Profilens namn', 'mutedText'))
        self.settings_profile_name = QLineEdit()
        self.settings_profile_name.setAccessibleName('Ny eller vald profils namn')
        self.settings_profile_name.setPlaceholderText('Behåll namnet för att spara över, eller ange nytt namn')
        prof_left_body.addWidget(self.settings_profile_name)

        prof_left_body.addWidget(label('Profilens sparplats', 'mutedText'))
        prof_root_row = QHBoxLayout()
        self.settings_profile_root = QLineEdit()
        self.settings_profile_root.setAccessibleName('Sparplats för profil i Inställningar')
        prof_root_row.addWidget(self.settings_profile_root, 1)

        def choose_settings_profile_root():
            path = QFileDialog.getExistingDirectory(self, 'Välj sparplats för profilen', self.settings_profile_root.text())
            if path:
                self.settings_profile_root.setText(path)
                self.settings_profile_root.setModified(True)

        button(prof_root_row, 'Bläddra…', choose_settings_profile_root, 'folder', self._action_icons)
        prof_left_body.addLayout(prof_root_row)
        self.settings_profile_summary = label('', 'mutedText')
        prof_left_body.addWidget(self.settings_profile_summary)

        button(prof_left_body, 'Spara / spara över profil', self._save_settings_profile, 'save', self._action_icons)
        button(prof_left_body, 'Använd som aktiv & standardprofil', self._activate_settings_profile, 'profiles', self._action_icons)
        button(prof_left_body, 'Ta bort profil…', self._delete_settings_profile, 'trash', self._action_icons)
        button(prof_left_body, 'Återställ borttagna standardmallar', self._restore_builtin_profiles, 'undo', self._action_icons)
        prof_left_body.addStretch(1)
        prof_grid.addWidget(prof_left, 0, 0)

        prof_right, prof_right_body = card_frame()
        prof_right_body.addWidget(label('Profilens mappstruktur', 'cardHeading'))
        self.settings_profile_structure = QPlainTextEdit()
        self._mono_editors.append(self.settings_profile_structure)
        prof_right_body.addWidget(self.settings_profile_structure, 1)
        prof_grid.addWidget(prof_right, 0, 1)

        self.settings_profile_picker.currentTextChanged.connect(self._load_settings_profile)
        self.settings_profile_structure.textChanged.connect(self._update_settings_profile_summary)
        self._load_settings_profile(self.settings_profile_picker.currentText())
        self.settings_subtabs.addTab(profiles_tab, 'Profiler')
        layout.addWidget(self.settings_subtabs, 1)

        # ── Sida 5: Snabbtangent (2 kolumner, noll scroll) ──
        hk_layout = page(self.tabs, 'Snabbtangent')
        hk_grid = QGridLayout()
        hk_grid.setSpacing(12)
        hk_grid.setColumnStretch(0, 1)
        hk_grid.setColumnStretch(1, 1)

        hk_left, hk_left_body = card_frame()
        hk_left_body.addWidget(label('Global snabbtangent', 'cardHeading'))
        hk_left_body.addWidget(label('Visa FolderForge direkt var du än arbetar i systemet.', 'mutedText'))
        self.hotkey_status = label('Snabbtangenten registreras vid start…')
        hk_left_body.addWidget(self.hotkey_status)
        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText('ctrl+shift+m')
        hk_left_body.addWidget(self.hotkey_edit)

        def save_hotkey():
            try:
                if self._hotkeys is None:
                    raise RuntimeError('Snabbtangentsbryggan är inte startad')
                self._hotkeys.register(self.hotkey_edit.text().split('+'), save=True)
                self.hotkey_edit.setModified(False)
                self.statusBar().showMessage(self._hotkeys.last_status)
            except Exception as exc:
                logging.getLogger('qt.hotkey').exception('Kunde inte ändra snabbtangent')
                QMessageBox.warning(self, 'Snabbtangent', str(exc))

        button(hk_left_body, 'Spara snabbtangent', save_hotkey, 'save', self._action_icons)
        hk_left_body.addStretch(1)
        hk_grid.addWidget(hk_left, 0, 0)

        hk_right, hk_right_body = card_frame()
        hk_right_body.addWidget(label('Spela in kombination', 'cardHeading'))
        hk_right_body.addWidget(label('Klicka i rutan, tryck tangentkombinationen och överför den:', 'mutedText'))
        self.hotkey_recorder = QKeySequenceEdit()
        self.hotkey_recorder.setAccessibleName('Spela in snabbtangent')
        hk_right_body.addWidget(self.hotkey_recorder)

        def recorded():
            text = self.hotkey_recorder.keySequence().toString(QKeySequence.PortableText)
            if ',' in text:
                QMessageBox.warning(self, 'Snabbtangent', 'Använd en enda kombination, inte en sekvens.')
                return
            text = text.lower().replace('meta', 'cmd')
            self.hotkey_edit.setText(text)
            self.hotkey_edit.setModified(True)

        def reset_hotkey():
            from settings import DEFAULT_HOTKEY
            self.hotkey_edit.setText('+'.join(DEFAULT_HOTKEY))
            self.hotkey_edit.setModified(True)

        button(hk_right_body, 'Använd inspelad kombination', recorded, 'keyboard', self._action_icons)
        button(hk_right_body, 'Återställ standardkombination i fältet', reset_hotkey, 'undo', self._action_icons)
        hk_right_body.addStretch(1)
        hk_grid.addWidget(hk_right, 0, 1)
        hk_layout.addLayout(hk_grid)
        hk_layout.addStretch(1)

    def _update_settings_profile_summary(self):
        try:
            _, items = StructureEngine.parse_structure_text(self.settings_profile_structure.toPlainText())
            folders, files = StructureEngine.count_items(items)
            self.settings_profile_summary.setText(f'Struktur: {folders} mappar, {files} filer')
        except Exception as exc:
            self.settings_profile_summary.setText(str(exc))

    def _load_settings_profile(self, name):
        self.settings_profile_name.setText(name)
        self.settings_profile_structure.setPlainText(self.workspace.templates.list_templates().get(name, ''))
        try:
            root = self.workspace.profile_root(name) if name else Path(self.workspace.config.save_root)
            self.settings_profile_root.setText(str(root))
        except ValueError:
            self.profile_root_fallback = self.workspace.config.save_root
            self.settings_profile_root.clear()
        self.settings_profile_name.setModified(False)
        self.settings_profile_root.setModified(False)
        self.settings_profile_structure.document().setModified(False)
        self._update_settings_profile_summary()

    def _save_settings_profile(self):
        try:
            self.workspace.require_lock()
            name = self.settings_profile_name.text().strip()
            overwrote = self.workspace.save_profile(
                name,
                self.settings_profile_structure.toPlainText(),
                self.settings_profile_root.text(),
            )
            self._sync_all_template_lists(name)
            self._load_settings_profile(name)
            self._load_template_into_editor(name)
            action_msg = 'uppdaterades (sparades över)' if overwrote else 'skapades'
            try:
                from logg import resolve_matching_errors
                resolve_matching_errors(modules=('qt.profiles', 'qt.templates'))
            except Exception:
                pass
            self.statusBar().showMessage(f'Profilen "{name}" {action_msg}')
        except (OSError, ValueError, RuntimeError) as exc:
            logging.getLogger('qt.profiles').exception('Profil kunde inte sparas')
            QMessageBox.warning(self, 'Kunde inte spara profil', str(exc))

    def _activate_settings_profile(self):
        name = self.settings_profile_name.text().strip()
        if (self.settings_profile_name.isModified() or self.settings_profile_root.isModified()
                or self.settings_profile_structure.document().isModified()
                or name not in self.workspace.templates.list_templates()):
            self._save_settings_profile()
            if name not in self.workspace.templates.list_templates():
                return
        self.workspace.config.default_template = name
        self.default_profile.setCurrentText(name)
        self.select_profile(name)
        self.save_settings()
        self.statusBar().showMessage(f'"{name}" är nu aktiv och sparad som standardprofil')

    def _delete_settings_profile(self):
        typed = self.settings_profile_name.text().strip()
        templates = self.workspace.templates.list_templates()
        target = next((k for k in templates if k.casefold() == typed.casefold()), None) or self.settings_profile_picker.currentText()
        if not target:
            return
        if QMessageBox.question(self, 'Ta bort profil?',
                f'Vill du ta bort profilen "{target}"?\nRedan skapade projektmappar på disken påverkas inte.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            fallback = self.workspace.delete_profile(target)
            self._sync_all_template_lists(fallback)
            self.select_profile(fallback)
            self._load_settings_profile(self.settings_profile_picker.currentText())
            self._load_template_into_editor(self.templates.currentText())
            self.statusBar().showMessage(f'Profilen "{target}" togs bort. Aktiv profil: "{fallback}".')
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Kunde inte ta bort profil', str(exc))

    def _restore_builtin_profiles(self):
        try:
            restored = self.workspace.restore_builtin_profiles()
            if not restored:
                self.statusBar().showMessage('Alla standardmallar är redan synliga')
                return
            self._sync_all_template_lists(restored[0])
            self._load_settings_profile(self.settings_profile_picker.currentText())
            self._load_template_into_editor(self.templates.currentText())
            self.statusBar().showMessage('Återställde standardmallar: ' + ', '.join(restored))
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Kunde inte återställa standardmallar', str(exc))

    def toggle_theme(self):
        self.workspace.config.theme = 'Light' if self._dark_theme else 'Dark'
        self.theme.setCurrentText(self.workspace.config.theme)
        self.save_settings()

    def apply_accessibility(self):
        config = self.workspace.config
        factor = int(config.text_size.rstrip('%')) / 100
        dark = config.theme == 'Dark'
        if config.theme == 'System':
            dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        self._dark_theme = dark
        font = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
        families = set(QFontDatabase.families())
        if sys.platform == 'win32':
            for preferred in ('Segoe UI Variable Text', 'Segoe UI'):
                if preferred in families:
                    font.setFamily(preferred)
                    break
        font.setPointSizeF(11 * factor)
        font.setWeight(QFont.Normal)
        font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        if hasattr(QFont, 'HintingPreference'):
            font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
        self.setFont(font)
        mono = monospace_font(factor)
        for editor in self._mono_editors:
            editor.setFont(mono)
        family = font.family().replace('"', '')
        index = 1 if dark else 0
        background, foreground = UI_BACKGROUND[index], UI_TEXT[index]
        field, border, muted, accent = UI_SURFACE[index], UI_BORDER[index], UI_MUTED[index], UI_PRIMARY[index]
        focus = '#FFCE66' if dark else '#005FCC'
        alt_row = '#1D2C42' if dark else '#F7FAFE'
        if config.high_contrast:
            background, foreground, field, border, muted, accent, focus, alt_row = (
                '#000000', '#FFFFFF', '#000000', '#FFFFFF', '#FFFFFF', '#164B73', '#FFFF00', '#0A0A0A')

        # Växla vektor-logotyp efter aktivt tema så skärpa och kontrast är optimal utan vit ruta
        if getattr(self, '_logo_svg', None) is not None:
            svg_file = BASE_DIR / ('Icon/folderforge-logo-inverse.svg' if (dark or config.high_contrast) else 'Icon/folderforge-logo.svg')
            if svg_file.is_file():
                self._logo_svg.load(str(svg_file))
                self._logo_svg.renderer().setAspectRatioMode(Qt.KeepAspectRatio)
        self._logo_widget.setFixedSize(round(212 * factor), round(44 * factor))

        self.setStyleSheet(f"""
            QWidget {{ background: {background}; color: {foreground}; font-family: "{family}"; font-size: {round(15 * factor)}px; font-weight: 400; }}
            QFrame#appHeader {{ background: {field}; border-bottom: 1px solid {border}; }}
            QFrame#appFooter {{ background: {field}; border-top: 1px solid {border}; }}
            QFrame#appHeader QLabel, QFrame#appFooter QLabel {{ background: transparent; color: {muted}; }}
            QWidget#appLogo {{ background: transparent; border: none; }}
            QLabel#versionBadge {{ color: {muted}; font-weight: 600; font-size: {round(13 * factor)}px; padding: 2px 6px; border: 1px solid {border}; border-radius: 6px; }}
            QPushButton {{ background: {accent}; color: white; padding: 7px 12px; border: 1px solid transparent; border-radius: 8px; font-weight: 500; }}
            QPushButton:hover {{ border-color: {focus}; }}
            QPushButton#secondaryAction, QPushButton#navigationTab, QPushButton#damageChip {{ background: {field}; color: {foreground}; border: 1px solid {border}; }}
            QPushButton#primaryAction {{ background: {accent}; color: white; font-weight: 600; padding: 10px 14px; }}
            QPushButton#secondaryAction:hover, QPushButton#damageChip:hover {{ border: 1px solid {accent}; }}
            QPushButton#damageChip:checked {{ background: {accent}; color: white; border: 1px solid {accent}; font-weight: 600; }}
            QPushButton:disabled {{ background: {field}; color: {muted}; border: 1px solid {border}; }}
            QPushButton#navigationTab {{ font-weight: 600; padding: 7px 10px; }}
            QPushButton#navigationTab:checked {{ background: {accent}; color: white; border: 1px solid {accent}; }}
            QTabWidget#settingsSubtabs::pane {{ border: 1px solid {border}; border-radius: 10px; background: {background}; top: -1px; }}
            QTabBar::tab {{ background: {field}; color: {foreground}; border: 1px solid {border}; border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; padding: 7px 16px; margin-right: 4px; font-weight: 600; }}
            QTabBar::tab:selected {{ background: {accent}; color: white; border-color: {accent}; }}
            QLabel#mutedText {{ color: {muted}; }}
            QLabel#errorText {{ color: #E5534B; font-weight: 600; }}
            QLabel#previewBox {{ font-weight: 600; color: {foreground}; }}
            QLineEdit:selection, QPlainTextEdit:selection {{ background: {accent}; color: white; }}
            QToolTip {{ background: {field}; color: {foreground}; border: 1px solid {border}; padding: 6px; }}
            QLabel#updateSummary {{ color: {muted}; font-size: {round(13 * factor)}px; }}
            QPushButton:focus, QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QListWidget:focus, QTableWidget:focus {{ border: 2px solid {focus}; }}
            QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QTableWidget {{ background: {field}; padding: 6px 8px; border: 1px solid {border}; border-radius: 7px; alternate-background-color: {alt_row}; gridline-color: {border}; }}
            QHeaderView::section {{ background: {field}; color: {foreground}; font-weight: 700; padding: 6px 10px; border: none; border-right: 1px solid {border}; border-bottom: 2px solid {border}; }}
            QHeaderView::section:hover {{ background: {alt_row}; color: {accent}; }}
            QTableWidget::item {{ padding: 6px 8px; }}
            QTableWidget::item:selected {{ background: {accent}; color: white; }}
            QListWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {border}; }}
            QListWidget::item:selected {{ background: {accent}; color: white; }}
            QProgressBar {{ background: {field}; border: 1px solid {border}; border-radius: 6px; text-align: center; min-height: 18px; }}
            QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
            QLabel#pageHeading {{ font-size: {round(22 * factor)}px; font-weight: 700; }}
            QLabel#cardHeading {{ font-size: {round(16 * factor)}px; font-weight: 700; }}
            QFrame#projectCard {{ background: {field}; border: 1px solid {border}; border-radius: 12px; }}
            QFrame#projectCard QLabel {{ background: transparent; border: none; }}
            QStatusBar {{ color: {muted}; background: {field}; }}
            QMenu {{ background: {field}; border: 1px solid {border}; }}
            QMenu::item:selected {{ background: {accent}; color: white; }}
        """)
        self.tabs.dark_theme = dark or config.high_contrast
        self.tabs.setCurrentIndex(self.tabs.currentIndex())
        icon_size = QSize(round(22 * factor), round(22 * factor))
        for control in self.tabs.buttons:
            control.setIconSize(icon_size)
        for control, name in self._action_icons:
            variant = '-dark.svg' if control.objectName() == 'primaryAction' or dark or config.high_contrast else '-light.svg'
            control.setIcon(navigation_icon(name, variant))
            control.setIconSize(icon_size)
        update_variant = '-dark.svg' if dark or config.high_contrast else '-light.svg'
        refresh_icon = navigation_icon('refresh', update_variant)
        self._global_update_button.setIcon(refresh_icon if not refresh_icon.isNull() else self.style().standardIcon(QStyle.SP_BrowserReload))
        self._global_update_button.setIconSize(icon_size)
        if hasattr(self, 'settings_subtabs') and self.settings_subtabs.count() >= 2:
            self.settings_subtabs.setTabIcon(0, navigation_icon('settings', update_variant))
            self.settings_subtabs.setTabIcon(1, navigation_icon('profiles', update_variant))
            self.settings_subtabs.setIconSize(QSize(round(18 * factor), round(18 * factor)))
        self.theme_toggle.setFixedWidth(round(42 * factor))
        self.theme_toggle.setToolTip('Växla till ljust tema' if dark else 'Växla till mörkt tema')
        QTimer.singleShot(0, lambda: self.tabs.reflow(force=True))
        QTimer.singleShot(0, lambda: self.reflow_home(force=True))

    def save_settings(self):
        try:
            self.workspace.save_settings()
            self.apply_accessibility()
            self.refresh_profile_choices()
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
            dpr = max(1.0, self.devicePixelRatioF())
            target_px = max(240, round(240 * dpr))
            sharp_qr = pixmap.scaled(target_px, target_px, Qt.KeepAspectRatio, Qt.FastTransformation)
            sharp_qr.setDevicePixelRatio(dpr)
            qr.setPixmap(sharp_qr)
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
        dialog.deleteLater()

    def update_status(self):
        from updater import get_update_status, pending_ready_for_restart, read_state
        existing = getattr(self, '_update_dialog', None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
        dialog = QDialog(self)
        self._update_dialog = dialog
        dialog.setWindowTitle('Uppdateringsstatus')
        dialog.setWindowIcon(self.windowIcon())
        layout = QVBoxLayout(dialog)
        headline = label('', 'cardHeading')
        layout.addWidget(headline)
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        layout.addWidget(progress)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setFont(monospace_font())
        layout.addWidget(text, 1)
        explanation = label('', 'mutedText')
        layout.addWidget(explanation)

        def restart():
            if QMessageBox.question(dialog, 'Installera hämtad uppdatering?',
                    'Läs ändringslistan ovan. Appen stängs och startas om dold i systemfältet. '
                    'Vid lyckad start tas säkerhetskopian bort automatiskt. Projekt, profiler och historik behålls. Fortsätt?',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
                dialog.accept()
                QTimer.singleShot(0, self.restart_update)

        restart_button = button(layout, 'Installera hämtad uppdatering och starta om…', restart)
        restart_button.setObjectName('installUpdate')

        def refresh():
            report = get_update_status(self.workspace.base, APP_VERSION)
            raw = read_state(self.workspace.base)
            headline.setText(report.get('Status', ''))
            received = raw.get('downloaded', 0)
            total = raw.get('download_total')
            status_code = raw.get('status')
            if status_code in {'checking', 'resolving', 'comparing', 'verifying'}:
                progress.setRange(0, 0)
                progress.setVisible(True)
            elif status_code == 'downloading':
                if isinstance(total, (int, float)) and total > 0:
                    progress.setRange(0, 100)
                    progress.setValue(min(100, int(received * 100 / total)))
                else:
                    progress.setRange(0, 0)
                progress.setVisible(True)
            else:
                progress.setRange(0, 100)
                progress.setValue(100 if pending_ready_for_restart(self.workspace.base) else 0)
                progress.setVisible(pending_ready_for_restart(self.workspace.base))
            formatted = '\n\n'.join(f'{key}: {val}' for key, val in report.items())
            if text.toPlainText() != formatted:
                bar = text.verticalScrollBar()
                position = bar.value()
                text.setPlainText(formatted)
                bar.setValue(position)
            ready = pending_ready_for_restart(self.workspace.base)
            restart_button.setEnabled(ready)
            explanation.setText(
                'Uppdateringen är SHA-256-verifierad. Stäng detta fönster för automatisk omstart, '
                'eller klicka på Installera ovan. Backupen rensas automatiskt när starten bekräftats.' if ready else
                'Uppdateraren jämför releasetagg, commit-ID och varje appfils SHA-256 mot den publicerade latest-releasen.'
            )

        timer = QTimer(dialog)
        timer.setTimerType(Qt.CoarseTimer)
        timer.timeout.connect(refresh)
        timer.start(1000)
        refresh()
        btn_row = QHBoxLayout()
        button(btn_row, 'Sök uppdatering nu', lambda: self._check_updates(False))
        button(btn_row, 'Stäng', dialog.reject)
        layout.addLayout(btn_row)
        fit_to_screen(dialog, 720, 640)
        dialog.exec()
        timer.stop()
        self._update_dialog = None
        dialog.deleteLater()
        self.refresh_update_summary(force=True)

    def restart_update(self):
        from updater import pending_ready_for_restart
        if not pending_ready_for_restart(self.workspace.base):
            QMessageBox.information(self, 'Uppdatering', 'Ingen verifierad uppdatering är redo att installeras.')
            return
        if not self.can_restart():
            QMessageBox.information(self, 'Omstart väntar',
                'Spara ändrade inställningar, profiler/mallar eller snabbtangent och stäng projektdialoger. '
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
        self.statusBar().showMessage('Söker uppdatering – hämtning och filjämförelse visas i Uppdateringsstatus')
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
        self.statusBar().showMessage('Struktur klar – du kan kopiera eller spara texten')

    def export_failed(self, message):
        self._busy_tasks = max(0, self._busy_tasks - 1)
        QMessageBox.warning(self, 'Export misslyckades', message)

    def can_restart(self):
        if any(isinstance(widget, QDialog) and widget.isVisible() for widget in QApplication.topLevelWidgets()):
            return False
        config = self.workspace.config
        settings_prof_dirty = (
            hasattr(self, 'settings_profile_name') and (
                self.settings_profile_name.isModified()
                or self.settings_profile_root.isModified()
                or self.settings_profile_structure.document().isModified()
            )
        )
        return (self._busy_tasks == 0 and not self.structure.document().isModified()
                and not self.profile_root_edit.isModified() and not self.template_name.isModified()
                and not settings_prof_dirty
                and self.default_profile.currentText() == config.default_template
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
        dialog.setWindowIcon(self.windowIcon())
        dialog.exec()
        dialog.deleteLater()

    def export_diagnostics(self):
        from qt_help import DiagnosticsDialog
        dialog = DiagnosticsDialog(self)
        dialog.setWindowIcon(self.windowIcon())
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

    save_settings_profile = property(lambda self: self._save_settings_profile)
    delete_settings_profile = property(lambda self: self._delete_settings_profile)


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

