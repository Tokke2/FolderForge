# OBLIGATORISKA PROJEKTREGLER FÖR FOLDERFORGE (`AGENTS.md`)

Denna fil läses vid varje session/chatt och innehåller **hårda, icke-förhandlingsbara regler** från projektägaren. Alla regler nedan gäller i **varje** chatt och vid **varje** kodändring.

---

## 1. HÅRD REGEL – Uppdatera ALLTID GitHub-releasen + markera som `Latest` vid kodförändring

- Vid **varje kodförändring** (oavsett om versionsnumret i `settings.py` höjs eller behålls) **måste** GitHub-releasen uppdateras mot den nya commit-SHA:n och markeras som **`Latest`** (`make_latest=true` / `--latest`).
- **Varför:** Appens inbyggda uppdaterare (`updater.py`) läser `/releases/latest`, slår upp taggens exakta commit-SHA via `/commits/<tag>`, hämtar `/zipball/<sha>` och jämför samtliga appfilers SHA-256 (`content_manifest`). Om taggen eller `Latest`-markeringen inte uppdateras ser appen inte kodförändringen.
- **Obligatoriskt flöde vid varje kodändring:**
  1. Synka inbäddade återställnings-/startfiler:
     ```bash
     python tools/sync_shared_core.py
     python tools/sync_runtime_bootstrap.py
     ```
  2. Kör hela enhetstestsviten (och rensa ev. `windows-evidence/` efteråt):
     ```bash
     python tools/ci_tests.py && rm -rf windows-evidence
     ```
  3. Committa och pusha till den **aktiva arbetsbranchen** (aldrig `main`) och vänta in gröna GitHub Actions-flöden.
  4. Publicera/uppdatera releasen och verifiera live med `updater.py`:
     ```bash
     python tools/publish_release.py
     ```
     *(Det finns även ett automatiskt skyddsnät i `.github/workflows/release-latest.yml` som kör `tools/publish_release.py` när Qt-CI passerar på en `arena/*`-branch.)*

---

## 2. HÅRD REGEL – Aldrig `main`, aldrig merge, endast en aktiv arbetsbranch

- **Arbeta aldrig direkt mot `main`.**
- **Öppna eller slå aldrig ihop (merge) en Pull Request mot `main`.**
- Rensa bort överblivna sidobrancher så att endast **en aktiv arbetsbranch** används åt gången (i Arena Agent Mode: sessionens tilldelade aktiva branch `arena/...`), särskilt vid appuppdateringar.

---

## 3. HÅRD REGEL – 10 nya, ej återbrukade funktionsförslag var 10:e chattmeddelande

- Efter **var 10:e chattmeddelande** ska en ny lista visas på **10 nya funktionsförslag**.
- **Inga förslag får återbrukas** från tidigare chattar eller dokument. Kontrollera alltid:
  1. Förslagslistan nedan (`#1–#50`, redan visade),
  2. `docs/100_FORBATTRINGSFORSLAG.md`,
  3. `docs/25-utvecklingsforslag.md`.
- Uppdatera avsnittet **"Redan visade chattförslag"** nedan när en ny 10-lista har presenterats så att nästa chatt aldrig återanvänder dem.

---

## 4. HÅRDA FUNKTIONS- OCH SÄKERHETSINVARIANTER

1. **Ingen tyst installation:** Inga Python- eller paketinstallationer/uppgraderingar får ske tyst vid vanlig appstart.
2. **Skydda användardata:** `data/` (inställningar, profiler, historik) får aldrig skrivas över vid uppdatering.
3. **Automatisk städning av uppdateringsbackup:** `data/update-backup` ska finnas kvar under pågående uppdateringsprov (och vid misslyckad start för rollback), men **raderas automatiskt** så fort den nya starten bekräftats (`confirm_startup` / `_supervise_update`).
4. **7-dagars rensning av arkiverade loggar:** Loggarkiv i `logs/archive/` och `logs/resolved-errors/` äldre än **7 dagar** (`ARCHIVE_RETENTION_DAYS = 7` i `logg.py`) rensas automatiskt och symlink-säkert. Aktiva loggar (`logs/folderforge.log`) och olösta fel (`logs/folderforge-errors.log`) får aldrig raderas automatiskt.
5. **UI-krav i Qt (`qt_app.py`):**
   - Snabbvalschips för ruta/skada i `ProjectDialog`: `STENSKOTT`, `VINDRUTA`, `SIDORUTA`, `BAKRUTA` (där `SIDORUTA`/`BAKRUTA` i `RUTA_CHOICES` utesluter varandra).
   - Egen underflik **`Profiler`** inne i `Inställningar` (`self.settings_subtabs`).
   - Start i skärmens maximala tillgängliga höjd (`availableGeometry`) med proportionerlig bredd och 2-kolumnskort för minimal rullning.
   - Knivskarp vektorlogotyp (`Icon/folderforge-logo.svg` / `Icon/folderforge-logo-inverse.svg`) samt redigerbart tryckoriginal i vektor (`Icon/folderforge-print-editable.svg`).

---

## Redan visade chattförslag (FÅR EJ ÅTERBRUKAS)

- **#1–#25:**
  1. Startmallfiler med platshållare (`{REGNR}`, `{DATUM}`, `{ORT}`, `{FORDON}`, `{SKADETYP}`).
  2. Smart filsluss (drag-drop av blandade filer till rätt undermapp).
  3. 90-dagars dubblettdetektor för regnummer/projekt.
  4. Urklippsigenkänning av regnummer vid snabbtangent.
  5. Hälsokontroll av saknade undermappar i äldre projekt.
  6. Tray-snabbsökning (Spotlight-liknande sökruta).
  7. Villkorsstyrda undermappar per skadetyp/fordon.
  8. Skrivskydda/klarmarkera arkiverade projekt.
  9. Automatisk kamerafoto-namngivning & HEIC->JPG.
  10. Lokal Wi-Fi QR-bilduppladdning från mobil till `Bilder/`.
  11. Tidslinje & filstatistik i Historik.
  12. Batch-skapande från CSV/Excel med samlad Ångra.
  13. `.ffprofile`-import/export av profiler.
  14. Offline-kö vid tillfälligt frånkopplad NAS/nätverksenhet.
  15. Högerklicksmeny i Utforskaren/Finder.
  16. Färgkodade mappikoner per profil (`desktop.ini`).
  17. Projektkopplad snabbanteckning (`ANTECKNING.txt`).
  18. Kund-/försäkringsexport (ZIP/PDF med fotoöversikt).
  19. Mappdiff mot profilens mall.
  20. Visuella namnbyggklossar och valfri separator.
  21. Automatiskt löpnummer (`2026-001`).
  22. Ett-klicks inställningsbackup (`.zip`).
  23. Sök i filnamn och anteckningar inuti projekt från Historik.
  24. Presentations-/kundläge som döljer interna sökvägar.
  25. Förhandsgranskning av ändrade filer i uppdateraren + versionshistorik.

- **#26–#50:**
  26. Obligatorisk fotochecklista per profil.
  27. Automatisk EXIF- och GPS-rensning vid extern delning.
  28. Offline-validering av registreringsnummer & 17-teckens VIN.
  29. Automatisk års-/månads-/veckogruppering per profil.
  30. Bevakad skanner-/kamerainkorg ("Watch Folder").
  31. Lokal revisionshistorik i projektmappen (`.folderforge-audit.json`).
  32. Klona projekt som nytt del-/omärende i Historik.
  33. Städning av tomma undermappar vid avslutat ärende.
  34. Lokala statusflaggor i Historik (`Pågående`, `Väntar reservdel`, `Klart`).
  35. Realtidsindikator för ledigt diskutrymme på sparplats/NAS.
  36. Drag-och-släpp av mejl (`.eml`/`.msg`) med bilagesortering.
  37. Profilkopplad "Öppna i valfritt fackprogram"-knapp.
  38. Smart namnkrockslösare med färdiga suffixförslag (`KOMPLETTERING`, `DEL 2`).
  39. Schemalagd flytt till kallarkiv/NAS efter X dagar.
  40. Icke-förstörande bildkomprimering (`<2 MB`) för portaler.
  41. Centralt synkad skrivskyddad team-profilkatalog över LAN/SMB.
  42. Karantän-Ångra i 24 timmar före permanent radering.
  43. Ett-klicks kopiering av UNC-nätverkssökväg (`\\server\utdelning\...`).
  44. Pekskärms-/verkstadsläge ("Handskläge").
  45. Inbyggd PDF-sammanfogare för `Underlag/`.
  46. Nåla fast aktiva veckoprojekt ("Favoriter") i Skapa och tray-meny.
  47. Integritetskontroll mot avbrutna kameraöverföringar (0-byte/korrupt JPEG/PDF).
  48. Egna globala snabbtangenter per profil (`Ctrl+Shift+1`, `Ctrl+Shift+2`).
  49. Skapa ny profil automatiskt från en befintlig mapp på disken.
  50. 1-sekunds hälsotest av nätverkssparplats (SMB-latens & behörigheter).
