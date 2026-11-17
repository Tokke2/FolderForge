"""Shared GUI-independent instance locking. Extracted from the tested Tk app."""
from __future__ import annotations
import atexit
import ctypes
import logging
import os
import re
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, Final, Iterable, List, Optional, Sequence, Set, Tuple
from settings import *
from historik import atomic_write_json, read_json_safe
logger = logging.getLogger(__name__)

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
        self.check_trigger()  # Baseline before acquisition; do not lose a startup focus request.

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
            return False         # Utan verifierat lås får ingen ny instans starta.

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
                logger.error("Windows-instanslåset är otillgängligt — start stoppad.")
                self._backend = "unavailable"
                return False
            except Exception as exc:
                logger.error("Win32-instanslåset kunde inte verifieras (%s) — start stoppad.", exc)
                self._backend = "unavailable"
                return False

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

        pending_focus = self.check_trigger()  # Preserve requests received while GUI initialized.
        from updater import service_instance_health
        try:
            service_instance_health(self.lock_dir, BASE_DIR / "folder.pyw")
        except Exception:
            logger.warning("Hälsosignalen kunde inte startas", exc_info=True)

        def _loop() -> None:
            nonlocal pending_focus
            if not self._is_primary:
                return
            try:
                service_instance_health(self.lock_dir, BASE_DIR / "folder.pyw")
                requested = self.check_trigger()
                if pending_focus or requested:
                    pending_focus = False
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
        if self._is_primary:
            try:
                from updater import clear_instance_health
                clear_instance_health(self.lock_dir)
            except Exception:
                pass  # Hälsostädning får aldrig hindra att instanslåset släpps.
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

