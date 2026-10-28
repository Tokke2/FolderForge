# folder.pyw
# -*- coding: utf-8 -*-
"""
FolderForge v5.0
Ett modernt verktyg för att skapa projektmappar och exportera strukturer.
Inkluderar projekthistorik och drag & drop-stöd.

v5.0 är KONSOLIDERINGEN: folderforge_v4.2.py, folderforge_v4.3.py och
folderforge_v4_2_patchar.py har slagits samman hit och raderats. Denna fil
är därefter enda källan. Nytt i v5.0:
  • M27 skärmanpassning — DPI-medvetenhet före fönsterskapande, multiskärms-
    medveten placering och skalning som frågar DPI före skärmbredd
  • M28 ikon överallt — samma ikon i titelrad, aktivitetsfält, tray och
    varje dialog, med procedurell reserv när .ico-filen saknas
  • M29 bättre autostart — register + Start-mappens genväg + Task Scheduler,
    där minst en mekanism räcker, plus testknapp med full diagnostik
  • M14 temaanpassade menyer — menyfärger följer temat, MENU_THEMES är enda
    källan istället för hårdkodat mörkt
  • idempotetsvakt i repair_stale_autostart — bryter en verklig reparations-
    loop (se B7 i blockfilen)

Ändringar sedan v4.2 (endast tillägg och felsäkring — ingen befintlig
funktion eller metod borttagen):

  M1 / F1    Atomisk JSON-skrivning överallt. atomic_write_json() följer
             tempfile.mkstemp → os.fdopen → fsync → os.replace och tar en
             .bak-backup före skrivning. Ersätter write_text()/json.dump() i
             ProjectHistory._save, TemplateManager.save_template,
             _save_settings_silent och _save_hotkey_rec — en krasch mitt i
             skrivningen kan inte längre lämna en trunkerad fil.

  M2 / C41.3 Självläkande JSON-läsning. read_json_safe() provar fil → .bak →
             .bak2 → default och är BOM-tolerant via utf-8-sig. Ersätter de
             nakna json.loads()-anropen i ProjectHistory._load,
             TemplateManager.list_templates, _load_settings och _load_hotkey.

  M3 / C2    Schema-validering med auto-repair för settings.json.
             validate_settings() rättar fel typ, okänt enum-värde och saknad
             nyckla till schema-default och rapporterar vad som lagats.
             Anropas i AppSettings.from_dict; _load_settings skriver tillbaka
             den lagade filen så att felet inte repareras om varje start.

  M5 / C40   Globala felkrokar. install_crash_hooks() sätter sys.excepthook och
             threading.excepthook så att inget undantag försvinner spårlöst —
             tre bakgrundstrådar (keyboard.Listener, export-worker, pystray)
             kunde tidigare dö helt tyst. Installeras allra först i __init__
             och kedjar vidare till originalkrokarna.

  M7 / MB5   Dubbel rotmapp vid mallanvändning och inklistring fixad.
             strip_root_level() skalar bort rad 1 när den är den enda
             toppnivåposten och är en mapp, eftersom _build_structure redan
             skapar base = save_root / rotnamn. Anropas före _show_preview så
             att förhandsgranskning och bygge ser samma struktur.

  M8         Drag & drop via officiellt tkinterdnd2-API. _setup_dnd() använder
             drop_target_register()/dnd_bind() istället för råa
             tk.call('tkdnd::drop_target', ...) + bind(), vilket inte gav
             <<Drop>>-eventen rätt Tcl-kontext.

  M9         tkdnd laddas via TkinterDnD.require(root), som lägger till RÄTT
             plattformsmapp i auto_path, istället för v4.2:s manuella
             'package require tkdnd' med sökvägsgissning. <<Drop>> returnerar
             DND_COPY_ACTION så att tkdnd bekräftar släppet.

  M10 / C43  Trådsäkra UI-anrop. ui_call() schemalägger widgetuppdateringar i
             Tk-huvudtråden via after(0, ...) och sväljer fel om fönstret redan
             stängts. Ersätter direkta configure()-anrop från pynput-tråden i
             _on_press_rec samt efter()-anrop i _setup_global_hotkey och
             _export_specific. hotkey_label()/normalize_hotkey_keys() ersätter
             den lokala prio-dictn med samma ordning men GUI-fri och testbar.

  M11 / C42  Snabbtangent valideras INNAN sparning och registrering.
             validate_hotkey_combo() kräver minst en modifierare och en vanlig
             tangent, samt högst HOTKEY_MAX_KEYS tangenter — utan detta kunde
             en kombination som bara "m" registreras globalt och stjäla varje
             m-tryckning i hela systemet. En ogiltig sparad kombination i
             hotkey_config.json faller tillbaka till DEFAULT_HOTKEY.

  M12 / MB10 Säker trälexport. generate_tree_string_safe() har djupgräns
             (MAX_TREE_DEPTH), symlink-loop-detektering via resolve(), posttak
             (MAX_TREE_ENTRIES) och PermissionError-hantering per mapp.
             StructureEngine.generate_tree_string delegerar till den, och
             _export_specifics worker får try/except/finally så att
             progressbaren alltid stängs och workern aldrig dör tyst.
             _tree_recursive() behålls oförändrad.

  M13 / C46  Korttitlars kontrast säkrad mot WCAG AA. ensure_contrast()
             justerar accentfärgen minimalt tills kontrasten mot den blendade
             kortbakgrunden når 4.5:1, separat för ljust och mörkt läge —
             alla 6 accentfärger låg tidigare under kravet (sämst 1.53:1).

  M18        sanitize_name() blockerar reserverade Windows-namn ÄVEN med
             filändelse (CON.txt, NUL.md, LPT1.log) via RESERVED_STEM_RE.
             NameValidator.sanitize delegerar till den; v4.1 jämförde bara
             cleaned.upper() mot INVALID_NAMES och släppte igenom "CON.txt".

Även kvar sedan v4.2: M22/C1 single instance-lås med fokusering av befintligt
fönster, och M19/C44 autostart utan svart konsolruta med verify-after-write
och självläkande reparation vid start.

All lyft kod är teckenidentisk med folderforge_v4_2_patchar.py och täcks av
tests/test_patchar*.py. All Windows-logik har injicerbara backends så att den
kan enhetstestas headless på Linux/macOS (C47).

Struktur: konstanter, sökvägar och standardvärden ligger i settings.py och
importeras oförändrade ovan. Konsolfri start är inbyggd — körs filen under
python.exe startar den om sig själv med pythonw.exe, så den fristående
starta_FolderForge.pyw behövs inte längre.

Author: Rickard Längkvist
"""

from __future__ import annotations

import sys
import subprocess
import importlib.metadata
import os
import json
import re
import shutil
import threading
import logging
import atexit
import ctypes
import math
import tempfile
import time
from datetime import datetime
from typing import (
    Any, Callable, Dict, Final, Iterable, List, Optional, Sequence, Set,
    Tuple,
)
from pathlib import Path, PureWindowsPath
from functools import lru_cache
from dataclasses import dataclass, field, asdict

# ============================================================
# Logging
# ------------------------------------------------------------
# OBS: handlare kopplas via logg.init_logging() nedanför settings-
# importen (implementationen bor i logg.py).
# ============================================================
logger = logging.getLogger(__name__)

# ============================================================
# Konstanter — utbrutna till settings.py (sökvägar, färger,
# standardvärden, paketkrav). Importen nedan binder exakt samma namn
# som tidigare definierades här, så resten av filen är oförändrad.
# Vill du ändra en konstant: redigera settings.py, inte denna fil.
# ============================================================
from settings import (  # noqa: F401
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_PURPLE, ACCENT_RED,
    ACCENT_TEAL, APP_ICON, APP_ICON_PNG, APP_NAME, APP_VERSION, BASE_DIR,
    COPYRIGHT_OWNER, DATA_DIR, DEFAULT_HOTKEY, HISTORY_FILE, HOTKEY_CONFIG,
    ICON_DIR, INVALID_NAME_CHARS, INVALID_NAMES, IS_WINDOWS, KNOWN_FILES,
    REQUIRED_PACKAGES, SETTINGS_ENUMS, SETTINGS_FILE,
    SETTINGS_META, SETTINGS_SCHEMA, TAB_ICONS, TEMPLATES_DIR,
    DAMAGE_TYPE_CHIPS, RUTA_CHOICES, LOKAL_CHOICES,
)
from historik import ProjectHistory, atomic_write_json, read_json_safe  # noqa: E402
from logg import init_logging  # noqa: E402


# ============================================================
# Loggning — initiering
# ------------------------------------------------------------
# Hela loggningen (roterande fil, kraschhookar, idempotent init) bor i
# logg.py. Handlarna sätts på rot-loggaren så att historik.py och
# framtida moduler loggar via propagation till samma fil.
# ============================================================
init_logging()


# ============================================================
# Paketinstallation
# ============================================================
@lru_cache(maxsize=32)
def _is_package_installed(package: str) -> bool:
    try:
        importlib.metadata.version(package)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def _get_missing_packages() -> List[str]:
    return [
        pip for mod, pip in REQUIRED_PACKAGES.items()
        if pip and not _is_package_installed(mod)
    ]


def _install_packages(packages: List[str]) -> Tuple[bool, str]:
    failed = []
    for pkg in packages:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", pkg],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError:
            failed.append(pkg)
    return (False, f"Kunde inte installera: {', '.join(failed)}") if failed else (True, "")


def check_and_install_requirements() -> bool:
    missing = _get_missing_packages()
    if not missing:
        return True
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
    except ImportError:
        sys.exit(1)

    try:
        root = _tk.Tk()
    except Exception as exc:
        # Ingen display tillgänglig för dialogen (SSH, tjänstekonto, eller en
        # underprocess utan session). Logga det som faktiskt betyder något —
        # vilka paket som saknas och hur de installeras — istället för att låta
        # en TclError-traceback läcka ut till användaren. Enkelt citerade
        # strängar här så att ingen escape-konflikt uppstår med omgivande kod.
        logger.error(
            'Saknade paket %s kunde inte installeras: ingen display för '
            'dialogen (%s). Installera manuellt: pip install %s',
            missing, exc, ' '.join(str(m) for m in missing if m))
        return False
    root.withdraw()
    if not _mb.askyesno(
        "Installation krävs",
        f"Saknade paket:\n{', '.join(missing)}\n\nInstallera nu?",
    ):
        root.destroy()
        return False

    prog = _tk.Toplevel(root)
    prog.title("Installerar...")
    _tk.Label(prog, text="Installerar paket, vänta...", padx=20, pady=20).pack()
    prog.update()

    ok, err = _install_packages(missing)
    prog.destroy()
    root.destroy()
    if ok:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    else:
        logger.error(err)
        return False


# ============================================================
# Konsolfri omstart — startfilens logik inbyggd i appen
# (ersätter den fristående starta_FolderForge.pyw)
# ============================================================
def relaunch_without_console() -> bool:
    """
    Startar om FolderForge med pythonw.exe om processen kördes igång med en
    konsol-tolk (python.exe / python3.13.exe ...). Returnerar True när en
    omstart initierats — den nuvarande processen ska då avslutas direkt.

    Filassociationen för .pyw pekar inte alltid på pythonw.exe, och startas
    skriptet explicit via python.exe visas en svart konsolruta under hela
    körningen. Omstarten använder tolkens granne "pythonw.exe" (annars
    py-startarens fönsterfria pyw.exe) samt flaggorna CREATE_NO_WINDOW |
    DETACHED_PROCESS, så inte ens en konsolblänkare hinner uppstå.

    Ingen omstart sker när:
      • plattformen inte är Windows (där finns ingen konsol-tolk att undvika)
      • appen är en fryst exe (redan fönsterfri per definition)
      • tolken redan är pythonw.exe
      • --selftest finns i argv (rapporten ska nå förälderns stdout)
      • ingen fönsterfri tolk hittas (konsolläge är bättre än ingen start)
    """
    if not IS_WINDOWS or getattr(sys, "frozen", False):
        return False
    if "--selftest" in sys.argv:
        return False
    exe = Path(sys.executable) if sys.executable else None
    if exe and exe.name.lower().startswith("pythonw"):
        return False
    tolk: Optional[str] = None
    if exe:
        granne = exe.with_name("pythonw.exe")
        if granne.exists():
            tolk = str(granne)
    if not tolk:
        tolk = shutil.which("pyw.exe") or shutil.which("pyw")
    if not tolk:
        return False
    try:
        subprocess.Popen(
            [tolk, str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=str(BASE_DIR),
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            ),
            close_fds=True,
        )
        return True
    except OSError as exc:
        logger.warning(
            "Konsolfri omstart misslyckades — fortsätter i denna process: %s",
            exc,
        )
        return False


if __name__ == "__main__":
    # Konsolfrihet FÖRE allt annat: råkade appen starta med en konsol-tolk
    # startar den om sig själv ljudlöst med pythonw.exe och denna process dör.
    # Ligger före beroendekollen medvetet — installationsdialogerna är rena
    # Tk-fönster och fungerar lika bra i den omstartade, fönsterfria processen.
    if relaunch_without_console():
        sys.exit(0)

    # M29c/v5.0 — --selftest får ALDRIG trigga beroendeinstallationen.
    #
    # check_and_install_requirements() visar en MODAL Tk-dialog och väntar på
    # svar. "Testa autostart"-knappen kör det registrerade kommandot i en
    # underprocess; en modal dialog där skulle blockera i det oändliga och
    # användaren skulle uppleva knappen som hängande, utan att någonsin få ett
    # svar. Självtestets hela uppgift är dessutom att RAPPORTERA saknade paket
    # exakt, inte att installera dem interaktivt — det sker längre ner i filen.
    #
    # Vaktet ligger här och inte vid självtestet eftersom detta är det FÖRSTA
    # __main__-blocket i filen och körs före allt annat.
    if "--selftest" not in sys.argv and not check_and_install_requirements():
        sys.exit(1)

# ============================================================
# Biblioteksimport
# ============================================================
try:
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import messagebox, filedialog
    from pynput import keyboard
    from PIL import Image
    import pystray

    if IS_WINDOWS:
        import winreg
except ImportError as e:
    logger.error("Import misslyckades: %s", e)
    sys.exit(1)

# Drag & Drop — kräver att root-fönstret använder TkinterDnD
DND_AVAILABLE = False
_TkDnDBase = None
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _TkDnDBase = TkinterDnD
    DND_AVAILABLE = True
    logger.info("tkinterdnd2 importerad — drag & drop redo.")
except ImportError:
    logger.info("tkinterdnd2 ej installerat — drag & drop inaktiverat.")
except Exception as e:
    logger.warning("tkinterdnd2 importfel: %s", e)


# ============================================================
# Systemintegritet — autostart (M19/C44) + single instance (M22/C1)
# ============================================================
# Blocken nedan är lyfta tecken för tecken ur folderforge_v4_2_patchar.py
# och täcks av tests/test_patchar.py, test_patchar3.py (185 tester gröna).
# All Windows-logik har injicerbara backends så att den kan enhetstestas
# headless på Linux/macOS (C47).

def build_autostart_command(script_args: Optional[Iterable[str]] = None) -> str:
    """
    Bygger autostart-kommandot och GARANTERAR att ingen svart konsolruta
    visas vid inloggning:
      • fryst exe (PyInstaller/Nuitka) → "exe" --tray  (ingen python alls)
      • python.exe / python3.12.exe    → pythonw.exe i samma mapp
      • pythonw saknas                 → pythonw.exe via 'start "" /B'
    """
    args = list(script_args) if script_args else ["--tray"]
    quoted_args = " ".join(f'"{a}"' for a in args)

    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {quoted_args}'.strip()

    exe = Path(sys.executable)
    win_noconsole = exe.with_name("pythonw.exe")
    if IS_WINDOWS and exe.name.lower().startswith("python") \
            and not exe.name.lower().startswith("pythonw") \
            and win_noconsole.exists():
        return f'"{win_noconsole}" "{Path(sys.argv[0]).resolve()}" {quoted_args}'

    if IS_WINDOWS:
        # Fallback: pythonw saknas eller heter något annat (python3.13.exe).
        return (f'cmd /c start "" /B "{exe}" '
                f'"{Path(sys.argv[0]).resolve()}" {quoted_args}')

    return f'"{exe}" "{Path(sys.argv[0]).resolve()}" {quoted_args}'

def is_stale_console_entry(command: str) -> bool:
    """
    True om kommandoraden refererar konsol-python (python.exe / python3.12.exe)
    istället för pythonw.exe eller en fryst exe — d.v.s. skulle visa en svart
    konsolruta vid inloggning.

    REN STRÄNGANALYS av Windows-kommandosemantik. Medvetet UTAN plattformsgrind:
    frågan "pekar detta på konsol-python?" är meningsfull oavsett var koden körs,
    och en grind här gjorde funktionen värdelös för headless-testning (C47) samt
    bröt befintliga tester. Plattformsgrinden hör hemma i repair_stale_autostart,
    som redan returnerar 'skipped' utanför Windows när ingen backend injicerats.
    I produktion körs denna funktion endast på Windows.
    """
    if not command:
        return False
    if getattr(sys, "frozen", False):
        return False
    low = command.lower()
    if "pythonw" in low:
        return False
    return "python" in low

ERROR_ALREADY_EXISTS: int = 183

DEFAULT_POLL_MS: int = 1000

def _pid_alive(pid: int) -> bool:
    """Sant om processen med angivet PID lever (stale-detektering)."""
    if not pid or pid <= 0:
        return False
    if IS_WINDOWS:
        try:
            import win32api
            import win32con
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = win32api.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                # ExitCodeProcess == STILL_ACTIVE (259) → lever
                import win32process
                code = win32process.GetExitCodeProcess(handle)
                return code == win32con.STILL_ACTIVE
            finally:
                win32api.CloseHandle(handle)
        except ImportError:
            # pywin32 saknas/är trasig — KRITISK fallback via ren ctypes.
            # Utan denna gren svarade funktionen "död" om varje PID på
            # pywin32-lösa maskiner, vilket fick PID-filslåset att överta
            # låset vid VARJE ny start → flera appfönster samtidigt.
            try:
                k32 = ctypes.windll.kernel32
                handle = k32.OpenProcess(0x1000, False, int(pid))
                if not handle:
                    return False
                try:
                    code = ctypes.c_ulong(0)
                    if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                        return False
                    return code.value == 259   # STILL_ACTIVE
                finally:
                    k32.CloseHandle(handle)
            except Exception:
                return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # finns men ägs av annan användare
    except OSError:
        return False
    return True

def default_lock_dir(app_name: str) -> Path:
    """Plattformsoberoende katalog för lås-/trigger-/pid-filer."""
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") \
            or tempfile.gettempdir()
    else:
        base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(base) / app_name

class SingleInstanceLock:
    """
    C1: Max en instans. Andra start → fokus på befintligt fönster.

      Windows  : CreateMutexW, "Global\\" → "Local\\"-fallback,
                 ERROR_ALREADY_EXISTS = 183
      macOS/Linux: flock LOCK_EX | LOCK_NB (+ PID-fil med stale-detektering)
      Ingen fcntl OCH ingen pywin32 → PID-filsfallback (självläkning, C41.2)

    Fokus via triggerfil + poll-loop (~1000 ms) som anropar on_trigger i
    Tk-huvudtråden via after(). Cleanup vid exit (atexit) och krasch (finally).
    """

    def __init__(
        self,
        app_name: str,
        lock_dir: Optional[Path] = None,
        poll_ms: int = DEFAULT_POLL_MS,
    ) -> None:
        self.app_name = str(app_name)
        self.lock_dir = Path(lock_dir) if lock_dir else default_lock_dir(self.app_name)
        self.poll_ms = max(50, int(poll_ms))

        slug = re.sub(r"[^a-z0-9_]+", "_", self.app_name.lower()).strip("_")
        self.lock_file = self.lock_dir / f"{slug}.lock"
        self.pid_file = self.lock_dir / f"{slug}.pid"
        self.trigger_file = self.lock_dir / f"{slug}_show.trigger"

        self._mutex_handle: Optional[int] = None
        self._mutex_name: Optional[str] = None
        self._fd: Optional[int] = None
        self._is_primary: bool = False
        self._backend: str = "none"
        self._last_trigger: Optional[str] = None   # filinnehåll, ej mtime
        self._trigger_init: bool = False
        self._poll_job: Optional[str] = None
        self._atexit_registered: bool = False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    @property
    def is_primary(self) -> bool:
        """True om DENNA process är den enda/primära instansen."""
        return self._is_primary

    @property
    def backend(self) -> str:
        """'win32-mutex-global', 'win32-mutex-local', 'flock', 'pidfile'."""
        return self._backend

    def read_owner_pid(self) -> Optional[int]:
        """PID för instansen som håller låset (diagnostik)."""
        try:
            return int(self.pid_file.read_text(encoding="utf-8").strip() or 0) or None
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Förvärv
    # ------------------------------------------------------------------
    def acquire(self) -> bool:
        """
        Försök ta låset. True = vi är primär instans och ska köra.
        False = en annan instans kör redan; anropa request_focus() och avsluta.
        Kastar aldrig.
        """
        try:
            self.lock_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Kan inte skapa låskatalog %s: %s", self.lock_dir, exc)
            return True          # hellre två instanser än en app som inte startar

        if IS_WINDOWS:
            try:
                ok = self._acquire_win32()
                # Låsbeslutet MÅSTE synas i loggen. Utan denna rad kunde
                # PyHANDLE-buggen leva osynlig: mutexen dog direkt, backend-
                # strängen såg frisk ut, och dubbelstarter passerade tyst.
                logger.info("Instanslås: %s (backend=%s pid=%d)",
                            "TAGET" if ok else "UPPTAGET av annan instans — avslutar",
                            self._backend, os.getpid())
                return ok
            except ImportError:
                logger.warning("pywin32 saknas — faller tillbaka på flock/pidfil.")
            except Exception as exc:
                logger.warning("Win32-mutex misslyckades (%s) — fallback.", exc)

        try:
            import fcntl  # noqa: F401
            ok = self._acquire_flock()
            logger.info("Instanslås: %s (backend=%s pid=%d)",
                        "TAGET" if ok else "UPPTAGET av annan instans — avslutar",
                        self._backend, os.getpid())
            return ok
        except ImportError:
            logger.warning("fcntl saknas — faller tillbaka på PID-fil.")
        except Exception as exc:
            logger.warning("flock misslyckades (%s) — fallback.", exc)

        ok = self._acquire_pidfile()
        logger.info("Instanslås: %s (backend=%s pid=%d)",
                    "TAGET" if ok else "UPPTAGET av annan instans — avslutar",
                    self._backend, os.getpid())
        return ok

    def _acquire_win32(self) -> bool:
        try:
            import win32api
            import win32event
            import winerror
        except ImportError:
            # pywin32 saknas på maskinen — ta samma mutex via ren ctypes
            # (stdlib) istället. Spärren får ALDRIG bero på ett valfritt
            # paket: PID-fils-fallbacken är inte atomär och kan släppa in
            # två instanser som startar samtidigt (autostart + manuell
            # start) → just det scenariot som gav dubbla tray-ikoner.
            return self._acquire_win32_ctypes()

        last_error = 0
        for prefix in ("Global\\", "Local\\"):
            name = f"{prefix}{self.app_name}_SingleInstance_Mutex"
            try:
                handle = win32event.CreateMutex(None, False, name)
            except Exception as exc:
                # Global\ kräver rättigheter på vissa system → prova Local\
                logger.warning("CreateMutex(%s) misslyckades: %s", name, exc)
                continue
            last_error = win32api.GetLastError()
            if last_error == winerror.ERROR_ALREADY_EXISTS:
                try:
                    win32api.CloseHandle(handle)
                except Exception:
                    pass
                self._backend = "win32-mutex-inuse"
                self._is_primary = False
                return False
            # KRITISKT: spara ALDRIG bara int(handle)! pywin32:s PyHANDLE
            # stänger det underliggande handtaget automatiskt när objektet
            # skräpsamlas — med int(handle) dog mutexen mikrosekunder efter
            # förvärvet och instansspärren existerade aldrig i praktiken
            # (verifierat i logg: dubbelstarter passerade utan avvisning).
            # Detach() överför ägandet till oss; release() stänger explicit.
            self._mutex_handle = handle.Detach()
            self._mutex_name = name
            self._backend = "win32-mutex-" + prefix.rstrip(chr(92)).lower()
            self._is_primary = True
            self._write_pid()
            self._register_atexit()
            return True

        raise RuntimeError(f"CreateMutex fungerade inte (sista fel={last_error})")

    def _acquire_win32_ctypes(self) -> bool:
        """
        Samma namngivna mutex som _acquire_win32, men via ren ctypes —
        körs när pywin32 saknas. Identiska namn = samma spärr även om
        två processer råkar gå olika vägar (den ena med, den andra utan
        pywin32). use_last_error=True + set_last_error(0) före anropet,
        annars är GetLastError opålitlig från ctypes.
        """
        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = (
            ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)

        for prefix in ("Global\\", "Local\\"):
            name = f"{prefix}{self.app_name}_SingleInstance_Mutex"
            ctypes.set_last_error(0)
            handle = kernel32.CreateMutexW(None, False, name)
            if not handle:
                logger.warning("CreateMutexW(%s) misslyckades (fel=%s) — provar nästa.",
                               name, ctypes.get_last_error())
                continue
            if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(ctypes.c_void_p(handle))
                self._backend = "win32-mutex-inuse"
                self._is_primary = False
                return False
            self._mutex_handle = int(handle)  # ctypes-int äger inget — ingen auto-stängning
            self._mutex_name = name
            self._backend = ("win32-mutex-global-ctypes" if prefix == "Global\\"
                             else "win32-mutex-local-ctypes")
            self._is_primary = True
            self._write_pid()
            self._register_atexit()
            return True

        raise RuntimeError("CreateMutexW (ctypes) fungerade inte")

    def _acquire_flock(self) -> bool:
        import fcntl

        fd = os.open(str(self.lock_file), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            self._backend = "flock-inuse"
            self._is_primary = False
            return False

        self._fd = fd
        try:
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.fsync(fd)
        except OSError as exc:
            logger.warning("Kunde inte skriva PID i låsfil: %s", exc)

        self._backend = "flock"
        self._is_primary = True
        self._write_pid()
        self._register_atexit()
        return True

    def _acquire_pidfile(self) -> bool:
        """Fallback utan fcntl/win32: PID-fil + stale-detektering."""
        owner = self.read_owner_pid()
        if owner and owner != os.getpid() and _pid_alive(owner):
            self._backend = "pidfile-inuse"
            self._is_primary = False
            return False
        if owner and not _pid_alive(owner):
            logger.info("Stale PID-fil (%s) upptäckt — övertar låset.", owner)
        self._write_pid()
        self._backend = "pidfile"
        self._is_primary = True
        self._register_atexit()
        return True

    def _write_pid(self) -> None:
        try:
            self.lock_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.lock_dir), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(str(os.getpid()))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.pid_file)
        except OSError as exc:
            logger.warning("Kunde inte skriva PID-fil: %s", exc)

    def _register_atexit(self) -> None:
        if self._atexit_registered:
            return
        try:
            atexit.register(self.release)
            self._atexit_registered = True
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Fokus mellan instanser (triggerfil + poll)
    # ------------------------------------------------------------------
    def request_focus(self) -> bool:
        """
        Skrivs av den AVVISADE instansen: begär att den primära instansen
        visar och fokuserar sitt fönster. Kastar aldrig.
        """
        try:
            self.lock_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.lock_dir), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(f"{time.time_ns()}\n{os.getpid()}\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.trigger_file)
            return True
        except OSError as exc:
            logger.error("Kunde inte skriva triggerfil: %s", exc)
            return False

    def check_trigger(self) -> bool:
        """
        True om triggerfilen ändrats sedan senaste anropet.

        Jämför FILINNEHÅLLET, inte mtime. Skäl (verifierat): två snabba
        request_focus()-anrop kan ge IDENTISK st_mtime_ns eftersom
        filsystemets tidsupplösning är för grov, medan innehållet
        (time_ns + pid) alltid är unikt. Med mtime tappades den andra
        förfrågan.

        Första anropet sätter baslinjen och returnerar False. Baslinjen sätts
        även när filen INTE finns ännu — annars tappas den första
        fokusförfrågan, eftersom None då betyder både "ingen baslinje" och
        "filen saknas" (se _trigger_init).
        """
        try:
            state: Optional[str] = self.trigger_file.read_text(encoding="utf-8")
        except OSError:
            state = None

        if not self._trigger_init:
            self._trigger_init = True
            self._last_trigger = state
            return False

        if state != self._last_trigger:
            self._last_trigger = state
            # En borttagen fil är ingen fokusförfrågan — bara ett nytt läge.
            return state is not None
        return False

    def poll_start(self, root: Any, on_trigger: Any) -> bool:
        """
        Starta Tk-poll-loop (C1: ~1000 ms). Anropar on_trigger() i
        huvudtråden när en annan instans begärt fokus.

        root     : något med .after(ms, fn) — din CTk/Tk-instans
        on_trigger: callback, t.ex. app._restore_from_tray
        """
        if not self._is_primary:
            return False

        self.check_trigger()               # sätt baslinje direkt

        def _loop() -> None:
            try:
                if self.check_trigger():
                    logger.info("Trigger mottagen — fokuserar fönster.")
                    on_trigger()
            except Exception:
                logger.exception("Fel i single-instance poll-loop")
            finally:
                try:
                    root.after(self.poll_ms, _loop)
                except Exception:
                    pass                   # fönstret stängs — avsluta loopen

        try:
            root.after(self.poll_ms, _loop)
            return True
        except Exception as exc:
            logger.error("Kunde inte starta poll-loop: %s", exc)
            return False

    def poll_stop(self) -> None:
        self._poll_job = None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def release(self) -> None:
        """Frigör låset. Idempotent — kan anropas flera gånger säkert."""
        self._is_primary = False

        if self._fd is not None:
            try:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

        if self._mutex_handle is not None:
            closed = False
            try:
                import win32api
                win32api.CloseHandle(self._mutex_handle)
                closed = True
            except Exception:
                pass
            if not closed and IS_WINDOWS:
                # Handtaget kan ha skapats via ctypes-vägen (utan pywin32) —
                # stäng det då via ctypes så mutexen verkligen frigörs.
                try:
                    ctypes.windll.kernel32.CloseHandle(
                        ctypes.c_void_p(self._mutex_handle))
                except Exception:
                    pass
            self._mutex_handle = None
            self._mutex_name = None

        try:
            logger.info("Instanslås frigivet (%s, pid=%d)",
                        self._backend, os.getpid())
        except Exception:
            pass

        for path in (self.pid_file, self.trigger_file):
            try:
                path.unlink()
            except OSError:
                pass

        try:
            if self.lock_file.exists() and not IS_WINDOWS:
                self.lock_file.unlink()
        except OSError:
            pass

AUTOSTART_KEY_PATH: str = r"Software\Microsoft\Windows\CurrentVersion\Run"

class _WinregBackend:
    """Standardbackend mot det riktiga Windows-registret."""

    def read(self, key_path: str, value_name: str) -> Optional[str]:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                winreg.KEY_READ) as k:
                data, kind = winreg.QueryValueEx(k, value_name)
                return str(data)
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning("Kunde inte läsa autostart: %s", exc)
            return None

    def write(self, key_path: str, value_name: str, command: str) -> bool:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                winreg.KEY_SET_VALUE | winreg.KEY_READ) as k:
                winreg.SetValueEx(k, value_name, 0, winreg.REG_SZ, command)
                # VERIFY-AFTER-WRITE: läs tillbaka inom samma nyckelhantering
                back, _kind = winreg.QueryValueEx(k, value_name)
                return str(back) == command
        except OSError as exc:
            logger.error("Kunde inte skriva autostart: %s", exc)
            return False

    def delete(self, key_path: str, value_name: str) -> bool:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                winreg.KEY_SET_VALUE) as k:
                try:
                    winreg.DeleteValue(k, value_name)
                except FileNotFoundError:
                    return True            # redan borta = önskat läge
                return self.read(key_path, value_name) is None
        except OSError as exc:
            logger.error("Kunde inte ta bort autostart: %s", exc)
            return False

def _backend(reg: Any) -> Any:
    return reg if reg is not None else _WinregBackend()

def read_autostart_entry(app_name: str, reg: Any = None,
                         key_path: str = AUTOSTART_KEY_PATH) -> Optional[str]:
    """Befintligt registervärde, eller None om det inte finns."""
    if not IS_WINDOWS and reg is None:
        return None
    return _backend(reg).read(key_path, app_name)

def write_autostart_entry(app_name: str, command: str, reg: Any = None,
                          key_path: str = AUTOSTART_KEY_PATH) -> Tuple[bool, str]:
    """
    Skriv autostartkommando och verifiera att det faktiskt lagrades.
    Returnerar (lyckades?, det som nu står i registret).
    """
    if not command or not command.strip():
        return False, ""
    backend = _backend(reg)
    if not IS_WINDOWS and reg is None:
        return False, ""
    ok = backend.write(key_path, app_name, command)
    stored = backend.read(key_path, app_name) or ""
    if ok and stored != command:
        logger.warning("Verify-after-write avvek: skrev %r, läste %r", command, stored)
        return False, stored
    return bool(ok), stored

def delete_autostart_entry(app_name: str, reg: Any = None,
                           key_path: str = AUTOSTART_KEY_PATH) -> bool:
    """Ta bort autostart. True även om värdet redan saknades."""
    if not IS_WINDOWS and reg is None:
        return True
    return bool(_backend(reg).delete(key_path, app_name))

def repair_stale_autostart(app_name: str, reg: Any = None,
                           script_args: Optional[List[str]] = None,
                           key_path: str = AUTOSTART_KEY_PATH,
                           command_builder: Optional[Any] = None) -> str:
    """
    C44: upptäck och reparera ett autostartvärde som skulle visa en svart
    konsolruta (pekar på python.exe istället för pythonw.exe).

    Returnerar en av:
      'not_set'   — ingen autostart registrerad (inget att göra)
      'ok'        — värde finns och är korrekt
      'repaired'  — trasigt värde funnet och omskrivet (verify-after-write OK)
      'error'     — reparation misslyckades (loggat)
      'skipped'   — ej Windows och ingen injicerad backend

    command_builder: valfri funktion (script_args) -> kommandosträng. Default
    är build_autostart_command. Injicerbar eftersom den är plattformsberoende —
    utan detta går Windows-reparationsgrenen inte att testa headless på Linux.
    """
    injected = reg is not None

    if not IS_WINDOWS and not injected:
        return "skipped"

    current = read_autostart_entry(app_name, reg, key_path)
    if current is None:
        return "not_set"
    if not is_stale_console_entry(current):
        return "ok"

    builder = command_builder if callable(command_builder) else build_autostart_command
    fixed = builder(script_args or ["--tray"])

    # B7/v5.0 — IDEMPOTENSVAKT, validering FÖRE skrivning.
    #
    # Utan denna vakt fanns en verklig oändlig reparations-loop. När
    # pythonw.exe saknas (embedded Python, omdömd interpreter) bygger
    # build_autostart_command() fallback-grenen
    #     cmd /c start "" /B "C:\Python312\python.exe" "..."
    # och is_stale_console_entry() dömer ut EXAKT den formen som stale, eftersom
    # den innehåller "python" men inte "pythonw". Funktionen skrev därför
    # tillbaka ett värde identiskt med det befintliga, och nästa uppstart
    # "reparerade" igen: en registerskrivning och en WARNING i loggen vid VARJE
    # start, i all evighet, utan att problemet någonsin löstes.
    #
    # v4.3 validerade dessutom EFTER skrivning, så ett känt trasigt värde hann
    # hamna i registret innan felet upptäcktes. Nu skrivs ingenting alls om
    # det byggda kommandot inte är en faktisk förbättring.
    #
    # Returvärdet är medvetet oförändrat ("error") för att inte bryta det
    # dokumenterade kontraktet eller befintliga tester — skillnaden är att
    # registret inte längre skrivs i onödan och att loggen säger vad användaren
    # faktiskt behöver göra.
    if fixed == current:
        logger.error(
            "Autostart kan inte repareras automatiskt: det byggda kommandot "
            "skiljer sig inte från det befintliga (%r). Saknas pythonw.exe? "
            "Bygg en fryst .exe med --windowed.", current)
        return "error"
    if is_stale_console_entry(fixed):
        logger.error(
            "Autostart kan inte repareras automatiskt: det byggda kommandot "
            "visar fortfarande en konsolruta (%r) och skrivs därför INTE till "
            "registret. Saknas pythonw.exe? Bygg en fryst .exe med --windowed.",
            fixed)
        return "error"

    logger.warning("Stale autostart upptäckt (konsol-python): %r — reparerar.", current)
    ok, stored = write_autostart_entry(app_name, fixed, reg, key_path)
    if ok and not is_stale_console_entry(stored):
        logger.info("Autostart reparerad till: %r", stored)
        return "repaired"
    logger.error("Autostart-reparation misslyckades; registret innehåller %r", stored)
    return "error"


# ============================================================
# v4.3 — självläkande kärna och felsäkring
# ============================================================
# Blocken nedan är lyfta TECKEN FÖR TECKEN ur folderforge_v4_2_patchar.py
# (P1-P5, P7-P11) och täcks av tests/test_patchar.py, test_patchar2.py och
# test_patchar3.py. Ordningen är signifikant: MAX_TREE_DEPTH och
# MAX_TREE_ENTRIES används som default-argument i generate_tree_string_safe
# och måste därför vara definierade före den.
#
#   M1/F1    atomic_write_json  — mkstemp → fdopen → fsync → os.replace + .bak
#   M2/C41.3 read_json_safe     — fil → .bak → .bak2 → default, BOM-tolerant
#   M3/C2    validate_settings  — schema-validering med auto-repair
#   M5/C40   install_crash_hooks — sys.excepthook + threading.excepthook
#   M7/MB5   strip_root_level   — motverkar dubbel rotmapp
#   M8/M9    parse_dnd_paths    — officiellt tkdnd-API, {braces}-tolerant
#   M10/C43  ui_call            — trådsäkra UI-anrop via after(0, ...)
#   M11/C42  validate_hotkey_combo — kräver modifierare, max tak
#   M12/MB10 generate_tree_string_safe — djupgräns, symlink-vakt, posttak
#   M13/C46  ensure_contrast    — WCAG AA 4.5:1 för information bärande text
#   M18      sanitize_name      — blockerar CON.txt / NUL.md / LPT1.log




# SETTINGS_SCHEMA och SETTINGS_ENUMS bor sedan designpaketet i settings.py
# (sektion 6 — inställningskontraktet är konfiguration, inte logik) och
# importeras ovan. validate_settings() nedan använder samma namn som förut.


def validate_settings(data: Any) -> Tuple[Dict[str, Any], bool, List[str]]:
    """
    Returnerar (rensat_data, reparerad?, loggrader).
    Okända nycklar behålls (framåtkompatibilitet) men ogiltiga TYPER och
    ogiltiga ENUM-värden korrigeras till default — aldrig krasch.
    """
    log: List[str] = []
    repaired = False

    if not isinstance(data, dict):
        return dict(), True, ["settings var inte en dict — nollställd till schema"]

    out: Dict[str, Any] = dict(data)

    for key, (typ, default) in SETTINGS_SCHEMA.items():
        if key not in out or not isinstance(out[key], typ):
            if key in out:
                # log-listan är en vanlig lista → formatering sker direkt.
                # (Lazy %s gäller endast logger-anrop, aldrig list.append.)
                log.append("ogiltigt värde för %s (%r) → default" % (key, out[key]))
                repaired = True
            out[key] = default if not callable(default) else default()

    for key, allowed in SETTINGS_ENUMS.items():
        if out.get(key) not in allowed:
            log.append("'%s' = %r ej i %s → %s" % (
                key, out.get(key), tuple(allowed), SETTINGS_SCHEMA[key][1]))
            out[key] = SETTINGS_SCHEMA[key][1]
            repaired = True

    if not out.get("save_root"):
        out["save_root"] = str(Path.home() / "Projects")
        repaired = True

    tabs = out.get("visible_tabs")
    if not isinstance(tabs, dict):
        tabs = {}
    cleaned_tabs: Dict[str, bool] = {}
    for name, val in tabs.items():
        cleaned_tabs[str(name)] = bool(val)
    out["visible_tabs"] = cleaned_tabs

    return out, repaired, log


def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
    v = value.lstrip('#')
    if len(v) == 3:
        v = ''.join(c * 2 for c in v)
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def relative_luminance(hex_color: str) -> float:
    r, g, b = _hex_to_rgb(hex_color)
    chan = []
    for c in (r, g, b):
        s = c / 255
        chan.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 kontrastförhållande, 1.0–21.0."""
    l1, l2 = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def darken(hex_color: str, factor: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    f = max(0.0, min(1.0, factor))
    return '#%02x%02x%02x' % (int(r * f), int(g * f), int(b * f))


def lighten(hex_color: str, factor: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    f = max(0.0, min(1.0, factor))
    return '#%02x%02x%02x' % (
        int(r + (255 - r) * f), int(g + (255 - g) * f), int(b + (255 - b) * f),
    )


def ensure_contrast(
    fg: str,
    bg_light: str,
    bg_dark: str,
    min_ratio: float = 4.5,
) -> Tuple[str, str]:
    """
    Justerar en accentfärg tills den klarar WCAG AA (4.5:1) mot både
    ljus och mörk bakgrund. Returnerar (färg_ljusläge, färg_mörkläge).
    Färgen förändras aldrig mer än nödvändigt. Utdata är alltid #rrggbb.
    """
    fg_norm = '#%02x%02x%02x' % _hex_to_rgb(fg)

    def sweep(fg_hex: str, bg: str, go_darker: bool) -> Tuple[str, float]:
        """
        Sveper en riktning i ordning av STIGANDE avvikelse från originalet och
        returnerar (bästa färg, uppnått förhållande). Första kandidat som når
        min_ratio vinner, vilket bevarar regeln "ändra aldrig mer än nödvändigt".
        Steg 0 är originalet självt. Någons ingen kandidat räcker returneras den
        med högst förhållande, så att anroparen alltid får bästa möjliga svar.
        """
        candidates = [fg_hex]
        for step in range(1, 41):
            pct = step * 0.04
            candidates.append(darken(fg_hex, 1 - pct) if go_darker
                              else lighten(fg_hex, pct))
        best_hex, best_ratio = fg_hex, -1.0
        for cand in candidates:
            ratio = contrast_ratio(cand, bg)
            if ratio >= min_ratio:
                return cand, ratio
            if ratio > best_ratio:
                best_hex, best_ratio = cand, ratio
        return best_hex, best_ratio

    def fix(fg_hex: str, bg: str, go_darker: bool) -> str:
        # M13/C46 — den riktning som bakgrundens namn antyder provas först
        # (mörka mot ljus bakgrund, ljustna mot mörk). Räcker den returneras
        # exakt samma färg som tidigare, så rättningen är MONOTON: inget
        # befintligt anrop ändrar utdata.
        hex_a, ratio_a = sweep(fg_hex, bg, go_darker)
        if ratio_a >= min_ratio:
            return '#%02x%02x%02x' % _hex_to_rgb(hex_a)
        # Annars kan antagandet "bg_dark är mörkare än accenten" vara falskt.
        # Det inträffar när blend_color() körs med hög alpha: då blir den
        # "mörka" bakgrunden ljusare än accenten och ljustning mättar i vitt
        # utan att nå kravet. Uppmätt exempel: ACCENT_BLUE mot
        # blend_color(ACCENT_BLUE, 0.85)[1] = #478cd3 gav 3.52:1 med ljustning
        # men 5.96:1 med mörkning. Motsatt riktning provas därför som reserv.
        hex_b, ratio_b = sweep(fg_hex, bg, not go_darker)
        winner = hex_b if ratio_b > ratio_a else hex_a
        return '#%02x%02x%02x' % _hex_to_rgb(winner)

    return (fix(fg_norm, bg_light, True), fix(fg_norm, bg_dark, False))


RESERVED_STEM_RE = re.compile(
    r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$', re.IGNORECASE,
)


def sanitize_name(name: str, *, max_len: int = 255) -> str:
    """
    Rensar ett mapp-/filnamn enligt Windows-regler:
      • ogiltiga tecken → '_'
      • inledande/avslutande mellanslag och punkter tas bort
      • reserverade namn blockeras ÄVEN med filändelse (CON.txt, NUL.md …)
      • längdtak
    """
    if not isinstance(name, str):
        raise ValueError("Namnet måste vara en sträng.")
    cleaned = INVALID_NAME_CHARS.sub('_', name)
    cleaned = cleaned.strip().strip('.').strip()
    if not cleaned:
        raise ValueError("Mappnamnet är tomt efter rensning.")
    if cleaned.upper() in INVALID_NAMES or RESERVED_STEM_RE.match(cleaned):
        raise ValueError(f"'{cleaned}' är ett reserverat systemnamn.")
    if len(cleaned) > max_len:
        raise ValueError(f"Mappnamnet är för långt (max {max_len} tecken).")
    return cleaned


# ------------------------------------------------------------
# Regns-läge — registreringsnummer i början av projektnamn
# ------------------------------------------------------------
_PLATE_RE = re.compile(
    r"""^\s*
    (?P<bokst>[a-z]{3})              # tre bokstäver (ABC)
    [\s\-–—]*                        # fri separator: mellanslag/streck/inget
    (?:
        (?P<s2>\d{2})[\s\-]*(?P<s3>\d)      # äldre format: ABC 123 (1973–2019)
      | (?P<n2>\d{2})[\s\-]*(?P<nb>[a-z])   # nyare format: ABC 12 A (2019–)
    )
    (?![a-zA-Z0-9])                  # regnr:t får inte flyta ihop med mer text
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SUFFIX_STRIP = " \t-–—_\u00b7"   # tecken som inte ska inleda den fria texten


def normalize_plate_name(name: str) -> Tuple[str, Optional[str]]:
    """
    Normalisera ett projektnamn som BÖRJAR med ett svenskt registreringsnummer.

      'dss 817'           → ('DSS817', 'DSS817')
      'dss 81 7'          → ('DSS817', 'DSS817')
      'dss 817 stenskott' → ('DSS817 stenskott', 'DSS817')   (suffix orört)
      'abc 12 a 2021'     → ('ABC12A 2021', 'ABC12A')
      'Biltest'           → ('Biltest', None)                (ingen ändring)

    Båda svenska formaten stöds: ABC123 (1973–2019) och ABC12A (2019–).
    Matchningen är medvetet tolerant (mellanslag/streck ignoreras, I/Q/V
    blockeras inte): funktionen VARNAR mjukt via returvärdet None — den
    stoppar eller ändrar aldrig ett namn som inte matchar.

    Versaliseringen av HELA namnet sker av anroparen (safe_name.upper());
    här normaliseras bara regnr-delen och gränsen mot fri eftertext.

    Returnerar (ev. normaliserat namn, regnr eller None).
    """
    m = _PLATE_RE.match(name or "")
    if not m:
        return (name, None)
    regnr = (m.group("bokst") + (m.group("s2") or m.group("n2"))
             + (m.group("s3") or m.group("nb") or "")).upper()
    suffix = name[m.end():].lstrip(_SUFFIX_STRIP)
    return (regnr + ((" " + suffix) if suffix else ""), regnr)


def parse_dnd_paths(raw: str, tk_obj: Optional[Any] = None) -> List[str]:
    """
    event.data är en RÅ TCL-LISTA — inte en sträng. Flera släppta filer kommer
    mellanslagsseparerade och varje sökväg med mellanslag ligger i {parenteser}.
    Korrekt tolkning är root.tk.splitlist(event.data).
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    if tk_obj is not None:
        try:
            return [str(p) for p in tk_obj.splitlist(raw) if str(p).strip()]
        except Exception:
            pass
    # Manuell fallback: mini-Tcl-listtolk. Parenteser kan vara nästlade och
    # bara en del av posterna behöver vara klamrade, t.ex.
    #   "{C:/Mina Projekt/a} {D:/Övrigt/b} C:/c"
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == '\\' and i + 1 < len(raw):
            nxt = raw[i + 1]
            if nxt == '\n':
                i += 2                  # radfortsättning gäller även inom {}
                continue
            if depth == 0:
                buf.append(nxt)         # utanför {}: Tcl-escape, nästa är bokstavligt
                i += 2
                continue
            # Inom {} är backslash BOKSTAVLIGT: Tcl undertrycker all substitution
            # mellan parenteser (enda undantaget är backslash+nyrad ovan). Att äta
            # backslash även här söndrade Windows-sökvägar — {C:\Users\Rickard\a}
            # blev 'C:UsersRickarda'. Verifierat mot en riktig Tcl-tolk
            # (tk.splitlist), som är auktoritativ. Tecknet faller vidare till
            # else-grenen nedan och läggs till som det är.
        if ch == '{':
            # Tcl: '{' inleder ett ord BARA som ordets första tecken; mitt i ett
            # ord är det bokstavligt (t.ex. 'kZ{}BZG' är ETT ord). Nästlade
            # parenteser räknas dock alltid, så att rätt '}' hittar sin '{'.
            if depth or not buf:
                if depth:
                    buf.append(ch)
                depth += 1
            else:
                buf.append(ch)
        elif ch == '}':
            # Omaka '}' (ingen öppnad parentes) är bokstavlig, inte felslut.
            if depth:
                depth -= 1
                if depth:
                    buf.append(ch)
            else:
                buf.append(ch)
        elif ch in ' \t\r\n' and depth == 0:
            if buf:
                parts.append(''.join(buf))
                buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        parts.append(''.join(buf))
    return [p for p in parts if p.strip()]


DND_COPY_ACTION = "copy"


HOTKEY_MODIFIERS: frozenset = frozenset({
    "ctrl", "alt", "shift", "cmd", "win", "super", "option", "command",
})


HOTKEY_MAX_KEYS: int = 5


def validate_hotkey_combo(keys: Iterable[str]) -> Tuple[bool, List[str], str]:
    """
    Godkänner bara kombinationer som INTE kan stjäla vanlig skrivning:
      • minst 1 modifierare (ctrl/alt/shift/cmd/win)
      • minst 1 icke-modifierare
      • max 5 tangenter
      • inga mellanslag i namn
    Returnerar (ok?, normaliserad_lista, felmeddelande).
    """
    norm: List[str] = []
    for k in keys or []:
        s = str(k).strip().lower().replace("key.", "").replace("_l", "").replace("_r", "")
        if s and s not in norm:
            norm.append(s)

    if not norm:
        return False, [], "Inga tangenter registrerade."
    if len(norm) > HOTKEY_MAX_KEYS:
        return False, norm, f"Max {HOTKEY_MAX_KEYS} tangenter i en kombination."

    mods = [k for k in norm if k in HOTKEY_MODIFIERS]
    base = [k for k in norm if k not in HOTKEY_MODIFIERS]

    if not mods:
        return False, norm, (
            "Snabbtangenten måste innehålla minst en modifierare "
            "(Ctrl, Alt, Shift eller Win) — annars blockerar den "
            "vanlig skrivning i hela Windows."
        )
    if not base:
        return False, norm, "Kombinationen saknar en vanlig tangent."
    return True, norm, ""


def strip_root_level(items: List[Dict[str, Any]], root_name: str) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Malltext och inklistrade träd har sin rot på rad 1 ('projektnamn/',
    'ärendenummer/'), men _build_structure skapar redan
    base = save_root / root_name. Utan denna funktion blir resultatet:

        PROJEKT123/
        └── PROJEKT123/      ← dublett (MB5)
            ├── src/ ...

    Bevis för att rad 1 ÄR roten: de inbyggda mallarna använder
    'projektnamn'/'ärendenummer' som placeholder som ersätts med användarens
    namn via .replace() — alltså är rad 1 per definition roten.

    Regel: finns EXAKT EN post på toppnivå och den är en mapp, skalas den
    nivån bort från alla poster. Flera toppnivåposter (docs/ + src/) lämnas
    orörda, eftersom base då redan är deras gemensamma förälder.

    Returnerar (nya_items, skalades_nivån_bort?).
    """
    if not items:
        return items, False

    top = [it for it in items if len(it.get('path', [])) == 1]
    if len(top) != 1 or not top[0].get('is_dir'):
        return items, False

    root_label = str(top[0]['path'][0]).strip()
    stripped: List[Dict[str, Any]] = []
    for it in items:
        path = list(it.get('path', []))
        if len(path) <= 1:
            continue                      # själva rotraden försvinner
        new_it = dict(it)
        new_it['path'] = path[1:]
        stripped.append(new_it)

    if not stripped:
        # Endast en tom rotmapp i mallen → behåll originalet så att
        # användaren inte står utan innehåll.
        return items, False

    return stripped, True


MAX_TREE_DEPTH: int = 40


MAX_TREE_ENTRIES: int = 20000


TREE_IGNORED_DIRS = frozenset({
    '.git', '__pycache__', '.idea', '.vscode',
    'node_modules', 'venv', '.env', '.tox',
})


def generate_tree_string_safe(
    root_path: Path,
    max_depth: int = MAX_TREE_DEPTH,
    max_entries: int = MAX_TREE_ENTRIES,
    include_dotfiles: bool = False,
) -> str:
    """
    Säkert alternativ till StructureEngine.generate_tree_string:
      • max_depth    → ingen RecursionError vid extremt djupa träd
      • resolve()-deduplicering → ingen oändlig loop vid cirkulära symlänkar
      • max_entries  → ingen minnesexplosion vid t.ex. node_modules-jättar
      • PermissionError per mapp → '<Åtkomst nekad>' istället för krasch
      • include_dotfiles → .gitignore/.env kan exporteras (MB12)

    Returnerar alltid en sträng; kastar aldrig.
    """
    root_path = Path(root_path)
    if not root_path.exists():
        return "Mappen finns inte."

    lines: List[str] = [f"{root_path.name}/"]
    state = {'entries': 0, 'hit_depth': False, 'hit_entries': False}
    seen: set = set()
    try:
        seen.add(str(root_path.resolve()))
    except OSError:
        seen.add(str(root_path))

    def walk(directory: Path, prefix: str, depth: int) -> None:
        if depth >= max_depth:
            state['hit_depth'] = True
            return
        if state['hit_entries']:
            return
        try:
            contents = list(directory.iterdir())
        except (PermissionError, OSError):
            lines.append(f"{prefix}└── <Åtkomst nekad>")
            return

        filtered = []
        for x in contents:
            if x.name in TREE_IGNORED_DIRS:
                continue
            if x.name.startswith('.') and not include_dotfiles:
                continue
            filtered.append(x)
        filtered.sort(key=lambda p: (not p.is_dir(), p.name.lower()))

        for i, path in enumerate(filtered):
            if state['entries'] >= max_entries:
                state['hit_entries'] = True
                return
            state['entries'] += 1

            is_last = i == len(filtered) - 1
            connector = "└── " if is_last else "├── "
            is_dir = path.is_dir()
            lines.append(f"{prefix}{connector}{path.name}{'/' if is_dir else ''}")

            if is_dir:
                try:
                    key = str(path.resolve())
                except OSError:
                    key = str(path)
                if key in seen:
                    lines.append(f"{prefix}{'    ' if is_last else '│   '}└── <symlink-loop, hoppad över>")
                    continue
                seen.add(key)
                walk(path, prefix + ("    " if is_last else "│   "), depth + 1)

    walk(root_path, "", 0)

    if state['hit_depth']:
        lines.append(f"... (avbröts: max djup {max_depth} nått)")
    if state['hit_entries']:
        lines.append(f"... (avbröts: max {max_entries} poster nådda)")
    return "\n".join(lines)


def ui_call(root: Any, fn: Any, *args: Any, **kwargs: Any) -> bool:
    """
    Anropa en Tk-widgetmetod från valfri tråd. Tk är inte trådsäkert:
    alla widgetanrop måste ske i huvudtråden via after(0, ...).

    Returnerar True om anropet schemalades, False om root redan är trasigt
    (t.ex. under nedstängning) — då ska anropet bara ignoreras, aldrig krascha.
    """
    def _run() -> None:
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("UI-anrop misslyckades i huvudtråden")

    try:
        root.after(0, _run)
        return True
    except Exception:
        return False


HOTKEY_KEY_ORDER: Dict[str, int] = {
    'ctrl': 0, 'control': 0, 'alt': 1, 'option': 1,
    'shift': 2, 'cmd': 3, 'win': 3, 'super': 3, 'command': 3,
}


def normalize_hotkey_keys(keys: Iterable[str]) -> List[str]:
    """
    Normaliserar pynput-tangentnamn till en stabil, läsbar ordning:
      'Key.ctrl_l' → 'ctrl', 'Key.shift_r' → 'shift', modifierare först.
    Samma logik som redan finns i _on_press_rec, men GUI-fri och testbar.
    """
    norm: List[str] = []
    for k in keys or []:
        if k is None:
            continue
        s = str(k).strip().lower()
        if not s:
            continue
        if s.startswith('key.'):
            s = s[4:]
        s = s.replace('_l', '').replace('_r', '')
        if s and s not in norm:
            norm.append(s)
    norm.sort(key=lambda x: (HOTKEY_KEY_ORDER.get(x, 99), x))
    return norm


def hotkey_label(keys: Iterable[str]) -> str:
    """Visningstext: 'Ctrl + Shift + M'."""
    return " + ".join(k.capitalize() for k in normalize_hotkey_keys(keys))


_PREV_THREAD_HOOK: List[Any] = []


def install_crash_hooks(log: Any = None) -> bool:
    """
    Installerar globala felkrokar så att INGET undantag försvinner spårlöst.
    `log` är en logger (eller något med .error/.exception). Originalkrokarna
    anropas alltid efteråt — beteendet i konsolen förändras inte.

    Returnerar True om båda krokarna installerades.
    """
    target = log if log is not None else logging.getLogger(__name__)
    ok = True

    def _excepthook(exc_type, exc_value, tb):
        try:
            target.error("OFÅNGAT UNDANTAG (huvudtråden)",
                         exc_info=(exc_type, exc_value, tb))
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, tb)

    # Spara undan kroken som fanns INNAN denna installation, så att den kan
    # kedjas vidare. Jämförelse mot oss själva sker efter att funktionen
    # definierats (se nedan) för att undvika NameError.
    prev = threading.excepthook

    def _thread_excepthook(args):
        try:
            name = getattr(getattr(args, 'thread', None), 'name', '?')
            target.error(
                "OFÅNGAT UNDANTAG i tråd '%s'", name,
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        except Exception:
            pass
        for old in list(_PREV_THREAD_HOOK):
            if callable(old) and old is not _thread_excepthook:
                try:
                    old(args)
                except Exception:
                    pass

    if prev is not _thread_excepthook:
        _PREV_THREAD_HOOK[:] = [prev] if callable(prev) else []

    try:
        sys.excepthook = _excepthook
    except Exception:
        ok = False
    try:
        threading.excepthook = _thread_excepthook
    except Exception:
        ok = False
    return ok

# ============================================================
# Färghjälpfunktion — simulerar transparens utan alpha-hex
# ============================================================
def blend_color(
    hex_color: str,
    alpha: float,
    bg_light: str = "#E5E5E5",
    bg_dark: str = "#2B2B2B",
) -> Tuple[str, str]:
    """
    Simulerar transparens genom att blanda hex_color med ljus/mörk bakgrund.
    alpha: 0.0 (helt transparent) → 1.0 (helt ogenomskinlig)
    Returnerar (ljusläge_färg, mörkläge_färg).
    """

    def _blend(fg: str, bg: str, a: float) -> str:
        fg = fg.lstrip('#')
        bg = bg.lstrip('#')
        fr, fg_g, fb = int(fg[0:2], 16), int(fg[2:4], 16), int(fg[4:6], 16)
        br, bg_g, bb = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
        r = int(fr * a + br * (1 - a))
        g = int(fg_g * a + bg_g * (1 - a))
        b = int(fb * a + bb * (1 - a))
        return f"#{r:02x}{g:02x}{b:02x}"

    return (_blend(hex_color, bg_light, alpha), _blend(hex_color, bg_dark, alpha))


# ============================================================
# Validering
# ============================================================
class NameValidator:
    @staticmethod
    def sanitize(name: str) -> str:
        """
        Rensar ett mappnamn enligt Windows-regler.

        M18 — delegerar till sanitize_name(), som utöver v4.1:s regler även
        blockerar reserverade systemnamn MED filändelse (CON.txt, NUL.md,
        LPT1.log) via RESERVED_STEM_RE. v4.1 jämförde bara cleaned.upper()
        mot INVALID_NAMES och släppte alltså igenom "CON.txt", vilket kan
        göra mappen omöjlig att skapa eller ta bort på Windows.

        Kontraktet är oförändrat: returnerar en rensad sträng eller kastar
        ValueError. Metoden behålls som publik API-yta — inget tas bort.
        """
        return sanitize_name(name)

    @staticmethod
    def is_safe_path(base: Path, target: Path) -> bool:
        try:
            target.resolve().relative_to(base.resolve())
            return True
        except ValueError:
            return False


# ============================================================
# Dataklasser
# ============================================================
@dataclass
class AppSettings:
    save_root: str = field(default_factory=lambda: str(Path.home() / "Projects"))
    open_after_creation: bool = True
    theme: str = "Dark"
    default_template: str = "Skaderapport"
    last_template: str = ""
    plate_mode: bool = True
    start_minimized: bool = True    # starta i systray utan att visa fönstret
    visible_tabs: Dict[str, bool] = field(default_factory=lambda: {
        t: True for t in TAB_ICONS
    })

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        # M3/C2 — validera mot schema INNAN något används. Fel typ, okänt
        # enum-värde eller saknad nyckel rättas till default istället för att
        # följa med in i appen och krascha längre ner i GUI:t. validate_settings
        # är idempotent, så att _load_settings redan validerat spelar ingen roll.
        data, repaired, log = validate_settings(data)
        if repaired:
            for line in log:
                logger.warning("Inställning reparerad: %s", line)
        default_tabs = {t: True for t in TAB_ICONS}
        saved_tabs = data.get("visible_tabs", {})
        default_tabs.update(saved_tabs)
        return cls(
            save_root=data.get("save_root", str(Path.home() / "Projects")),
            open_after_creation=data.get("open_after_creation", True),
            theme=data.get("theme", "Dark"),
            default_template=data.get("default_template", "Skaderapport"),
            last_template=data.get("last_template", ""),
            plate_mode=data.get("plate_mode", True),
            start_minimized=data.get("start_minimized", True),
            visible_tabs=default_tabs,
        )


# ============================================================
# Undo-system
# ============================================================
class UndoManager:
    def __init__(self) -> None:
        self._history: List[Path] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._history)

    @property
    def last_path(self) -> Optional[Path]:
        return self._history[-1] if self._history else None

    def record(self, path: Path) -> None:
        self._history.append(path)

    def undo(self) -> Optional[Path]:
        if not self._history:
            return None
        path = self._history.pop()
        if path.exists():
            shutil.rmtree(path)
        return path


# ============================================================
# Mallsystem
# ============================================================
class TemplateManager:
    def __init__(self) -> None:
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        self._builtin = self._create_builtins()

    @staticmethod
    def _create_builtins() -> Dict[str, str]:
        return {
            "Python Projekt": (
                "projektnamn/\n    src/\n        __init__.py\n        main.py\n"
                "    tests/\n        test_main.py\n    docs/\n"
                "    requirements.txt\n    README.md\n    .gitignore\n"
            ),
            "Webb Projekt": (
                "projektnamn/\n    public/\n        index.html\n        style.css\n"
                "    src/\n        app.js\n    assets/\n        images/\n"
                "    README.md\n    package.json\n"
            ),
            "Skaderapport": (
                "ärendenummer/\n    Bilder/\n    Skadeanmälan/\n"
                "    Diagnos/\n    Instruktioner/\n    Kvalitetsrapport/\n"
            ),
        }

    def list_templates(self) -> Dict[str, str]:
        templates = dict(self._builtin)
        for f in TEMPLATES_DIR.glob("*.json"):
            # M2/C41.3 — read_json_safe() återställer från .bak/.bak2 om filen
            # är trasig, istället för att bara hoppa över mallen.
            data = read_json_safe(f, None)
            if not isinstance(data, dict):
                logger.warning("Kunde inte läsa mall %s: ogiltig eller saknad JSON",
                               f.name)
                continue
            try:
                if isinstance(data["name"], str) and isinstance(data["structure"], str):
                    templates[data["name"]] = data["structure"]
            except KeyError as e:
                logger.warning("Kunde inte läsa mall %s: %s", f.name, e)
        return templates

    def save_template(self, name: str, structure: str) -> None:
        if name in self._builtin:
            raise ValueError("Inbyggda mallar kan inte skrivas över. Välj ett eget namn.")
        if not StructureEngine.parse_structure_text(structure)[1]:
            raise ValueError("Mallen måste innehålla en struktur.")
        safe = NameValidator.sanitize(name)
        # M1/F1 — atomisk skrivning med backup. Obs: filen får nu indent=2
        # (atomic_write_json:s standard) istället för en enda lång rad;
        # innehållet och inläsningsvägen är oförändrade.
        if not atomic_write_json(
            TEMPLATES_DIR / f"{safe}.json",
            {"name": name, "structure": structure},
        ):
            raise OSError(f"Kunde inte spara mall {name!r}")

    def delete_template(self, name: str) -> bool:
        if name in self._builtin:
            return False
        safe = NameValidator.sanitize(name)
        p = TEMPLATES_DIR / f"{safe}.json"
        if p.exists():
            p.unlink()
            return True
        return False


# ============================================================
# Strukturmotor
# ============================================================
class StructureEngine:
    IGNORED_DIRS: Final[frozenset] = frozenset({
        '.git', '__pycache__', '.idea', '.vscode',
        'node_modules', 'venv', '.env', '.tox',
    })

    @staticmethod
    def is_file(name: str) -> bool:
        clean = name.rstrip('/\\')
        if name.endswith(('/', '\\')):
            return False
        if clean.lower() in KNOWN_FILES:
            return True
        return '.' in clean

    @staticmethod
    def parse_structure_text(text: str) -> Tuple[Optional[str], List[dict]]:
        lines = text.splitlines()
        preprocessed: List[Tuple[int, str, Optional[str]]] = []
        indent_lengths: Set[int] = set()

        for line in lines:
            if not line.strip():
                continue
            comment = None
            if '<-' in line:
                line, comment = line.split('<-', 1)
            elif '←' in line:
                line, comment = line.split('←', 1)
            line = line.rstrip()
            match = re.match(r'^([ │├──└──\t]*)', line)
            prefix = match.group(1) if match else ""
            name = line[len(prefix):].strip()
            if not name:
                continue
            if len(prefix) > 0:
                indent_lengths.add(len(prefix))
            preprocessed.append(
                (len(prefix), name, comment.strip() if comment else None)
            )

        unit = min(indent_lengths) if indent_lengths else 1
        items: List[dict] = []
        stack: List[str] = []

        for ilen, name, cmt in preprocessed:
            depth = ilen // unit if unit else 0
            while len(stack) > depth:
                stack.pop()
            clean = name.rstrip('/\\')
            is_dir = not StructureEngine.is_file(name)
            items.append({
                'path': list(stack) + [clean],
                'is_dir': is_dir,
                'comment': cmt,
            })
            if is_dir:
                stack.append(clean)

        return None, items

    @classmethod
    def generate_tree_string(cls, root_path: Path) -> str:
        """
        M12/MB10 — delegerar till generate_tree_string_safe(), som har
        djupgräns (MAX_TREE_DEPTH), symlink-loop-detektering via resolve(),
        posttak (MAX_TREE_ENTRIES) och PermissionError-hantering per mapp.

        v4.1:s version rekade utan något tak: ett tillräckligt djupt träd gav
        RecursionError och en cirkulär symlänk gav en oändlig loop. Alla
        anropare får nu det säkra beteendet via denna enda ingång.

        _tree_recursive() behålls oförändrad nedan — ingen metod tas bort.
        """
        return generate_tree_string_safe(root_path)

    @classmethod
    def _tree_recursive(
        cls, directory: Path, prefix: str, lines: List[str],
    ) -> None:
        try:
            contents = list(directory.iterdir())
        except PermissionError:
            lines.append(f"{prefix}└── <Åtkomst nekad>")
            return
        filtered = [
            x for x in contents
            if x.name not in cls.IGNORED_DIRS and not x.name.startswith('.')
        ]
        filtered.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
        for i, path in enumerate(filtered):
            is_last = i == len(filtered) - 1
            connector = "└── " if is_last else "├── "
            suffix = '/' if path.is_dir() else ''
            lines.append(f"{prefix}{connector}{path.name}{suffix}")
            if path.is_dir():
                cls._tree_recursive(
                    path, prefix + ("    " if is_last else "│   "), lines,
                )

    @staticmethod
    def count_items(items: List[dict]) -> Tuple[int, int]:
        return (
            sum(1 for i in items if i['is_dir']),
            sum(1 for i in items if not i['is_dir']),
        )


# ============================================================
# v5.0 — SKÄRMANPASSNING, IKON, AUTOSTART, TEMAMENYER, DIAGNOSTIK
# ============================================================
# Blocken nedan är lyfta TECKEN FÖR TECKEN ur folderforge_v5_block.py,
# som är GUI-fri och körs som egen testsvit (tests/test_v5_block.py) innan
# sammanslagning. Ordningen är signifikant: resolve_scale_factor() används
# av get_scale_factor() längre ner, och MENU_THEMES/menu_configure_kwargs()
# används av _build_menu() och _apply_menu_theme().
#
#   M27/B1  set_dpi_awareness, resolve_scale_factor, enumerate_monitors,
#           pick_monitor_for_point, clamp_window_into_monitor
#   M28/B2  build_fallback_icon, load_app_icon, apply_icon_to_window
#   M29/B3  get_startup_folder, write_startup_shortcut,
#           build_task_scheduler_command, enable/disable_autostart_all_methods
#   M14/B5  MENU_THEMES, normalize_appearance_mode, menu_colors,
#           menu_configure_kwargs
#   M29c/B6 parse_autostart_command, test_autostart_command,
#           collect_diagnostics, format_diagnostics, collect_autostart_status
#
# B1 — SKÄRMANPASSNING: DPI-medvetenhet (M27)
# ══════════════════════════════════════════════════════════════════
DPI_UNAWARE: int = 0
DPI_SYSTEM_AWARE: int = 1
DPI_PER_MONITOR_AWARE: int = 2
DPI_PER_MONITOR_V2: int = 3

# Windows 10 1703+ använder "DPI_AWARENESS_CONTEXT"-pekarvärden, inte heltal.
# -4 = PER_MONITOR_AWARE_V2. Dokumenterat av Microsoft; värdet är en konstant
# och inte ett handtag, så det måste aldrig CloseHandle()s.
_DPI_CONTEXT_PER_MONITOR_V2 = ctypes.c_void_p(-4)
_DPI_CONTEXT_SYSTEM_AWARE = ctypes.c_void_p(-2)


def set_app_user_model_id(app_id: str = APP_NAME) -> None:
    """
    Ge processen en egen AppUserModelID (AUMID) — krävs för att ikonen ska
    bete sig rätt i AKTIVITETSFÄLTET på Windows.

    Utan en egen AUMID ärver fönstret pythonw.exe-processens identitet:
    appen kan då slås ihop med andra Python-fönster i aktivitetsfältet, visa
    Pythons ikon istället för sin egen, och en eventuell fästning hamnar på
    fel program. Med AUMID får FolderForge egen gruppering, egen ikon i
    aktivitetsfält/Alt-Tab och rätt identitet vid fästning.

    Måste anropas FÖRE att något fönster skapas (samma krav som DPI-sättning).
    Kastar aldrig — utanför Windows eller vid misslyckande händer inget.
    """
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        logger.debug("AppUserModelID satt till %r", app_id)
    except Exception as exc:
        logger.debug("AppUserModelID kunde inte sättas: %s", exc)


def set_dpi_awareness(
    windll: Any = None,
) -> Tuple[int, str]:
    """
    Sätt processens DPI-medvetenhet FÖRE Tk initieras.

    Utan detta skalar Windows hela fönstret som en bitmapp (DPI-virtualisering),
    vilket ger suddig text på alla högupplösta skärmar — och winfo_screenwidth()
    rapporterar den virtualiserade, inte den fysiska, upplösningen.

    Prova i fallande ordning och returnera (nivå, metod):
      1. SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)  — Win10 1703+
      2. SetProcessDpiAwareness(PER_MONITOR_DPI_AWARE)        — Win8.1+
      3. SetProcessDPIAware()                                 — Vista+
      4. (0, "skipped") utanför Windows

    Kastar aldrig: DPI är en förbättring, inte ett krav, och ett misslyckande
    får aldrig hindra appen från att starta (C41).
    """
    if not IS_WINDOWS:
        return DPI_UNAWARE, "skipped"

    dll = windll if windll is not None else getattr(ctypes, "windll", None)
    if dll is None:
        return DPI_UNAWARE, "no-windll"

    # 1) Modern kontextbaserad API (bäst: per-monitor V2)
    try:
        user32 = dll.user32
        fn = getattr(user32, "SetProcessDpiAwarenessContext", None)
        if fn is not None and fn(_DPI_CONTEXT_PER_MONITOR_V2):
            return DPI_PER_MONITOR_V2, "SetProcessDpiAwarenessContext"
    except Exception as exc:                       # pragma: no cover - OS-beroende
        logger.debug("SetProcessDpiAwarenessContext otillgänglig: %s", exc)

    # 2) Win8.1 shcore
    try:
        shcore = dll.shcore
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        if shcore.SetProcessDpiAwareness(DPI_PER_MONITOR_AWARE) == 0:
            return DPI_PER_MONITOR_AWARE, "SetProcessDpiAwareness"
    except Exception as exc:                       # pragma: no cover - OS-beroende
        logger.debug("shcore.SetProcessDpiAwareness otillgänglig: %s", exc)

    # 3) Vista system-aware
    try:
        if dll.user32.SetProcessDPIAware():
            return DPI_SYSTEM_AWARE, "SetProcessDPIAware"
    except Exception as exc:                       # pragma: no cover - OS-beroende
        logger.debug("SetProcessDPIAware otillgänglig: %s", exc)

    return DPI_UNAWARE, "failed"


def dpi_scale_from_pixels_per_inch(dpi: float) -> float:
    """
    Översätt verklig DPI till en skalfaktor relativt Windows baseline 96 DPI.

    Ren aritmetik — testbar utan Tk. Klampad till [0.5, 4.0] så att ett
    trasigt DPI-värde (0 eller negativt) aldrig ger nollstorlek på widgeter
    eller en absurd layout.
    """
    try:
        d = float(dpi)
    except (TypeError, ValueError):
        return 1.0
    # NaN och oändlighet måste fångas UTTRYCKLIGEN. Jämförelsen d <= 0 är False
    # för NaN, så utan denna vakt faller NaN igenom till min(4.0, nan) — som i
    # Python returnerar 4.0 eftersom alla NaN-jämförelser är falska. En skräp-
    # avläsning skulle då ge den MAXIMALA skalfaktorn, d.v.s. det mest extrema
    # gränssnittet möjligt, istället för det neutrala. isfinite() täcker NaN,
    # inf och -inf i ett svep.
    if not math.isfinite(d) or d <= 0:
        return 1.0
    return max(0.5, min(4.0, d / 96.0))


def resolve_scale_factor(
    dpi: Optional[float] = None,
    screen_width: Optional[int] = None,
) -> Tuple[float, str]:
    """
    Välj skalfaktor: verklig DPI om den finns, annars skärmbredd som reserv.

    Returnerar (scale, källa) där källa är "dpi" eller "screen_width" — så att
    diagnostiken (B5) kan visa VARFÖR appen skalade som den gjorde.

    Detta är den DPI-medvetna uppgraderingen av get_scale_factor(). Den gamla
    funktionen gissade utifrån skärmbredd alone, vilket gav fel på en 1920x1080
    skärm körd i 150 % Windows-skalning (bredden rapporteras då virtualiserad).
    """
    if dpi is not None:
        try:
            d = float(dpi)
        except (TypeError, ValueError):
            d = 0.0
        if d > 0:
            return dpi_scale_from_pixels_per_inch(d), "dpi"

    if screen_width is not None:
        try:
            sw = int(screen_width)
        except (TypeError, ValueError):
            sw = 0
        # Samma trösklar som get_scale_factor() i v4.3 — bevarat som reserv
        # så att beteendet är oförändrat när DPI inte kan läsas.
        if sw >= 3840:
            return 2.0, "screen_width"
        if sw >= 2560:
            return 1.5, "screen_width"
        if sw >= 1920:
            return 1.25, "screen_width"
        if sw > 0:
            return 1.0, "screen_width"

    return 1.0, "default"


# ── Multi-monitor ─────────────────────────────────────────────────
class MonitorInfo:
    """En fysisk bildskärm: rektangel + DPI + om den är primär."""

    __slots__ = ("left", "top", "right", "bottom", "dpi", "is_primary", "index")

    def __init__(
        self,
        left: int, top: int, right: int, bottom: int,
        dpi: float = 96.0, is_primary: bool = False, index: int = 0,
    ) -> None:
        self.left = int(left)
        self.top = int(top)
        self.right = int(right)
        self.bottom = int(bottom)
        self.dpi = float(dpi)
        self.is_primary = bool(is_primary)
        self.index = int(index)

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> Tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

    def contains(self, x: int, y: int) -> bool:
        """Sant om punkten ligger inom denna skärm (inkl. kant)."""
        return self.left <= x < self.right and self.top <= y < self.bottom

    def __repr__(self) -> str:                      # pragma: no cover - debug
        prim = " primär" if self.is_primary else ""
        return (f"<Monitor#{self.index} {self.width}x{self.height}"
                f"+{self.left}+{self.top}{prim} @ {self.dpi:.0f}dpi>")


def enumerate_monitors(windll: Any = None) -> List[MonitorInfo]:
    """
    Räkna upp alla bildskärmar via EnumDisplayMonitors.

    Returnerar [] utanför Windows eller om API:et saknas — anroparen faller
    då tillbaka på winfo_screenwidth() (en enda virtuell skärm).

    Använder ctypes-callback med referens hållen i en lokal variabel: om
    callback-objektet samlas in mitt i anropet kraschar processen hårt
    (access violation), inte bara med ett undantag.
    """
    if not IS_WINDOWS:
        return []

    dll = windll if windll is not None else getattr(ctypes, "windll", None)
    if dll is None:
        return []

    try:
        user32 = dll.user32
        shcore = getattr(dll, "shcore", None)
    except Exception as exc:                        # pragma: no cover - OS-beroende
        logger.debug("user32/shcore otillgängliga: %s", exc)
        return []

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_long * 4), ctypes.c_double,
    )
    found: List[MonitorInfo] = []

    def _cb(hmon, _hdc, lprc, _lparam):
        try:
            rect = lprc.contents
            left, top, right, bottom = rect[0], rect[1], rect[2], rect[3]
            dpi = 96.0
            if shcore is not None:
                try:
                    val = ctypes.c_uint(0)
                    # MDT_EFFECTIVE_DPI = 0
                    if shcore.GetDpiForMonitor(
                            hmon, 0, ctypes.byref(val), ctypes.byref(val)) == 0:
                        dpi = float(val.value) or 96.0
                except Exception:
                    dpi = 96.0
            prim = False
            try:
                prim = bool(user32.MonitorFromWindow(0, 0)) and \
                    hmon == user32.MonitorFromPoint(0, 0, 1)
            except Exception:
                prim = False
            found.append(MonitorInfo(
                left, top, right, bottom, dpi=dpi,
                is_primary=prim, index=len(found),
            ))
        except Exception as exc:                    # pragma: no cover
            logger.debug("Monitoruppräkning hoppade över en skärm: %s", exc)
        return 1                                    # fortsätt enumerera

    # HÅLL referensen: utan den kan GC frigöra callbacken under anropet.
    proc = MONITORENUMPROC(_cb)
    try:
        # MONITOR_DEFAULTTONULL = 0; hela virtuella skrivbordet
        user32.EnumDisplayMonitors(None, None, proc, 0)
    except Exception as exc:                        # pragma: no cover - OS-beroende
        logger.debug("EnumDisplayMonitors misslyckades: %s", exc)
        return []

    if not found:
        return []
    # Om ingen markerades primär, peka på den som innehåller origo
    if not any(m.is_primary for m in found):
        for m in found:
            if m.contains(0, 0):
                m.is_primary = True
                break
        else:
            found[0].is_primary = True
    return found


def pick_monitor_for_point(
    monitors: List[MonitorInfo], x: int, y: int,
) -> Optional[MonitorInfo]:
    """Välj skärmen som innehåller punkten; annars primär; annars första."""
    if not monitors:
        return None
    for m in monitors:
        if m.contains(x, y):
            return m
    for m in monitors:
        if m.is_primary:
            return m
    return monitors[0]


def clamp_window_into_monitor(
    x: int, y: int, w: int, h: int, mon: MonitorInfo, margin: int = 0,
) -> Tuple[int, int]:
    """
    Flytta ett fönster så att det HELT hamnar inom skärmen.

    Löser det verkliga problemet med sparad geometri: ett fönster placerat på
    en skärm som kopplats ur hamnar utanför alla synliga pixlar och går inte
    att dra tillbaka. Garanterar också att minst en remsa är nåbar.
    """
    m = max(0, int(margin))
    avail_w = max(1, mon.width - 2 * m)
    avail_h = max(1, mon.height - 2 * m)
    # Ett fönster större än skärmen: låt det fylla skärmen från dess övre vänstra
    ww = min(int(w), avail_w)
    hh = min(int(h), avail_h)
    nx = min(max(int(x), mon.left + m), mon.right - m - ww)
    ny = min(max(int(y), mon.top + m), mon.bottom - m - hh)
    return nx, ny


# ══════════════════════════════════════════════════════════════════
# B2 — IKON ÖVERALLT (M28)
# ══════════════════════════════════════════════════════════════════
# Fallback-färger: samma accentpalett som appen (ACCENT_BLUE / ACCENT_TEAL).
_ICON_BG_TOP: Tuple[int, int, int] = (76, 158, 241)
_ICON_BG_BOTTOM: Tuple[int, int, int] = (26, 188, 156)
_ICON_FG: Tuple[int, int, int] = (255, 255, 255)


def build_fallback_icon(size: int = 64) -> Optional[Any]:
    """
    Rita FolderForge-ikonen procedurellt (PIL) när projektmapp.ico saknas.

    C41-självläkning: v4.3 kontrollerade APP_ICON.exists() och hoppade tyst
    över ikonen om filen saknades — vilket den gjorde i arbetsytan, så appen
    körde utan ikon överallt. Denna fallback garanterar att en ikon alltid
    finns, utan att en binärfil måste följa med källkoden.

    Returnerar en PIL.Image i RGBA, eller None om Pillow saknas/kraschar.
    Kastar aldrig.
    """
    try:
        s = int(size)
    except (TypeError, ValueError):
        s = 64
    if s < 8:
        s = 8
    if s > 512:
        s = 512

    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        logger.debug("Pillow saknas — ingen fallback-ikon: %s", exc)
        return None

    try:
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)

        # Vertikal gradient bakgrund (blå → teal), rundade hörn via mask
        grad = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        for row in range(s):
            t = row / max(1, s - 1)
            r = int(_ICON_BG_TOP[0] + (_ICON_BG_BOTTOM[0] - _ICON_BG_TOP[0]) * t)
            g = int(_ICON_BG_TOP[1] + (_ICON_BG_BOTTOM[1] - _ICON_BG_TOP[1]) * t)
            b = int(_ICON_BG_TOP[2] + (_ICON_BG_BOTTOM[2] - _ICON_BG_TOP[2]) * t)
            gd.line([(0, row), (s, row)], fill=(r, g, b, 255))

        radius = max(2, int(s * 0.22))
        try:
            mask = Image.new("L", (s, s), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, s - 1, s - 1), radius=radius, fill=255)
            img.paste(grad, (0, 0), mask)
        except AttributeError:
            # Äldre Pillow utan rounded_rectangle — fyrkantig men fungerande
            img.paste(grad, (0, 0))

        # Mappsiluett: flik + kropp
        u = s / 16.0
        dr = ImageDraw.Draw(img)
        tab = [(3 * u, 4 * u), (7 * u, 4 * u), (8 * u, 5.5 * u), (3 * u, 5.5 * u)]
        dr.polygon(tab, fill=_ICON_FG)
        dr.rounded_rectangle(
            (3 * u, 5.5 * u, 13 * u, 12 * u),
            radius=max(1, int(u * 0.8)), fill=_ICON_FG,
        ) if hasattr(dr, "rounded_rectangle") else dr.rectangle(
            (3 * u, 5.5 * u, 13 * u, 12 * u), fill=_ICON_FG)

        # Plus-tecken i mappens mitt (signal: "skapa mapp")
        cx, cy = 8 * u, 8.75 * u
        arm, thick = 2.2 * u, max(1.0, 0.75 * u)
        accent = _ICON_BG_TOP
        dr.rectangle((cx - arm, cy - thick, cx + arm, cy + thick), fill=accent)
        dr.rectangle((cx - thick, cy - arm, cx + thick, cy + arm), fill=accent)

        return img
    except Exception as exc:
        logger.warning("Kunde inte rita fallback-ikon: %s", exc)
        return None


def load_app_icon(
    icon_path: Optional[Path] = None,
    size: int = 64,
    _cache: Dict[Tuple[str, int], Any] = {},
) -> Optional[Any]:
    """
    Hämta appikonen som PIL.Image: fil först, procedurell fallback annars.

    Cache per (sökväg, storlek) så att tray, root och varje Toplevel inte
    läser om och ritar om samma bild. Cachen är en modulnivå-dict (mutable
    default) — medvetet, eftersom ikonen är oföränderlig under körning.

    Kastar aldrig: returnerar None om varken fil eller fallback kan skapas.
    """
    p = Path(icon_path) if icon_path else None
    key = (str(p) if p else "<fallback>", int(size))
    if key in _cache:
        return _cache[key]

    img = None
    if p is not None:
        try:
            if p.exists():
                from PIL import Image
                img = Image.open(p)
                img = img.convert("RGBA")
                if img.size != (size, size):
                    img = img.resize((int(size), int(size)))
        except Exception as exc:
            logger.warning("Ikonfilen %s kunde inte läsas (%s) — fallback.", p, exc)
            img = None

    if img is None:
        img = build_fallback_icon(size)

    _cache[key] = img
    return img


def apply_icon_to_window(
    win: Any,
    icon_path: Optional[Path] = None,
    photo_holder: Optional[List[Any]] = None,
    size: int = 64,
) -> str:
    """
    Sätt ikon på ett Tk-root eller CTkToplevel, på alla plattformar.

    Windows  : iconbitmap(.ico)  — ger ikon i titelrad, taskbar och Alt-Tab
    Övrigt   : iconphoto(True, PhotoImage) — samma sak på X11/macOS

    KRITISK DETALJ: Tk:s PhotoImage samlas in av Python-GC om ingen referens
    hålls, vilket gör att ikonen tyst försvinner efter en stund. photo_holder
    (en lista som ägs av fönstret/appen) behåller referensen.

    Returnerar vilken metod som användes ("iconbitmap", "iconphoto", "none")
    — används av diagnostiken (B5) så att du kan se om ikonen faktiskt sattes.

    Kastar aldrig.
    """
    if win is None:
        return "none"

    # Windows: .ico direkt är bäst (flerstorleks-fil, skalas av OS)
    if IS_WINDOWS and icon_path is not None:
        try:
            p = Path(icon_path)
            if p.exists():
                win.iconbitmap(str(p))
                return "iconbitmap"
        except Exception as exc:
            logger.debug("iconbitmap misslyckades (%s) — provar iconphoto.", exc)

    # Plattformsoberoende: iconphoto med en PIL-bild (fil eller fallback)
    try:
        from PIL import Image, ImageTk
        img = load_app_icon(icon_path, size=size)
        if img is None:
            return "none"
        photo = ImageTk.PhotoImage(img)
        if photo_holder is not None:
            photo_holder.append(photo)          # förhindra GC av ikonen
        else:
            # Ingen ägare: fäst på widgeten själv så att den lever lika länge
            try:
                setattr(win, "_ms_icon_photo", photo)
            except Exception:
                pass
        try:
            win.iconphoto(True, photo)
        except TypeError:
            # Vissa CTk-versioner saknar default-arg
            win.iconphoto(photo)
        return "iconphoto"
    except Exception as exc:
        logger.debug("iconphoto misslyckades: %s", exc)
        return "none"


# ══════════════════════════════════════════════════════════════════
# B3 — BÄTTRE AUTOSTART (M29): startup-genväg, Task Scheduler, diagnostik
# ══════════════════════════════════════════════════════════════════
# Tre oberoende mekanismer i fallande ordning. v4.3 hade EN (Run-nyckeln),
# och när den nekades av gruppolicy eller ett standardkonto fick användaren
# bara en felruta utan alternativ.

AUTOSTART_METHODS: Tuple[str, ...] = ("registry", "startup_folder", "task_scheduler")
AUTOSTART_TASK_NAME: str = "FolderForge_Autostart"

# FOLDERID_Startup — Microsoft-dokumenterad GUID, oförändrad sedan Vista.
_FOLDERID_STARTUP: str = "{B97D20BB-F46A-4C97-BA10-5E3608430854}"
_CSLID_STARTUP: int = 0x0007


def get_startup_folder(
    windll: Any = None, create: bool = False,
) -> Optional[Path]:
    """
    Sökvägen till användarens Start-meny\\Program\\Startup (shell:startup).

    Prova SHGetKnownFolderPath (Vista+) och fall tillbaka på
    SHGetFolderPathW med CSIDL_STARTUP. Returnerar None utanför Windows
    eller om båda misslyckas.

    Kastar aldrig.
    """
    if not IS_WINDOWS:
        return None

    dll = windll if windll is not None else getattr(ctypes, "windll", None)
    if dll is None:
        return None

    # 1) Modern API: SHGetKnownFolderPath. GUID-strukturen byggs manuellt med
    #    ctypes så att inget extra beroende (comtypes/pywin32) krävs för att
    #    hitta mappen — detta är en fallback-väg och måste vara beroendefri.
    try:
        shell32 = dll.shell32
        ole32 = dll.ole32

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        g = GUID()
        g.Data1 = 0xB97D20BB
        g.Data2 = 0xF46A
        g.Data3 = 0x4C97
        for i, byte in enumerate(
                (0xBA, 0x10, 0x5E, 0x36, 0x08, 0x43, 0x08, 0x54)):
            g.Data4[i] = byte

        out = ctypes.c_wchar_p()
        # KF_FLAG_DEFAULT = 0
        hr = shell32.SHGetKnownFolderPath(
            ctypes.byref(g), 0, None, ctypes.byref(out))
        if hr == 0 and out.value:
            p = Path(out.value)
            try:
                ole32.CoTaskMemFree(out)
            except Exception:
                pass
            if create:
                try:
                    p.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    logger.debug("Kunde inte skapa startup-mappen: %s", exc)
            return p
    except Exception as exc:                        # pragma: no cover - OS
        logger.debug("SHGetKnownFolderPath misslyckades: %s", exc)

    # 2) Fallback: SHGetFolderPathW med CSIDL_STARTUP
    try:
        buf = ctypes.create_unicode_buffer(260)     # MAX_PATH
        # SHGetFolderPathW(hwnd, csidl, hToken, dwFlags, pszPath)
        hr = dll.shell32.SHGetFolderPathW(None, _CSLID_STARTUP, None, 0, buf)
        if hr == 0 and buf.value:
            p = Path(buf.value)
            if create:
                try:
                    p.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    logger.debug("Kunde inte skapa startup-mappen: %s", exc)
            return p
    except Exception as exc:                        # pragma: no cover - OS
        logger.debug("SHGetFolderPathW misslyckades: %s", exc)

    return None


def write_startup_shortcut(
    app_name: str,
    command: str,
    startup_dir: Optional[Path] = None,
    runner: Optional[Callable[..., Any]] = None,
    icon_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """
    Skriv en autostart-genväg i Start-menyns startup-mapp.

    Två spår, eftersom .lnk kräver COM (pywin32 eller PowerShell):
      1. .lnk via PowerShell WScript.Shell — riktig genväg med ikon
      2. .bat-fallback — ful men fungerar utan några beroenden alls

    Returnerar (ok, detalj). Kastar aldrig: detta är en fallback-väg som körs
    NÄR registret redan nekat, och får inte självt krascha appen.
    """
    if not command or not command.strip():
        return False, "tomt kommando"

    folder = Path(startup_dir) if startup_dir else get_startup_folder(create=True)
    if folder is None:
        return False, "startup-mappen kunde inte hittas"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"startup-mappen är inte skrivbar: {exc}"

    slug = re.sub(r"[^A-Za-z0-9_\-]+", "_", str(app_name)).strip("_") or "App"
    run = runner if runner is not None else subprocess.run

    # ── Spår 1: riktig .lnk via PowerShell ────────────────────────
    lnk = folder / f"{slug}.lnk"
    exe, _, args = command.partition(" ")
    exe = exe.strip('"')

    def _psq(text: Any) -> str:
        """PowerShell-citering: ' dubbleras till '' i enkelciterade strängar.

        Utan detta bröt en sökväg med apostrof (t.ex. C:\\Users\\Lisa's ...)
        hela kommandot, och spår 1 föll tyst tillbaka på .bat-varianten."""
        return str(text).replace("'", "''")

    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
        f"'{_psq(lnk)}');"
        f"$s.TargetPath='{_psq(exe)}';"
        f"$s.Arguments='{_psq(args.strip())}';"
        f"$s.WorkingDirectory='{_psq(Path(exe).parent)}';"
        "$s.WindowStyle=7;"       # 7 = minimerad, ingen konsolruta
    )
    if icon_path is not None:
        # Genvägen får appens ikon — annars visar Explorer Pythons standard.
        ps += f"$s.IconLocation='{_psq(icon_path)}';"
    ps += "$s.Save()"
    try:
        res = run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if getattr(res, "returncode", 1) == 0 and lnk.exists():
            return True, f"lnk:{lnk}"
        logger.debug("PowerShell-genväg misslyckades: %s",
                     getattr(res, "stderr", "")[:200])
    except FileNotFoundError:
        logger.debug("powershell finns inte — provar .bat-fallback.")
    except Exception as exc:
        logger.debug("PowerShell-genväg kastade: %s", exc)

    # ── Spår 2: .bat-fallback ─────────────────────────────────────
    bat = folder / f"{slug}.bat"
    try:
        # 'start "" /B' + pythonw ger ingen konsolruta (samma mönster som
        # build_autostart_command redan använder).
        bat.write_text(f"@echo off\r\nstart \"\" /B {command}\r\n",
                       encoding="utf-8")
        if bat.exists():
            return True, f"bat:{bat}"
    except OSError as exc:
        return False, f"kunde inte skriva genväg: {exc}"

    return False, "både .lnk och .bat misslyckades"


def delete_startup_shortcut(
    app_name: str, startup_dir: Optional[Path] = None,
) -> bool:
    """Ta bort både .lnk och .bat ur startup-mappen. Kastar aldrig."""
    folder = Path(startup_dir) if startup_dir else get_startup_folder()
    if folder is None or not folder.exists():
        return True                                   # inget att ta bort
    slug = re.sub(r"[^A-Za-z0-9_\-]+", "_", str(app_name)).strip("_") or "App"
    removed_any = True
    for ext in (".lnk", ".bat"):
        f = folder / f"{slug}{ext}"
        try:
            if f.exists():
                f.unlink()
        except OSError as exc:
            logger.warning("Kunde inte ta bort %s: %s", f, exc)
            removed_any = False
    return removed_any


def read_startup_shortcut(app_name: str, startup_dir: Optional[Path] = None) -> Optional[str]:
    """Returnera sökvägen till befintlig genväg, annars None. Kastar aldrig."""
    folder = Path(startup_dir) if startup_dir else get_startup_folder()
    if folder is None or not folder.exists():
        return None
    slug = re.sub(r"[^A-Za-z0-9_\-]+", "_", str(app_name)).strip("_") or "App"
    for ext in (".lnk", ".bat"):
        f = folder / f"{slug}{ext}"
        if f.exists():
            return str(f)
    return None


def build_task_scheduler_command(
    app_name: str, command: str, task_name: Optional[str] = None,
) -> List[str]:
    """
    Bygg schtasks-kommandot för "kör vid inloggning".

    Returnerar en ARGUMENTLISTA (inte en sträng) så att anropet kan göras utan
    shell=True — ingen injektionsrisk från användarens sökvägar (C19-anda).

    /RL LIMITED  — kör utan förhöjda rättigheter, så att ingen UAC-prompt
                   dyker upp vid inloggning (höger prio: användaren ser inget).
    /SC ONLOGON  — vid inloggning, inte vid uppstart (app är per-användare).
    /F           — skriv över befintlig uppgift (idempotent).
    """
    tn = str(task_name or AUTOSTART_TASK_NAME)
    return [
        "schtasks", "/Create", "/F",
        "/TN", tn,
        "/TR", str(command),
        "/SC", "ONLOGON",
        "/RL", "LIMITED",
    ]


def register_task_scheduler(
    app_name: str,
    command: str,
    task_name: Optional[str] = None,
    runner: Optional[Callable[..., Any]] = None,
) -> Tuple[bool, str]:
    """
    Registrera autostart via Task Scheduler — tredje spåret.

    Mer robust än Run-nyckeln: överlever vissa gruppolicyer som rensar
    HKCU\\...\\Run, och syns i schemaläggaren där användaren kan felsöka.

    Returnerar (ok, detalj). Kastar aldrig.
    """
    if not IS_WINDOWS:
        return False, "task scheduler är Windows-only"
    if not command or not command.strip():
        return False, "tomt kommando"

    run = runner if runner is not None else subprocess.run
    argv = build_task_scheduler_command(app_name, command, task_name)
    try:
        res = run(
            argv, capture_output=True, text=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        rc = getattr(res, "returncode", 1)
        if rc == 0:
            return True, f"schtasks:{task_name or AUTOSTART_TASK_NAME}"
        err = (getattr(res, "stderr", "") or getattr(res, "stdout", "") or "").strip()
        return False, f"schtasks rc={rc}: {err[:200]}"
    except FileNotFoundError:
        return False, "schtasks.exe finns inte"
    except subprocess.TimeoutExpired:
        return False, "schtasks-timeout (25 s)"
    except Exception as exc:
        return False, f"schtasks kastade: {exc}"


def unregister_task_scheduler(
    task_name: Optional[str] = None,
    runner: Optional[Callable[..., Any]] = None,
) -> Tuple[bool, str]:
    """Avregistrera uppgiften. Saknad uppgift räknas som lyckat (idempotent)."""
    if not IS_WINDOWS:
        return True, "skipped"
    tn = str(task_name or AUTOSTART_TASK_NAME)
    run = runner if runner is not None else subprocess.run
    try:
        res = run(
            ["schtasks", "/Delete", "/F", "/TN", tn],
            capture_output=True, text=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        rc = getattr(res, "returncode", 1)
        if rc == 0:
            return True, "deleted"
        err = (getattr(res, "stderr", "") or "").lower()
        # "The system cannot find the file specified" → fanns inte redan
        if "cannot find" in err or "inte hitta" in err:
            return True, "not-present"
        return False, f"schtasks rc={rc}: {err[:200]}"
    except FileNotFoundError:
        return False, "schtasks.exe finns inte"
    except Exception as exc:
        return False, f"schtasks kastade: {exc}"


def query_task_scheduler(
    task_name: Optional[str] = None,
    runner: Optional[Callable[..., Any]] = None,
) -> Optional[str]:
    """Returnera rå schtasks-utdata om uppgiften finns, annars None."""
    if not IS_WINDOWS:
        return None
    tn = str(task_name or AUTOSTART_TASK_NAME)
    run = runner if runner is not None else subprocess.run
    try:
        res = run(
            ["schtasks", "/Query", "/TN", tn, "/FO", "LIST", "/V"],
            capture_output=True, text=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if getattr(res, "returncode", 1) == 0:
            return getattr(res, "stdout", "") or ""
    except Exception as exc:
        logger.debug("schtasks /Query misslyckades: %s", exc)
    return None


def enable_autostart_all_methods(
    app_name: str,
    command: str,
    reg_writer: Optional[Callable[..., Tuple[bool, Optional[str]]]] = None,
    startup_dir: Optional[Path] = None,
    runner: Optional[Callable[..., Any]] = None,
    icon_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Slå på autostart och rapportera utfallet för VARJE metod.

    Detta är orkestreringen: registret först (billigast, mest osynligt),
    därefter startup-genväg om registret nekade, därefter Task Scheduler.
    Appen kräver att MINST EN lyckas — men rapporterar alla tre så att
    diagnostiken (B5) kan visa exakt vad som hände.

    Returnerar en dict: {"ok": bool, "methods": {namn: {"ok":..,"detail":..}}}
    Kastar aldrig.
    """
    resultat: Dict[str, Any] = {"ok": False, "methods": {}}

    # 1) Registret — använd befintlig write_autostart_entry om ingen injiceras
    try:
        writer = reg_writer
        if writer is None:
            writer = globals().get("write_autostart_entry")
        if writer is not None:
            ok, stored = writer(app_name, command)
            resultat["methods"]["registry"] = {
                "ok": bool(ok), "detail": stored or ("skrivet" if ok else "nekad"),
            }
        else:
            resultat["methods"]["registry"] = {
                "ok": False, "detail": "write_autostart_entry saknas"}
    except Exception as exc:
        resultat["methods"]["registry"] = {"ok": False, "detail": f"kastade: {exc}"}

    # 2) Startup-genväg — prova ALLTID, så att vi har redundans
    try:
        ok, detail = write_startup_shortcut(app_name, command, startup_dir,
                                            runner, icon_path=icon_path)
        resultat["methods"]["startup_folder"] = {"ok": bool(ok), "detail": detail}
    except Exception as exc:
        resultat["methods"]["startup_folder"] = {"ok": False, "detail": f"kastade: {exc}"}

    # 3) Task Scheduler — endast om de två första misslyckades (undvik
    #    trippla poster som alla startar appen)
    if not any(m["ok"] for m in resultat["methods"].values()):
        try:
            ok, detail = register_task_scheduler(app_name, command, None, runner)
            resultat["methods"]["task_scheduler"] = {"ok": bool(ok), "detail": detail}
        except Exception as exc:
            resultat["methods"]["task_scheduler"] = {"ok": False, "detail": f"kastade: {exc}"}

    resultat["ok"] = any(m["ok"] for m in resultat["methods"].values())
    return resultat


def disable_autostart_all_methods(
    app_name: str,
    reg_deleter: Optional[Callable[..., Any]] = None,
    startup_dir: Optional[Path] = None,
    runner: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """
    Stäng av autostart i ALLA tre mekanismer (idempotent).

    Viktigt: v4.3 raderade bara Run-nyckeln. Om en genväg eller uppgift
    skapats tidigare skulle appen fortsätta starta trots att rutan visar "av"
    — ett tyst löftesbrott. Därför rensas alla tre.
    """
    resultat: Dict[str, Any] = {"ok": True, "methods": {}}
    try:
        deleter = reg_deleter or globals().get("delete_autostart_entry")
        if deleter is not None:
            deleter(app_name)
            resultat["methods"]["registry"] = {"ok": True, "detail": "raderad"}
        else:
            resultat["methods"]["registry"] = {"ok": True, "detail": "saknad backend"}
    except Exception as exc:
        resultat["methods"]["registry"] = {"ok": False, "detail": f"kastade: {exc}"}
        resultat["ok"] = False

    try:
        ok = delete_startup_shortcut(app_name, startup_dir)
        resultat["methods"]["startup_folder"] = {
            "ok": bool(ok), "detail": "rensad" if ok else "kunde inte raderas"}
        if not ok:
            resultat["ok"] = False
    except Exception as exc:
        resultat["methods"]["startup_folder"] = {"ok": False, "detail": f"kastade: {exc}"}
        resultat["ok"] = False

    try:
        ok, detail = unregister_task_scheduler(None, runner)
        resultat["methods"]["task_scheduler"] = {"ok": bool(ok), "detail": detail}
        if not ok:
            resultat["ok"] = False
    except Exception as exc:
        resultat["methods"]["task_scheduler"] = {"ok": False, "detail": f"kastade: {exc}"}
        resultat["ok"] = False

    return resultat


# ══════════════════════════════════════════════════════════════════
# B5 — TEMAAVPASSADE MENYER (M14)
# ══════════════════════════════════════════════════════════════════
# v4.3 hårdkodade bg="#1e1e2e" (menyrad) och bg="#2b2b2b" (högerklick) på
# fem ställen. I ljust läge gav det en mörk menyrad ovanför ett ljust fönster
# — C12/C13 kräver att temat gäller HELA UI, inte bara CTk-widgeter.
#
# Färgerna definieras HÄR en gång (enda källan) istället för inline på varje
# användningsställe, vilket är vad regeln "inga hårdkodade färger" syftar på.

MENU_THEMES: Dict[str, Dict[str, str]] = {
    "Dark": {
        "bg": "#1e1e2e",
        "fg": "#f0f0f5",
        "active_bg": "#4C9EF1",
        "active_fg": "#ffffff",
        "disabled_fg": "#6a6a80",
        "border": "#2e2e42",
    },
    "Light": {
        "bg": "#f5f5f7",
        "fg": "#1a1a2e",
        "active_bg": "#30659a",
        "active_fg": "#ffffff",
        "disabled_fg": "#9a9aa8",
        "border": "#d8d8e0",
    },
}
DEFAULT_MENU_THEME: str = "Dark"


def normalize_appearance_mode(mode: Any) -> str:
    """
    Normalisera ett CTk-appearance_mode till 'Dark' eller 'Light'.

    Hanterar 'System' (och None/skräp) genom att fråga customtkinter om det
    faktiskt aktiva läget — annars faller tillbaka på DEFAULT_MENU_THEME.
    Ren stränglogik med injicerbar upslagare, så den testas headless.
    """
    m = str(mode or "").strip().lower()
    if m in ("dark", "light"):
        return m.capitalize()
    if m in ("system", ""):
        # 'System' → fråga CTk vilket läge som faktiskt är aktivt
        try:
            import customtkinter as _ctk
            resolved = str(_ctk.get_appearance_mode() or "").strip().lower()
            if resolved in ("dark", "light"):
                return resolved.capitalize()
        except Exception:
            pass
        return DEFAULT_MENU_THEME
    return DEFAULT_MENU_THEME


def menu_colors(appearance_mode: Any = None) -> Dict[str, str]:
    """
    Returnera menyfärgerna för givet läge — EN källa till sanning.

    Returnerar alltid en komplett dict (kopior, så att anroparen inte kan
    mutera temat). Okänt läge faller tillbaka på DEFAULT_MENU_THEME istället
    för att kasta: en meny som inte kan ritas är värre än en meny i fel tema.
    """
    key = normalize_appearance_mode(appearance_mode)
    theme = MENU_THEMES.get(key) or MENU_THEMES[DEFAULT_MENU_THEME]
    return dict(theme)


def menu_configure_kwargs(appearance_mode: Any = None) -> Dict[str, Any]:
    """
    kwargs till tk.Menu.configure() — så att alla menyer får samma utseende
    med ETT anrop istället för fem upprepade färglistor.

    Nycklarna är de som tk.Menu faktiskt accepterar: bg, fg, activebackground,
    activeforeground, disabledforeground, relief, bd, tearoff.
    """
    c = menu_colors(appearance_mode)
    return {
        "bg": c["bg"],
        "fg": c["fg"],
        "activebackground": c["active_bg"],
        "activeforeground": c["active_fg"],
        "disabledforeground": c["disabled_fg"],
        "relief": "flat",
        "bd": 0,
        "tearoff": 0,
    }


# ══════════════════════════════════════════════════════════════════
# B6 — AUTOSTART-DIAGNOSTIK + TESTKNAPP (M29c)
# ══════════════════════════════════════════════════════════════════
# Användaren valde "diagnostik + testknapp": kunna se EXAKT vad som står i
# registret/genvägen/schemaläggaren och verifiera att kommandot faktiskt
# skulle fungera — utan att gissa.

_CONSOLE_PYTHON_RE = re.compile(r"python[w]?\d*(?:\.\d+)*\.exe$", re.IGNORECASE)


def parse_autostart_command(command: str) -> Dict[str, Any]:
    """
    Dela upp en autostart-kommandorad i beståndsdelar och bedöm den.

    Returnerar:
      exe             : den körbara filen (avciterad)
      exe_exists      : finns den på disk?
      args            : övriga argument som lista
      script          : första argument som ser ut som en .py/.pyw-sökväg
      script_exists   : finns den på disk?
      console_python  : True om exe är python.exe (SVART RUTA vid inloggning)
      noconsole       : True om pythonw/fryst exe/'start "" /B'-wrapper
      uses_start      : True om kommandot lindats i cmd /c start "" /B
      frozen_assumed  : True om exe antas vara ett fryst (--windowed) bygge
      problems        : lista med mänskligt läsbara problem (tom = OK)

    Ren sträng- och filanalys: testbar headless utan Windows. Kompletterar
    is_stale_console_entry() (som bara svarar ja/nej) med DETALJERNA.
    """
    out: Dict[str, Any] = {
        "exe": "", "exe_exists": False, "args": [], "script": None,
        "script_exists": False, "console_python": False, "noconsole": False,
        "uses_start": False, "frozen_assumed": False, "problems": [],
    }
    raw = (command or "").strip()
    if not raw:
        out["problems"].append("Kommandot är tomt — autostart kan inte fungera.")
        return out

    low = raw.lower()
    out["uses_start"] = "start \"\" /b" in low or "start \"\"/b" in low

    # Dela med hänsyn till citattecken (shlex klarar Windows-stilar bättre
    # än en naiv split, men posix-läget äter backslash — därför posix=False).
    import shlex
    try:
        tokens = shlex.split(raw, posix=False)
    except ValueError:
        tokens = raw.split()
    tokens = [t.strip('"') for t in tokens if t and t.strip('"')]

    if not tokens:
        out["problems"].append("Kommandot innehåller inga körbara delar.")
        return out

    # Hoppa över en 'cmd /c start "" /B'-inledning för att hitta riktig exe
    idx = 0
    if tokens and tokens[0].lower().endswith(("cmd", "cmd.exe")):
        idx = 1
        while idx < len(tokens) and tokens[idx].lower() in ("/c", "start", ""):
            idx += 1
        while idx < len(tokens) and tokens[idx].lower() in ("/b", "/min"):
            idx += 1

    exe = tokens[idx] if idx < len(tokens) else tokens[0]
    rest = tokens[idx + 1:] if idx < len(tokens) else []
    out["exe"] = exe
    out["args"] = rest
    try:
        out["exe_exists"] = Path(exe).exists()
    except OSError:
        out["exe_exists"] = False

    # BUGGFIX: namnet måste plockas ur SÖKVÄGEN. Med Path() på Linux blir hela
    # "C:\Python312\python.exe" ett enda namn (backslash är inte separator i
    # POSIX), så startswith("python") slår aldrig till och konsolvarningen —
    # hela poängen med analysen — uteblir. PureWindowsPath delar på BÅDE '\'
    # och '/' och fungerar därför på alla plattformar. Autostart är Windows-
    # specifikt (Register/Startup/Task Scheduler), så formatet är givet.
    exe_name = PureWindowsPath(exe).name.lower() if exe else ""
    is_frozen = exe_name.endswith(".exe")
    if exe_name.startswith("pythonw"):
        # Fönsterlös tolk — korrekt för en GUI-app.
        out["noconsole"] = True
    elif exe_name.startswith("python"):
        # python.exe / python3.exe öppnar en svart konsolruta vid varje
        # inloggning. Uppstår typiskt när kommandot skrivs med sys.executable,
        # som oftast ÄR python.exe och inte pythonw.exe.
        out["console_python"] = True
        out["problems"].append(
            f"Pekar på konsol-python ({exe_name}) — en svart ruta visas "
            "vid varje inloggning. Ska vara pythonw.exe eller en fryst exe.")
    elif is_frozen:
        # Fryst PyInstaller-bygge. req.txt föreskriver --windowed, så ingen
        # konsol förväntas. Att filen heter just "folderforge" är ingen
        # förutsättning — användaren kan ha döpt om bygget.
        out["noconsole"] = True
        out["frozen_assumed"] = True
    if out["uses_start"] and not out["console_python"]:
        out["noconsole"] = True

    if not out["exe_exists"]:
        out["problems"].append(
            f"Den körbara filen finns inte: {exe or '(tom)'}")

    for a in rest:
        if a.lower().endswith((".py", ".pyw")):
            out["script"] = a
            try:
                out["script_exists"] = Path(a).exists()
            except OSError:
                out["script_exists"] = False
            if not out["script_exists"]:
                out["problems"].append(f"Skriptfilen finns inte: {a}")
            break

    if not out["noconsole"] and not out["console_python"]:
        out["problems"].append(
            "Kunde inte avgöra om kommandot visar en konsolruta — kontrollera manuellt.")

    return out


def test_autostart_command(
    command: str,
    runner: Optional[Callable[..., Any]] = None,
    dry_run: bool = True,
    timeout: int = 20,
) -> Dict[str, Any]:
    """
    Verifiera att ett autostart-kommando faktiskt skulle fungera.

    Med dry_run=True (standard) körs kommandot med tilläggsflaggan
    --selftest, som får appen att avsluta omedelbart med kod 0 utan att
    visa något fönster. Det bevisar att exe + skript + argument är korrekta
    utan att starta en riktig instans.

    Returnerar {"ok": bool, "returncode": int|None, "detail": str,
                "analysis": dict}. Kastar aldrig.
    """
    analysis = parse_autostart_command(command)
    result: Dict[str, Any] = {
        "ok": False, "returncode": None, "detail": "", "analysis": analysis,
    }
    if analysis["problems"]:
        result["detail"] = "; ".join(analysis["problems"])
        return result

    if not dry_run:
        result["ok"] = True
        result["detail"] = "Statisk analys OK (ingen körning begärd)."
        return result

    run = runner if runner is not None else subprocess.run
    argv = [analysis["exe"], *analysis["args"], "--selftest"]
    try:
        res = run(
            argv, capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        rc = getattr(res, "returncode", None)
        result["returncode"] = rc
        if rc == 0:
            result["ok"] = True
            result["detail"] = "Testkörning lyckades (exit 0, inget fönster)."
        else:
            err = (getattr(res, "stderr", "") or "").strip()[:300]
            result["detail"] = f"Testkörning gav exit {rc}. {err}".strip()
    except FileNotFoundError:
        result["detail"] = f"Kunde inte köra: {analysis['exe']} finns inte."
    except subprocess.TimeoutExpired:
        result["detail"] = f"Testkörningen tog över {timeout} s och avbröts."
    except Exception as exc:
        result["detail"] = f"Testkörning kastade: {exc}"
    return result


def collect_diagnostics(
    app_name: str = "FolderForge",
    app_version: str = "",
    icon_path: Optional[Path] = None,
    data_paths: Optional[Dict[str, Path]] = None,
    providers: Optional[Dict[str, Callable[[], Any]]] = None,
) -> Dict[str, Any]:
    """
    Samla ALL diagnostik i en dict — underlaget för Om-dialogen,
    "Kopiera systemdiagnostik"-knappen (M24) och autostart-testet.

    Varje avläsning sker via providers-dicten med säkra standarder, så att
    funktionen kan testas headless med fejkade värden och aldrig kraschar i
    produktion om ett enskilt anrop (t.ex. tkdnd-version) misslyckas.

    Kastar aldrig: diagnostik som kraschar är värre än ingen diagnostik.
    """
    prov = dict(providers or {})

    def safe(key: str, default: Any = "") -> Any:
        fn = prov.get(key)
        if fn is None:
            return default
        try:
            return fn()
        except Exception as exc:
            return f"<fel: {exc}>"

    info: Dict[str, Any] = {
        "app": {"name": app_name, "version": app_version,
                "frozen": bool(getattr(sys, "frozen", False))},
        "python": {
            "version": safe("python_version", sys.version.split()[0]),
            "executable": safe("python_executable", sys.executable),
            "platform": safe("platform", sys.platform),
        },
        "gui": {
            "tk_version": safe("tk_version"),
            "tkdnd_version": safe("tkdnd_version"),
            "dnd_available": safe("dnd_available"),
            "appearance_mode": safe("appearance_mode"),
            "customtkinter": safe("customtkinter_version"),
        },
        "display": {
            "dpi_level": safe("dpi_level"),
            "dpi_method": safe("dpi_method"),
            "scale_factor": safe("scale_factor"),
            "scale_source": safe("scale_source"),
            "monitors": safe("monitors", []),
            "screen": safe("screen"),
        },
        "icon": {
            "path": str(icon_path) if icon_path else "",
            "exists": bool(icon_path and Path(icon_path).exists()),
            "method": safe("icon_method"),
        },
        "packages": safe("packages", {}),
        "autostart": safe("autostart", {}),
        "data": {},
    }

    def _kan_skriva_har(target: Path) -> bool:
        """
        Kan appen skriva här? För en fil som inte finns än är den relevanta
        frågan inte "är filen skrivbar" utan "kan den SKAPAS" — därför testas
        närmaste befintliga förfader. os.access på en saknad fil svarar
        annars godtyckligt och ger falska "ej skrivbar"-larm vid första körningen.
        """
        kandidat = target if target.is_dir() else target.parent
        while not kandidat.exists() and kandidat != kandidat.parent:
            kandidat = kandidat.parent
        return bool(os.access(str(kandidat), os.W_OK))

    for label, p in (data_paths or {}).items():
        try:
            pp = Path(p)
            info["data"][label] = {
                "path": str(pp),
                "exists": pp.exists(),
                "writable": _kan_skriva_har(pp),
            }
        except OSError as exc:
            info["data"][label] = {"path": str(p), "error": str(exc)}

    info["data"]["writable_ok"] = all(
        v.get("writable", False) for k, v in info["data"].items()
        if isinstance(v, dict) and "writable" in v
    ) if info["data"] else True

    return info


def format_diagnostics(info: Dict[str, Any]) -> str:
    """
    Formatera collect_diagnostics()-utdata som läsbar text för urklipp.

    Platt, nyckel: värde-per-rad med sektionsrubriker — lätt att klistra in i
    ett forum eller ett felrapportssystem utan att formatering går förlorad.
    """
    lines: List[str] = []
    lines.append("=" * 62)
    app = info.get("app", {})
    lines.append(f"{app.get('name', 'App')} {app.get('version', '')} — "
                 f"SYSTEMDIAGNOSTIK")
    lines.append(f"Genererad: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 62)

    def section(title: str, data: Any) -> None:
        lines.append("")
        lines.append(f"[{title}]")
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict):
                    lines.append(f"  {k}:")
                    for k2, v2 in v.items():
                        lines.append(f"    {k2}: {v2}")
                elif isinstance(v, (list, tuple)):
                    lines.append(f"  {k}: {len(v)} st")
                    for item in v:
                        lines.append(f"    - {item}")
                else:
                    lines.append(f"  {k}: {v}")
        else:
            lines.append(f"  {data}")

    section("Python", info.get("python", {}))
    section("GUI", info.get("gui", {}))
    section("Skärm & DPI", info.get("display", {}))
    section("Ikon", info.get("icon", {}))
    section("Paket", info.get("packages", {}))
    section("Autostart", info.get("autostart", {}))
    section("Data & skrivbarhet", info.get("data", {}))
    lines.append("")
    lines.append("=" * 62)
    return "\n".join(lines)


def collect_autostart_status(
    app_name: str,
    reg_reader: Optional[Callable[..., Any]] = None,
    startup_dir: Optional[Path] = None,
    runner: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """
    Läs av autostart-läget i ALLA tre mekanismer + bedöm kommandot.

    Detta är vad testknappen visar: inte bara "på/av" utan exakt VAR appen
    startas ifrån och om det kommandot är friskt.
    """
    reader = reg_reader or globals().get("read_autostart_entry")
    reg_cmd: Optional[str] = None
    reg_err = ""
    try:
        if reader is not None:
            reg_cmd = reader(app_name)
    except Exception as exc:
        reg_err = str(exc)

    shortcut = read_startup_shortcut(app_name, startup_dir)
    task = query_task_scheduler(None, runner)

    active_command = reg_cmd or ""
    if not active_command and shortcut:
        active_command = f"(genväg: {shortcut})"

    out: Dict[str, Any] = {
        "enabled": bool(reg_cmd or shortcut or task),
        "registry": {"command": reg_cmd or "", "error": reg_err},
        "startup_folder": {"shortcut": shortcut or ""},
        "task_scheduler": {"present": bool(task)},
        "methods_active": [
            n for n, v in (
                ("registry", bool(reg_cmd)),
                ("startup_folder", bool(shortcut)),
                ("task_scheduler", bool(task)),
            ) if v
        ],
    }
    if reg_cmd:
        out["command_analysis"] = parse_autostart_command(reg_cmd)
    else:
        out["command_analysis"] = {}
    return out


# ============================================================
# v5.0 steg 2 — SIDEBAR-MODELL (GUI-fri, designvalen är testade)
# ============================================================
# Lyft ur tools/v5_block_sidebar.py. Allt som AVGÖR hur sidebarn beter sig
# ligger här istället för i widgetn, så att designen är testad och inte gissad:
# bredd, ikoner, ordning, kollapsgräns och färger. Widgetn i DynamicTabView
# blir då tunn presentation utan egen logik. Täcks av tests/test_v5_sidebar.py.
#
# Färgerna läses ur MENU_THEMES (M14) så att sidebar och menyer aldrig kan
# drifta isär i tema.
#
SIDEBAR_ITEMS: Tuple[Tuple[str, str, str], ...] = (
    # (nyckel, etikett, ikon)
    ("Skapa", "Skapa", "🏗️"),
    ("Historik", "Historik", "🕐"),
    ("Mallar", "Mallar", "📋"),
    ("Exportera", "Exportera", "📤"),
    ("Inställningar", "Inställningar", "⚙️"),
    ("Snabbtangent", "Snabbtangent", "⌨️"),
)

# Nycklar som alltid måste finnas i sidebarn, oavsett användarens
# visible_tabs-inställning. Utan minst en synlig post finns inget sätt att
# navigera, och appen skulle kunna hamna i ett läge utan innehåll alltså.
SIDEBAR_MINIMUM_VISIBLE: Tuple[str, ...] = ("Skapa",)

# Bredder i omskalade pixlar (basvärden för scale=1.0).
SIDEBAR_WIDTH_EXPANDED: int = 200
SIDEBAR_WIDTH_COLLAPSED: int = 62

# Under denna skärmbredd (logiska pixlar) kollapsar sidebarn automatiskt till
# ikon-läge. 1100 är valt så att ett 720 px brett huvudinnehåll fortfarande får
# plats bredvid en utfälld sidebar på en 1366x768-skärm — den minsta upplösning
# som fortfarande är vanlig — men inte på en smalare.
SIDEBAR_COLLAPSE_BELOW_WIDTH: int = 1100


@dataclass
class SidebarItem:
    """
    En post i sidebarn.

    Dataclass medvetet: appen använder redan @dataclass för AppSettings, så
    stilen är etablerad. Fälten är presentation (label/icon) plus tillstånd
    (visible/selected), vilket gör att widgetn i steg 2 bara behöver rita.
    """
    key: str
    label: str
    icon: str
    visible: bool = True
    selected: bool = False

    def display_text(self, collapsed: bool = False) -> str:
        """
        Texten som visas: ikon + etikett utfälld, endast ikon kollapsad.

        I kollapsat läge är ikonen den enda ledtråden, därför måste varje post
        ha en ikon — build_sidebar_items() garanterar det.
        """
        if collapsed:
            return self.icon
        return f"{self.icon}  {self.label}"

    def tooltip(self, collapsed: bool = False) -> str:
        """
        Verktygstips. Endast meningsfullt i kollapsat läge, där etiketten inte
        visas — men returneras alltid så att anroparen inte behöver grena.
        """
        return self.label if collapsed else ""


def build_sidebar_items(
    visible_tabs: Optional[Dict[str, Any]] = None,
    selected: Optional[str] = None,
    items: Optional[Sequence[Tuple[str, str, str]]] = None,
) -> List[SidebarItem]:
    """
    Bygg sidebarposterna ur användarens inställningar.

    visible_tabs är samma dict som appen redan sparar i settings.json
    ({"Skapa": True, "Historik": False, ...}), så sidebarn och den befintliga
    flikmekaniken delar EN källa till sanning om vad som visas. Okända nycklar
    i dictn ignoreras, och saknade nycklar betyder "synlig" — bakåtkompatibelt
    med en settings.json från v4.1 som inte känner till fältet.

    Garanterar att minst SIDEBAR_MINIMUM_VISIBLE poster är synliga, annars
    skulle appen kunna hamna i ett läge utan någon navigation alls.

    Kastar aldrig: en trasig settings.json får inte göra att appen inte startar.
    """
    kalla = items if items is not None else SIDEBAR_ITEMS
    valda = dict(visible_tabs or {})

    ut: List[SidebarItem] = []
    for post in kalla:
        try:
            key, label, icon = post[0], post[1], post[2]
        except (IndexError, TypeError):
            continue  # en trasig post hoppas över, resten byggs ändå
        synlig = bool(valda.get(key, True))
        ut.append(SidebarItem(
            key=str(key),
            label=str(label) or str(key),
            icon=str(icon) or "•",   # en post utan ikon vore oläsbar kollapsad
            visible=synlig,
        ))

    # Säkerställ att appen aldrig blir navigeringslös.
    for krav in SIDEBAR_MINIMUM_VISIBLE:
        for it in ut:
            if it.key == krav and not it.visible:
                it.visible = True
                break

    if selected:
        markera_vald(ut, selected)
    return ut


def visible_sidebar_items(items: Sequence[SidebarItem]) -> List[SidebarItem]:
    """Endast de synliga posterna, i given ordning."""
    return [it for it in items if it.visible]


def markera_vald(items: Sequence[SidebarItem], key: str) -> Optional[SidebarItem]:
    """
    Markera exakt en post som vald och avmarkera alla andra.

    Returnerar den valda posten, eller None om nyckeln inte finns — anroparen
    måste kunna skilja "valt något" från "bad om en obefintlig post", annars
    skulle ett felaktigt anrop tyst lämna sidebarn utan markering.

    En dold post kan väljas (anroparen kan ha skäl), men widgetn i steg 2 visar
    den inte; därför returneras den ändå.
    """
    vald = None
    for it in items:
        if it.key == key:
            it.selected = True
            vald = it
        else:
            it.selected = False
    return vald


def nasta_post(
    items: Sequence[SidebarItem],
    current: Optional[str],
    steg: int = 1,
) -> Optional[SidebarItem]:
    """
    Navigera med piltangenterna bland de SYNLIGA posterna, med omloop.

    Doldas måste hoppas över: att flytta markeringen till en post som inte
    syns vore detsamma som att tangentbordet slutade fungera.
    """
    synliga = visible_sidebar_items(items)
    if not synliga:
        return None
    idx = next((i for i, it in enumerate(synliga) if it.key == current), None)
    if idx is None:
        return synliga[0]
    return synliga[(idx + steg) % len(synliga)]


# ============================================================
# B4a — SIDEBAR: geometri och skärmanpassning
# ============================================================
def sidebar_width(collapsed: bool = False, scale: float = 1.0) -> int:
    """
    Sidebarens bredd i pixlar, skalad efter DPI.

    Klampad till minst 1 px så att ett trasigt scale-värde aldrig ger en widget
    med noll eller negativ bredd (vilket i Tk ger en osynlig men ändå
    klickbar yta — ett svårfelsökt fel).
    """
    try:
        s = float(scale)
    except (TypeError, ValueError):
        s = 1.0
    if s != s or s <= 0:      # NaN eller icke-positivt
        s = 1.0
    bas = SIDEBAR_WIDTH_COLLAPSED if collapsed else SIDEBAR_WIDTH_EXPANDED
    return max(1, int(bas * s))


def should_collapse_sidebar(
    screen_width: Optional[int],
    scale: float = 1.0,
) -> bool:
    """
    Ska sidebarn kollapsas automatiskt på denna skärm?

    Jämförelsen görs mot den SKALADE tröskeln, inte mot råa pixlar: på en
    hidpi-skärm i 200 % skalning är 1100 logiska pixlar lika trångt som 2200
    fysiska, och enbart skärmbredden skulle därför ge fel svar. Tröskeln
    skalas alltså med samma faktor som resten av gränssnittet.

    Saknas skärmbredden (None, eller en avläsning som misslyckades) kollapsas
    INTE — att fälla in sidebarn utan anledning vore sämre än att låta den vara.
    """
    try:
        w = float(screen_width)
    except (TypeError, ValueError):
        return False
    if w != w or w <= 0:
        return False
    try:
        s = float(scale)
    except (TypeError, ValueError):
        s = 1.0
    if s != s or s <= 0:
        s = 1.0
    return w < SIDEBAR_COLLAPSE_BELOW_WIDTH * s


def content_width(
    screen_width: Optional[int],
    collapsed: bool = False,
    scale: float = 1.0,
) -> Optional[int]:
    """
    Kvarvarande bredd för huvudinnehållet, eller None om skärmbredd saknas.

    Används i steg 3 för att ge korten en verklig bredd att fylla — det är
    förutsättningen för "större kort" i beställningen. Utan detta mått ritas
    korten som i v4.3: med pack(fill="x") mot en behållare vars bredd ingen
    känner till.
    """
    try:
        w = float(screen_width)
    except (TypeError, ValueError):
        return None
    if w != w or w <= 0:
        return None
    rest = w - sidebar_width(collapsed, scale)
    return max(1, int(rest))


# ============================================================
# B4a — SIDEBAR: färger från temat (M14)
# ============================================================
# Sidebarens färger härleds ur MENU_THEMES så att meny och sidebar alltid följer
# samma tema. Att lägga in en egen färgtabell här vore en andra källa och skulle
# strida mot specens regel om inga hårdkodade färger.
SIDEBAR_COLOR_KEYS: Tuple[str, ...] = (
    "bg", "fg", "active_bg", "active_fg", "hover_bg",
)


def sidebar_colors(appearance_mode: Any = None) -> Dict[str, str]:
    """
    Färger för sidebarn, härledda ur samma källa som menyerna.

    Returnerar alltid alla SIDEBAR_COLOR_KEYS, så att widgetn i steg 2 kan
    läsa fält utan att behöva hantera saknade nycklar.
    """
    # Uppslag i TRE steg, eftersom denna fil lever i två olika sammanhang:
    #   1. globals() — efter sammanslagningen ligger menu_colors() i SAMMA modul
    #      som denna kod, och då är en import både onödig och omöjlig.
    #   2. import av blockfilen — när filen körs fristående i tools/ för att
    #      testas headless, innan sammanslagning har skett.
    #   3. hårda standardvärden — om båda ovan misslyckas. Färger är alltid
    #      giltiga #rrggbb, så widgetn kan aldrig få None och krascha.
    losare = globals().get("menu_colors")
    if losare is None:
        for modulnamn in ("v5_block_kalla", "folderforge_v5_block"):
            try:
                losare = getattr(__import__(modulnamn), "menu_colors", None)
            except Exception:
                losare = None
            if losare is not None:
                break

    bas: Dict[str, str] = {}
    if losare is not None:
        try:
            resultat = losare(appearance_mode)
            if isinstance(resultat, dict):
                bas = resultat
        except Exception:
            bas = {}

    bg = bas.get("bg", "#1e1e2e")
    fg = bas.get("fg", "#f0f0f5")
    aktiv = bas.get("active_bg", "#4C9EF1")
    aktiv_fg = bas.get("active_fg", "#ffffff")

    return {
        "bg": bg,
        "fg": fg,
        "active_bg": aktiv,
        "active_fg": aktiv_fg,
        # Hover: samma färg som aktiv men visuell distinktion saknas i
        # MENU_THEMES, därför återanvänds bg som grund med aktiv som markör.
        # Steg 2 kan komplettera med blend_color() som redan finns i appen.
        "hover_bg": bas.get("hover_bg", bg),
    }


def sidebar_item_state(
    item: SidebarItem,
    colors: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Färger för EN post, beroende på om den är vald.

    Utbruten så att widgetn inte behöver grena per post — samma funktion används
    vid bygge, vid klick och vid temabyte, vilket förhindrar att de tre vägarna
    ger olika färger (ett fel som är lätt att införa och svårt att se i kod).
    """
    c = dict(colors if colors is not None else sidebar_colors())
    if item.selected:
        return {"bg": c["active_bg"], "fg": c["active_fg"]}
    return {"bg": c["bg"], "fg": c["fg"]}


def sidebar_geometry(
    screen_width: Optional[int],
    scale: float = 1.0,
    force_collapsed: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Samla alla geometribeslut i ett anrop — det som widgetn behöver veta.

    force_collapsed åsidosätter automatiken: användaren ska kunna fälla in
    sidebarn manuellt även på en bred skärm, och det valet ska inte skrivas över
    av nästa fönsterändring (None = följ automatiken).
    """
    auto = should_collapse_sidebar(screen_width, scale)
    collapsed = auto if force_collapsed is None else bool(force_collapsed)
    return {
        "collapsed": collapsed,
        "auto_collapsed": auto,
        "sidebar_width": sidebar_width(collapsed, scale),
        "content_width": content_width(screen_width, collapsed, scale),
        "scale": scale,
    }


def rymling(värde: Any) -> Any:
    """
    Översätt None till "none" för pack(fill=...).

    Tk pack accepterar fill=None som 'ingen fyllning', men värdet skickas
    vidare till Tcl där None blir strängen "None" — ett ogiltigt fill-värde
    som kastar TclError. "none" är det korrekta Tcl-värdet.
    """
    return "none" if värde is None else värde


# ============================================================
# Skalningsfunktioner
# ============================================================
def get_scale_factor(root: tk.Misc) -> float:
    """
    M27/v5.0 — fråga DPI först, skärmbredd som reserv.

    v4.3 läste ENBART winfo_screenwidth(). Det ger fel faktor på den
    vanligaste moderna kombinationen: en 1920x1080-skärm i 150 % Windows-
    skalning rapporterar 1280 logiska pixlar, så appen ritade i 1.0 medan
    resten av systemet var 1,5 gånger större — små etiketter och träffytor.

    resolve_scale_factor() läser DPI (satt av set_dpi_awareness() före
    fönsterskapandet) och faller tillbaka på skärmbredden med EXAKT samma
    trösklar som v4.3 när DPI inte kan läsas, så beteendet på äldre system
    och utanför Windows är oförändrat.
    """
    try:
        sw = root.winfo_screenwidth()
    except Exception:
        sw = None
    try:
        # winfo_fpixels("1i") = pixlar per tum, d.v.s. det verkliga DPI:t
        # som Tk ser det. Kräver att processen är DPI-medveten, annars
        # rapporterar Windows ett virtualiserat 96 dpi.
        ppi = float(root.winfo_fpixels("1i"))
    except Exception:
        ppi = None
    factor, source = resolve_scale_factor(ppi, sw)
    logger.debug("Skalningsfaktor %.2f (källa: %s)", factor, source)
    return factor


def scaled(value: int, scale: float) -> int:
    return max(1, int(value * scale))


def scaled_font(size: int, scale: float) -> int:
    return max(10, int(size * scale))


# ============================================================
# Dynamisk TabView
# ============================================================
class DynamicTabView(ctk.CTkFrame):
    def __init__(
        self, parent, settings: AppSettings, scale: float,
        on_visibility_change: callable,
        layout: str = "tabs",
        collapsed: bool = False,
        **kwargs,
    ):
        """
        layout: "tabs" (v4.3-beteende, horisontell flikrad) eller "sidebar"
                (v5.0, vertikal meny till vänster med ikoner + text).
        collapsed: endast sidebar — True ger ikon-läge (smalare, utan etiketter).

        Default är "tabs" medvetet: det bevarar v4.3:s beteende exakt, så att
        införandet av sidebarn sker i kontrollerade steg och inte som en osynlig
        ändring av hela navigationen. Appen slår över till "sidebar" i steg 3.

        Båda lägena delar SAMMA publika API (add_tab, show_tab, _hide_tab,
        _toggle_tab, get_active_tab, show_first_visible), så resten av appen
        behöver inte veta vilket läge som är aktivt.
        """
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._settings = settings
        self._scale = scale
        self._on_visibility_change = on_visibility_change
        self._tabs: Dict[str, ctk.CTkFrame] = {}
        self._tab_buttons: Dict[str, ctk.CTkButton] = {}
        self._active_tab: Optional[str] = None
        # Okänt layoutvärde faller tillbaka på "tabs" istället för att krascha:
        # ett trasigt värde från settings.json får inte göra appen oanvändbar.
        self._layout = layout if layout in ("tabs", "sidebar") else "tabs"
        self._collapsed = bool(collapsed)
        self._sidebar_items: Dict[str, SidebarItem] = {}

        if self._layout == "sidebar":
            farger = sidebar_colors(ctk.get_appearance_mode())
            bredd = sidebar_width(self._collapsed, scale)
            self._tab_bar = ctk.CTkFrame(
                self, fg_color=farger["bg"], corner_radius=12, width=bredd,
            )
            # pack_propagate(False) är avgörande: utan den krymper ramen till
            # innehållets naturliga storlek och den beräknade bredden ignoreras,
            # vilket gör att sidebarnsbredd ändras med etiketternas längd.
            self._tab_bar.pack_propagate(False)
            self._tab_bar.pack(
                side="left", fill="y", padx=(0, scaled(10, scale)),
            )
            # v5.0 steg 4 — kollapsknapp i sidebarns nederkant.
            #
            # Packas FÖRE sidoknapparna och med side="bottom", så att den hamnar
            # längst ner och sidoknapparna fyller uppifrån i det som blir kvar.
            # Packas den istället efteråt hamnar den direkt under sista sidan,
            # vilket flyttas varje gång en sida döljs eller visas.
            self._collapse_btn = ctk.CTkButton(
                self._tab_bar,
                text=self.collapse_label(self._collapsed),
                command=self._on_collapse_click,
                anchor="w",
                corner_radius=10,
                height=scaled(34, scale),
                font=ctk.CTkFont(size=scaled_font(12, scale)),
            )
            self._collapse_btn.pack(
                side="bottom", fill="x",
                padx=scaled(6, scale), pady=scaled(6, scale),
            )
            self._content = ctk.CTkFrame(self, fg_color="transparent")
            self._content.pack(side="left", fill="both", expand=True)
        else:
            self._tab_bar = ctk.CTkFrame(
                self, fg_color=("gray85", "gray20"), corner_radius=12,
            )
            self._tab_bar.pack(fill="x", padx=0, pady=(0, scaled(8, scale)))

            self._content = ctk.CTkFrame(self, fg_color="transparent")
            self._content.pack(fill="both", expand=True)

    def is_sidebar(self) -> bool:
        """True om sidebarnsläget är aktivt."""
        return self._layout == "sidebar"

    @staticmethod
    def collapse_label(collapsed: bool) -> str:
        """
        Knappetikett för kollaps/utfällning.

        Pilen pekar i den riktning innehållet kommer att röra sig: « fäller in
        (vänster), » fäller ut. I kollapsat läge visas ENDAST pilen eftersom
        sidebarn då är för smal för text — samma princip som för sidoknapparna.

        Statisk metod medvetet: etiketten beror bara av läget, inte av
        instanstillstånd, vilket gör den testbar utan att skapa någon widget.
        """
        return "»" if collapsed else "«  Fäll in"

    def _on_collapse_click(self) -> None:
        """
        Växla kollaps vid klick.

        Ligger i widgeten och inte i appklassen så att sidebarn äger sitt eget
        tillstånd; appklassens _toggle_sidebar() finns kvar som den ingång som
        menyn använder, och båda hamnar i samma set_collapsed().
        """
        try:
            callback = getattr(self, "_on_collapse", None)
            self.set_collapsed(not self._collapsed)
            if callable(callback):
                callback(self._collapsed)
        except Exception:
            logger.debug("Kollapsknappens klick hanterades inte", exc_info=True)

    def apply_theme(self, mode: Optional[str] = None) -> None:
        """
        Färga om sidebarn efter aktuellt tema.

        CTk-widgetar följer INTE ctk.set_appearance_mode() automatiskt när
        färgen satts uttryckligen vid bygge — samma fel som M14 rättade för
        menyraden. Utan detta anrop hänger sidebarn kvar i gamla temat tills
        omstart, medan resten av appen byter.

        Kastar aldrig: ett misslyckat färgbyte får inte ta ner appen.
        """
        if self._layout != "sidebar":
            return
        try:
            farger = sidebar_colors(
                mode if mode is not None else ctk.get_appearance_mode())
            self._tab_bar.configure(fg_color=farger["bg"])
            for namn, btn in self._tab_buttons.items():
                btn.configure(**self._button_kwargs(
                    namn, selected=(namn == self._active_tab)))
            # v5.0 steg 4 — även kollapsknappen följer temat.
            knapp = getattr(self, "_collapse_btn", None)
            if knapp is not None:
                knapp.configure(
                    fg_color="transparent",
                    text_color=farger["fg"],
                    hover_color=farger["hover_bg"],
                )
        except Exception:
            logger.debug("Sidebartema kunde inte appliceras", exc_info=True)

    def update_for_width(self, bredd: Optional[int]) -> bool:
        """
        Fäll in/ut sidebarn om den tillgängliga bredden kräver det.

        Returnerar True om läget faktiskt ändrades — anroparen kan då logga
        händelsen. Att returnera ändringen (istället för None) gör beteendet
        testbart utan GUI: tröskellogiken kan verifieras utan att ett enda
        widget skapas.

        Tröskeln hämtas från modellen (should_collapse_sidebar), som redan är
        enhetstestad för DPI-skalning, NaN och saknad bredd.
        """
        if self._layout != "sidebar":
            return False
        borde = should_collapse_sidebar(bredd, self._scale)
        if borde == self._collapsed:
            return False
        self.set_collapsed(borde)
        return True

    def set_collapsed(self, collapsed: bool) -> None:
        """
        Fäll in/ut sidebarn. Ändrar bredd och etiketter i ett svep.

        Separat metod istället för en parameter i __init__ eftersom valet ändras
        vid körning (fönsterbredd, användarens klick) och inte bara vid bygge.
        """
        if self._layout != "sidebar":
            return
        self._collapsed = bool(collapsed)
        try:
            self._tab_bar.configure(
                width=sidebar_width(self._collapsed, self._scale))
        except Exception:
            logger.debug("Sidebarsbredd kunde inte ändras", exc_info=True)
        for namn, btn in self._tab_buttons.items():
            it = self._sidebar_items.get(namn)
            if it is None:
                continue
            btn.configure(text=it.display_text(self._collapsed))
        # v5.0 steg 4 — knappens pil måste vända med läget, annars visar den
        # "Fäll in" när sidebarn redan är infälld.
        knapp = getattr(self, "_collapse_btn", None)
        if knapp is not None:
            try:
                knapp.configure(text=self.collapse_label(self._collapsed))
            except Exception:
                logger.debug("Kollapsknapp kunde inte uppdateras", exc_info=True)
        self._rebuild_tab_bar()

    def _button_kwargs(self, name: str, selected: bool) -> Dict[str, Any]:
        """
        Färger och form för EN knapp, i båda lägena.

        Utbruten så att bygge, klick och temabyte går genom SAMMA kodväg. Tre
        separata färgsättningar är exakt hur v4.3 fick en hårdkodad mörk
        menyrad som inte följde temat (M14).
        """
        if self._layout == "sidebar":
            it = self._sidebar_items.get(name)
            farger = sidebar_colors(ctk.get_appearance_mode())
            state = sidebar_item_state(it, farger) if it else {
                "bg": farger["bg"], "fg": farger["fg"]}
            return {
                "fg_color": state["bg"],
                "text_color": state["fg"],
                "hover_color": farger["hover_bg"],
                "anchor": "w",
                "corner_radius": 10,
                "height": scaled(40, self._scale),
                "font": ctk.CTkFont(
                    size=scaled_font(13, self._scale),
                    weight="bold" if selected else "normal",
                ),
            }
        if selected:
            return {
                "fg_color": (ACCENT_BLUE, ACCENT_BLUE),
                "text_color": "white",
                "hover_color": ("gray75", "gray30"),
                "corner_radius": 10,
                "height": scaled(36, self._scale),
                "font": ctk.CTkFont(
                    size=scaled_font(13, self._scale), weight="bold",
                ),
            }
        return {
            "fg_color": "transparent",
            "text_color": ("gray30", "gray70"),
            "hover_color": ("gray75", "gray30"),
            "corner_radius": 10,
            "height": scaled(36, self._scale),
            "font": ctk.CTkFont(
                size=scaled_font(13, self._scale), weight="normal",
            ),
        }

    def add_tab(self, name: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        self._tabs[name] = frame

        # v5.0 steg 2 — i sidebarläget kommer etikett och ikon från modellen
        # (SIDEBAR_ITEMS) istället för TAB_ICONS, och i kollapsat läge visas
        # ENDAST ikonen. TAB_ICONS används oförändrat i flikläget, så inget
        # befintligt beteende rubbas.
        if self._layout == "sidebar":
            it = next(
                (x for x in build_sidebar_items() if x.key == name), None)
            if it is None:
                it = SidebarItem(
                    key=name, label=name, icon=TAB_ICONS.get(name, "•"))
            self._sidebar_items[name] = it
            btn_text = it.display_text(self._collapsed)
        else:
            icon = TAB_ICONS.get(name, "")
            btn_text = f"{icon} {name}"

        btn = ctk.CTkButton(
            self._tab_bar,
            text=btn_text,
            command=lambda n=name: self.show_tab(n),
            **self._button_kwargs(name, selected=False),
        )
        # I kollapsat läge är ikonen enda ledtråden, därför verktygstips.
        # Bindningen är ofarlig i utfällt läge eftersom tipset blir tomt.
        btn.bind("<Enter>", lambda e, n=name: self._visa_tip(n))
        btn.bind("<Leave>", lambda e: self._dolj_tip())
        self._tab_buttons[name] = btn
        btn.bind("<Button-3>", lambda e, n=name: self._right_click_tab(e, n))
        self._rebuild_tab_bar()
        return frame

    def _rebuild_tab_bar(self) -> None:
        for btn in self._tab_buttons.values():
            btn.pack_forget()
        sida = "top" if self._layout == "sidebar" else "left"
        fyll = "x" if self._layout == "sidebar" else None
        for name, btn in self._tab_buttons.items():
            if self._settings.visible_tabs.get(name, True):
                # fill="x" i sidebarläget är vad som gör knapparna lika breda
                # som ramen; utan det blir varje knapp bara så bred som sin text
                # och markeringen av vald post ser ojämn ut.
                btn.pack(
                    side=sida,
                    fill=rymling(fyll),
                    padx=scaled(6 if self._layout == "sidebar" else 4,
                               self._scale),
                    pady=scaled(3, self._scale),
                )

    def _visa_tip(self, name: str) -> None:
        """Visa verktygstips i kollapsat läge (där etiketten inte syns)."""
        if self._layout != "sidebar" or not self._collapsed:
            return
        it = self._sidebar_items.get(name)
        if it is None:
            return
        try:
            self._tab_buttons[name].configure(text=it.icon + "  " + it.label)
        except Exception:
            logger.debug("Verktygstips kunde inte visas", exc_info=True)

    def _dolj_tip(self) -> None:
        """Återställ ikon-only-visningen efter hover."""
        if self._layout != "sidebar" or not self._collapsed:
            return
        for namn, btn in self._tab_buttons.items():
            it = self._sidebar_items.get(namn)
            if it is None:
                continue
            try:
                btn.configure(text=it.display_text(True))
            except Exception:
                logger.debug("Verktygstips kunde inte döljas", exc_info=True)

    def show_tab(self, name: str) -> None:
        if not self._settings.visible_tabs.get(name, True):
            return
        for frame in self._tabs.values():
            frame.pack_forget()
        if name in self._tabs:
            self._tabs[name].pack(fill="both", expand=True)
            self._active_tab = name
        for n, btn in self._tab_buttons.items():
            # v5.0 steg 2 — samma färgsättning som vid bygge och vid temabyte,
            # via _button_kwargs(). v4.3 hade tre separata kopior av färgerna
            # (add_tab, show_tab-vald, show_tab-ej-vald), vilket är precis hur
            # den hårdkodade mörka menyraden i M14 kunde uppstå.
            try:
                btn.configure(**self._button_kwargs(n, selected=(n == name)))
            except Exception:
                logger.debug("Knappfärg kunde inte uppdateras", exc_info=True)

    def _right_click_tab(self, event: tk.Event, name: str) -> None:
        # M14/v5.0 steg 4 — högerklicksmenyn hade en EGEN hårdkodad färg
        # (#2b2b2b) som skiljde sig från både menyraden och rullgardinerna,
        # så appen hade tre olika "mörka" nyanser. Nu en källa.
        menu = tk.Menu(
            self,
            font=("Segoe UI", scaled_font(11, self._scale)),
            **menu_configure_kwargs(ctk.get_appearance_mode()),
        )
        menu.add_command(
            label=f"Dölj '{name}'",
            command=lambda: self._hide_tab(name),
        )
        menu.add_separator()
        for tab_name in self._tabs:
            vis = self._settings.visible_tabs.get(tab_name, True)
            label = f"✓ {tab_name}" if vis else f"  {tab_name}"
            menu.add_command(
                label=label,
                command=lambda n=tab_name: self._toggle_tab(n),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _hide_tab(self, name: str) -> None:
        self._settings.visible_tabs[name] = False
        self._rebuild_tab_bar()
        for n, vis in self._settings.visible_tabs.items():
            if vis and n in self._tabs:
                self.show_tab(n)
                break
        self._on_visibility_change()

    def _toggle_tab(self, name: str) -> None:
        current = self._settings.visible_tabs.get(name, True)
        self._settings.visible_tabs[name] = not current
        self._rebuild_tab_bar()
        if not current:
            self.show_tab(name)
        elif self._active_tab == name:
            for n, vis in self._settings.visible_tabs.items():
                if vis and n in self._tabs:
                    self.show_tab(n)
                    break
        self._on_visibility_change()

    def get_active_tab(self) -> Optional[str]:
        return self._active_tab

    def show_first_visible(self) -> None:
        for name, vis in self._settings.visible_tabs.items():
            if vis and name in self._tabs:
                self.show_tab(name)
                return


# ============================================================
# Drop-zon Widget (fixad DnD-registrering)
# ============================================================
class DropZone(ctk.CTkFrame):
    """
    Visuell drag & drop-zon.
    DnD registreras på den underliggande tk-widgeten via
    root-fönstrets TkDnD-stöd. Fallback-knapp finns alltid.
    """

    def __init__(
        self, parent, on_drop: callable, scale: float, **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._on_drop = on_drop
        self._scale = scale
        self._is_hovering = False
        self._dnd_active = False

        self.configure(
            fg_color=("gray90", "gray22"),
            corner_radius=16,
            border_width=3,
            border_color=("gray70", "gray40"),
        )

        s = scale

        self._icon_lbl = ctk.CTkLabel(
            self, text="📂",
            font=ctk.CTkFont(size=scaled_font(48, s)),
        )
        self._icon_lbl.pack(pady=(scaled(25, s), scaled(5, s)))

        if DND_AVAILABLE:
            instruction = "Dra & släpp en mapp här för att exportera"
        else:
            instruction = "Klicka för att välja en mapp att exportera"

        self._text_lbl = ctk.CTkLabel(
            self, text=instruction,
            font=ctk.CTkFont(size=scaled_font(14, s), weight="bold"),
            text_color=("gray40", "gray60"),
        )
        self._text_lbl.pack(pady=(0, scaled(5, s)))

        self._sub_lbl = ctk.CTkLabel(
            self,
            text="Stöder mappar från Utforskaren" if DND_AVAILABLE
            else "Eller dra & släpp om tkinterdnd2 installeras",
            font=ctk.CTkFont(size=scaled_font(11, s)),
            text_color=("gray50", "gray50"),
        )
        self._sub_lbl.pack(pady=(0, scaled(20, s)))

        self._browse_btn = ctk.CTkButton(
            self, text="📁 Välj mapp...",
            command=self._browse,
            fg_color=ACCENT_ORANGE,
            hover_color="#e67e22",
            height=scaled(36, s),
            corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(12, s), weight="bold"),
        )
        self._browse_btn.pack(pady=(0, scaled(20, s)))

        # Klick på hela zonen
        self.bind("<Button-1>", lambda e: self._browse())
        self._icon_lbl.bind("<Button-1>", lambda e: self._browse())
        self._text_lbl.bind("<Button-1>", lambda e: self._browse())

        # DnD — fördröjd registrering så fönstret är klart
        if DND_AVAILABLE:
            self.after(500, self._setup_dnd)

    def _setup_dnd(self) -> None:
        try:
            target = getattr(self, "_canvas", self)   # CTkFrame ritar på sin canvas
            target.drop_target_register(DND_FILES)
            target.dnd_bind("<<DropEnter>>", self._on_drag_enter)
            target.dnd_bind("<<DropLeave>>", self._on_drag_leave)
            target.dnd_bind("<<Drop>>", self._on_dnd_drop)
            self._dnd_active = True
            logger.info("DnD registrerad på %s", getattr(target, "_w", target))
        except Exception as e:
            logger.warning("DnD registrering misslyckades: %s", e)
            self._fallback_dnd()

    def _fallback_dnd(self) -> None:
        """Inaktivera DnD visuellt och uppdatera text."""
        global DND_AVAILABLE  # MÅSTE vara första raden för att undvika SyntaxError
        DND_AVAILABLE = False
        self._dnd_active = False
        self._text_lbl.configure(
            text="Klicka för att välja en mapp att exportera",
        )
        self._sub_lbl.configure(
            text="Drag & drop kunde inte aktiveras — använd knappen",
        )
        logger.info("Fallback: DnD inaktiverad, klick-knapp används istället.")

    def _on_drag_enter(self, event=None) -> None:
        self._is_hovering = True
        light_bg, _ = blend_color(ACCENT_BLUE, 0.13)
        _, dark_bg = blend_color(ACCENT_BLUE, 0.20)
        self.configure(
            border_color=(ACCENT_BLUE, ACCENT_BLUE),
            fg_color=(light_bg, dark_bg),
        )
        self._icon_lbl.configure(text="📥")
        self._text_lbl.configure(
            text="Släpp här!",
            text_color=(ACCENT_BLUE, ACCENT_BLUE),
        )

    def _on_drag_leave(self, event=None) -> None:
        self._is_hovering = False
        self.configure(
            border_color=("gray70", "gray40"),
            fg_color=("gray90", "gray22"),
        )
        self._icon_lbl.configure(text="📂")
        instruction = (
            "Dra & släpp en mapp här för att exportera"
            if self._dnd_active
            else "Klicka för att välja en mapp att exportera"
        )
        self._text_lbl.configure(
            text=instruction,
            text_color=("gray40", "gray60"),
        )

    def _on_dnd_drop(self, event):
        self._on_drag_leave()
        paths = parse_dnd_paths(getattr(event, "data", ""), self.tk)
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                self._on_drop(p)
                return DND_COPY_ACTION      # "copy" — bekräftar släppet för tkdnd
            if p.is_file():
                self._on_drop(p.parent)
                return DND_COPY_ACTION
        if paths:
            messagebox.showwarning(
                "Ogiltig sökväg", f"'{paths[0]}' är varken en mapp eller fil.",
            )
        return DND_COPY_ACTION

    def _browse(self) -> None:
        d = filedialog.askdirectory(title="Välj mapp att exportera")
        if d:
            self._on_drop(Path(d))


# ============================================================
# CustomTkinter + TkinterDnD root-fönster
# ============================================================
class _DnDCTkBase(ctk.CTk):
    """CTk-root med officiellt tkdnd-stöd via TkinterDnD.require(self)."""

    def __init__(self, *args, **kwargs):
        global DND_AVAILABLE
        super().__init__(*args, **kwargs)
        if not DND_AVAILABLE:
            return
        try:
            import tkinterdnd2
            # require() lägger till RÄTT plattformsmapp (tkdnd/win-x64 …) i
            # auto_path och laddar paketet. Finns i tkinterdnd2 >= 0.5.
            require = getattr(tkinterdnd2.TkinterDnD, "require", None)
            if require is None:                       # äldre versioner
                self.TkdndVersion = tkinterdnd2.TkinterDnD._require(self)
            else:
                self.TkdndVersion = require(self)
            logger.info("tkdnd laddad: %s", self.TkdndVersion)
        except Exception as e:
            logger.warning("Kunde inte ladda tkdnd (%s) — DnD inaktiveras.", e)
            DND_AVAILABLE = False


def dialog_layout(win):
    """Scrollbart innehåll och en separat knappfot som aldrig scrollas bort."""
    win.grid_rowconfigure(0, weight=1)
    win.grid_columnconfigure(0, weight=1)
    body = ctk.CTkScrollableFrame(win, fg_color="transparent")
    body.grid(row=0, column=0, sticky="nsew")
    footer = ctk.CTkFrame(win, fg_color="transparent")
    footer.grid(row=1, column=0, sticky="ew", padx=12, pady=10)
    return body, footer


def validate_project_year(value):
    """År kan väljas eller skrivas; tomt/streck betyder inget år."""
    year = str(value).strip()
    if year in ("", "—"):
        return "—"
    if not re.fullmatch(r"[1-9][0-9]{3}", year):
        raise ValueError("Ange ett fyrsiffrigt år, till exempel 2020, eller lämna fältet tomt.")
    return year


def project_year_choices(today=None):
    """Innevarande år och tre år bakåt, beräknat när väljaren öppnas."""
    year = (today or datetime.now()).year
    return [str(year - offset) for offset in range(4)]


def focus_project_name(entry) -> None:
    """Fokusera namn och markera befintlig text när dialogen har visats."""
    if entry.winfo_exists():
        entry.focus_set()
        entry.select_range(0, "end")
        entry.icursor("end")


# ============================================================
# Huvudapplikation
# ============================================================
class FolderForgeApp(_DnDCTkBase):
    def __init__(self, start_minimerad: bool = False, **kwargs) -> None:
        # M5/C40 — globala felkrokar ALLRA FÖRST, innan någon tråd startas.
        # Tre bakgrundstrådar (keyboard.Listener, export-worker, pystray) kan
        # annars dö HELT TYST. install_crash_hooks() kedjar vidare till
        # originalkrokarna, är idempotent och kastar aldrig.
        install_crash_hooks(logger)
        super().__init__(**kwargs)
        # Dölj före update_idletasks så att inget fönster blinkar till.
        if start_minimerad:
            self.withdraw()

        # M19/C44 — självläkning: reparera ett autostartvärde som pekar på
        # konsol-python (svart ruta vid inloggning) INNAN något annat körs.
        # Kastar aldrig; returnerar 'skipped' utanför Windows.
        try:
            resultat = repair_stale_autostart(APP_NAME)
            if resultat == "repaired":
                logger.info("Autostart reparerad vid start (ingen konsolruta).")
        except Exception:
            logger.warning("Autostart-reparation vid start misslyckades",
                           exc_info=True)

        self.settings = self._load_settings()
        self.current_hotkey: Set[str] = self._load_hotkey()
        self.undo_mgr = UndoManager()
        self.template_mgr = TemplateManager()
        self.history = ProjectHistory()

        self.recording_hotkey = False
        self.pressed_keys_for_recording: Set[str] = set()
        self.hotkey_listener: Optional[keyboard.Listener] = None
        self.global_hotkey: Optional[keyboard.GlobalHotKeys] = None
        self.systray_icon: Optional[pystray.Icon] = None
        # Endast-EN-ikon-maskin: spärr mot nyskapande medan en ikon stoppas.
        self._tray_stopping: bool = False

        self.update_idletasks()
        self._scale = get_scale_factor(self)

        ctk.set_appearance_mode(self.settings.theme)
        ctk.set_default_color_theme("blue")

        self._configure_window()
        self._build_menu()
        self._create_gui()
        self._update_ui_from_settings()
        self._setup_global_hotkey()
        self._toggle_autostart(self.autostart_var.get(), initial=True)

        self.protocol("WM_DELETE_WINDOW", self._minimize_to_systray)
        self.bind("<Configure>", self._on_resize)
        self.bind("<Unmap>", self._on_window_unmap, add="+")

        if start_minimerad:
            self.after_idle(self._minimize_to_systray)

    # ============================================================
    # Fönster
    # ============================================================
    def _configure_window(self) -> None:
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.minsize(scaled(500, self._scale), scaled(400, self._scale))

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(scaled(720, self._scale), int(sw * 0.6))
        h = min(scaled(780, self._scale), int(sh * 0.85))
        x = (sw - w) // 2
        y = (sh - h) // 2

        # M27/v5.0 — multiskärmsmedveten placering. winfo_screenwidth() svarar
        # ALLTID med primärskärmens mått, oavsett hur många skärmar som finns
        # och var de ligger. På ett skrivbord med en skärm till vänster (negativa
        # x-koordinater) hamnade fönstret därför alltid mitt på primärskärmen,
        # och ett fönster som var större än skärmen kunde hamna delvis utanför
        # allt synligt område utan sätt att dra tillbaka det.
        #
        # enumerate_monitors() listar alla skärmar med deras verkliga geometri,
        # pick_monitor_for_point() väljer den skärm muspekaren står på, och
        # clamp_window_into_monitor() garanterar att fönstret ryms innanför.
        # Hela blocket är defensivt: misslyckas avläsningen behålls den gamla
        # primärskärmsplaceringen, så en ensam skärm fungerar exakt som i v4.3.
        try:
            monitors = enumerate_monitors()
            if monitors:
                px, py = self.winfo_pointerxy()
                target = pick_monitor_for_point(monitors, px, py)
                if target is not None:
                    cx = target.left + (target.width - w) // 2
                    cy = target.top + max(0, (target.height - h) // 2)
                    x, y = clamp_window_into_monitor(cx, cy, w, h, target)
        except Exception:
            logger.debug(
                "Multiskärmsplacering misslyckades — använder primärskärmen",
                exc_info=True)

        self.geometry(f"{w}x{h}+{x}+{y}")
        self.resizable(True, True)

        # M28/v5.0 — ikonen överallt, med procedurell reserv.
        # v4.3 satte ikon ENDAST om projektmapp.ico fanns och ENDAST via
        # iconbitmap (Windows-API). Saknades filen — t.ex. i en PyInstaller-
        # build där ikonen inte följde med, eller på macOS/Linux — fick appen
        # den omärkta standard-Tk-ikonen i titelrad, aktivitetsfält och tray.
        # apply_icon_to_window() väljer iconbitmap på Windows och iconphoto
        # annars, håller en referens så att PhotoImage inte skräpsamlas bort
        # (GC-bugg som gör att ikonen försvinner efter några sekunder), och
        # faller tillbaka på build_fallback_icon() som ritar mappen i kod.
        # size= som NYCKELORD: tredje positionella parametern är photo_holder
        # (en lista). Ett naket 32 hamnade där, och när iconphoto-grenen väl
        # togs (ico-fil saknas / icke-Windows) dog den tyst på int.append().
        self._icon_method = apply_icon_to_window(self, APP_ICON, size=32)
        logger.debug("Fönsterikon applicerad via %s", self._icon_method)

    # ============================================================
    # Menyrad
    # ============================================================
    def _build_menu(self) -> None:
        # M14/v5.0 — menyfärger från temat, inte hårdkodade.
        # v4.3 hade bg="#1e1e2e" fast i koden: i ljust läge fick appen en mörk
        # menyrad mot ett ljust fönster. Detta strider också mot specens regel
        # om inga hårdkodade färger. MENU_THEMES är nu enda källan.
        self._menubar = tk.Menu(
            self,
            font=("Segoe UI", scaled_font(11, self._scale)),
            **menu_configure_kwargs(ctk.get_appearance_mode()),
        )
        self.configure(menu=self._menubar)

        # M14/v5.0 steg 4 — SLUTFÖRD. Block B5:s kommentar hävdade att alla
        # fem hårdkodade menyfärgerna ersatts, men i verkligheten patchades
        # endast menyraden. Denna rullgardin var fortfarande mörk i ljust läge,
        # så appen fick en ljus menyrad med ett mörkt uppslag under sig.
        # menu_configure_kwargs() levererar även tearoff, relief och bd, så
        # hela blocket ersätts — att lämna tearoff=0 här vore en dublett.
        self._visa_menu = tk.Menu(
            self._menubar,
            font=("Segoe UI", scaled_font(11, self._scale)),
            **menu_configure_kwargs(ctk.get_appearance_mode()),
        )
        self._menubar.add_cascade(label="Visa", menu=self._visa_menu)
        self._rebuild_visa_menu()

        # M14/v5.0 steg 4 — se _visa_menu: samma hårdkodade mörka färger fanns
        # kvar här och gjorde Hjälp-menyn mörk även i ljust tema.
        help_menu = tk.Menu(
            self._menubar,
            font=("Segoe UI", scaled_font(11, self._scale)),
            **menu_configure_kwargs(ctk.get_appearance_mode()),
        )
        self._menubar.add_cascade(label="Hjälp", menu=help_menu)
        help_menu.add_command(label="Rensa cache (smartfilter)", command=self._show_cache_cleanup)
        help_menu.add_command(label="Sök uppdatering nu", command=self._check_updates_now)
        help_menu.add_command(label="Uppdateringsstatus", command=self._show_update_status)
        help_menu.add_command(label="Om FolderForge", command=self._show_info)

    def _rebuild_visa_menu(self) -> None:
        self._visa_menu.delete(0, "end")
        self._visa_menu.add_command(
            label="Visa alla sidor", command=self._show_all_tabs,
        )
        # v5.0 steg 4 — gör _toggle_sidebar() nåbar från menyn. Utan denna post
        # fanns metoden men inget sätt att anropa den från UI:t, vilket gjorde
        # den till död kod trots att dess logik var testad.
        #
        # Etiketten beräknas vid varje ombyggnad av menyn, eftersom _rebuild_-
        # visa_menu() körs både vid start och efter att sidor dolts/visats; en
        # statisk etikett hade snart visat fel håll.
        self._visa_menu.add_separator()
        _tab_view = getattr(self, "_tab_view", None)
        _kollapsad = bool(getattr(_tab_view, "_collapsed", False))
        self._visa_menu.add_command(
            label=("Fäll ut sidomenyn" if _kollapsad else "Fäll in sidomenyn"),
            command=self._toggle_sidebar,
        )
        self._visa_menu.add_separator()
        for name in TAB_ICONS:
            vis = self.settings.visible_tabs.get(name, True)
            label = f"{'✓' if vis else '○'} {TAB_ICONS[name]} {name}"
            self._visa_menu.add_command(
                label=label,
                command=lambda n=name: self._toggle_tab_from_menu(n),
            )

    def _toggle_tab_from_menu(self, name: str) -> None:
        if hasattr(self, '_tab_view'):
            self._tab_view._toggle_tab(name)
        self._rebuild_visa_menu()

    def _show_all_tabs(self) -> None:
        for name in TAB_ICONS:
            self.settings.visible_tabs[name] = True
        if hasattr(self, '_tab_view'):
            self._tab_view._rebuild_tab_bar()
            self._tab_view.show_first_visible()
        if hasattr(self, '_tab_check_vars'):
            for name, var in self._tab_check_vars.items():
                var.set(True)
        self._rebuild_visa_menu()
        self._save_settings_silent()

    # ============================================================
    # Huvud-GUI
    # ============================================================
    def _create_gui(self) -> None:
        s = self._scale

        # Header
        self._header = ctk.CTkFrame(
            self, fg_color=(ACCENT_BLUE, "#1a1a2e"),
            corner_radius=0, height=scaled(80, s),
        )
        self._header.pack(fill="x", side="top")
        self._header.pack_propagate(False)

        header_inner = ctk.CTkFrame(self._header, fg_color="transparent")
        header_inner.pack(
            fill="both", expand=True,
            padx=scaled(20, s), pady=scaled(10, s),
        )

        ctk.CTkLabel(
            header_inner, text="📁 FolderForge",
            font=ctk.CTkFont(size=scaled_font(26, s), weight="bold"),
            text_color="white",
        ).pack(side="left")

        ctk.CTkLabel(
            header_inner, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=scaled_font(12, s)),
            text_color=("white", "#aaaacc"),
        ).pack(side="left", padx=(scaled(8, s), 0), pady=(scaled(10, s), 0))

        self._theme_btn = ctk.CTkButton(
            header_inner, text="🌙",
            width=scaled(40, s), height=scaled(40, s),
            corner_radius=scaled(20, s),
            fg_color=("white", "#2a2a3e"),
            text_color=(ACCENT_BLUE, "white"),
            hover_color=("gray90", "#3a3a4e"),
            command=self._toggle_theme,
            font=ctk.CTkFont(size=scaled_font(18, s)),
        )
        self._theme_btn.pack(side="right", pady=scaled(5, s))

        # Resultat-banner
        self._result_banner = ctk.CTkFrame(
            self, fg_color="transparent", height=scaled(36, s),
        )
        self._result_banner.pack(
            fill="x", padx=scaled(15, s), pady=(scaled(8, s), 0),
        )
        self._result_banner.pack_propagate(False)

        self.result_label = ctk.CTkLabel(
            self._result_banner, text="",
            font=ctk.CTkFont(size=scaled_font(13, s), weight="bold"),
            anchor="center",
        )
        self.result_label.pack(fill="both", expand=True)

        # Undo
        self._undo_bar = ctk.CTkFrame(self, fg_color="transparent")
        self._undo_bar.pack(
            fill="x", padx=scaled(15, s), pady=(0, scaled(4, s)),
        )
        self.undo_btn = ctk.CTkButton(
            self._undo_bar,
            text="↩ Ångra senaste skapandet",
            command=self._undo_last,
            fg_color=ACCENT_RED, hover_color="#c0392b",
            state="disabled", height=scaled(32, s),
            corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(12, s), weight="bold"),
        )
        self.undo_btn.pack(fill="x")

        # Tabbar
        # v5.0 steg 3 — SIDEBAR aktiverad. Flikraden ersätts av en vertikal
        # meny till vänster med ikoner + text, vilket ger innehållet hela
        # fönsterbredden istället för att konkurrera med en rad ovanför.
        #
        # Kollapsläget avgörs av den faktiska skärmbredden via modellen, inte av
        # en gissning: should_collapse_sidebar() är DPI-skalad och enhetstestad.
        # En användare som manuellt fäller in/ut sidebarn får sitt val respekterat
        # (force_collapsed i sidebar_geometry), men vid start följs automatiken.
        try:
            _bredd = self.winfo_screenwidth()
        except Exception:
            _bredd = None
        self._tab_view = DynamicTabView(
            self, settings=self.settings, scale=s,
            on_visibility_change=self._on_tab_visibility_changed,
            layout="sidebar",
            collapsed=should_collapse_sidebar(_bredd, s),
        )
        # Ökat andrum runt innehållet: 15→20 px i sidled och 6→12 px uppåt.
        # Tillsammans med sidebarn är detta det som gör korten större — de får
        # nu både mer bredd och mer luft runt sig istället för att packas mot
        # fönsterkanten som i v4.3.
        self._tab_view.pack(
            fill="both", expand=True,
            padx=scaled(20, s), pady=(scaled(12, s), scaled(12, s)),
        )
        # Responsiv kollaps: fönstret ändrar storlek → sidebarn följer med.
        # VIKTIGT: add="+" — utan den ERSÄTTER denna bindning den tidigare
        # <Configure>-bindningen (self._on_resize, M27-skalningen) på samma
        # fönster, och skalningshanteraren blir död kod. Båda ska avfyras.
        self._sidebar_kollapsad = bool(self._tab_view._collapsed)
        self.bind("<Configure>", self._on_app_resize, add="+")

        self._tab_skapa = self._tab_view.add_tab("Skapa")
        self._tab_historik = self._tab_view.add_tab("Historik")
        self._tab_mallar = self._tab_view.add_tab("Mallar")
        self._tab_exportera = self._tab_view.add_tab("Exportera")
        self._tab_installningar = self._tab_view.add_tab("Inställningar")
        self._tab_hotkey = self._tab_view.add_tab("Snabbtangent")

        self._build_tab_skapa(self._tab_skapa)
        self._build_tab_historik(self._tab_historik)
        self._build_tab_mallar(self._tab_mallar)
        self._build_tab_exportera(self._tab_exportera)
        self._build_tab_installningar(self._tab_installningar)
        self._build_tab_hotkey(self._tab_hotkey)

        self._tab_view.show_first_visible()

        # Footer
        footer = ctk.CTkFrame(
            self, fg_color=(ACCENT_BLUE, "#1a1a2e"),
            corner_radius=0, height=scaled(40, s),
        )
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        ctk.CTkLabel(
            footer, text=COPYRIGHT_OWNER,
            font=ctk.CTkFont(size=scaled_font(11, s)),
            text_color=("white", "#8888aa"),
        ).pack(side="left", padx=scaled(15, s), pady=scaled(5, s))

        dnd_status = "✅ Drag & Drop aktiv" if DND_AVAILABLE else ""
        if dnd_status:
            ctk.CTkLabel(
                footer, text=dnd_status,
                font=ctk.CTkFont(size=scaled_font(10, s)),
                text_color=("white", ACCENT_GREEN),
            ).pack(side="left", padx=scaled(10, s))

        ctk.CTkButton(
            footer, text="Minimera till fältet",
            command=self._minimize_to_systray,
            fg_color="transparent",
            hover_color=("white", "#2a2a3e"),
            text_color="white", height=scaled(28, s),
            font=ctk.CTkFont(size=scaled_font(11, s)),
        ).pack(side="right", padx=scaled(15, s), pady=scaled(5, s))

    # ============================================================
    # Tabb: Skapa
    # ============================================================
    def _build_tab_skapa(self, parent: ctk.CTkFrame) -> None:
        s = self._scale
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        self._card(scroll, title="🏗️  Standardprojekt", color=ACCENT_BLUE)
        ctk.CTkLabel(
            scroll,
            text=(
                "Använder din sparade standardmall (väljs under Projektmallar).\n"
                "Egen struktur nedan gäller endast det aktuella projektet."
            ),
            font=ctk.CTkFont(size=scaled_font(12, s)),
            justify="left", wraplength=0,
        ).pack(fill="x", padx=scaled(15, s), pady=(0, scaled(8, s)))

        ctk.CTkButton(
            scroll, text="🏗️  Skapa Standardprojekt",
            command=self._create_folder_dialog,
            fg_color=ACCENT_BLUE, hover_color="#3a8ee0",
            height=scaled(42, s), corner_radius=10,
            font=ctk.CTkFont(size=scaled_font(14, s), weight="bold"),
        ).pack(fill="x", padx=scaled(15, s), pady=(0, scaled(15, s)))

        ctk.CTkFrame(scroll, height=2, fg_color=("gray80", "gray30")).pack(
            fill="x", padx=scaled(15, s), pady=scaled(10, s),
        )

        self._card(scroll, title="📋  Klistra in struktur", color=ACCENT_PURPLE)
        ctk.CTkLabel(
            scroll,
            text="Klistra in en trädstruktur (indenterad text) och skapa mappar automatiskt.",
            font=ctk.CTkFont(size=scaled_font(12, s)),
            justify="left", wraplength=0,
        ).pack(fill="x", padx=scaled(15, s), pady=(0, scaled(8, s)))

        ctk.CTkButton(
            scroll, text="📋  Klistra in Struktur",
            command=self._create_from_structure_dialog,
            fg_color=ACCENT_PURPLE, hover_color="#8e44ad",
            height=scaled(42, s), corner_radius=10,
            font=ctk.CTkFont(size=scaled_font(14, s), weight="bold"),
        ).pack(fill="x", padx=scaled(15, s), pady=(0, scaled(15, s)))

    # ============================================================
    # Tabb: Historik
    # ============================================================
    def _build_tab_historik(self, parent: ctk.CTkFrame) -> None:
        s = self._scale

        header_row = ctk.CTkFrame(parent, fg_color="transparent")
        header_row.pack(
            fill="x", padx=scaled(15, s),
            pady=(scaled(10, s), scaled(5, s)),
        )

        ctk.CTkLabel(
            header_row, text="🕐  Senaste Projekt",
            font=ctk.CTkFont(size=scaled_font(16, s), weight="bold"),
        ).pack(side="left")

        ctk.CTkButton(
            header_row, text="🔄",
            command=self._refresh_history_tab,
            width=scaled(36, s), height=scaled(30, s),
            fg_color=ACCENT_BLUE, corner_radius=6,
            font=ctk.CTkFont(size=scaled_font(14, s)),
        ).pack(side="right", padx=(scaled(5, s), 0))

        ctk.CTkButton(
            header_row, text="🗑  Rensa alla",
            command=self._clear_history,
            width=scaled(100, s), height=scaled(30, s),
            fg_color=ACCENT_RED, hover_color="#c0392b",
            corner_radius=6,
            font=ctk.CTkFont(size=scaled_font(11, s)),
        ).pack(side="right")

        self._history_scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent",
        )
        self._history_scroll.pack(
            fill="both", expand=True,
            padx=scaled(15, s), pady=(0, scaled(10, s)),
        )

        self._refresh_history_tab()

    def _refresh_history_tab(self) -> None:
        s = self._scale
        if not hasattr(self, '_history_scroll'):
            return

        for w in self._history_scroll.winfo_children():
            w.destroy()

        items = self.history.get_all()

        if not items:
            empty = ctk.CTkFrame(self._history_scroll, fg_color="transparent")
            empty.pack(fill="both", expand=True)

            ctk.CTkLabel(
                empty, text="📭",
                font=ctk.CTkFont(size=scaled_font(48, s)),
            ).pack(pady=(scaled(40, s), scaled(10, s)))

            ctk.CTkLabel(
                empty, text="Inga projekt i historiken ännu.",
                font=ctk.CTkFont(size=scaled_font(14, s)),
                text_color="gray",
            ).pack()

            ctk.CTkLabel(
                empty,
                text="Skapa ett projekt så visas det här.",
                font=ctk.CTkFont(size=scaled_font(12, s)),
                text_color="gray",
            ).pack(pady=(scaled(5, s), 0))
            return

        for item in items:
            path = Path(item["path"])

            try:
                created = datetime.fromisoformat(item["created"])
                delta = datetime.now() - created
                if delta.days == 0:
                    hours = delta.seconds // 3600
                    if hours == 0:
                        mins = delta.seconds // 60
                        age_text = f"för {mins} min sedan" if mins > 0 else "Just nu"
                    else:
                        age_text = f"för {hours} tim sedan"
                elif delta.days == 1:
                    age_text = "Igår"
                elif delta.days < 7:
                    age_text = f"för {delta.days} dagar sedan"
                elif delta.days < 30:
                    age_text = f"för {delta.days // 7} veckor sedan"
                else:
                    age_text = created.strftime("%Y-%m-%d")
            except (ValueError, KeyError):
                age_text = "Okänt datum"

            try:
                total_size = sum(
                    f.stat().st_size for f in path.rglob("*") if f.is_file()
                )
                if total_size < 1024:
                    size_text = f"{total_size} B"
                elif total_size < 1_048_576:
                    size_text = f"{total_size / 1024:.1f} KB"
                else:
                    size_text = f"{total_size / 1_048_576:.1f} MB"
            except OSError:
                size_text = "?"

            try:
                sub_count = sum(1 for x in path.iterdir() if x.is_dir())
                sub_text = f"{sub_count} undermappar"
            except OSError:
                sub_text = ""

            card = ctk.CTkFrame(
                self._history_scroll,
                fg_color=("gray92", "gray20"),
                corner_radius=10,
            )
            card.pack(fill="x", pady=scaled(3, s))

            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(
                side="left", fill="both", expand=True,
                padx=scaled(12, s), pady=scaled(8, s),
            )

            ctk.CTkLabel(
                left,
                text=f"📁  {item['name']}" + (" (saknas)" if not path.exists() else ""),
                font=ctk.CTkFont(size=scaled_font(13, s), weight="bold"),
                anchor="w",
            ).pack(fill="x")

            meta_parts = [age_text, size_text]
            if sub_text:
                meta_parts.append(sub_text)
            meta = "  •  ".join(meta_parts)

            ctk.CTkLabel(
                left, text=meta,
                font=ctk.CTkFont(size=scaled_font(10, s)),
                text_color="gray", anchor="w",
            ).pack(fill="x")

            display_path = str(path.parent)
            if len(display_path) > 45:
                display_path = "..." + display_path[-42:]

            ctk.CTkLabel(
                left, text=display_path,
                font=ctk.CTkFont(size=scaled_font(10, s)),
                text_color=("gray50", "gray45"), anchor="w",
            ).pack(fill="x")

            btn_col = ctk.CTkFrame(card, fg_color="transparent")
            btn_col.pack(side="right", padx=scaled(8, s), pady=scaled(6, s))

            ctk.CTkButton(
                btn_col, text="📂 Öppna",
                command=lambda p=path: self._open_path(p),
                width=scaled(80, s), height=scaled(28, s),
                fg_color=ACCENT_BLUE, corner_radius=6,
                font=ctk.CTkFont(size=scaled_font(11, s), weight="bold"),
            ).pack(pady=(0, scaled(3, s)))

            ctk.CTkButton(
                btn_col, text="📤 Exportera",
                command=lambda p=path: self._export_specific(p),
                width=scaled(80, s), height=scaled(28, s),
                fg_color=ACCENT_ORANGE, corner_radius=6,
                font=ctk.CTkFont(size=scaled_font(11, s)),
            ).pack(pady=(0, scaled(3, s)))

            ctk.CTkButton(
                btn_col, text="✕",
                command=lambda ps=item["path"]: self._remove_from_history(ps),
                width=scaled(80, s), height=scaled(24, s),
                fg_color="gray", hover_color="#555",
                corner_radius=6,
                font=ctk.CTkFont(size=scaled_font(10, s)),
            ).pack()

    def _remove_from_history(self, path_str: str) -> None:
        self.history.remove(path_str)
        self._refresh_history_tab()

    def _clear_history(self) -> None:
        if not messagebox.askyesno(
            "Rensa historik",
            "Ta bort all historik?\n\n(Inga mappar raderas, bara listan.)",
        ):
            return
        self.history.clear()
        self._refresh_history_tab()
        self._set_result("🗑  Historiken rensad", "gray")

    def _export_specific(self, path: Path) -> None:
        s = self._scale
        prog = ctk.CTkProgressBar(self._tab_exportera, mode="indeterminate")
        prog.pack(fill="x", padx=scaled(15, s), pady=scaled(5, s))
        prog.start()

        def worker():
            # M12/MB10 — generate_tree_string_safe har djupgräns, symlink-vakt
            # och posttak, så ingen RecursionError eller minnesexplosion.
            # Workern FÅR aldrig dö tyst: finally garanterar att progressbaren
            # stängs även om något oväntat ändå kastar.
            result = ""
            try:
                result = generate_tree_string_safe(path)
            except Exception as e:
                logger.exception("Export misslyckades för %s: %s", path, e)
                result = f"Export misslyckades: {e}"
            finally:
                # M10/C43 — ui_call schemalägger i Tk-huvudtråden och sväljer
                # felet om fönstret redan stängts, istället för att krascha
                # bakgrundstråden.
                ui_call(self, _done, result)

        def _done(result: str):
            prog.stop()
            prog.destroy()
            self._show_export_result(result)

        threading.Thread(target=worker, daemon=True).start()

    # ============================================================
    # Tabb: Mallar
    # ============================================================
    def _build_tab_mallar(self, parent: ctk.CTkFrame) -> None:
        s = self._scale
        self._card(parent, title="📋  Projektmallar", color=ACCENT_GREEN)
        ctk.CTkLabel(
            parent,
            text="Välj en inbyggd mall eller en du sparat tidigare.",
            font=ctk.CTkFont(size=scaled_font(12, s)),
            justify="left",
        ).pack(fill="x", padx=scaled(15, s), pady=(0, scaled(8, s)))

        ctk.CTkButton(
            parent, text="📋  Öppna Mallväljaren",
            command=self._template_dialog,
            fg_color=ACCENT_GREEN, hover_color="#27ae60",
            height=scaled(42, s), corner_radius=10,
            font=ctk.CTkFont(size=scaled_font(14, s), weight="bold"),
        ).pack(fill="x", padx=scaled(15, s), pady=(0, scaled(10, s)))

    # ============================================================
    # Tabb: Exportera (med Drag & Drop)
    # ============================================================
    def _build_tab_exportera(self, parent: ctk.CTkFrame) -> None:
        s = self._scale

        self._card(parent, title="📤  Exportera Mappstruktur", color=ACCENT_ORANGE)

        ctk.CTkLabel(
            parent,
            text="Exportera en mapps trädstruktur som text.",
            font=ctk.CTkFont(size=scaled_font(12, s)),
            justify="left", wraplength=0,
        ).pack(fill="x", padx=scaled(15, s), pady=(0, scaled(8, s)))

        self._drop_zone = DropZone(
            parent, on_drop=self._on_drop_export, scale=s,
        )
        self._drop_zone.pack(
            fill="both", expand=True,
            padx=scaled(15, s), pady=scaled(10, s),
        )

    def _on_drop_export(self, path: Path) -> None:
        if not path.is_dir():
            messagebox.showwarning("Ogiltig", f"'{path.name}' är inte en mapp.")
            return
        self._export_specific(path)
        self._set_result(f"📤 Exporterar: {path.name}...", ACCENT_ORANGE)

    # ============================================================
    # Tabb: Inställningar
    # ============================================================
    def _build_tab_installningar(self, parent: ctk.CTkFrame) -> None:
        s = self._scale
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # Sparplats
        self._card(scroll, title="📂  Sparningsplats", color=ACCENT_BLUE)
        path_row = ctk.CTkFrame(scroll, fg_color="transparent")
        path_row.pack(fill="x", padx=scaled(15, s), pady=(0, scaled(12, s)))

        self.path_lbl = ctk.CTkLabel(
            path_row, text="",
            font=ctk.CTkFont(size=scaled_font(12, s)), anchor="w",
        )
        self.path_lbl.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            path_row, text="Välj...", command=self._choose_path,
            width=scaled(70, s), height=scaled(30, s),
            fg_color=ACCENT_BLUE, corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(12, s)),
        ).pack(side="right")

        # Tema
        self._card(scroll, title="🎨  Utseende", color=ACCENT_PURPLE)
        self.theme_var = ctk.StringVar(value=self.settings.theme)
        ctk.CTkSegmentedButton(
            scroll, values=["System", "Dark", "Light"],
            variable=self.theme_var, command=self._change_theme,
            font=ctk.CTkFont(size=scaled_font(12, s)),
            height=scaled(34, s),
        ).pack(fill="x", padx=scaled(15, s), pady=(0, scaled(12, s)))

        # Alternativ — ALL synlig text hämtas från SETTINGS_META i
        # settings.py (sektion 7): ändra etikett/hjälptext där, inte här.
        self._card(scroll, title="⚙️  Alternativ", color=ACCENT_GREEN)
        self.open_var = ctk.BooleanVar()
        self._settings_option(scroll, "open_after_creation",
                              self.open_var, self._save_settings_silent)

        self.autostart_var = ctk.BooleanVar(value=self._check_autostart())
        self._settings_option(
            scroll, "autostart", self.autostart_var,
            lambda: self._toggle_autostart(self.autostart_var.get()),
        )

        # Regns-läge: normaliserar bara regnr-prefixet ('dss 817 årg 2020' →
        # 'DSS817 ÅRG 2020') — fri text efter följer alltid med.
        self.plate_mode_var = ctk.BooleanVar(value=self.settings.plate_mode)
        self._settings_option(scroll, "plate_mode",
                              self.plate_mode_var, self._save_settings_silent)

        # Startläge: alltid minimerad i systray (default PÅ — användarens
        # beslut), texten hämtas ur SETTINGS_META som allt annat här.
        self.start_minimized_var = ctk.BooleanVar(value=self.settings.start_minimized)
        self._settings_option(scroll, "start_minimized",
                              self.start_minimized_var, self._save_settings_silent)

        # Drag & Drop info
        self._card(scroll, title="📥  Drag & Drop", color=ACCENT_TEAL)
        dnd_text = (
            "✅ Aktivt — dra mappar direkt till Exportera-fliken"
            if DND_AVAILABLE
            else "❌ Inaktivt — installera tkinterdnd2 för att aktivera:\n"
                 "pip install tkinterdnd2"
        )
        ctk.CTkLabel(
            scroll, text=dnd_text,
            font=ctk.CTkFont(size=scaled_font(12, s)),
            justify="left", wraplength=0,
        ).pack(fill="x", padx=scaled(15, s), pady=(0, scaled(12, s)))

        # Synliga flikar
        self._card(scroll, title="👁️  Synliga Flikar", color=ACCENT_ORANGE)
        self._tab_check_vars: Dict[str, ctk.BooleanVar] = {}
        for tab_name in TAB_ICONS:
            var = ctk.BooleanVar(
                value=self.settings.visible_tabs.get(tab_name, True),
            )
            self._tab_check_vars[tab_name] = var
            ctk.CTkCheckBox(
                scroll,
                text=f"{TAB_ICONS[tab_name]}  {tab_name}",
                variable=var,
                command=lambda n=tab_name: self._toggle_tab_from_settings(n),
                font=ctk.CTkFont(size=scaled_font(13, s)),
                checkbox_width=scaled(20, s), checkbox_height=scaled(20, s),
                checkmark_color="white",
                fg_color=ACCENT_ORANGE, hover_color="#e67e22",
            ).pack(anchor="w", padx=scaled(15, s), pady=scaled(3, s))

        ctk.CTkButton(
            scroll, text="Visa alla flikar",
            command=self._show_all_tabs,
            fg_color=ACCENT_ORANGE, hover_color="#e67e22",
            height=scaled(32, s), corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(12, s)),
        ).pack(fill="x", padx=scaled(15, s), pady=scaled(10, s))

    def _toggle_tab_from_settings(self, name: str) -> None:
        val = self._tab_check_vars[name].get()
        self.settings.visible_tabs[name] = val
        if hasattr(self, '_tab_view'):
            self._tab_view._rebuild_tab_bar()
            if not val and self._tab_view.get_active_tab() == name:
                self._tab_view.show_first_visible()
            elif val:
                self._tab_view.show_tab(name)
        self._rebuild_visa_menu()
        self._save_settings_silent()

    # ============================================================
    # Tabb: Snabbtangent
    # ============================================================
    def _build_tab_hotkey(self, parent: ctk.CTkFrame) -> None:
        s = self._scale

        self._card(parent, title="⌨️  Global Snabbtangent", color=ACCENT_PURPLE)

        ctk.CTkLabel(
            parent,
            text="Tryck på snabbtangenten var som helst för att öppna FolderForge.",
            font=ctk.CTkFont(size=scaled_font(12, s)),
            justify="left", wraplength=0,
        ).pack(fill="x", padx=scaled(15, s), pady=(0, scaled(10, s)))

        self.hk_display_frame = ctk.CTkFrame(
            parent, fg_color=(ACCENT_PURPLE, "#1a1030"),
            corner_radius=12,
        )
        self.hk_display_frame.pack(
            fill="x", padx=scaled(15, s), pady=(0, scaled(10, s)),
        )

        self.hk_lbl = ctk.CTkLabel(
            self.hk_display_frame, text="",
            font=ctk.CTkFont(size=scaled_font(20, s), weight="bold"),
            text_color="white",
        )
        self.hk_lbl.pack(pady=scaled(12, s))

        ctk.CTkButton(
            parent, text="✏️  Ändra Snabbtangent",
            command=self._rec_hotkey,
            fg_color=ACCENT_PURPLE, hover_color="#8e44ad",
            height=scaled(40, s), corner_radius=10,
            font=ctk.CTkFont(size=scaled_font(13, s), weight="bold"),
        ).pack(fill="x", padx=scaled(15, s), pady=(0, scaled(8, s)))

        self.hk_rec_frame = ctk.CTkFrame(
            parent, fg_color=("gray90", "gray20"), corner_radius=12,
        )
        self.hk_rec_lbl = ctk.CTkLabel(
            self.hk_rec_frame, text="Tryck önskade tangenter...",
            font=ctk.CTkFont(size=scaled_font(16, s), slant="italic"),
        )
        self.hk_rec_lbl.pack(pady=scaled(10, s))

        rec_btns = ctk.CTkFrame(self.hk_rec_frame, fg_color="transparent")
        rec_btns.pack(pady=(0, scaled(10, s)))

        ctk.CTkButton(
            rec_btns, text="✅ Spara",
            command=self._save_hotkey_rec,
            fg_color=ACCENT_GREEN, hover_color="#27ae60",
            width=scaled(90, s), height=scaled(34, s),
            font=ctk.CTkFont(size=scaled_font(12, s), weight="bold"),
        ).pack(side="left", padx=scaled(5, s))

        ctk.CTkButton(
            rec_btns, text="❌ Avbryt",
            command=self._cancel_hotkey_rec,
            fg_color="gray", hover_color="#555",
            width=scaled(90, s), height=scaled(34, s),
            font=ctk.CTkFont(size=scaled_font(12, s)),
        ).pack(side="left", padx=scaled(5, s))

    # ============================================================
    # Card helper
    # ============================================================
    def _settings_option(
        self, parent: ctk.CTkFrame, key: str, var: Any, command: Any,
    ) -> None:
        """Kryssruta + hjälptext driven av SETTINGS_META (settings.py).

        All synlig text i Inställningar-fönstret har EN källa (sektion 7 i
        settings.py): ändras 'label' eller 'beskrivning' där slår det igenom
        här direkt — ingen hårdkodad text i GUI-koden längre.
        """
        s = self._scale
        meta = SETTINGS_META[key]
        ctk.CTkCheckBox(
            parent, text=meta["label"],
            variable=var, command=command,
            font=ctk.CTkFont(size=scaled_font(13, s)),
            checkbox_width=scaled(20, s), checkbox_height=scaled(20, s),
            checkmark_color="white",
            fg_color=ACCENT_GREEN, hover_color="#27ae60",
        ).pack(anchor="w", padx=scaled(15, s), pady=(scaled(6, s), 0))
        ctk.CTkLabel(
            parent, text=meta["beskrivning"],
            font=ctk.CTkFont(size=scaled_font(11, s)),
            text_color=("gray40", "gray55"),
            anchor="w", justify="left",
            wraplength=scaled(430, s),
        ).pack(anchor="w", padx=scaled(52, s), pady=(0, scaled(8, s)))

    def _card(self, parent: ctk.CTkFrame, title: str, color: str) -> None:
        s = self._scale
        light_bg, _ = blend_color(color, 0.13)
        _, dark_bg = blend_color(color, 0.20)
        # M13/C46 — titeln bär information, men alla 6 accentfärger låg under
        # WCAG AA 4.5:1 mot den blendade kortbakgrunden (sämst 1.53:1).
        # ensure_contrast() justerar färgen endast så mycket som krävs, och gör
        # det separat för ljust och mörkt läge eftersom bakgrunden skiljer sig.
        title_light, title_dark = ensure_contrast(color, light_bg, dark_bg)

        f = ctk.CTkFrame(
            parent,
            fg_color=(light_bg, dark_bg),
            corner_radius=10,
        )
        f.pack(fill="x", padx=scaled(10, s), pady=(scaled(8, s), scaled(4, s)))

        ctk.CTkLabel(
            f, text=title,
            font=ctk.CTkFont(size=scaled_font(14, s), weight="bold"),
            text_color=(title_light, title_dark), anchor="w",
        ).pack(
            anchor="w",
            padx=scaled(12, s),
            pady=(scaled(8, s), scaled(4, s)),
        )

    # ============================================================
    # Resize
    # ============================================================
    def _on_resize(self, event: tk.Event) -> None:
        try:
            w = self.winfo_width()
            self.result_label.configure(
                wraplength=max(200, w - scaled(60, self._scale)),
            )
        except Exception:
            pass

    # ============================================================
    # Tab-synlighet callback
    # ============================================================
    def _on_tab_visibility_changed(self) -> None:
        if hasattr(self, '_tab_check_vars'):
            for name, var in self._tab_check_vars.items():
                var.set(self.settings.visible_tabs.get(name, True))
        self._rebuild_visa_menu()
        self._save_settings_silent()

    # ============================================================
    # LOGIK: Settings
    # ============================================================
    def _load_settings(self) -> AppSettings:
        # M2/C41.3 — read_json_safe() provar fil → .bak → .bak2 innan default,
        # så en trasig settings.json kostar inte längre alla inställningar.
        data = read_json_safe(SETTINGS_FILE, None)
        if data is None:
            return AppSettings()
        # M3/C2 — validera mot schema och SKRIV TILLBAKA den lagade filen, så
        # att ett felaktigt värde inte återkommer och repareras om varje start.
        clean, repaired, log = validate_settings(data)
        for line in log:
            logger.warning("Inställning reparerad: %s", line)
        if repaired and atomic_write_json(SETTINGS_FILE, clean):
            logger.info("settings.json lagad och tillbaka-skriven.")
        return AppSettings.from_dict(clean)

    def _save_settings_silent(self) -> None:
        if hasattr(self, 'open_var'):
            self.settings.open_after_creation = self.open_var.get()
        if hasattr(self, 'plate_mode_var'):
            self.settings.plate_mode = self.plate_mode_var.get()
        if hasattr(self, 'start_minimized_var'):
            self.settings.start_minimized = self.start_minimized_var.get()
        if hasattr(self, 'theme_var'):
            self.settings.theme = self.theme_var.get()
        # M1/F1 — atomisk skrivning: mkstemp → fdopen → fsync → os.replace, med
        # backup före skrivning. En krasch mitt i json.dump() kunde tidigare
        # lämna en trunkerad settings.json som nästa start inte kunde läsa.
        if not atomic_write_json(SETTINGS_FILE, self.settings.to_dict()):
            logger.error("Kunde inte spara inställningar "
                         "(atomisk skrivning misslyckades)")

    def _update_ui_from_settings(self) -> None:
        p = self.settings.save_root
        if hasattr(self, 'path_lbl'):
            self.path_lbl.configure(
                text=("..." + p[-38:]) if len(p) > 41 else p,
            )
        if hasattr(self, 'open_var'):
            self.open_var.set(self.settings.open_after_creation)
        if hasattr(self, 'plate_mode_var'):
            self.plate_mode_var.set(self.settings.plate_mode)
        if hasattr(self, 'hk_lbl'):
            self.hk_lbl.configure(
                text=" + ".join(
                    k.capitalize() for k in sorted(self.current_hotkey)
                ),
            )
        if hasattr(self, 'theme_var'):
            self.theme_var.set(self.settings.theme)

    def _choose_path(self) -> None:
        d = filedialog.askdirectory(initialdir=self.settings.save_root)
        if d:
            self.settings.save_root = d
            self._save_settings_silent()
            self._update_ui_from_settings()

    def _toggle_theme(self) -> None:
        modes = ["Dark", "Light", "System"]
        current = ctk.get_appearance_mode().lower()
        for i, m in enumerate(modes):
            if m.lower() == current:
                new_mode = modes[(i + 1) % len(modes)]
                break
        else:
            new_mode = "Dark"
        ctk.set_appearance_mode(new_mode)
        self.settings.theme = new_mode
        # M14/v5.0 — Tk-menyer följer INTE ctk.set_appearance_mode() automatiskt,
        # de måste konfigureras om uttryckligen.
        self._apply_menu_theme(new_mode)
        icons = {"Dark": "🌙", "Light": "☀️", "System": "💻"}
        self._theme_btn.configure(text=icons.get(new_mode, "🌙"))
        self._save_settings_silent()

    def _change_theme(self, value: str) -> None:
        ctk.set_appearance_mode(value)
        self.settings.theme = value
        # M14/v5.0 — se _toggle_theme: Tk-menyer måste konfigureras om för hand.
        self._apply_menu_theme(value)
        self._save_settings_silent()

    def _on_app_resize(self, event=None) -> None:
        """
        v5.0 steg 3 — fäll in/ut sidebarn när fönstret blir smalt/brett.

        TVÅ vakter gör detta ofarligt att binda till <Configure>:

        1. Eventet ignoreras om det inte gäller själva appfönstret. <Configure>
           avfyras för VARJE widget i trädet, så utan denna kontroll skulle
           hanteraren köras hundratals gånger per fönsterdragning.
        2. update_for_width() ändrar endast läget vid en TRÖSKELÖVERGÅNG och
           returnerar då True. Att konfigurera om vid varje pixeländring skulle
           ge en märkbart trög fönsterdragning.

        Kastar aldrig: en layoutuppdatering får inte ta ner appen.
        """
        try:
            if event is not None and getattr(event, "widget", None) is not self:
                return
            ändrat = self._tab_view.update_for_width(self.winfo_width())
            if ändrat:
                self._sidebar_kollapsad = bool(self._tab_view._collapsed)
                logger.debug("Sidebar %s vid bredd %s px",
                             "infälld" if self._sidebar_kollapsad else "utfälld",
                             self.winfo_width())
        except Exception:
            logger.debug("Sidebaruppdatering vid resize misslyckades",
                         exc_info=True)

    def _toggle_sidebar(self) -> None:
        """
        Fäll in/ut sidebarn manuellt.

        Användarens manuella val ska alltid fungera, även på en bred skärm där
        automatiken vill ha den utfälld. Nästa resize kan dock skriva över valet
        om tröskeln passeras — det är avsiktligt, eftersom alternativet (att
        låta ett manuellt val låsa automatiken permanent) gör att en användare
        som en gång fällde in sidebarn aldrig får tillbaka den automatiskt när
        fönstret blir stort igen.
        """
        try:
            self._tab_view.set_collapsed(not self._tab_view._collapsed)
            self._sidebar_kollapsad = bool(self._tab_view._collapsed)
        except Exception:
            logger.debug("Manuell sidebarväxling misslyckades", exc_info=True)

    def _apply_menu_theme(self, mode: Optional[str] = None) -> None:
        """
        M14/v5.0 — applicera temats menyfärger på menyraden.

        Utbruten ur _build_menu så att samma kodväg används både vid bygge och
        vid temabyte; två kopior av färgsättningen hade garanterat drivit isär.
        Kastar aldrig: en meny som inte går att färga om får behålla sina
        färger, det får inte ta ner appen.
        """
        try:
            bar = getattr(self, "_menubar", None)
            if bar is None:
                return
            aktiv = mode if mode is not None else ctk.get_appearance_mode()
            bar.configure(**menu_configure_kwargs(aktiv))
            # v5.0 steg 3 — sidebarn måste färgas om i samma svep. Annars byter
            # menyraden och innehållet tema medan sidebarn hänger kvar i det
            # gamla, vilket är exakt samma klass av fel som M14 rättade.
            tab_view = getattr(self, "_tab_view", None)
            if tab_view is not None:
                try:
                    tab_view.apply_theme(aktiv)
                except Exception:
                    logger.debug("Sidebarn kunde inte färgas om", exc_info=True)
        except Exception:
            logger.debug("Menytema kunde inte appliceras", exc_info=True)

    # ============================================================
    # LOGIK: Skapa mappar
    # ============================================================
    @staticmethod
    def _bygg_projektnamn(namn_text: str, lokal: str, year: str = "—") -> str:
        """Sätter ihop slutnamnet för standardprojekt.

        Lokalen läggs efter projektnamnet, och valt år efter lokalen —
        användarens beslut ("JPM602 SIDORUTA LAXÅ"). Handskrivna lokal-
        ord i textfältet plockas bort först (case-insensitivt), så
        dropdownen är enda källan → inga dubbletter möjliga.
        """
        year = str(year).strip()
        ord_lista = [o for o in str(namn_text).split()
                     if o.upper() not in LOKAL_CHOICES]
        # Undvik dubbelt valt år utan att radera andra år i fri text.
        if year and year != "—":
            ord_lista = [o for o in ord_lista if o != year]
        if lokal and lokal != "—":
            ord_lista.append(lokal)
        if year and year != "—":
            ord_lista.append(year)
        return " ".join(ord_lista)

    def _create_folder_dialog(self) -> None:
        """Namndialog för Standardprojekt — design v2.

        Egen dialog istället för CTkInputDialog. Designbesluten:
          * Chips har VISUELLT läge: markerad chip fylls i sin accentfärg
            och får "✓" framför sig — läget synkas mot textfältet via
            trace, så även handskrivna ord (gemener tillåtna) tänder
            rätt chip och kanoniseras vid toggle
          * RUTA_CHOICES-paret utesluter varandra inom chip-raden
          * Lokal-dropdown (LOKAL_CHOICES) — hamnar sist i namnet,
            "—" = ingen lokal
          * Live-förhandsvisning av exakt det mappnamn som skapas, och
            Skapa-knappen är avstängd tills namnet inte är tomt
        Allt blir ren TEXT i samma namnfält — normalisering, sanering
        och versalisering sker i _create_std_proj som vanligt.
        """
        s = self._scale
        win = ctk.CTkToplevel(self)
        win.title("Nytt Standardprojekt")
        win.transient(self)
        apply_icon_to_window(win, APP_ICON)
        win.grab_set()
        win.resizable(True, True)

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        bredd = min(scaled(560, s), max(320, sw - 80))
        höjd = min(scaled(560, s), max(240, sh - 100))
        win.geometry(f"{bredd}x{höjd}+{(sw - bredd) // 2}+{(sh - höjd) // 2}")
        body, footer = dialog_layout(win)
        footer.grid_remove()  # Knapparna följer slutnamnet, inte fönstrets nederkant.

        # ── Rubrik + underrubrik ───────────────────────────────────
        ctk.CTkLabel(
            body, text="📁  Nytt standardprojekt",
            font=ctk.CTkFont(size=scaled_font(15, s), weight="bold"),
            anchor="w", text_color=("gray15", "gray90"),
        ).pack(anchor="w", padx=scaled(15, s), pady=(scaled(12, s), 0))
        ctk.CTkLabel(
            body, text="Skapar projektmappen med din valda standardmall.",
            font=ctk.CTkFont(size=scaled_font(11, s)),
            text_color=("gray40", "gray55"), anchor="w",
        ).pack(anchor="w", padx=scaled(15, s), pady=(0, scaled(4, s)))

        resultat: Dict[str, Optional[str]] = {"namn": None}
        namn_var = ctk.StringVar()
        lokal_var = ctk.StringVar(value="—")
        year_var = ctk.StringVar(value="—")

        def _rubrik(text: str) -> None:
            ctk.CTkLabel(
                body, text=text,
                font=ctk.CTkFont(size=scaled_font(11, s), weight="bold"),
                text_color=("gray40", "gray55"), anchor="w",
            ).pack(anchor="w", padx=scaled(15, s),
                   pady=(scaled(8, s), scaled(3, s)))

        # ── Projektnamn ────────────────────────────────────────────
        _rubrik("PROJEKTNAMN")
        entry = ctk.CTkEntry(
            body, textvariable=namn_var,
            placeholder_text="t.ex. DSS817 eller dss 817 ...",
            font=ctk.CTkFont(size=scaled_font(13, s)),
            height=scaled(34, s),
        )
        entry.pack(fill="x", padx=scaled(15, s))

        def _avsluta_redigering() -> None:
            # Fokus + markör sist — CTkEntry exponerar inte alltid icursor()
            entry.focus_set()
            try:
                entry.icursor("end")
            except Exception:
                pass

        # ── Skadetyp-chips med visuellt markeringsläge ─────────────
        _rubrik("SKADETYP  ·  SIDORUTA/BAKRUTA utesluter varandra")
        chips_row = ctk.CTkFrame(body, fg_color="transparent")
        chips_row.pack(fill="x", padx=scaled(15, s))
        chip_färger = (ACCENT_ORANGE, ACCENT_PURPLE, ACCENT_TEAL, ACCENT_BLUE)
        chip_knappar: Dict[str, Any] = {}
        for i, chip in enumerate(DAMAGE_TYPE_CHIPS):
            knapp = ctk.CTkButton(
                chips_row, text=chip,
                command=lambda c=chip: toggla(c),
                fg_color=("gray70", "gray30"),
                height=scaled(26, s), corner_radius=13,
                font=ctk.CTkFont(size=scaled_font(11, s)),
            )
            knapp.grid(row=i // 2, column=i % 2, sticky="ew", padx=3, pady=3)
            chips_row.grid_columnconfigure(i % 2, weight=1)
            chip_knappar[chip] = knapp

        def toggla(chip: str) -> None:
            # Slår ordet av/på i namnfältet. Case-insensitiv jämförelse:
            # ett handskrivet "stenskott" räknas som samma ord och
            # kanoniseras till STENSKOTT — aldrig dubbletter.
            # RUTA_CHOICES-paret utesluter varandra (användarens beslut).
            upp = chip.upper()
            ord_lista = namn_var.get().split()
            if any(o.upper() == upp for o in ord_lista):
                ord_lista = [o for o in ord_lista if o.upper() != upp]
            else:
                if chip in RUTA_CHOICES:
                    ord_lista = [o for o in ord_lista
                                 if o.upper() not in RUTA_CHOICES]
                ord_lista.append(chip)
            namn_var.set(" ".join(ord_lista))
            _avsluta_redigering()

        # ── Lokal ──────────────────────────────────────────────────
        _rubrik("LOKAL  ·  före valt år")
        ctk.CTkOptionMenu(
            body, values=["—"] + list(LOKAL_CHOICES),
            variable=lokal_var,
            command=lambda _v: _förnya_utseende(),
            fg_color=ACCENT_BLUE, button_color=ACCENT_BLUE,
            height=scaled(28, s), corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(12, s)),
        ).pack(anchor="w", padx=scaled(15, s))

        _rubrik("ÅR  ·  välj eller skriv ett år, valfritt")
        year_menu = ctk.CTkComboBox(
            body, values=["—"] + project_year_choices(), variable=year_var,
            command=lambda _v: _förnya_utseende(),
            height=scaled(28, s), corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(12, s)),
        )
        year_menu.pack(anchor="w", padx=scaled(15, s))

        def refresh_year_choices():
            values = ["—"] + project_year_choices()
            year_menu.configure(values=values)
            # Även en dialog som är öppen över nyår följer med.
            win.after(60_000, refresh_year_choices)

        win.after(60_000, refresh_year_choices)

        # ── Live-förhandsvisning av slutnamnet ─────────────────────
        preview_ram = ctk.CTkFrame(body, corner_radius=8,
                                   fg_color=("gray88", "gray20"))
        preview_ram.pack(fill="x", padx=scaled(15, s), pady=(scaled(12, s), 0))
        preview_var = ctk.StringVar()
        ctk.CTkLabel(
            preview_ram, textvariable=preview_var,
            font=ctk.CTkFont(size=scaled_font(12, s), weight="bold"),
            text_color=("gray20", ACCENT_BLUE), anchor="w",
        ).pack(anchor="w", padx=scaled(12, s), pady=scaled(8, s))

        # ── Knappar ────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", padx=scaled(15, s), pady=(scaled(8, s), scaled(12, s)))

        def ok(*_e) -> None:
            if not namn_var.get().strip():
                return    # Return-vakt: lokal ensam är INTE ett projektnamn
            try:
                year = validate_project_year(year_var.get())
            except ValueError as exc:
                messagebox.showwarning("Ogiltigt år", str(exc), parent=win)
                year_menu.focus_set()
                return
            resultat["namn"] = self._bygg_projektnamn(
                namn_var.get(), lokal_var.get(), year)
            win.destroy()

        skapa_knapp = ctk.CTkButton(
            btn_row, text="Skapa", command=ok,
            fg_color=ACCENT_BLUE, height=scaled(34, s), corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(12, s), weight="bold"),
        )
        skapa_knapp.pack(side="right")
        ctk.CTkButton(
            btn_row, text="Avbryt", command=win.destroy,
            fg_color=("gray70", "gray30"), height=scaled(34, s), corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(12, s)),
        ).pack(side="right", padx=(0, scaled(8, s)))

        def _förnya_utseende(*_a) -> None:
            """Synkar chips-lägen, förhandsvisning och Skapa-knappens
            status mot textfältet — körs via trace vid VARJE ändring,
            så vyn aldrig ljuger om vad som kommer skapas."""
            ord_set = {o.upper() for o in namn_var.get().split()}
            for i, chip in enumerate(DAMAGE_TYPE_CHIPS):
                aktiv = chip.upper() in ord_set
                chip_knappar[chip].configure(
                    text=("✓ " + chip) if aktiv else chip,
                    fg_color=(chip_färger[i % len(chip_färger)] if aktiv
                              else ("gray70", "gray30")),
                )
            eget_namn = namn_var.get().strip()
            # Viktigt: "tomt namn" mäts på textfältet — ENBART en vald
            # lokal (utan eget namn) är aldrig ett giltigt projektnamn.
            namn = self._bygg_projektnamn(eget_namn, lokal_var.get(), year_var.get()).strip()
            preview_var.set(f"📁 {namn}" if eget_namn
                            else "📁 (ange ett projektnamn)")
            skapa_knapp.configure(state=("normal" if eget_namn else "disabled"))

        year_var.trace_add("write", _förnya_utseende)
        namn_var.trace_add("write", _förnya_utseende)
        _förnya_utseende()                  # startläge: chips släckta, Skapa av

        year_menu.bind("<Return>", ok)
        entry.bind("<Return>", ok)
        win.bind("<Escape>", lambda _e: win.destroy())
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.after(150, lambda: focus_project_name(entry))

        self.wait_window(win)
        namn = (resultat["namn"] or "").strip()
        if namn:
            self._create_std_proj(namn)

    def _create_std_proj(self, name: str) -> None:
        if self.settings.plate_mode:
            name, _regnr = normalize_plate_name(name)
        try:
            safe_name = NameValidator.sanitize(name)
        except ValueError as e:
            messagebox.showwarning("Ogiltigt namn", str(e))
            return

        # Alltid VERSALER by design (krav från användaren: "endast uppercase
        # namn även om jag skriver lower case") — ta INTE bort .upper() igen.
        root = Path(self.settings.save_root) / safe_name.upper()

        templates = self.template_mgr.list_templates()
        selected = self.settings.default_template
        if selected not in templates:
            messagebox.showwarning("Standardmall saknas", "Välj en ny standard under Projektmallar.")
            return
        structure = templates[selected]
        _, items = StructureEngine.parse_structure_text(structure)
        items, _ = strip_root_level(items, root.name)
        if self._show_preview(root.name, items):
            self._build_structure(root.name, items)

    def _create_from_structure_dialog(self) -> None:
        s = self._scale
        win = ctk.CTkToplevel(self)
        win.title("Skapa från Struktur")
        win.transient(self)
        # M28 — ikon även i dialogfönster: på Windows propagerar rotfönstrets
        # iconbitmap inte till Toplevels, varje dialog behöver sin egen.
        apply_icon_to_window(win, APP_ICON)
        win.grab_set()

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(scaled(750, s), int(sw * 0.65))
        h = min(scaled(650, s), int(sh * 0.80))
        x = (sw - w) // 2
        y = (sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")
        body, footer = dialog_layout(win)
        win.resizable(True, True)

        ctk.CTkFrame(
            body, fg_color=ACCENT_PURPLE,
            height=scaled(50, s), corner_radius=0,
        ).pack(fill="x")
        ctk.CTkLabel(
            body, text="📋  Skapa från Struktur",
            font=ctk.CTkFont(size=scaled_font(18, s), weight="bold"),
            text_color="white",
        ).pack(fill="x", padx=scaled(15, s), pady=scaled(8, s))

        inner = ctk.CTkScrollableFrame(body, fg_color="transparent")
        inner.pack(
            fill="both", expand=True,
            padx=scaled(15, s), pady=scaled(10, s),
        )

        ctk.CTkLabel(
            inner, text="Rotmappens namn:",
            font=ctk.CTkFont(size=scaled_font(13, s), weight="bold"),
        ).pack(anchor="w", pady=(scaled(5, s), scaled(2, s)))

        root_var = ctk.StringVar()
        root_entry = ctk.CTkEntry(
            inner, textvariable=root_var,
            height=scaled(36, s),
            font=ctk.CTkFont(size=scaled_font(13, s)),
            placeholder_text="T.ex. MittProjekt",
        )
        root_entry.pack(fill="x")
        win.after(150, lambda: focus_project_name(root_entry))

        ctk.CTkLabel(
            inner, text="Klistra in trädstruktur:",
            font=ctk.CTkFont(size=scaled_font(13, s), weight="bold"),
        ).pack(anchor="w", pady=(scaled(10, s), scaled(2, s)))

        txt = ctk.CTkTextbox(
            inner,
            font=ctk.CTkFont(family="Consolas", size=scaled_font(12, s)),
            height=scaled(280, s),
        )
        txt.pack(fill="both", expand=True)

        btn_row = footer

        def preview_and_create():
            raw = txt.get("1.0", "end")
            r_val = root_var.get().strip()
            if not r_val:
                for line in raw.splitlines():
                    if re.match(r'^[\w\s\-åäöÅÄÖ]+/$', line.strip()):
                        r_val = line.strip().strip("/")
                        break
            if not r_val:
                messagebox.showwarning(
                    "Saknar rotnamn", "Ange rotmappens namn.",
                )
                return
            try:
                r_val = NameValidator.sanitize(r_val)
            except ValueError as e:
                messagebox.showwarning("Ogiltigt namn", str(e))
                return
            _, items = StructureEngine.parse_structure_text(raw)
            # M7/MB5 — inklistrade träd har ofta roten på rad 1. Eftersom
            # _build_structure redan skapar base = save_root / rotnamn skulle
            # roten annars dubbleras (PROJEKT/PROJEKT/...). Skalningen sker
            # FÖRE _show_preview så att förhandsgranskning och bygge ser exakt
            # samma struktur — annars visar rutan något annat än det som skapas.
            items, _stripped = strip_root_level(items, r_val)
            if not items:
                messagebox.showwarning("Tom", "Ingen struktur hittades.")
                return
            if self._show_preview(r_val, items):
                if self._build_structure(r_val, items):
                    win.destroy()

        ctk.CTkButton(
            btn_row, text="🔍  Förhandsgranska & Skapa",
            command=preview_and_create,
            fg_color=ACCENT_PURPLE, hover_color="#8e44ad",
            height=scaled(40, s), corner_radius=10,
            font=ctk.CTkFont(size=scaled_font(13, s), weight="bold"),
        ).pack(side="right")

        ctk.CTkButton(
            btn_row, text="Avbryt", command=win.destroy,
            fg_color="gray", hover_color="#555",
            height=scaled(40, s), corner_radius=10,
            font=ctk.CTkFont(size=scaled_font(13, s)),
        ).pack(side="right", padx=(0, scaled(8, s)))

    def _show_preview(self, root_name: str, items: List[dict]) -> bool:
        dirs, files = StructureEngine.count_items(items)
        lines = []
        for it in items:
            icon = "📁" if it['is_dir'] else "📄"
            indent = "    " * (len(it['path']) - 1)
            name = it['path'][-1]
            suffix = "/" if it['is_dir'] else ""
            comment = f"  ← {it['comment']}" if it.get('comment') else ""
            lines.append(f"{indent}{icon} {name}{suffix}{comment}")

        full = f"📁 {root_name}/\n" + "\n".join(lines)
        full += f"\n\nTotalt: {dirs} mappar, {files} filer"
        if len(full) > 1500:
            full = full[:1500] + "\n... (trunkerad)"
        return messagebox.askyesno(
            "Förhandsvisning", f"Skapa detta?\n\n{full}",
        )

    def _build_structure(self, root_name: str, items: List[dict]) -> bool:
        try:
            root_name = NameValidator.sanitize(root_name)
        except ValueError as exc:
            messagebox.showwarning("Ogiltigt namn", str(exc))
            return False
        base = Path(self.settings.save_root) / root_name

        # Samma namn med annan skiftning räknas också som en dubblett.
        try:
            existing = next((p for p in base.parent.iterdir()
                             if p.name.casefold() == base.name.casefold()), None) if base.parent.exists() else None
        except OSError as exc:
            messagebox.showerror("Fel", f"Kunde inte läsa projektmappen: {exc}")
            return False
        if existing is not None:
            if messagebox.askyesno("Mappen finns redan",
                                  f"'{existing.name}' finns redan. Öppna befintlig mapp istället?"):
                self._open_path(existing)
            return False

        try:
            # exist_ok=False skyddar även om mappen skapas efter kontrollen.
            base.mkdir(parents=True, exist_ok=False)
            for it in items:
                p = base.joinpath(*it['path'])
                if not NameValidator.is_safe_path(base, p):
                    logger.warning("Hoppade över osäker sökväg: %s", p)
                    continue
                if it['is_dir']:
                    p.mkdir(parents=True, exist_ok=True)
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    if not p.exists():
                        p.write_text(
                            f"# {it['comment'] or p.name}",
                            encoding="utf-8",
                        )
            self._on_creation_success(base)
            return True
        except OSError as e:
            messagebox.showerror("Fel", f"Kunde inte skapa struktur: {e}")
            return False

    def _on_creation_success(self, path: Path) -> None:
        self.undo_mgr.record(path)
        self.history.add(path)
        self.undo_btn.configure(state="normal")
        self._set_result(f"✅ Skapad: {path.name}", ACCENT_GREEN)
        self._refresh_history_tab()
        if self.settings.open_after_creation:
            self._open_path(path)

    def _set_result(self, text: str, color: str) -> None:
        self.result_label.configure(text=text, text_color=color)

    def _undo_last(self) -> None:
        if not self.undo_mgr.can_undo:
            return
        path = self.undo_mgr.last_path
        if not path:
            return
        if not messagebox.askyesno(
            "Ångra skapande",
            f"Ta bort '{path.name}' och allt innehåll?\n\n"
            f"Detta går inte att ångra!",
        ):
            return
        removed = self.undo_mgr.undo()
        if removed:
            self._set_result(f"↩ Borttagen: {removed.name}", ACCENT_ORANGE)
            self._refresh_history_tab()
        if not self.undo_mgr.can_undo:
            self.undo_btn.configure(state="disabled")

    # ============================================================
    # LOGIK: Export
    # ============================================================
    def _export_structure_dialog(self) -> None:
        target_dir = filedialog.askdirectory(title="Välj mapp att exportera")
        if not target_dir:
            return
        self._export_specific(Path(target_dir))

    def _show_export_result(self, text: str) -> None:
        s = self._scale
        win = ctk.CTkToplevel(self)
        win.title("Exporterad Struktur")
        win.transient(self)
        # M28 — ikon även i dialogfönster (behövs per Toplevel på Windows).
        apply_icon_to_window(win, APP_ICON)
        win.grab_set()

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(scaled(700, s), int(sw * 0.65))
        h = min(scaled(750, s), int(sh * 0.85))
        x = (sw - w) // 2
        y = (sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")
        body, footer = dialog_layout(win)
        win.resizable(True, True)

        ctk.CTkFrame(
            body, fg_color=ACCENT_ORANGE,
            height=scaled(50, s), corner_radius=0,
        ).pack(fill="x")
        ctk.CTkLabel(
            body, text="📤  Exporterad Mappstruktur",
            font=ctk.CTkFont(size=scaled_font(18, s), weight="bold"),
            text_color="white",
        ).pack(fill="x", padx=scaled(15, s), pady=scaled(8, s))

        ctk.CTkLabel(
            body, text="Mappstruktur:",
            font=ctk.CTkFont(size=scaled_font(13, s), weight="bold"),
        ).pack(
            anchor="w", padx=scaled(15, s),
            pady=(scaled(8, s), scaled(5, s)),
        )

        textbox = ctk.CTkTextbox(
            body,
            font=ctk.CTkFont(family="Consolas", size=scaled_font(12, s)),
        )
        textbox.pack(
            fill="both", expand=True,
            padx=scaled(15, s), pady=scaled(5, s),
        )
        textbox.insert("1.0", text)

        btn_row = footer

        def copy_clip():
            self.clipboard_clear()
            self.clipboard_append(textbox.get("1.0", "end-1c"))
            messagebox.showinfo("Kopierat", "Strukturen kopierad till urklipp!")

        def save_file():
            f = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Textfil", "*.txt"), ("Markdown", "*.md")],
            )
            if f:
                Path(f).write_text(
                    textbox.get("1.0", "end-1c"), encoding="utf-8",
                )
                messagebox.showinfo("Sparat", f"Sparades till {f}")

        def save_as_template():
            name = ctk.CTkInputDialog(
                title="Spara mall", text="Mallens namn:",
            ).get_input()
            if name and name.strip():
                try:
                    self.template_mgr.save_template(name.strip(), textbox.get("1.0", "end-1c"))
                except (ValueError, OSError) as exc:
                    messagebox.showerror("Kunde inte spara mall", str(exc))
                    return
                messagebox.showinfo("Sparat", f"Mall '{name}' sparad!")

        for index, (txt_btn, cmd, color) in enumerate([
            ("📋 Kopiera", copy_clip, ACCENT_BLUE),
            ("💾 Spara fil", save_file, ACCENT_GREEN),
            ("⭐ Spara som mall", save_as_template, ACCENT_ORANGE),
            ("Stäng", win.destroy, "gray"),
        ]):
            btn_row.grid_columnconfigure(index % 2, weight=1)
            ctk.CTkButton(
                btn_row, text=txt_btn, command=cmd,
                fg_color=color,
                hover_color="#555" if color == "gray" else None,
                height=scaled(36, s), corner_radius=8,
                font=ctk.CTkFont(size=scaled_font(12, s), weight="bold"),
            ).grid(row=index // 2, column=index % 2, sticky="ew", padx=3, pady=3)

    # ============================================================
    # LOGIK: Mallar
    # ============================================================
    def _template_dialog(self) -> None:
        s = self._scale
        templates = self.template_mgr.list_templates()

        win = ctk.CTkToplevel(self)
        win.title("Projektmallar")
        win.transient(self)
        # M28 — ikon även i dialogfönster (behövs per Toplevel på Windows).
        apply_icon_to_window(win, APP_ICON)
        win.grab_set()

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(scaled(650, s), int(sw * 0.60))
        h = min(scaled(600, s), int(sh * 0.80))
        x = (sw - w) // 2
        y = (sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")
        body, footer = dialog_layout(win)
        win.resizable(True, True)

        ctk.CTkFrame(
            body, fg_color=ACCENT_GREEN,
            height=scaled(50, s), corner_radius=0,
        ).pack(fill="x")
        ctk.CTkLabel(
            body, text="📋  Projektmallar",
            font=ctk.CTkFont(size=scaled_font(18, s), weight="bold"),
            text_color="white",
        ).pack(fill="x", padx=scaled(15, s), pady=scaled(8, s))

        selected_var = ctk.StringVar()

        list_frame = ctk.CTkScrollableFrame(
            body, height=scaled(100, s),
            fg_color=("gray92", "gray18"),
        )
        list_frame.pack(
            fill="both", expand=True,
            padx=scaled(15, s), pady=(scaled(8, s), 0),
        )

        for name in templates:
            is_builtin = name in self.template_mgr._builtin
            icon = "⭐" if is_builtin else "📄"
            ctk.CTkRadioButton(
                list_frame,
                text=f"{icon}  {name}" + (" — standard" if name == self.settings.default_template else ""),
                variable=selected_var, value=name,
                font=ctk.CTkFont(size=scaled_font(13, s)),
                fg_color=ACCENT_GREEN, hover_color="#27ae60",
            ).pack(anchor="w", pady=scaled(4, s), padx=scaled(8, s))

        ctk.CTkLabel(
            body, text="Struktur (redigerbar, rotmappen på första raden):",
            font=ctk.CTkFont(size=scaled_font(13, s), weight="bold"),
        ).pack(
            anchor="w", padx=scaled(15, s),
            pady=(scaled(8, s), scaled(2, s)),
        )

        preview_box = ctk.CTkTextbox(
            body, height=scaled(130, s),
            font=ctk.CTkFont(family="Consolas", size=scaled_font(11, s)),
        )
        preview_box.pack(fill="x", padx=scaled(15, s))

        def on_select(*_):
            sel = selected_var.get()
            if sel in templates:
                preview_box.delete("1.0", "end")
                preview_box.insert("1.0", templates[sel])

        selected_var.trace_add("write", on_select)
        if self.settings.default_template in templates:
            selected_var.set(self.settings.default_template)

        edit_row = ctk.CTkFrame(body, fg_color="transparent")
        edit_row.pack(fill="x", padx=scaled(15, s), pady=scaled(5, s))

        def save_edited():
            name = ctk.CTkInputDialog(title="Spara mall", text="Namn på den egna mallen:").get_input()
            if not name or not name.strip():
                return
            name = name.strip()
            if name in templates and not messagebox.askyesno("Skriv över mall", f"Ersätt '{name}'?"):
                return
            try:
                self.template_mgr.save_template(name, preview_box.get("1.0", "end-1c"))
            except (ValueError, OSError) as exc:
                messagebox.showerror("Kunde inte spara mall", str(exc))
                return
            win.destroy()
            self._template_dialog()

        def set_default():
            sel = selected_var.get()
            if sel not in templates:
                messagebox.showwarning("Välj mall", "Spara och välj en mall först.")
                return
            self.settings.default_template = sel
            self._save_settings_silent()
            messagebox.showinfo("Standardmall", f"Nya standardprojekt använder nu '{sel}'.")
            win.destroy()
            self._template_dialog()

        ctk.CTkButton(edit_row, text="Ny mall", command=lambda: (
            selected_var.set(""), preview_box.delete("1.0", "end"),
            preview_box.insert("1.0", "projektnamn/\n    Bilder/\n")), width=100).pack(fill="x", pady=3)
        ctk.CTkButton(edit_row, text="Spara som mall", command=save_edited, width=130).pack(fill="x", pady=3)
        ctk.CTkButton(edit_row, text="Ange som standard", command=set_default, width=150).pack(fill="x", pady=3)

        btn_row = footer
        for column in range(3):
            btn_row.grid_columnconfigure(column, weight=1)

        def use_template():
            if not preview_box.get("1.0", "end-1c").strip():
                messagebox.showwarning("Tom struktur", "Välj en mall eller skriv en egen struktur.")
                return
            name = ctk.CTkInputDialog(
                title="Projektnamn", text="Namnge projektet:",
            ).get_input()
            if not name or not name.strip():
                return
            try:
                safe = NameValidator.sanitize(name.strip())
            except ValueError as e:
                messagebox.showwarning("Ogiltigt namn", str(e))
                return
            structure = preview_box.get("1.0", "end-1c").replace(
                "projektnamn", safe,
            ).replace("ärendenummer", safe)
            _, items = StructureEngine.parse_structure_text(structure)
            # M7/MB5 — malltextens rad 1 ÄR roten: placeholderen
            # 'projektnamn'/'ärendenummer' har just ersatts med användarens namn.
            # Utan skalning skapas PROJEKT/PROJEKT/... eftersom _build_structure
            # redan lagt roten. Före _show_preview av samma skäl som ovan.
            # Inget NYTT tomhetstest läggs till: use_template() hade inget i
            # v4.2, och strip_root_level() gör aldrig en icke-tom lista tom
            # (den returnerar items oförändrad om resultatet skulle bli tomt).
            items, _stripped = strip_root_level(items, safe)
            if not items:
                messagebox.showwarning("Tom struktur", "Ange en struktur först.")
                return
            if self._show_preview(safe, items):
                if self._build_structure(safe, items):
                    win.destroy()

        def delete_template():
            sel = selected_var.get()
            if not sel:
                return
            if sel == self.settings.default_template:
                messagebox.showinfo("Standardmall", "Välj en annan standardmall innan denna tas bort.")
                return
            if not self.template_mgr.delete_template(sel):
                messagebox.showinfo(
                    "Info", "Inbyggda mallar kan inte tas bort.",
                )
                return
            messagebox.showinfo("Borttaget", f"Mall '{sel}' borttagen.")
            win.destroy()
            self._template_dialog()

        ctk.CTkButton(
            btn_row, text="✅ Skapa (tillfälligt)",
            command=use_template,
            fg_color=ACCENT_GREEN, hover_color="#27ae60",
            height=scaled(38, s), corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(13, s), weight="bold"),
        ).grid(row=0, column=2, sticky="ew", padx=3)

        ctk.CTkButton(
            btn_row, text="🗑 Ta bort",
            command=delete_template,
            fg_color=ACCENT_RED, hover_color="#c0392b",
            width=scaled(90, s), height=scaled(38, s),
            corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(13, s)),
        ).grid(row=0, column=1, sticky="ew", padx=3)

        ctk.CTkButton(
            btn_row, text="Stäng", command=win.destroy,
            fg_color="gray", hover_color="#555",
            width=scaled(80, s), height=scaled(38, s),
            corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(13, s)),
        ).grid(row=0, column=0, sticky="ew", padx=3)

    # ============================================================
    # Hjälpfunktioner
    # ============================================================
    def _open_path(self, path: Path) -> None:
        if not path.exists():
            messagebox.showwarning("Mappen saknas", f"Mappen finns inte längre:\n{path}")
            return
        try:
            if IS_WINDOWS:
                os.startfile(path)
            else:
                subprocess.Popen(['xdg-open', str(path)])
        except OSError as e:
            logger.warning("Kunde inte öppna mapp: %s", e)

    # ============================================================
    # Hotkeys
    # ============================================================
    def _load_hotkey(self) -> Set[str]:
        # M2/C41.3 — read_json_safe() med .bak/.bak2-fallback.
        data = read_json_safe(HOTKEY_CONFIG, None)
        if isinstance(data, dict):
            # M11/C42 — en sparad men ogiltig kombination (t.ex. ["m"] utan
            # modifierare) skulle annars registreras globalt och stjäla varje
            # m-tryckning i hela systemet. Validera INNAN den används.
            ok, norm, err = validate_hotkey_combo(data.get("hotkey") or [])
            if ok:
                return set(norm)
            logger.warning("Sparad snabbtangent ogiltig (%s) — standard används", err)
        elif data is not None:
            logger.warning("Hotkey-config hade oväntat format — standard används")
        return set(DEFAULT_HOTKEY)

    def _rec_hotkey(self) -> None:
        # Stoppa en eventuell gammal inspelningslyssnare FÖRST — annars läggs
        # två keyboard.Listener-trådar ovanpå varandra om man trycker Spela in
        # på nytt utan att spara/avbryta, och båda matar samma set.
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self.recording_hotkey = True
        self.pressed_keys_for_recording.clear()
        self.hk_display_frame.pack_forget()
        self.hk_rec_frame.pack(
            fill="x",
            padx=scaled(15, self._scale),
            pady=scaled(5, self._scale),
        )
        self.hk_rec_lbl.configure(text="Tryck önskade tangenter...")
        self.hotkey_listener = keyboard.Listener(on_press=self._on_press_rec)
        self.hotkey_listener.start()

    def _on_press_rec(self, key) -> None:
        # Körs i pynput-lyssnarens tråd, ALDRIG i Tk-huvudtråden.
        try:
            k = (
                key.char.lower()
                if hasattr(key, 'char') and key.char
                else str(key).split('.')[-1].lower()
            )
        except AttributeError:
            k = str(key).lower()
        k = k.replace('_l', '').replace('_r', '')
        self.pressed_keys_for_recording.add(k)
        # M10 — hotkey_label() ersätter den lokala prio-dictn med samma ordning
        # (modifierare först) men GUI-fri och enhetstestad. ui_call() schemalägger
        # configure() i huvudtråden: att anropa Tk direkt från en bakgrundstråd
        # kan krascha eller tyst korrumpera hela GUI:t (C43).
        label = hotkey_label(self.pressed_keys_for_recording)
        ui_call(self, self.hk_rec_lbl.configure, text=label)

    def _save_hotkey_rec(self) -> None:
        if not self.pressed_keys_for_recording:
            return
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        # M11/C42 — validera FÖRE sparning och registrering. En kombination utan
        # modifierare skulle göra att appen fångar vanlig skrivning systemöver-
        # gripande; v4.1 sparade och registrerade den utan någon kontroll.
        ok, norm, err = validate_hotkey_combo(self.pressed_keys_for_recording)
        if not ok:
            logger.warning("Snabbtangent förkastad: %s", err)
            messagebox.showwarning("Ogiltig snabbtangent", err)
            self._cancel_hotkey_rec()
            return
        self.current_hotkey = set(norm)
        # M1/F1 — atomisk skrivning med backup.
        if not atomic_write_json(HOTKEY_CONFIG, {"hotkey": list(self.current_hotkey)}):
            logger.error("Kunde inte spara snabbtangent "
                         "(atomisk skrivning misslyckades)")
        self._setup_global_hotkey()
        self._cancel_hotkey_rec()

    def _cancel_hotkey_rec(self) -> None:
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self.hk_rec_frame.pack_forget()
        self.hk_display_frame.pack(
            fill="x",
            padx=scaled(15, self._scale),
            pady=(0, scaled(10, self._scale)),
        )
        self._update_ui_from_settings()

    def _setup_global_hotkey(self) -> None:
        if self.global_hotkey:
            self.global_hotkey.stop()
        # M11/C42 — samma validering som vid sparning: registrera aldrig en
        # kombination som kan stjäla vanlig skrivning i hela systemet.
        ok, norm, err = validate_hotkey_combo(self.current_hotkey)
        if not ok:
            logger.warning("Global snabbtangent ej registrerad: %s", err)
            return
        # M10 — normalize_hotkey_keys() ger stabil ordning (modifierare först)
        # istället för alfabetisk, så strängen blir deterministisk och läsbar.
        hk_str = "+".join(f"<{k}>" for k in normalize_hotkey_keys(norm))
        try:
            self.global_hotkey = keyboard.GlobalHotKeys({
                # M10/C43 — återanrop via ui_call: GlobalHotKeys avfyras i
                # pynput-tråden, så self.after() därifrån är inte trådsäkert.
                hk_str: lambda: ui_call(self, self._restore_from_tray),
            })
            self.global_hotkey.start()
        except ValueError as e:
            logger.warning("Ogiltig hotkey-kombination: %s", e)

    # ============================================================
    # Tray & Autostart
    # ============================================================
    def _on_window_unmap(self, event) -> None:
        # Barnwidgetar och withdraw() får också Unmap. Bara en verklig
        # minimering av huvudfönstret ska skapa/återanvända tray-ikonen.
        if event.widget is self:
            self.after_idle(self._send_iconic_window_to_tray)

    def _send_iconic_window_to_tray(self) -> None:
        # Läs läget efter att fönsterhanteraren hunnit uppdatera det.
        # Ett återställt fönster ska inte döljas av ett gammalt event.
        if self.winfo_exists() and self.state() == "iconic":
            self._minimize_to_systray()

    def _minimize_to_systray(self) -> None:
        self.withdraw()
        # ENDAST EN TRAY-IKON, alltid:
        #  • ikon finns redan          → gör inget (dubbelminimering/X+hotkey)
        #  • en ikon håller på stoppas → vänta 500 ms och prova igen, så att
        #    den gamla ikonen hinner försvinna ur fältet innan nästa ritas
        if self.systray_icon is not None:
            return
        if self._tray_stopping:
            self.after(500, self._minimize_to_systray)
            return
        # Samma ikonkedja som fönstren (M28): cachad, RGBA och med
        # procedurell reserv — inte rå Image.open som kraschar om .ico saknas.
        img = load_app_icon(
            APP_ICON_PNG if APP_ICON_PNG.exists() else APP_ICON, 64)
        if img is None:
            img = Image.new('RGB', (64, 64), (76, 158, 241))
        # lambda *args: pystray anropar menycallbacks med (icon, item) i
        # nyare versioner — en noll-args-lambda dör då tyst i bakgrundstråden.
        menu = pystray.Menu(
            pystray.MenuItem(
                "Öppna FolderForge",
                lambda *args: self.after(0, self._restore_from_tray),
                default=True,
            ),
            pystray.MenuItem(
                "Sök uppdatering nu",
                lambda *args: ui_call(self, self._check_updates_now),
            ),
            pystray.MenuItem(
                "Avsluta",
                lambda *args: self.after(0, self._quit_app),
            ),
        )
        self.systray_icon = pystray.Icon(APP_NAME, img, APP_NAME, menu)
        threading.Thread(target=self.systray_icon.run, daemon=True).start()

    def _stop_tray_icon(self) -> None:
        """Stoppa tray-ikonen exakt en gång — den ENDA vägen att plocka bort den.

        _tray_stopping håller spärren uppe en kort stund efter stop(): pystray
        fäller sin meddelandeloop asynkront, och utan pausen kunde ett snabbt
        min→visa→min skapa nästa ikon innan den gamla försvunnit ur fältet.
        """
        icon = self.systray_icon
        self.systray_icon = None
        if icon is None:
            return
        self._tray_stopping = True
        try:
            icon.stop()
        except Exception as exc:
            logger.debug("tray-ikonens stop() kastade: %s", exc)
        self.after(400, self._release_tray_lock)

    def _release_tray_lock(self) -> None:
        """Släpper ikon-spärren när fältet garanterat är rent igen."""
        self._tray_stopping = False

    def _restore_from_tray(self, *_) -> None:
        self._stop_tray_icon()
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit_app(self, *_) -> None:
        if hasattr(self, "_cleanup_stop"):
            self._cleanup_stop.set()
        if hasattr(self, "_update_stop"):
            self._update_stop.set()
        self._stop_tray_icon()
        if self.global_hotkey:
            self.global_hotkey.stop()
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self.quit()
        sys.exit(0)

    def _show_cache_cleanup(self) -> None:
        from cache_cleanup import clean_cache, status_text

        win = ctk.CTkToplevel(self)
        win.title("Smart cacherensning")
        win.transient(self)
        apply_icon_to_window(win, APP_ICON)
        win.geometry(f"{scaled(520, self._scale)}x{scaled(460, self._scale)}")
        body, footer = dialog_layout(win)
        content = ctk.CTkScrollableFrame(body)
        content.pack(fill="both", expand=True, padx=15, pady=15)
        rules = ("Automatisk rensning en gång per 24 timmar när appen körs.\n"
                 "Om appen varit stängd görs förfallen rensning vid nästa start.\n\n"
                 "Smartfilter (gäller även manuell rensning):\n"
                 "• Filer i data/cache och data/tmp: minst 24 timmar gamla.\n"
                 "• Roterade loggarkiv: minst 14 dagar gamla.\n"
                 "• Länkar, aktiv logg och okända filer utanför cache lämnas kvar.\n\n"
                 "Projekt, mallar, historik, inställningar, väntande uppdateringar "
                 "och uppdateringsbackuper rörs aldrig.")
        ctk.CTkLabel(content, text=rules, justify="left", wraplength=scaled(450, self._scale)).pack(fill="x")
        status = ctk.CTkLabel(content, text=status_text(BASE_DIR), justify="left")
        status.pack(fill="x", pady=15)

        def finished(result=None, error=None):
            if not win.winfo_exists():
                return
            button.configure(state="normal")
            status.configure(text=(f"Rensningen misslyckades: {error}" if error else status_text(BASE_DIR)))

        def run():
            if not messagebox.askyesno("Rensa cache", "Rensa gamla filer enligt smartfiltret?", parent=win):
                return
            button.configure(state="disabled")
            status.configure(text="Rensar…")

            def worker():
                try:
                    result = clean_cache(BASE_DIR, manual=True)
                except Exception as exc:
                    ui_call(self, finished, None, str(exc))
                else:
                    ui_call(self, finished, result)

            threading.Thread(target=worker, name="manual-cache-cleanup", daemon=True).start()

        button = ctk.CTkButton(footer, text="Rensa nu med smartfilter", command=run)
        button.pack(pady=(0, 10))
        ctk.CTkButton(footer, text="Stäng", command=win.destroy).pack(pady=(0, 15))

    def _check_updates_now(self) -> None:
        from updater import check_once

        # Tray-menyn använder samma vy och bakgrundsjobb som knappen i appen.
        self._restore_from_tray()
        self._show_update_status()
        if getattr(self, "_manual_update_running", False):
            return
        self._manual_update_running = True

        def finished():
            self._manual_update_running = False

        def worker():
            try:
                if not check_once(BASE_DIR, APP_VERSION, force=True):
                    logger.info("En uppdateringskontroll pågår redan")
            except Exception:
                logger.warning("Manuell uppdateringskontroll misslyckades", exc_info=True)
            finally:
                ui_call(self, finished)

        threading.Thread(target=worker, name="manual-release-check", daemon=True).start()

    def _show_update_status(self) -> None:
        from updater import get_update_status

        existing = getattr(self, "_update_status_window", None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            return
        s = self._scale
        win = ctk.CTkToplevel(self)
        self._update_status_window = win
        win.title("Uppdateringsstatus")
        win.transient(self)
        apply_icon_to_window(win, APP_ICON)
        win.geometry(f"{scaled(560, s)}x{scaled(570, s)}")
        body, footer = dialog_layout(win)
        win.minsize(scaled(400, s), scaled(350, s))
        ctk.CTkLabel(body, text="Uppdateringsstatus", font=ctk.CTkFont(
            size=scaled_font(20, s), weight="bold")).pack(pady=scaled(15, s))
        content = ctk.CTkScrollableFrame(body)
        content.pack(fill="both", expand=True, padx=scaled(15, s))
        labels = {}
        for name in get_update_status(BASE_DIR, APP_VERSION):
            ctk.CTkLabel(content, text=name, anchor="w", font=ctk.CTkFont(
                size=scaled_font(12, s), weight="bold")).pack(fill="x", pady=(scaled(8, s), 0))
            value = ctk.CTkLabel(content, text="", anchor="w", justify="left",
                                 wraplength=scaled(440, s))
            value.pack(fill="x")
            labels[name] = value
        ctk.CTkLabel(body, text="Hämtade uppdateringar installeras vid nästa appstart.\n"
                     "Ingen pågående session avbryts.", justify="left").pack(pady=scaled(8, s))
        ctk.CTkButton(footer, text="Sök uppdatering nu", command=self._check_updates_now).pack(fill="x", pady=(0, scaled(8, s)))
        ctk.CTkButton(footer, text="Stäng", command=win.destroy).pack(pady=(0, scaled(12, s)))

        def refresh():
            if not win.winfo_exists():
                return
            for name, value in get_update_status(BASE_DIR, APP_VERSION).items():
                labels[name].configure(text=value)
            win.after(2000, refresh)

        refresh()

    def _show_info(self) -> None:
        s = self._scale
        win = ctk.CTkToplevel(self)
        win.title("Om FolderForge")
        win.transient(self)
        # M28 — ikon även i dialogfönster (behövs per Toplevel på Windows).
        apply_icon_to_window(win, APP_ICON)
        win.grab_set()
        win.geometry(f"{scaled(420, s)}x{scaled(500, s)}")
        body, footer = dialog_layout(win)
        win.resizable(True, True)

        ctk.CTkFrame(
            body, fg_color=ACCENT_BLUE,
            height=scaled(60, s), corner_radius=0,
        ).pack(fill="x")
        ctk.CTkLabel(
            body, text="📁 FolderForge",
            font=ctk.CTkFont(size=scaled_font(22, s), weight="bold"),
            text_color="white",
        ).place(x=scaled(15, s), y=scaled(15, s))

        info_frame = ctk.CTkFrame(body, fg_color="transparent")
        info_frame.pack(
            fill="both", expand=True,
            padx=scaled(20, s), pady=scaled(15, s),
        )

        dnd_text = "Ja ✅" if DND_AVAILABLE else "Nej (installera tkinterdnd2)"

        for label, value in [
            ("Version", APP_VERSION),
            ("Upphovsman", "Rickard Längkvist"),
            ("År", str(datetime.now().year)),
            ("Snabbtangent", " + ".join(
                k.capitalize() for k in sorted(self.current_hotkey)
            )),
            ("Sparplats", self.settings.save_root),
            ("Drag & Drop", dnd_text),
            ("Historik", f"{len(self.history.get_all())} projekt"),
              # Ska säga 'win32-mutex-global'. Säger den 'pidfile' saknas
              # pywin32 — och före C41.3-fixen i _pid_alive kunde då VARJE
              # ny start öppna ett eget fönster.
            ("Instanslås", getattr(
                getattr(self, "_instance_lock", None), "backend", "okänt")),
        ]:
            row = ctk.CTkFrame(info_frame, fg_color="transparent")
            row.pack(fill="x", pady=scaled(3, s))
            ctk.CTkLabel(
                row, text=f"{label}:",
                font=ctk.CTkFont(size=scaled_font(12, s), weight="bold"),
                width=scaled(110, s), anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=value,
                font=ctk.CTkFont(size=scaled_font(12, s)),
                anchor="w", wraplength=scaled(260, s),
            ).pack(side="left", fill="x", expand=True)

        # Autostart-status per mekanism (M29) — samma avläsning som
        # _check_autostart() men uppdelad, så att användaren ser VAR appen
        # startas ifrån istället för bara "på/av".
        status_frame = ctk.CTkFrame(body, fg_color="transparent")
        status_frame.pack(
            fill="x", padx=scaled(20, s), pady=(0, scaled(8, s)),
        )
        ctk.CTkLabel(
            status_frame, text="Autostart:",
            font=ctk.CTkFont(size=scaled_font(12, s), weight="bold"),
            anchor="w",
        ).pack(anchor="w")
        try:
            _as = collect_autostart_status(APP_NAME)
            _rader = [
                ("Registret (HKCU Run)", bool(_as["registry"]["command"])),
                ("Start-mappens genväg", bool(_as["startup_folder"]["shortcut"])),
                ("Task Scheduler", bool(_as["task_scheduler"]["present"])),
            ]
        except Exception:
            _rader = [(n, None) for n in (
                "Registret (HKCU Run)", "Start-mappens genväg",
                "Task Scheduler")]
        for namn, aktiv in _rader:
            mark = "❓" if aktiv is None else ("✅" if aktiv else "—")
            ctk.CTkLabel(
                status_frame, text=f"{mark}  {namn}",
                font=ctk.CTkFont(size=scaled_font(12, s)),
                anchor="w",
            ).pack(anchor="w")

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, scaled(8, s)))
        ctk.CTkButton(
            btn_row, text="🔍 Testa autostart",
            command=self._test_autostart_ui,
            fg_color=ACCENT_TEAL, height=scaled(32, s), corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(12, s)),
        ).pack(side="left", fill="x", expand=True, padx=(0, scaled(6, s)))
        ctk.CTkButton(
            btn_row, text="📋 Kopiera diagnostik",
            command=self._copy_diagnostics,
            fg_color=ACCENT_PURPLE, height=scaled(32, s), corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(12, s)),
        ).pack(side="left", fill="x", expand=True, padx=(scaled(6, s), 0))

        ctk.CTkButton(
            footer, text="Stäng", command=win.destroy,
            fg_color=ACCENT_BLUE, height=scaled(36, s),
            corner_radius=8,
            font=ctk.CTkFont(size=scaled_font(13, s)),
        ).pack(pady=(0, scaled(15, s)), padx=scaled(20, s), fill="x")

    def _test_autostart_ui(self) -> None:
        """Kör autostart-diagnosen (B6/M29c) i en bakgrundstråd.

        Testar det REGISTRERADE kommandot om autostart är aktiverad, annars
        det kommando som skulle registreras vid aktivering — då är knappen
        meningsfull även före aktivering. Körningen tar någon sekund
        (underprocess med --selftest) och ligger i en daemon-tråd så att
        Om-dialogen aldrig fryser; resultatet visas i huvudtråden via ui_call.
        """
        def jobb() -> None:
            try:
                lagrat = read_autostart_entry(APP_NAME)
                if lagrat:
                    kommando, källa = lagrat, "registrerat kommando"
                else:
                    kommando = build_autostart_command(["--tray"])
                    källa = "föreslaget kommando (autostart ej aktiverad ännu)"
                rep = test_autostart_command(kommando)
                detaljer = rep.get("detail", "")
                if rep.get("ok"):
                    ui_call(self, messagebox.showinfo, "Autostart-test ✅",
                            f"Testet lyckades ({källa}).\n\n{detaljer}\n\n"
                            f"Kommando:\n{kommando}")
                else:
                    analys = rep.get("analysis", {}) or {}
                    problem = analys.get("problems") or []
                    extra = ("\n\nAnalys:\n  " + "\n  ".join(problem)
                             ) if problem else ""
                    ui_call(self, messagebox.showwarning, "Autostart-test ⚠️",
                            f"Testet misslyckades ({källa}).\n\n{detaljer}{extra}\n\n"
                            f"Kommando:\n{kommando}")
            except Exception as exc:
                ui_call(self, messagebox.showerror, "Autostart-test",
                        f"Testet kunde inte köras:\n{exc}")

        threading.Thread(target=jobb, daemon=True).start()

    def _copy_diagnostics(self) -> None:
        """Kopiera full systemdiagnostik (M24/B5) till urklipp.

        Samma underlag som felrutorna hänvisar till: plattform, paketversioner,
        DPI/skalning, ikonmetod, autostart-status per mekanism och skrivbarhet
        för datafilerna. Avsett att klistras in vid felrapportering.
        """
        try:
            info = collect_diagnostics(
                app_name=APP_NAME,
                app_version=APP_VERSION,
                icon_path=APP_ICON,
                data_paths={
                    "settings": SETTINGS_FILE,
                    "history": HISTORY_FILE,
                    "templates": TEMPLATES_DIR,
                    "hotkey_config": HOTKEY_CONFIG,
                },
                providers={
                    "python_version": lambda: sys.version.split()[0],
                    "python_executable": lambda: sys.executable,
                    "platform": lambda: sys.platform,
                    "tk_version": lambda: str(tk.TkVersion),
                    "dnd_available": lambda: DND_AVAILABLE,
                    "appearance_mode": lambda: ctk.get_appearance_mode(),
                    "customtkinter_version": lambda: getattr(ctk, "__version__", "?"),
                    "scale_factor": lambda: self._scale,
                    "screen": lambda: (
                        f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}"),
                    "icon_method": lambda: getattr(self, "_icon_method", "?"),
                    "packages": lambda: {
                        mod: (importlib.metadata.version(mod)
                              if _is_package_installed(mod) else "saknas")
                        for mod in REQUIRED_PACKAGES
                    },
                    "autostart": lambda: collect_autostart_status(APP_NAME),
                },
            )
            text = format_diagnostics(info)
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Kopierat",
                                "Systemdiagnostiken kopierad till urklipp.")
        except Exception as exc:
            messagebox.showerror("Fel", f"Kunde inte samla diagnostik:\n{exc}")

    def _check_autostart(self) -> bool:
        """M19/C44: läs autostart-status via den verifierande registerbackenden.

        Namn och signatur är oförändrade. Innehållet delegerar till
        read_autostart_entry() så att läsning, skrivning och reparation delar
        EN kodväg — v4.1 hade duplicerad winreg-logik här och i
        _toggle_autostart, vilket gjorde att rutan kunde visa fel läge.
        """
        if not IS_WINDOWS:
            return False
        # M29/v5.0 — rutan ska visa "på" om NÅGON av de tre mekanismerna är
        # aktiv. Med enbart registerläsning visade rutan "av" på en dator där
        # grupppolicy blockerat registret men Start-mappens genväg fungerade
        # utmärkt, och användaren trodde att autostart var avstängt.
        try:
            return bool(collect_autostart_status(APP_NAME)["enabled"])
        except Exception:
            logger.warning("Fullständig autostart-status kunde inte läsas — "
                           "faller tillbaka på registret", exc_info=True)
            return bool(read_autostart_entry(APP_NAME))

    def _toggle_autostart(self, enable: bool, initial: bool = False) -> None:
        """M19/C44: slå på/av autostart med verify-after-write.

        Signaturen (enable, initial) och felrutan vid initial=False är
        oförändrade. Två v4.1-fel är rättade:

        1. exe = sys.executable.replace("python.exe", "pythonw.exe") träffade
           INTE python3.12.exe / python3.13.exe, så en svart konsolruta kunde
           dyka upp vid inloggning. build_autostart_command() hanterar alla
           varianter och faller tillbaka på 'start "" /B' om pythonw saknas.
        2. Ingen återläsning efter skrivning. write_autostart_entry() läser
           tillbaka värdet och rapporterar om registret inte accepterade det.
        """
        if not IS_WINDOWS:
            return
        if initial:
            # Uppstartssynk: rutan initierades redan ur faktiskt läge via
            # _check_autostart(), så här finns inget att göra. Utan spärren
            # SKREV __init__ om registret och startup-genvägen (en PowerShell-
            # underprocess!) vid VARJE appstart — dessutom kunde en tillfälligt
            # nekad skrivning slå över rutan till "av" trots fungerande genväg.
            return
        # M29/v5.0 — ALLA TRE mekanismer istället för endast registret.
        #
        # På domänanslutna och företagsstyrda datorer är HKCU\...\Run ofta låst
        # av grupppolicy: skrivningen kunde "lyckas" tekniskt men värdet
        # försvann, eller kastade OSError, och v4.3 gav bara en felruta utan
        # någon reserv. Start-mappens genväg och Task Scheduler är båda
        # skrivbara utan administratörsrättigheter och täcker de fallen.
        #
        # enable_autostart_all_methods() kräver att MINST EN lyckas och
        # rapporterar utfallet per metod, så felrutan kan säga VAD som
        # misslyckades istället för bara att något gjorde det.
        if enable:
            resultat = enable_autostart_all_methods(
                APP_NAME, build_autostart_command(["--tray"]),
                icon_path=APP_ICON)
            if not resultat.get("ok") and not initial:
                missade = [n for n, v in resultat.get("methods", {}).items()
                           if not v.get("ok")]
                messagebox.showerror(
                    "Fel",
                    "Autostart kunde inte aktiveras i någon mekanism.\n\n"
                    "Försökt: " + ", ".join(missade or ["(ingen)"]) +
                    "\n\nÖppna Om-dialogen och klicka på 'Testa autostart' "
                    "för full diagnostik.",
                )
        else:
            # Rensar alla tre. Idempotent: saknas en mekanism är det inget fel.
            disable_autostart_all_methods(APP_NAME)
        # verify-after-write: rutan visar vad som FAKTISKT står i registret
        try:
            self.autostart_var.set(bool(read_autostart_entry(APP_NAME)))
        except Exception:
            logger.warning("Kunde inte verifiera autostart-status", exc_info=True)


# ============================================================
# Entry Point
# ============================================================
if __name__ == "__main__":
    # M29c/v5.0 — --selftest: verifiera att det REGISTRERADE autostart-kommandot
    # faktiskt fungerar, utan att öppna ett fönster.
    #
    # "Testa autostart"-knappen i Om-dialogen kör autostart-kommandot med denna
    # flagga tillagd. Om kommandot är trasigt (fel python, saknad skriptfil,
    # saknade paket, felaktig arbetskatalog) returnerar processen nollskilt och
    # knappen visar EXAKT varför — istället för att användaren upptäcker felet
    # som en svart ruta eller en app som aldrig startar vid nästa inloggning.
    #
    # Körs FÖRE instanslåset medvetet: ett självtest ska aldrig krocka med en
    # redan körande instans, och aldrig lämna låset i ett konstigt läge.
    # Skrivningen går till stdout via sys.stdout.write istället för print()
    # eftersom specen förbjuder print() — men en föräldraprocess som fångar
    # utdata behöver en ström att läsa, och loggern går till fil.
    if "--selftest" in sys.argv:
        _fel: List[str] = []
        try:
            _raw = read_json_safe(SETTINGS_FILE, {})
            _clean, _repaired, _log = validate_settings(_raw)
            if _repaired:
                _fel.append("settings.json behövde repareras: " + "; ".join(_log))
        except Exception as _exc:
            _fel.append("settings: %s" % _exc)
        try:
            if load_app_icon(APP_ICON, 16) is None:
                _fel.append("ikonen kunde inte laddas (reserven användes)")
        except Exception as _exc:
            _fel.append("ikon: %s" % _exc)
        for _pkg in ("customtkinter", "PIL", "pystray", "pynput"):
            try:
                importlib.metadata.version(_pkg)
            except Exception:
                _fel.append("paket saknas: %s" % _pkg)
        if _fel:
            sys.stdout.write("SJÄLVTEST MISSLYCKADES:\n  " + "\n  ".join(_fel) + "\n")
            sys.stdout.flush()
            sys.exit(1)
        sys.stdout.write("%s %s självtest OK\n" % (APP_NAME, APP_VERSION))
        sys.stdout.flush()
        sys.exit(0)

    # M27/v5.0 — DPI-medvetenhet MÅSTE sättas före att något fönster skapas.
    # Sätts den efteråt, eller inte alls, virtualiserar Windows hela appen
    # (bitmappsstretchning) och texten blir suddig på hidpi-skärmar. Värdet är
    # 0-3 och loggas, så användarens "Testa autostart"/diagnostik kan visa om
    # skalningen kom från DPI eller från skärmbredden.
    _dpi_niva = set_dpi_awareness()
    logger.debug("DPI-medvetenhet satt till nivå %s", _dpi_niva)

    # M28b — egen AppUserModelID FÖRE något fönster skapas, annars kan
    # aktivitetsfältet slå ihop appen med andra pythonw.exe-fönster och visa
    # Pythons ikon istället för FolderForges egen.
    set_app_user_model_id()

    # M22/C1 — max en instans. Utan detta låg två tray-ikoner och två
    # GlobalHotKeys-listeners i minnet efter en dubbelstart, och båda
    # instanserna skrev till settings.json/history.json med varsin kopia av
    # datat i minnet (sista skrivning vann → tyst dataförlust).
    #
    # En andra start begär fokus på det befintliga fönstret via en triggerfil
    # och avslutar sig själv. Låset frigörs i finally OCH via atexit, och
    # release() är idempotent — en krasch lämnar alltså aldrig ett zombielås.
    _instance_lock = SingleInstanceLock(APP_NAME)
    if not _instance_lock.acquire():
        _instance_lock.request_focus()
        logger.info("FolderForge körs redan — fokus begärt på befintligt fönster.")
        sys.exit(0)
    # Startläge (användarens beslut): "start_minimized" i settings.json styr
    # — default PÅ = starta alltid minimerad, oavsett startsätt. --tray
    # (autostart/CLI) tvingar minimerat även om inställningen vore avstängd.
    _raw_start = read_json_safe(SETTINGS_FILE, {}) or {}
    _start_clean, _start_rep, _start_log = validate_settings(_raw_start)
    for _rad in _start_log:
        logger.warning("Inställning reparerad: %s", _rad)
    _start_minimerad = (bool(_start_clean.get("start_minimized", True))
                        or "--tray" in sys.argv)

    try:
        from updater import apply_pending, start_updates
        try:
            _updated = apply_pending(BASE_DIR)
        except Exception:
            logger.exception("Kunde inte installera release; befintlig version används")
            _updated = False
        if _updated:
            # Läs in alla nya moduler i en ren process, med samma startläge.
            _instance_lock.release()
            os.execv(sys.executable, [sys.executable, str(BASE_DIR / "folder.pyw"), *sys.argv[1:]])
        app = FolderForgeApp(start_minimerad=_start_minimerad)
        app._update_stop = start_updates(BASE_DIR, APP_VERSION)
        from cache_cleanup import start_cleanup
        app._cleanup_stop = start_cleanup(BASE_DIR)
        app._instance_lock = _instance_lock  # visar lås-backend i Om-dialogen
        # Polla triggerfilen i Tk-huvudtråden (~1 s) och återställ fönstret.
        # root.after() är den trådsäkra vägen in i Tk (C43).
        _instance_lock.poll_start(app, app._restore_from_tray)
        app.mainloop()
    finally:
        _instance_lock.release()
