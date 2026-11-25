Läs och följ alltid alla hårda projektregler i `AGENTS.md` i repots rot:
- Vid VARJE kodförändring måste GitHub-releasen uppdateras mot aktuell commit-SHA och markeras som `Latest` via `python tools/publish_release.py` (appen jämför filer med SHA-256 via `updater.py`).
- Arbeta ALDRIG mot `main` och merga ALDRIG till `main`; håll endast en aktiv arbetsbranch.
- Visa 10 nya, ej återbrukade förslag var 10:e chattmeddelande (se `AGENTS.md` för redan använda `#1–#50`).
