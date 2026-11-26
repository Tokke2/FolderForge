"""Qt troubleshooting UI with sortable/movable error columns and resolved-error cleanup."""
import json
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QFontDatabase, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from qt_preview import fit_to_screen


class _NumericTableItem(QTableWidgetItem):
    def __init__(self, value: int):
        super().__init__(str(value))
        self._num = int(value)

    def __lt__(self, other):
        if isinstance(other, _NumericTableItem):
            return self._num < other._num
        return super().__lt__(other)


class DiagnosticsDialog(QDialog):
    COLUMNS = ('Nivå', 'Antal', 'Senaste', 'Modul', 'Felmeddelande')

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('FolderForge – felsökning och fellista')
        self.digest = None
        self.issues = []
        self.visible = []
        self.current_id = None
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        notice = QLabel(
            'Aktiv fellogg (logs/folderforge-errors.log) och komplett applogg (logs/folderforge.log).\n'
            'Gårdagens applogg arkiveras dagligen och arkiv äldre än 7 dagar raderas automatiskt.\n'
            'När ett fel har åtgärdats kan du rensa bort valt fel eller alla åtgärdade fel ur felloggen.\n'
            'Tips: Klicka på kolumnrubrikerna för att sortera eller dra rubrikerna för att flytta kolumner.'
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        filters = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText('Sök i fel, modul eller traceback…')
        self.level = QComboBox()
        self.level.addItems(['Alla nivåer', 'WARNING', 'ERROR', 'CRITICAL'])
        filters.addWidget(self.query, 1)
        filters.addWidget(self.level)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionsMovable(True)
        hdr.setSectionsClickable(True)
        hdr.setStretchLastSection(True)
        for col in range(len(self.COLUMNS) - 1):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table, 1)

        # Synkad QListWidget för bakåtkompatibilitet vid skriptad åtkomst
        self.list = QListWidget()
        self.list.setVisible(False)
        layout.addWidget(self.list)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        mono.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        self.details.setFont(mono)
        layout.addWidget(self.details, 1)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.table.itemSelectionChanged.connect(self._on_table_selection)
        self.list.currentRowChanged.connect(self.select)
        self.query.textChanged.connect(self.filter)
        self.level.currentTextChanged.connect(self.filter)

        action_row_1 = QHBoxLayout()
        for title, callback in [
            ('Uppdatera', self.refresh),
            ('Markera valt fel åtgärdat…', self.resolve),
            ('Rensa alla åtgärdade fel…', self.resolve_all),
        ]:
            btn = QPushButton(title)
            btn.clicked.connect(callback)
            action_row_1.addWidget(btn)
        layout.addLayout(action_row_1)

        action_row_2 = QHBoxLayout()
        for title, callback in [
            ('Öppna fellogg', self._open_error_log),
            ('Öppna applogg', self._open_app_log),
            ('Start-/systemkontroll', self.system_check),
            ('Exportera ZIP…', self.export),
        ]:
            btn = QPushButton(title)
            btn.clicked.connect(callback)
            action_row_2.addWidget(btn)
        layout.addLayout(action_row_2)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.CoarseTimer)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()
        fit_to_screen(self, 900, 740)

    def _base_dir(self) -> Path:
        parent = self.parentWidget()
        if parent is not None and hasattr(parent, 'workspace'):
            return Path(parent.workspace.base)
        from settings import BASE_DIR
        return Path(BASE_DIR)

    def _open_error_log(self):
        path = self._base_dir() / 'logs/folderforge-errors.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_app_log(self):
        path = self._base_dir() / 'logs/folderforge.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def refresh(self):
        from logg import get_error_issues
        try:
            issues, digest = get_error_issues()
            if digest == self.digest:
                return
            self.issues, self.digest = issues, digest
            self.filter()
        except OSError as exc:
            self.summary.setText(f'Kunde inte läsa felloggen: {exc}')

    def filter(self):
        from logg import filter_error_issues
        selected = self.current_id
        self.visible = filter_error_issues(self.issues, self.query.text(), self.level.currentText())

        self.list.blockSignals(True)
        self.list.clear()
        for issue in self.visible:
            self.list.addItem(f"{issue['level']} · {issue['count']} gånger · {issue['module']} · {issue['message']}")

        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.visible))
        selected_row = -1
        for row, issue in enumerate(self.visible):
            lvl = QTableWidgetItem(str(issue['level']))
            lvl.setData(Qt.UserRole, issue['id'])
            cnt = _NumericTableItem(int(issue['count']))
            last = QTableWidgetItem(str(issue['last']))
            mod = QTableWidgetItem(str(issue['module']))
            msg = QTableWidgetItem(str(issue['message']))
            for col, item in enumerate((lvl, cnt, last, mod, msg)):
                self.table.setItem(row, col, item)
            if issue['id'] == selected:
                selected_row = row
        if selected_row == -1 and self.visible:
            selected_row = 0
        self.table.blockSignals(False)
        self.table.setSortingEnabled(sorting)

        if 0 <= selected_row < self.table.rowCount():
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 0)
                if item and item.data(Qt.UserRole) == (selected or self.visible[0]['id']):
                    self.table.selectRow(r)
                    break
        else:
            self.current_id = None
            self.details.clear()

        list_idx = next((n for n, issue in enumerate(self.visible) if issue['id'] == self.current_id), -1)
        self.list.setCurrentRow(list_idx)
        self.list.blockSignals(False)

        self.summary.setText(
            f'{len(self.visible)} visade aktiva felgrupper av {len(self.issues)}. '
            'Åtgärdade fel tas bort ur felloggen och raderas automatiskt ur arkivet efter 7 dagar.'
        )

    def _on_table_selection(self):
        row = self.table.currentRow()
        if row < 0:
            self.current_id = None
            self.details.clear()
            return
        item = self.table.item(row, 0)
        issue_id = item.data(Qt.UserRole) if item else None
        issue = next((it for it in self.visible if it['id'] == issue_id), None)
        if issue is not None:
            self.current_id = issue['id']
            self.details.setPlainText(f"Första: {issue['first']}\nSenaste: {issue['last']}\n\n{issue['text']}")
        else:
            self.current_id = None
            self.details.clear()

    def select(self, index):
        if 0 <= index < len(self.visible):
            issue = self.visible[index]
            self.current_id = issue['id']
            self.details.setPlainText(f"Första: {issue['first']}\nSenaste: {issue['last']}\n\n{issue['text']}")
        else:
            self.current_id = None
            self.details.clear()

    def resolve(self):
        if not self.current_id:
            QMessageBox.information(self, 'Inget fel markerat', 'Markera ett åtgärdat fel i tabellen först.')
            return
        from logg import resolve_error_issue
        if QMessageBox.question(
            self, 'Ta bort åtgärdat fel ur felloggen?',
            'Detta rensar bort det markerade felet ur den aktiva felloggen (folderforge-errors.log).\n'
            'En arkivkopia sparas i resolved-errors i 7 dagar innan den raderas. Fortsätt?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            resolve_error_issue(self.current_id, self.digest)
            self.digest = None
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Rensning stoppad', str(exc))
        self.refresh()

    def resolve_all(self):
        if not self.issues:
            QMessageBox.information(self, 'Felloggen är tom', 'Inga aktiva fel finns att rensa.')
            return
        from logg import archive_resolved_errors
        if QMessageBox.question(
            self, 'Rensa alla åtgärdade fel ur felloggen?',
            f'Detta tömmer samtliga {len(self.issues)} aktiva felgrupper ur folderforge-errors.log.\n'
            'Arkivkopian sparas i resolved-errors i 7 dagar och raderas därefter automatiskt. Fortsätt?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            archive_resolved_errors(expected_digest=self.digest)
            self.digest = None
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Rensning stoppad', str(exc))
        self.refresh()

    def display_report(self):
        from qt_diagnostics import startup_report
        from PySide6.QtCore import qVersion
        report = startup_report(self._base_dir(), 'manual-system-check')
        report['qt_version'] = qVersion()
        report['screens'] = [dict(width=s.availableGeometry().width(), height=s.availableGeometry().height(),
                                  dpi=round(s.logicalDotsPerInch(), 2), ratio=s.devicePixelRatio())
                             for s in QApplication.screens()]
        return report

    def system_check(self):
        self.timer.stop()
        try:
            self.details.setPlainText(json.dumps(self.display_report(), ensure_ascii=False, indent=2))
        except Exception as exc:
            QMessageBox.warning(self, 'Systemkontroll misslyckades', str(exc))

    def export(self):
        from logg import export_diagnostic_package
        if QMessageBox.question(
            self, 'Exportera lokalt felsökningspaket?',
            'ZIP-filen innehåller loggar, fel, tolk-/paketversioner, uppdateringsstatus och skärmdata.\n'
            'Personliga sökvägar och feltexter kan finnas. Inga projektfiler eller '
            'inställningsfiler samlas in och ingenting skickas. Granska ZIP-filen innan delning.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Spara felsökningspaket', 'FolderForge-felsokning.zip', 'ZIP (*.zip)')
        if not path:
            return
        try:
            export_diagnostic_package(path, self.display_report())
            QMessageBox.information(self, 'Export klar', f'Sparad lokalt:\n{path}\nIngenting har skickats.')
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Export misslyckades', str(exc))
