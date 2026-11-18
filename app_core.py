"""Shared GUI-independent project/domain logic. Extracted from the tested Tk app."""
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

    if out.get("start_minimized") is not True:
        out["start_minimized"] = True
        repaired = True
        log.append("start_minimized → True (obligatorisk start i systemfältet)")
    return out, repaired, log


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


@dataclass
class AppSettings:
    save_root: str = field(default_factory=lambda: str(Path.home() / "Projects"))
    open_after_creation: bool = True
    theme: str = "Dark"
    text_size: str = "100%"
    high_contrast: bool = False
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
            text_size=data.get("text_size", "100%"),
            high_contrast=data.get("high_contrast", False),
            default_template=data.get("default_template", "Skaderapport"),
            last_template=data.get("last_template", ""),
            plate_mode=data.get("plate_mode", True),
            start_minimized=data.get("start_minimized", True),
            visible_tabs=default_tabs,
        )


class TemplateManager:
    def __init__(self, directory=None) -> None:
        self.directory = Path(directory) if directory is not None else TEMPLATES_DIR
        self.directory.mkdir(parents=True, exist_ok=True)
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
        for f in self.directory.glob("*.json"):
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
            self.directory / f"{safe}.json",
            {"name": name, "structure": structure},
        ):
            raise OSError(f"Kunde inte spara mall {name!r}")

    def delete_template(self, name: str) -> bool:
        if name in self._builtin:
            return False
        safe = NameValidator.sanitize(name)
        p = self.directory / f"{safe}.json"
        if p.exists():
            p.unlink()
            return True
        return False


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



class ExistingProject(FileExistsError):
    def __init__(self, path):
        self.path = Path(path)
        super().__init__(f"Projektet finns redan: {self.path}")


def create_project_tree(save_root, root_name, items):
    """Single implementation for both GUIs. Never merge into an existing project.

    Validate every relative component before writing. On I/O failure a partial
    project is left for inspection; never recursively delete potentially useful data.
    """
    root_name = NameValidator.sanitize(root_name)
    base = Path(save_root) / root_name
    checked = []
    for item in items:
        parts = item.get('path')
        if not isinstance(parts, (list, tuple)) or not parts:
            raise ValueError('Tom sökväg i strukturen')
        for part in parts:
            if not isinstance(part, str) or part in {'.', '..'} or sanitize_name(part) != part:
                raise ValueError(f'Otillåten sökväg i strukturen: {parts!r}')
        if not NameValidator.is_safe_path(base, base.joinpath(*parts)):
            raise ValueError('Strukturen lämnar projektmappen')
        checked.append((list(parts), bool(item['is_dir']), item.get('comment')))
    if base.parent.exists():
        for path in base.parent.iterdir():
            if path.name.casefold() == base.name.casefold():
                raise ExistingProject(path)
    base.mkdir(parents=True, exist_ok=False)
    for parts, is_dir, comment in checked:
        path = base.joinpath(*parts)
        if not NameValidator.is_safe_path(base, path):
            raise ValueError('Sökvägen har ändrats under skapandet')
        if is_dir:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8') as stream:
                stream.write(f'# {comment or path.name}')
    return base


def build_project_name(namn_text: str, lokal: str, year: str = "—", vehicle_type: str = "") -> str:
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
    vehicle = str(vehicle_type or "").strip().upper()
    if vehicle:
        if vehicle not in VEHICLE_CHOICES:
            raise ValueError("Okänt fordonsslag")
        ord_lista = [word for word in ord_lista if word.upper() not in VEHICLE_CHOICES]
        ord_lista.append(vehicle)
    if lokal and lokal != "—":
        ord_lista.append(lokal)
    if year and year != "—":
        ord_lista.append(year)
    return " ".join(ord_lista)



def validate_hotkey_combo(keys: Iterable[str]) -> Tuple[bool, List[str], str]:
    """
    Godkänner bara kombinationer som INTE kan stjäla vanlig skrivning:
      • minst 1 modifierare (ctrl/alt/shift/cmd/win)
      • minst 1 icke-modifierare
      • max 5 tangenter
      • inga mellanslag i namn
    Returnerar (ok?, normaliserad_lista, felmeddelande).
    """
    norm = normalize_hotkey_keys(keys)

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
    for key in base:
        if not ((len(key) == 1 and key.isprintable() and key not in "+<> ")
                or key in {"space", "enter", "tab", "esc", "backspace", "delete", "insert", "home", "end", "page_up", "page_down", "up", "down", "left", "right"}
                or re.fullmatch(r"f(?:[1-9]|1[0-9]|2[0-4])", key)):
            return False, norm, "Okänd tangent: " + key
    return True, norm, ""


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
        raw = str(k)
        if len(raw) == 1 and 1 <= ord(raw) <= 26:
            raw = chr(ord(raw) + 96)  # pynput kan ge Ctrl+M som \r
        s = raw.strip().lower()
        if not s:
            continue
        if s.startswith('key.'):
            s = s[4:]
        s = s.replace('_l', '').replace('_r', '')
        s = {'win': 'cmd', 'super': 'cmd', 'command': 'cmd', 'option': 'alt', 'control': 'ctrl'}.get(s, s)
        if s and s not in norm:
            norm.append(s)
    norm.sort(key=lambda x: (HOTKEY_KEY_ORDER.get(x, 99), x))
    return norm


def hotkey_expression(keys):
    """pynput: <ctrl>+<alt>+m, aldrig <m>."""
    return "+".join(k if len(k) == 1 else "<" + k + ">" for k in normalize_hotkey_keys(keys))

