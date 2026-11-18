import json
import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch
from os_startup import configure_autostart


class StartupTests(unittest.TestCase):
    def test_linux_explicit_enable_disable_and_quoted_app_path(self):
        with tempfile.TemporaryDirectory() as temp:
            base = (Path(temp) / 'App with spaces').resolve()
            with patch.dict(os.environ, XDG_CONFIG_HOME=temp):
                result = configure_autostart(True, base, system='linux')
                path = Path(temp) / 'autostart/FolderForge.desktop'
                self.assertTrue(result['ok'])
                text = path.read_text()
                self.assertIn('Terminal=false', text)
                self.assertIn('Exec=/bin/sh "' + str(base).replace('\\', '\\\\'), text)
                self.assertTrue(configure_autostart(False, base, system='linux')['ok'])
                self.assertFalse(path.exists())

    def test_macos_explicit_user_login_agent(self):
        with tempfile.TemporaryDirectory() as temp, patch('os_startup.Path.home', return_value=Path(temp)):
            base = (Path(temp) / 'FolderForge').resolve()
            self.assertTrue(configure_autostart(True, base, system='darwin')['ok'])
            path = Path(temp) / 'Library/LaunchAgents/se.folderforge.autostart.plist'
            data = plistlib.loads(path.read_bytes())
            self.assertEqual(data['ProgramArguments'], ['/bin/sh', str(base / 'Starta-FolderForge.sh')])
            self.assertTrue(data['RunAtLoad'])
            self.assertTrue(configure_autostart(False, base, system='darwin')['ok'])
            self.assertFalse(path.exists())

    def test_unsupported_os_does_not_write(self):
        with self.assertRaises(ValueError):
            configure_autostart(True, system='unsupported')
