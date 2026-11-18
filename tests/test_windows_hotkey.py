"""Pure Windows key translation tests; native registration is checked in Qt CI."""
import ast
from pathlib import Path
import unittest

source = Path('qt_integrations.py').read_text(encoding='utf-8')
node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'windows_hotkey_spec')
namespace = {}
exec(compile(ast.Module(body=[node], type_ignores=[]), 'qt_integrations.py', 'exec'), namespace)
spec = namespace['windows_hotkey_spec']


class WindowsHotkeyTests(unittest.TestCase):
    def test_standard_combination(self):
        self.assertEqual(spec(['ctrl', 'alt', 'm']), (0x4003, ord('M')))

    def test_function_and_windows_keys(self):
        self.assertEqual(spec(['win', 'shift', 'f12']), (0x400C, 0x7B))
        self.assertEqual(spec(['ctrl', 'space']), (0x4002, 0x20))

    def test_unsupported_or_multiple_main_keys_fail_explicitly(self):
        for keys in (['ctrl'], ['ctrl', 'm', 'n'], ['ctrl', 'å'], ['ctrl', 'f25']):
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                spec(keys)

    def test_windows_backend_uses_native_api_without_pynput(self):
        self.assertIn("if sys.platform == 'win32':", source)
        self.assertIn('RegisterHotKey(None, identifier, flags, key)', source)
        self.assertIn('removeNativeEventFilter(self)', source)
        branch = source.split("if sys.platform == 'win32':", 1)[1].split('else:', 1)[0]
        self.assertNotIn('pynput', branch)
