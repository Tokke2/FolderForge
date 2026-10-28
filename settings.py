# settings.py
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════════════
  FolderForge — DEN ENDA platsen för konfiguration
════════════════════════════════════════════════════════════════════════════

Allt som är "värden, inte logik" bor här — aldrig spritt i GUI-koden:

  ┌─ Sektion ────────────────────┬─ Ändra här när du vill ───────────────┐
  │ 1. Appidentitet               │ byta namn/version/upphovsman          │
  │ 2. Sökvägar                   │ flytta data/ eller Icon/-mappen       │
  │ 3. Plattform & gränser        │ ändra historikdjup                    │
  │ 4. Filnamnsregler             │ ändra saneringsreglerna               │
  │ 5. Paketkrav                  │ lägga till/ta bort beroenden          │
  │ 6. Inställningskontrakt       │ lägga till en ny inställning          │
  │ 7. Inställningstexter         │ ändra texten i Inställningar-fönstret │
  │ 8. Tema & UI-standarder       │ färger, flik-ikoner, snabbtangent     │
  └───────────────────────────────┴───────────────────────────────────────┘

folder.pyw importerar alla namn oförändrade (from settings import ...) —
den här filen kan redigeras fritt utan att huvudfilen rörs, så länge
samma namn finns kvar.
"""

from __future__ import annotations

import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, Optional, Sequence, Tuple


# ══════════════════════════════════════════════════════════════════════════
#  1. APPIDENTITET — vem/vad appen är
# ══════════════════════════════════════════════════════════════════════════
APP_NAME: Final[str] = "FolderForge"
APP_VERSION: Final[str] = "0.0.2"
COPYRIGHT_OWNER: Final[str] = f"© Rickard Längkvist {datetime.now().year}"


# ══════════════════════════════════════════════════════════════════════════
#  2. SÖKVÄGAR — alltid relativt denna mapp, oavsett var appen startas ifrån
# ══════════════════════════════════════════════════════════════════════════
# BASE_DIR pekar på projektmappen (denna fils mapp). Alla andra sökvägar
# härleds ur den — flytta aldrig någon del för sig.
BASE_DIR: Final[Path] = Path(__file__).parent.resolve()

# data/ — användartillstånd (skapas automatiskt vid behov)
DATA_DIR: Final[Path] = BASE_DIR / "data"
SETTINGS_FILE: Final[Path] = DATA_DIR / "settings.json"      # användarens val
HISTORY_FILE: Final[Path] = DATA_DIR / "history.json"        # projekthistorik
HOTKEY_CONFIG: Final[Path] = DATA_DIR / "hotkey_config.json" # snabbtangent
TEMPLATES_DIR: Final[Path] = DATA_DIR / "templates"          # egna mallar
LOG_DIR: Final[Path] = DATA_DIR / "logs"                     # roterande loggfiler

# Icon/ — appens ikon i tre format (fönster/tray/bygge)
ICON_DIR: Final[Path] = BASE_DIR / "Icon"
APP_ICON: Final[Path] = ICON_DIR / "projektmapp.ico"         # Windows .ico
APP_ICON_PNG: Final[Path] = ICON_DIR / "projektmapp_icon_256.png"


# ══════════════════════════════════════════════════════════════════════════
#  3. PLATTFORM & GRÄNSER
# ══════════════════════════════════════════════════════════════════════════
IS_WINDOWS: Final[bool] = platform.system() == "Windows"

# Max antal poster i projekthistoriken (Historik-fliken)
MAX_HISTORY: Final[int] = 20


# ══════════════════════════════════════════════════════════════════════════
#  4. FILNAMNSREGLER — Windows kompabilitet, sanera aldrig mer än nödvändigt
# ══════════════════════════════════════════════════════════════════════════
# Kända "extensionslösa" filnamn (README, Dockerfile …) — används av
# struktur-importen för att känna igen filer kontra mappar.
KNOWN_FILES: Final[frozenset] = frozenset({
    'makefile', 'dockerfile', 'license', 'readme',
    'changelog', 'contributing', 'authors', 'todo',
    '.gitignore', '.gitkeep', '.env', '.dockerignore',
    'procfile', 'gemfile', 'rakefile', 'vagrantfile',
})

# De 9 förbjudna tecknen i Windows-filnamn + kontrolltecken 0x00–0x1F.
# Dessa — och bara dessa — ersätts med '_' vid sanering.
# (OBS: exakt två backslashes här. Fyra fördubblade teckenklassen förra
# gången så att ALLA versaler och siffror blev '_', t.ex. 'DSS817'→'______'.)
INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows reserverade enhetsnamn — får inte användas ens med filändelse
# (CON.txt går inte att skapa på Windows). Kompletteras av RESERVED_STEM_RE
# i folder.pyw som täcker '.\anything'-varianten.
INVALID_NAMES: Final[frozenset] = frozenset({
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
})


# ══════════════════════════════════════════════════════════════════════════
#  5. PAKETKRAV — vad som måste finnas, och varför
# ══════════════════════════════════════════════════════════════════════════
# importnamn → pip-namn. None betyder "hoppa över på denna plattform"
# (pywin32 saknar mening utanför Windows). Saknade paket installeras
# automatiskt vid start — användaren tillfrågas först i en dialog.
REQUIRED_PACKAGES: Final[Dict[str, Optional[str]]] = {
    "customtkinter": "customtkinter",
    "Pillow": "pillow",
    "pystray": "pystray",
    "pynput": "pynput",
    "pywin32": "pywin32" if IS_WINDOWS else None,
    "tkinterdnd2": "tkinterdnd2",
}

# Vad varje paket används till — visas i diagnostik och felmeddelanden.
PACKAGE_PURPOSE: Final[Dict[str, str]] = {
    "customtkinter": "hela gränssnittet (fönster, kort, knappar)",
    "Pillow": "ikonhantering (läser .ico/.png, ritar reserv-ikonen)",
    "pystray": "ikonen i systemfältet med Öppna/Avsluta-menyn",
    "pynput": "global snabbtangent (Ctrl+Shift+M även när appen är dold)",
    "pywin32": "Windows-integration: instanslås-mutex, register, processer",
    "tkinterdnd2": "dra & släppa mappar till Exportera-fliken",
}


# ══════════════════════════════════════════════════════════════════════════
#  6. INSTÄLLNINGSKONTRAKT — settings.json valideras mot detta vid start
# ══════════════════════════════════════════════════════════════════════════
# nyckel → (typ, standardvärde). Fel typ, okänt enum eller saknad nyckel
# repareras automatiskt till standarden (M3/C2) — lägg därför alltid till
# nya inställningar här, annars "lagras" de inte korrekt.
SETTINGS_SCHEMA: Final[Dict[str, Tuple[type, Any]]] = {
    "save_root": (str, ""),                 # rotmapp för nya projekt
    "open_after_creation": (bool, True),    # öppna Utforskaren efter skapande
    "theme": (str, "Dark"),                 # se SETTINGS_ENUMS nedan
    "default_template": (str, "Skaderapport"), # sparad standardmall
    "last_template": (str, ""),             # senast använda mall
    "plate_mode": (bool, True),             # regns-läge (ABC 123 → ABC123)
    "start_minimized": (bool, True),        # starta alltid minimerad i systray
    "visible_tabs": (dict, {}),             # flik → ska synas?
}

# Tillåtna värden för inställningar som är uppräkningar.
SETTINGS_ENUMS: Final[Dict[str, Sequence[str]]] = {
    "theme": ("System", "Dark", "Light"),
}


# ══════════════════════════════════════════════════════════════════════════
#  7. INSTÄLLNINGSTEXTER — ALL synlig text i Inställningar-fönstret
# ══════════════════════════════════════════════════════════════════════════
# En enda källa: vill du ändra en etikett eller hjälptext ändrar du HÄR —
# fönstret hämtar sin text via appens _settings_option()-hjälp.
SETTINGS_META: Final[Dict[str, Dict[str, str]]] = {
    "save_root": {
        "label": "Spara projekt i",
        "beskrivning": "Rotmappen där nya projektmappar skapas.",
    },
    "open_after_creation": {
        "label": "Öppna mapp automatiskt efter skapande",
        "beskrivning": ("Utforskaren öppnas direkt i den nya projektmappen "
                        "så fort den skapats."),
    },
    "autostart": {
        "label": "Starta automatiskt med Windows",
        "beskrivning": ("Startar minimerad i systemfältet vid inloggning. "
                        "Skrivs till register, Start-mappen och Schemaläggaren "
                        "— minst en räcker, alla tre rensas vid avstängning."),
    },
    "plate_mode": {
        "label": "Regnr-läge — normalisera regnr i projektnamnets början",
        "beskrivning": ("'dss 817 stenskott' blir 'DSS817 STENSKOTT'. Båda "
                        "formaten ABC123 och ABC12A känns igen; text efter "
                        "regnr:t (år, stenskott …) följer med. Namn utan "
                        "regnr skapas som skrivet, med en mjuk varning."),
    },
    "start_minimized": {
        "label": "Starta alltid minimerad i systemfältet",
        "beskrivning": ("Appen startar direkt i systray utan att fönstret "
                        "visas — gäller ALLA startsätt, även dubbelklick. "
                        "Klicka på tray-ikonen (eller starta appen igen) "
                        "för att öppna fönstret."),
    },
    "theme": {
        "label": "Tema",
        "beskrivning": "System följer Windows-läget; Dark/Light tvingar läge.",
    },
    "visible_tabs": {
        "label": "Synliga flikar",
        "beskrivning": "Välj flikar i sidofältet. 'Skapa' kan inte döljas.",
    },
}


# ══════════════════════════════════════════════════════════════════════════
#  8. TEMA & UI-STANDARDER — färger och utseende-ikoner
# ══════════════════════════════════════════════════════════════════════════
# Accentfärgerna används per kort/sektion i appen. MENU_THEMES i folder.pyw
# är svaret på frågan "vilken färg blir bakgrunden?" — dessa är förgrunden.
ACCENT_BLUE: Final[str] = "#4C9EF1"
ACCENT_GREEN: Final[str] = "#2ECC71"
ACCENT_RED: Final[str] = "#E74C3C"
ACCENT_ORANGE: Final[str] = "#F39C12"
ACCENT_PURPLE: Final[str] = "#9B59B6"
ACCENT_TEAL: Final[str] = "#1ABC9C"

# Konventionell visningsordning (menyer, temaväljare, dubblett-kontroller).
ACCENT_ORDER: Final[Tuple[str, ...]] = (
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_PURPLE,
    ACCENT_ORANGE, ACCENT_TEAL, ACCENT_RED,
)

# Sidofältets flikar: etikett → ikon. Ordningen här är ordningen på skärmen.
TAB_ICONS: Final[Dict[str, str]] = {
    "Skapa": "🏗️",
    "Historik": "🕐",
    "Mallar": "📋",
    "Exportera": "📤",
    "Inställningar": "⚙️",
    "Snabbtangent": "⌨️",
}

# Standard om inget sparats: Ctrl+Shift+M visar/döljer appen globalt.
DEFAULT_HOTKEY: frozenset[str] = frozenset({"ctrl", "shift", "m"})


# ══════════════════════════════════════════════════════════════════════════
#  9. PROJEKTFLÖDE — snabbval i dialogen "Nytt Standardprojekt"
# ══════════════════════════════════════════════════════════════════════════
# Skadetyperna visas som klickbara chips under namnfältet. Ett klick lägger
# till / tar bort ordet i namnet — t.ex. "DSS817" + STENSKOTT. Redigera
# listan fritt: chip-raden byggs direkt ur listan, och namnet genomgår
# alltid samma normalisering/sanering som handskriven text.
DAMAGE_TYPE_CHIPS: Final[Tuple[str, ...]] = (
    "STENSKOTT",
    "SIDORUTA",
    "BAKRUTA",
)

# Undantagsregel INOM skadetyperna: även SIDORUTA och BAKRUTA är skadetyper
# (användarens kategorisering), men just detta PAR är ömsesidigt uteslutande
# — att toggla det ena ruta-ordet plockar alltid bort det andra ur namnet.
RUTA_CHOICES: Final[Tuple[str, ...]] = (
    "SIDORUTA",
    "BAKRUTA",
)

# Lokaler i dropdownen. Väljer man en lokal läggs ordet ALLTID sist i
# mappnamnet ("JPM602 SIDORUTA LAXÅ"); standardvalet "—" = ingen lokal.
LOKAL_CHOICES: Final[Tuple[str, ...]] = (
    "LAXÅ",
    "ÖREBRO",
)
