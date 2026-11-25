"""Qt-safe global shortcut bridge. Registration errors are logged, never hidden."""
import logging
import sys
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
        if self.listener is not None and normalized == self.keys:
            if save and not atomic_write_json(HOTKEY_CONFIG, {'hotkey': normalized}):
                raise OSError('Snabbtangenten kunde inte sparas')
            return
        if sys.platform == 'win32':
            identifier = 0x4F01 if getattr(self.listener, 'identifier', 0) != 0x4F01 else 0x4F02
            replacement = WindowsHotkey(normalized, self.activated.emit, identifier)
        else:
            from pynput import keyboard
            expression = hotkey_expression(normalized)
            keyboard.HotKey.parse(expression)
            replacement = keyboard.GlobalHotKeys({expression: self.activated.emit})
            replacement.start()
        if save and not atomic_write_json(HOTKEY_CONFIG, {'hotkey': normalized}):
            replacement.stop()
            raise OSError('Snabbtangenten kunde inte sparas')
        if self.listener is not None:
            self.listener.stop()
        self.listener = replacement
        self.keys = normalized
        self.last_status = 'Snabbtangent aktiv: ' + ' + '.join(normalized) + (' (Windows inbyggda stöd)' if sys.platform == 'win32' else '')
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


def windows_hotkey_spec(keys):
    """Translate validated names to RegisterHotKey flags without third-party hooks."""
    modifiers = {'ctrl': 2, 'control': 2, 'alt': 1, 'option': 1,
                 'shift': 4, 'cmd': 8, 'command': 8, 'win': 8, 'super': 8}
    special = {'space': 0x20, 'enter': 0x0D, 'return': 0x0D, 'tab': 9,
               'esc': 0x1B, 'escape': 0x1B, 'home': 0x24, 'end': 0x23,
               'page_up': 0x21, 'page_down': 0x22, 'up': 0x26, 'down': 0x28,
               'left': 0x25, 'right': 0x27, 'insert': 0x2D, 'delete': 0x2E,
               'backspace': 8}
    flags, key = 0, None
    for name in keys:
        if name in modifiers:
            flags |= modifiers[name]
            continue
        if key is not None:
            raise ValueError('Windows-snabbtangenten får ha en huvudtangent och valfria modifierare.')
        if len(name) == 1 and name.isascii() and name.isalnum():
            key = ord(name.upper())
        elif name.startswith('f') and name[1:].isdigit() and 1 <= int(name[1:]) <= 24:
            key = 0x70 + int(name[1:]) - 1
        else:
            key = special.get(name)
        if key is None:
            raise ValueError('Tangenten stöds inte av Windows-snabbtangenten: ' + name)
    if key is None:
        raise ValueError('Välj en huvudtangent, till exempel M.')
    return flags | 0x4000, key  # MOD_NOREPEAT


from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication


class WindowsHotkey(QAbstractNativeEventFilter):
    """GUI-thread RegisterHotKey/WM_HOTKEY. No pynput, listener thread or console."""
    def __init__(self, keys, callback, identifier):
        super().__init__()
        import ctypes
        from ctypes import wintypes
        self._msg_type = wintypes.MSG
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        self.api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.api.RegisterHotKey.restype = wintypes.BOOL
        self.api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.UnregisterHotKey.restype = wintypes.BOOL
        self.identifier = identifier
        self.callback = callback
        self.active = False
        flags, key = windows_hotkey_spec(keys)
        if not self.api.RegisterHotKey(None, identifier, flags, key):
            code = ctypes.get_last_error()
            raise OSError(code, 'Windows kunde inte registrera snabbtangenten. '
                          'Den kan vara upptagen av ett annat program eller reserverad av Windows.')
        self.active = True
        QCoreApplication.instance().installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if self.active and message and event_type in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
            addr = int(message)
            if addr:
                msg = self._msg_type.from_address(addr)
                if msg.message == 0x0312 and msg.wParam == self.identifier:
                    self.callback()
                    return True, 0
        return False, 0

    def stop(self):
        if self.active:
            self.api.UnregisterHotKey(None, self.identifier)
            self.active = False
            QCoreApplication.instance().removeNativeEventFilter(self)
