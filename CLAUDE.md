# Projektregler för AI-agenter (`CLAUDE.md`)

Läs och följ **alltid** samtliga hårda regler i [`AGENTS.md`](AGENTS.md) innan du gör ändringar eller svarar:

1. **Hård regel – Uppdatera ALLTID GitHub-releasen + markera som `Latest` vid kodförändring:** Appen (`updater.py`) jämför filer via `/releases/latest` -> `/commits/<tag>` -> SHA-256 `content_manifest`. Kör alltid `python tools/sync_shared_core.py`, `python tools/sync_runtime_bootstrap.py`, `python tools/ci_tests.py` före commit, och `python tools/publish_release.py` efter push.
2. **Hård regel – Aldrig `main` / aldrig merge / en aktiv arbetsbranch:** Arbeta aldrig mot `main`, öppna/merga aldrig PR mot `main`, och rensa bort överblivna sidobrancher så endast en aktiv arbetsbranch används.
3. **Hård regel – Förslagslista var 10:e chattmeddelande:** Visa 10 helt nya, ej återbrukade förslag var 10:e chattmeddelande (kontrollera `AGENTS.md`, `docs/100_FORBATTRINGSFORSLAG.md` och `docs/25-utvecklingsforslag.md`).
4. **Hårda funktionskrav:** Ta bort `data/update-backup` när uppdaterad start bekräftats (behåll vid fel), rensa arkiverade loggar äldre än 7 dagar (`ARCHIVE_RETENTION_DAYS = 7`), och behåll ruta/skadeval i `ProjectDialog`, underfliken `Profiler` i `Inställningar`, maxhöjdsstart och `Icon/folderforge-print-editable.svg`.
