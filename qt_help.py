"""Qt troubleshooting UI using the existing persistent error archive and export."""
import json
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPlainTextEdit, QPushButton, QVBoxLayout)

from qt_preview import fit_to_screen


class DiagnosticsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('FolderForge – felsökning och fellista')
        self.digest = None
        self.issues = []
        self.current_id = None
        layout = QVBoxLayout(self)
        notice = QLabel('Lokala fel och startdiagnostik. Inget skickas automatiskt.\n'
                        'Markera ett fel för hela tracebacken. Export kan innehålla personliga sökvägar.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        filters = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText('Sök i fel, modul eller traceback…')
        self.level = QComboBox()
        self.level.addItems(['Alla nivåer', 'WARNING', 'ERROR', 'CRITICAL'])
        filters.addWidget(self.query)
        filters.addWidget(self.level)
        layout.addLayout(filters)
        self.list = QListWidget()
        layout.addWidget(self.list)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.list.currentRowChanged.connect(self.select)
        self.query.textChanged.connect(self.filter)
        self.level.currentTextChanged.connect(self.filter)
        for title, callback in [('Uppdatera', self.refresh), ('Markera valt fel åtgärdat…', self.resolve),
                                ('Start-/systemkontroll', self.system_check), ('Exportera ZIP…', self.export)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            layout.addWidget(button)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()
        fit_to_screen(self, 800, 720)

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
        index = next((n for n, issue in enumerate(self.visible) if issue['id'] == selected), -1)
        self.list.setCurrentRow(index)
        self.list.blockSignals(False)
        self.select(index)
        self.summary.setText(f'{len(self.visible)} visade felgrupper av {len(self.issues)}. '
                             'Åtgärdade fel arkiveras; nytillkomna fel stoppar samtidig arkivering.')

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
            return
        from logg import resolve_error_issue
        if QMessageBox.question(self, 'Arkivera valt fel?',
                'Detta markerar felet åtgärdat i listan, men reparerar inte orsaken.\n'
                'Originalet sparas i resolved-errors. Fortsätt?', QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            resolve_error_issue(self.current_id, self.digest)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Arkivering stoppad', str(exc))
        self.refresh()

    def display_report(self):
        from qt_diagnostics import startup_report
        from settings import BASE_DIR
        from PySide6.QtCore import qVersion
        report = startup_report(BASE_DIR, 'manual-system-check')
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
        if QMessageBox.question(self, 'Exportera lokalt felsökningspaket?',
                'ZIP-filen innehåller loggar, fel, tolk-/paketversioner, uppdateringsstatus och skärmdata.\n'
                'Personliga sökvägar och feltexter kan finnas. Inga projektfiler eller '
                'inställningsfiler samlas in och ingenting skickas. Granska ZIP-filen innan delning.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Spara felsökningspaket', 'FolderForge-felsokning.zip', 'ZIP (*.zip)')
        if not path:
            return
        try:
            export_diagnostic_package(path, self.display_report())
            QMessageBox.information(self, 'Export klar', f'Sparad lokalt:\n{path}\nIngenting har skickats.')
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Export misslyckades', str(exc))
