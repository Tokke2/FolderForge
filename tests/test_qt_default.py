"""Default routing, explicit reserve, update diagnostics and privacy contracts."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import updater
from qt_diagnostics import save_startup_report


class QtDefaultTests(unittest.TestCase):
    def test_default_dispatch_is_before_tk_imports_and_reserve_is_explicit(self):
        source = Path('folder.pyw').read_text()
        self.assertLess(source.index('from gui_entry import main'), source.index('import tkinter'))
        self.assertIn("environ.get('FOLDERFORGE_GUI') != 'tk'", source)
        reserve = Path('Starta-FolderForge-Tk.py').read_text()
        self.assertIn("os.environ['FOLDERFORGE_GUI'] = 'tk'", reserve)
        self.assertNotIn('pip install', reserve)

    @unittest.skipIf(os.name == 'nt', 'POSIX unit branch; native Windows bootstrap covered separately')
    def test_entry_calls_qt_without_importing_or_starting_tk(self):
        import gui_entry
        run = Mock(return_value=0)
        with patch.dict('sys.modules', {'logg': SimpleNamespace(init_logging=Mock()),
                'qt_app': SimpleNamespace(run=run),
                'qt_diagnostics': SimpleNamespace(save_startup_report=Mock())}):
            self.assertEqual(gui_entry.main(), 0)
        run.assert_called_once()

    def test_local_startup_report_has_no_environment_or_project_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'data').mkdir()
            (root / 'data/settings.json').write_text('{"secret": "PRIVATE_PROJECT_NAME"}')
            with patch.dict(os.environ, SECRET_DIAG_TEST='PRIVATE_TOKEN'):
                report = save_startup_report(root, 'ready')
            text = json.dumps(report)
            self.assertNotIn('PRIVATE_TOKEN', text)
            self.assertNotIn('PRIVATE_PROJECT_NAME', text)
            self.assertEqual(report['gui'], 'Qt')
            self.assertEqual(json.loads((root / 'logs/startup-diagnostics.json').read_text())['phase'], 'ready')

    def test_shared_hotkeys_execute_in_the_real_module_namespace(self):
        from app_core import validate_hotkey_combo, hotkey_expression
        valid, keys, error = validate_hotkey_combo(['ctrl', 'alt', 'm'])
        self.assertTrue(valid, error)
        self.assertEqual(hotkey_expression(keys), '<ctrl>+<alt>+m')

    def test_manifest_diagnostics_name_only_real_modified_app_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in updater.FILES:
                (root / name).write_text('# app')
            manifest = updater.content_manifest(root)
            (root / 'settings.py').write_text('# changed')
            self.assertEqual(updater.manifest_differences(root, manifest), ['settings.py'])
            manifest['../outside'] = 'anything'
            self.assertEqual(updater.manifest_differences(root, manifest), ['otillåten manifestsökväg'])

    def test_default_runtime_has_real_update_acknowledgement_and_deferred_restart(self):
        source = Path('qt_preview.py').read_text()
        for token in ('apply_pending(ROOT)', 'confirm_startup(ROOT)', 'window.can_restart()',
                      'launch_update_trial(ROOT', 'restart_timer.start(2000)'):
            self.assertIn(token, source)


class ProductNameTests(unittest.TestCase):
    def test_production_uses_product_name_without_gui_framework(self):
        source = Path('qt_app.py').read_text(encoding='utf-8')
        self.assertIn("self.setWindowTitle(f'FolderForge {APP_VERSION}')", source)
        self.assertIn("self.exit_action.setText('Avsluta FolderForge')", source)
        for old in ('Skapa standardprojekt – Qt', 'Avsluta FolderForge Qt',
                    'Uppdateringsstatus – Qt', 'FolderForge {APP_VERSION} · Qt'):
            self.assertNotIn(old, source)
        self.assertIn("tray.setToolTip('FolderForge' if production", Path('qt_preview.py').read_text(encoding='utf-8'))


class FamiliarDesignTests(unittest.TestCase):
    def test_production_reuses_legacy_design_palette_and_shell(self):
        source = Path('qt_app.py').read_text(encoding='utf-8')
        for shared in ('UI_BACKGROUND[index]', 'UI_SURFACE[index]', 'UI_BORDER[index]',
                       'UI_TEXT[index]', 'UI_MUTED[index]', 'UI_PRIMARY[index]'):
            self.assertIn(shared, source)
        for element in ('appHeader', 'appFooter', 'appLogo', 'projectCard', 'navigationTab',
                        'folderforge-logo.svg', 'Minimera till fältet'):
            self.assertIn(element, source)
