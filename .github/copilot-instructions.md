Läs och följ alltid alla hårda projektregler i `AGENTS.md` i repots rot:
- Om användaren skriver `' - hård regel '` eller `' regel '` ska regeln direkt läggas till i `AGENTS.md` och pushas till GitHub.
- Endast en aktiv arbetsbranch (standardbranch); arbeta ALDRIG mot `main` och gör ALDRIG PR eller merge.
- Vid VARJE kodförändring måste GitHub-releasen uppdateras och markeras som `Latest` via `python tools/publish_release.py` (appen jämför filer via `updater.py`).
- Inget terminalfönster vid start eller skanning; starta alltid minimerat (`--tray`); inga tysta beroende- eller gränssnittsbrott (`REQ-K4`).
- Visa 10 nya, ej återbrukade förslag direkt i chatten var 10:e chattmeddelande (kontrollera `#1–#75` i `AGENTS.md`).
