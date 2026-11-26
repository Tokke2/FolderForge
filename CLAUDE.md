# Projektregler för AI-agenter (`CLAUDE.md`)

Läs och följ **alltid** hela regelverket i [`AGENTS.md`](AGENTS.md) i repots rot i varje chatt:

- **Meta-regel:** Om användaren skriver `' - hård regel '` eller `' regel '` ska regeln omedelbart läggas till i `AGENTS.md` (och här), pushas till GitHub och synkas till `Latest`-releasen.
- **Branch & PR (`REQ-BRANCH`):** Endast en aktiv arbetsbranch (standardbranch); arbeta **aldrig** emot `main`; öppna **aldrig** PR och **merga aldrig**.
- **Release & Latest (`REQ-REL`):** Uppdatera **alltid** GitHub-releasen vid varje kodförändring och markera som `Latest` via `python tools/publish_release.py` (appen jämför filer med SHA-256 via `updater.py`).
- **Inget terminalfönster & `REQ-K4`:** Inget konsolfönster vid vare sig start, skanning eller omstart (`pythonw.exe`, `CREATE_NO_WINDOW`, `-WindowStyle Hidden`); starta alltid minimerat i systemfältet (`--tray`); inga tysta beroende- eller gränssnittsbrott; rör aldrig `data/`.
- **Backup & Loggar (`REQ-UPD` / `REQ-LOG`):** Ta bort `data/update-backup` när uppdaterad start bekräftats (behåll vid fel). Arkivera gårdagens applogg (`folderforge.log`) och radera arkiv äldre än 7 dagar; aktiv fellogg (`folderforge-errors.log`) kan rensas när fel åtgärdats (arkiv raderas efter 7 dagar).
- **UI & Prestanda (`REQ-UI`):** Maxhöjd vid start, adaptiv bredd, minimal scroll, skarp High-DPI, skarp vektorlogotyp + redigerbar tryckvektor (`Icon/folderforge-print-editable.svg`) + nya ikoner, sorterbara/flyttbara kolumner i tabeller, underfliken `Profiler` i `Inställningar`, val av ruta i `ProjectDialog`, samt minnes-/energisnål drift.
- **Testkrav (`REQ-TEST`):** Kör `sync_shared_core.py`, `sync_runtime_bootstrap.py`, `ci_tests.py` samt verifiera gröna GitHub Actions + `publish_release.py` innan klar.
- **Förslagsregeln (`REQ-IDEAS`):** Skriv alltid förslag direkt i chatten; var 10:e chattmeddelande ska 10 nya, ej återbrukade förslag visas (se `#1–#75` i `AGENTS.md`).
