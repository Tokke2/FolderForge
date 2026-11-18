"""Qt-safe global shortcut bridge. Registration errors are logged, never hidden."""
import logging
from PySide6.QtCore import QObject, Signal
from app_core import validate_hotkey_combo, hotkey_expression
from historik import read_json_safe, atomic_write_json
from settings import HOTKEY_CONFIG, DEFAULT_HOTKEY


class HotkeyBridge(QObject):
    activated = Signal()
    status = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.listener = None
        data = read_json_safe(HOTKEY_CONFIG, {})
        keys = data.get('hotkey', DEFAULT_HOTKEY) if isinstance(data, dict) else DEFAULT_HOTKEY
        ok, normalized, error = validate_hotkey_combo(keys)
        self.keys = normalized if ok else list(DEFAULT_HOTKEY)
        self.activated.connect(parent.restore)
        self.last_status = ''

    def register(self, keys=None, save=False):
        ok, normalized, error = validate_hotkey_combo(keys if keys is not None else self.keys)
        if not ok:
            raise ValueError(error)
        expression = hotkey_expression(normalized)
        from pynput import keyboard
        keyboard.HotKey.parse(expression)
        if save and not atomic_write_json(HOTKEY_CONFIG, {'hotkey': normalized}):
            raise OSError('Snabbtangenten kunde inte sparas')
        if self.listener is not None:
            self.listener.stop()
        self.listener = keyboard.GlobalHotKeys({expression: self.activated.emit})
        self.listener.start()
        self.keys = normalized
        self.last_status = 'Snabbtangent aktiv: ' + ' + '.join(normalized)
        self.status.emit(self.last_status)

    def start(self):
        try:
            self.register()
        except Exception as exc:
            self.last_status = 'Snabbtangent ej tillgänglig: ' + str(exc)
            logging.getLogger('qt.hotkey').warning(self.last_status, exc_info=True)
            self.status.emit(self.last_status)

    def stop(self):
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
