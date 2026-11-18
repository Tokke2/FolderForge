"""Shared OS startup integration. No GUI imports and no changes without explicit calls."""
from __future__ import annotations
import ctypes
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from settings import APP_ICON, BASE_DIR, IS_WINDOWS
logger = logging.getLogger(__name__)

def build_autostart_command(script_args: Optional[Iterable[str]] = None) -> str:
    """
    Bygger autostart-kommandot och GARANTERAR att ingen svart konsolruta
    visas vid inloggning:
      • fryst exe (PyInstaller/Nuitka) → "exe" --tray  (ingen python alls)
      • Python-källkod på Windows → egen FolderForge.exe med inbäddad ikon
      • inga .pyw-filassociationer eller Python-ikoner i autostartgenvägen
    """
    args = list(script_args) if script_args else ["--tray"]
    quoted_args = " ".join(f'"{a}"' for a in args)

    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {quoted_args}'.strip()

    exe = Path(sys.executable)
    if IS_WINDOWS:
        from updater import ensure_launcher
        # En egen winexe med inbäddad ikon, inte .pyw-filassociationen.
        launcher = ensure_launcher(BASE_DIR, exe, APP_ICON)
        return f'"{launcher}" {quoted_args}'.strip()
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


AUTOSTART_TASK_NAME: str = "FolderForge_Autostart"


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

    .lnk via PowerShell WScript.Shell med appens ikon. Ingen generisk
    .bat/.pyw-fallback: register eller Schemaläggaren kan starta vår exe.

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
    match = re.fullmatch(r'\s*(?:"([^"]+)"|(\S+))(?:\s+(.*))?', command.strip())
    if not match:
        return False, "ogiltigt startkommando"
    exe = match.group(1) or match.group(2)
    args = match.group(3) or ""

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
        ps += f"$s.IconLocation='{_psq(icon_path)},0';"
    ps += "$s.Save()"
    try:
        res = run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if getattr(res, "returncode", 1) == 0 and lnk.exists():
            legacy = folder / f"{slug}.bat"
            if legacy.exists():
                legacy.unlink()
            return True, f"lnk:{lnk}"
        logger.debug("PowerShell-genväg misslyckades: %s",
                     getattr(res, "stderr", "")[:200])
    except FileNotFoundError:
        logger.debug("powershell finns inte — ingen ikonlös reservgenväg skapas.")
    except Exception as exc:
        logger.debug("PowerShell-genväg kastade: %s", exc)

    # Registrera aldrig en generisk .bat/.pyw som ikonmässig reserv.
    # Register/Schemaläggaren kan fortfarande starta vår brandade exe.
    return False, "kunde inte skapa Windows-genväg med FolderForge-ikon"


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



def configure_autostart(enabled, base=BASE_DIR, system=None):
    """Explicit user action only. Never installs packages or bypasses OS policy."""
    import plistlib
    from historik import _fsync_dir
    system = system or sys.platform
    base = Path(base).resolve()
    if system == 'win32':
        if enabled:
            return enable_autostart_all_methods('FolderForge', build_autostart_command(), icon_path=APP_ICON)
        return disable_autostart_all_methods('FolderForge')
    if system == 'darwin':
        target = Path.home() / 'Library/LaunchAgents/se.folderforge.autostart.plist'
        content = plistlib.dumps(dict(Label='se.folderforge.autostart', RunAtLoad=True,
            ProgramArguments=['/bin/sh', str(base / 'Starta-FolderForge.sh')],
            WorkingDirectory=str(base), ProcessType='Background'))
    elif system.startswith('linux'):
        target = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'autostart/FolderForge.desktop'
        def quote(value):
            value = str(value)
            if any(char in value for char in '\r\n'):
                raise ValueError('Radbrytning i appens sökväg')
            return '"' + value.replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$') + '"'
        content = ('[Desktop Entry]\nType=Application\nName=FolderForge\nTerminal=false\n'
            'Exec=/bin/sh ' + quote(base / 'Starta-FolderForge.sh') + '\nIcon=' +
            str(base / 'Icon/projektmapp_icon_256.png').replace('\\', '\\\\') + '\n').encode('utf-8')
    else:
        raise ValueError('Operativsystemet stöds inte för autostart')
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError('Symbolisk länk i autostartplatsen; ingen ändring görs')
    if enabled:
        import tempfile
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.folderforge-', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    else:
        target.unlink(missing_ok=True)
    return {'ok': True, 'methods': {'os_login': {'ok': True,
            'detail': ('Aktiverad för nästa inloggning: ' if enabled else 'Avaktiverad: ') + str(target)}}}
