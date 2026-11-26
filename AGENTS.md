# OBLIGATORISKA HÅRDA REGLER FÖR FOLDERFORGE (`AGENTS.md`)

Denna fil är **källan till sanning** för alla AI-agenter och utvecklare i **FolderForge** (`Tokke2/FolderForge`). Läs och följ samtliga regler nedan i **varje chatt** och vid **varje kodförändring**.

---

## META-REGEL – Spara alltid nya regler direkt till GitHub

- Om användaren skriver **` - hård regel `** eller **` regel `** i chatten ska den nya regeln **alltid skrivas in här i `AGENTS.md`** (samt speglas i `CLAUDE.md` / `.github/copilot-instructions.md`), committas och pushas till den aktiva branchen på GitHub – följt av att GitHub-releasen uppdateras och markeras som `Latest`.

---

## 1. HÅRD REGEL – Branch-, PR- och Standardbranch-disciplin (`REQ-BRANCH`)

- **Endast en aktiv arbetsbranch (standardbranch):** Ta bort överblivna sidobrancher så att endast en aktiv branch används, och arbeta endast emot den – även efter byte av chatt (via GitHubs *Default branch / standardbranch*).
  - *Notis i Arena Agent Mode:* Arena låser varje session till sessionens tilldelade aktiva branch (`arena/...`). Pusha alltid enbart till sessionens aktiva branch och påminn vid behov ägaren att sätta den senaste branchen som *Default branch* på GitHub om en gammal branch ligger kvar.
- **Arbeta ALDRIG emot `main`:** Varken commits, pushar eller appuppdateringar får ske emot `main`.
- **ALDRIG merge eller Pull Request:** Öppna **aldrig** en PR och **merga aldrig** grenar.

---

## 2. HÅRD REGEL – Uppdatera ALLTID Releasen + Markera som `Latest` vid Kodförändring (`REQ-REL`)

- Vid **varje kodförändring** ska GitHub-releasen uppdateras så att releasens git-tagg (`refs/tags/v<APP_VERSION>`) pekar på den nya commitens SHA, och releasen ska **alltid markeras som `Latest`** (`make_latest=true` / `--latest`).
- **Orsak:** Appens uppdaterare (`updater.py`) läser `/releases/latest` → `/commits/<tag>` → `/zipball/<sha>` och jämför alla appfilers SHA-256 (`content_manifest`) mot den lokala installationen.
- Kör alltid efter push:
  ```bash
  python tools/publish_release.py
  ```
  som flyttar/skapar taggen, uppdaterar releasen med `--latest` och live-verifierar alla SHA-256-hashar via `updater.check_once()`.

---

## 3. HÅRD REGEL – Inget Terminalfönster, Minimerad Start & Inga Tysta Beroende-/Gränssnittsbrott (`REQ-K4`)

- **Inget terminalfönster någonstans:** Inget konsol- eller terminalfönster får någonsin blinka förbi eller visas – varken vid appstart (`Starta-FolderForge.vbs` / `Starta-FolderForge.ps1` / `pythonw.exe`), vid Python-detektering, vid mapp-/trälexportskanning eller vid omstart/uppdatering (`CREATE_NO_WINDOW`, `-WindowStyle Hidden`, `LSUIElement=true`).
- **Starta alltid minimerat/dolt:** Appen ska alltid starta minimerad till systemfältet (`--tray`) utan att öppna huvudfönstret förrän användaren själv klickar på ikonen eller trycker snabbtangenten.
- **Inga tysta installationer eller dataskador (`REQ-K4`):**
  - Installera eller uppgradera aldrig Python eller pip-paket tyst vid vanlig start.
  - Skriv aldrig över eller radera användardata i `data/` (`settings.json`, `history.json`, `templates/`).
  - Bryt aldrig befintliga CLI-flaggor (`--tray`, `--selftest`, `--preview`), låsfiler eller den uttryckliga Tk-reserven (`Starta-FolderForge-Tk.py`).

---

## 4. HÅRD REGEL – Säker Uppdaterare, Backup-städning & 7-Dagars Logg-/Felloggshantering (`REQ-UPD` & `REQ-LOG`)

- **Säker appuppdatering (`updater.py`):** Validera alla uppackade Python-, XML/SVG/plist- och ikonfiler samt SHA-256-manifest innan byte av filer; bevara `data/` orörd.
- **Ta bort backup vid lyckad uppdatering:** Så fort den uppdaterade appstarten har bekräftats (`confirm_startup` / `_supervise_update`) ska `data/update-backup` tas bort automatiskt. Om starten misslyckas behålls backupen för automatisk återställning.
- **Komplett applogg + aktiv fellogg + 7-dagars radering (`logg.py` & `qt_help.py`):**
  - `logs/folderforge.log` är den kompletta apploggen. Gårdagens loggar arkiveras automatiskt till `logs/archive/YYYY-MM-DD/` och raderas automatiskt efter **7 dagar** (`ARCHIVE_RETENTION_DAYS = 7`).
  - `logs/folderforge-errors.log` innehåller **alla aktiva fel**. När ett fel har åtgärdats ska det kunna rensas bort ur felloggen i UI (*Felsökning och fellista*: både enskilt valt fel och alla åtgärdade fel), varpå arkivkopian i `logs/resolved-errors/` också raderas automatiskt efter **7 dagar**.

---

## 5. HÅRD REGEL – Skärmanpassning, High-DPI-skärpa, Logotyp/Ikoner, Prestanda & FolderForge-UI (`REQ-UI`)

- **Start i maxhöjd & adaptiv bredd:** Huvudfönstret ska öppnas i skärmens maximala tillgängliga höjd (`availableGeometry` exkl. aktivitetsfält/ramar) och anpassa bredden efter skärmstorlek och textskala. Alla sidor använder tydlig 2-kolumnslayout för minimal scroll och anpassar sig rent ned till små/smala skärmar.
- **Skärpa & High-DPI:** Krispig text, font, bild och kolumnrendering vid >100 % skalning utan grumlig omskalning (`devicePixelRatio`-medveten rendering, `PreferQuality`/`PreferVerticalHinting`, fastbreddstypsnitt i strukturvyer).
- **Logotyp & ikoner överallt + tryckoriginal:** Skarp vektorlogotyp i hela appen (`Icon/folderforge-logo.svg` och `Icon/folderforge-logo-inverse.svg`), redigerbart vektororiginal för tryck (`Icon/folderforge-print-editable.svg`) samt enhetliga vektorikoner (`Icon/nav-*.svg`).
- **Sorterbara & flyttbara kolumner:** Tabellvyer i appen (`Historik` och `Fellista`) ska ha klickbar kolumnsortering (`setSortingEnabled(True)`) och flyttbara kolumnrubriker med dra-och-släpp (`setSectionsMovable(True)`).
- **FolderForge-specifika funktioner:**
  - **Underfliken `Profiler` i `Inställningar`** (`self.settings_subtabs`) för att skapa, redigera och hantera profiler (mall + egen sparplats).
  - **Val av ruta/skadetyp i projektskaparen (`ProjectDialog`)**: snabbvalschips för `STENSKOTT`, `VINDRUTA`, `SIDORUTA` och `BAKRUTA` (`SIDORUTA`/`BAKRUTA` utesluter varandra), precis som i `ttk`-versionen.
- **Minnes-, hastighets- och energisnålhet:** Händelsestyrd filbevakning (`QFileSystemWatcher`) + `Qt.CoarseTimer`, begränsad `QPixmapCache`, pausad UI-statusuppdatering när fönstret är minimerat samt `deleteLater()` på stängda dialoger.

---

## 6. HÅRD REGEL – Obligatoriska Testkrav Innan Klar (`REQ-TEST`)

Ingen kodändring är klar förrän samtliga steg nedan har körts utan fel:
1. `python tools/sync_shared_core.py`
2. `python tools/sync_runtime_bootstrap.py`
3. `python tools/ci_tests.py && rm -rf windows-evidence` (hela enhetstestsviten grön)
4. Push till aktiv arbetsbranch och verifiering att alla GitHub Actions-workflows (`Windows startup and update safety`, `Linux and macOS desktop`, `Default Qt desktop and recovery`) går i mål med `success`.
5. `python tools/publish_release.py` (uppdaterar releasen, sätter `Latest` och verifierar 100 % matchande SHA-256 via `updater.py`).

---

## 7. HÅRD REGEL – Förslagsregeln i Chatten (`REQ-IDEAS`)

- Alla förslagslistor ska **alltid skrivas direkt i chatten** (aldrig bara hänvisas till en fil).
- **Var 10:e chattmeddelande** ska en ny lista visas i chatten på **10 nya funktionsförslag** som konkurrenterna saknar och användare efterfrågar.
- **Ej återbrukade:** Inga förslag får någonsin återanvändas från tidigare listor nedan eller från `docs/100_FORBATTRINGSFORSLAG.md` / `docs/25-utvecklingsforslag.md`. Registrera alltid nyvisade förslag här i `AGENTS.md`.

### Redan visade chattförslag (`#1–#75` – FÅR EJ ÅTERBRUKAS)

- **#1–#25:** 1. Startmallfiler med platshållare (`{REGNR}`, `{DATUM}`, `{ORT}`, `{FORDON}`, `{SKADETYP}`). 2. Smart filsluss (drag-drop till rätt undermapp). 3. 90-dagars dubblettdetektor. 4. Urklippsigenkänning vid snabbtangent. 5. Hälsokontroll av saknade undermappar. 6. Tray-snabbsökning (Spotlight). 7. Villkorsstyrda undermappar per skada/fordon. 8. Skrivskydda/klarmarkera arkiverade projekt. 9. Kamerafoto-namngivning & HEIC->JPG. 10. Lokal Wi-Fi QR-bilduppladdning. 11. Tidslinje & filstatistik i Historik. 12. Batch-skapande från CSV/Excel med Ångra. 13. `.ffprofile`-import/export. 14. Offline-kö vid frånkopplad NAS. 15. Utforskaren/Finder högerklicksmeny. 16. Färgkodade mappikoner (`desktop.ini`). 17. Projektkopplad snabbanteckning (`ANTECKNING.txt`). 18. Kund-/försäkringsexport (ZIP/PDF). 19. Mappdiff mot mall. 20. Visuella namnbyggklossar/separator. 21. Automatiskt löpnummer (`2026-001`). 22. Ett-klicks inställningsbackup (`.zip`). 23. Sök i filnamn/anteckningar från Historik. 24. Presentations-/kundläge. 25. Förhandsgranskning av ändrade filer i uppdateraren + versionshistorik.
- **#26–#50:** 26. Obligatorisk fotochecklista per profil. 27. EXIF-/GPS-rensning vid delning. 28. Offline-validering av regnummer & 17-teckens VIN. 29. Års-/månads-/veckogruppering per profil. 30. Bevakad skanner-/kamerainkorg ("Watch Folder"). 31. Lokal revisionshistorik (`.folderforge-audit.json`). 32. Klona projekt som nytt del-/omärende. 33. Städning av tomma undermappar vid avslutat ärende. 34. Lokala statusflaggor i Historik. 35. Realtidsindikator för ledigt diskutrymme på NAS. 36. Drag-drop av mejl (`.eml`/`.msg`) med bilagesortering. 37. Profilkopplad "Öppna i fackprogram"-knapp. 38. Smart namnkrockslösare (`KOMPLETTERING`, `DEL 2`). 39. Schemalagd flytt till kallarkiv/NAS efter X dagar. 40. Icke-förstörande bildkomprimering (`<2 MB`). 41. Centralt synkad skrivskyddad team-profilkatalog över LAN/SMB. 42. Karantän-Ångra i 24 timmar. 43. Ett-klicks kopiering av UNC-nätverkssökväg. 44. Pekskärms-/verkstadsläge ("Handskläge"). 45. Inbyggd PDF-sammanfogare för `Underlag/`. 46. Nåla fast aktiva veckoprojekt ("Favoriter"). 47. Integritetskontroll mot 0-byte/avbrutna kameraöverföringar. 48. Egna globala snabbtangenter per profil. 49. Skapa ny profil från befintlig mapp på disken. 50. 1-sekunds hälsotest av SMB-nätverkssparplats.
- **#51–#75:** 51. Offline streckkods-/QR-avläsning av arbetsorder på inskannade dokument. 52. Automatisk registreringsskyltsmaskering (lokal oskärpa) för arkiv-/referensbilder. 53. Före-/efter-bildparvy med svepreglage direkt från Historik. 54. Ljudnotis/röstanteckning till textlogg (`RÖSTNOTIS.wav` + tidsstämpel) i projektmappen. 55. Kalibrerings-/ADAS-protokollkontroll för vindrutebyten (varnar om protokoll-PDF saknas vid `VINDRUTA`). 56. Utländska registreringsskyltsprofiler (SE, NO, DK, FI, DE, PL) i regnummernormaliseraren. 57. Automatisk dubblettbildrensning (exakt SHA-256) vid dubbelkopiering från minneskort. 58. Tidsbudget-/SLA-räknare per aktivt ärende i Historik (t.ex. "Öppet i 3 arbetsdagar"). 59. Utskriftsvänlig mappetikett / fysisk arbetsorderlapp med QR-kod till projektmappen. 60. Automatisk mörker-/motljusvarning vid oskarpa eller underexponerade skadefoton. 61. Snabbväxling mellan sommar-/vinter- eller filialspecifika `LOKAL_CHOICES` per profil. 62. Skydd mot för långa Windows-sökvägar (`MAX_PATH` 260 tecken) innan djupa undermappar skapas. 63. Lokal PDF/A- och filformatkontroll inför arkivering mot myndighet eller försäkringsbolag. 64. Flervalsåtgärder i Historik-tabellen (exportera, klarmarkera eller kontrollera 10 valda projekt samtidigt). 65. Valfri skrivbords-droppzon (flytande miniatyrikon vid skärmkanten) under pågående kameraimport. 66. Automatisk extrahering av datum ur kamerans EXIF `DateTimeOriginal` när äldre skadebilder importeras. 67. Säkert anonymiserat demoprojektläge för utbildning av nyanställda utan skarpa kunddata. 68. Valfri krypterad delmapp (`Känsligt.zip` med AES-256) för personuppgifter/ID-handlingar i ärendet. 69. Sammanställningsrapport (CSV/HTML) över antal skapade projekt per månad, lokal, fordonstyp och ruta. 70. Automatisk kontroll av skrivlås (öppna Word/Excel/PDF-filer) innan arkivering eller flytt av projektmapp. 71. Stöd för anpassade metadatafält per profil (t.ex. Försäkringsbolag, Skadenummer, Tekniker) i `projektinfo.json`. 72. Snabb "Öppna senast ändrade fil i projektet"-knapp i Historiks detaljpanel. 73. Tangentbordsstyrda siffergenvägar (`Alt+1`…`Alt+4`) för ruta-/skadechipsen direkt i projektdialogen. 74. Valfri verifierad spegling (lokal reservkopia + nätverks-NAS) i realtid vid projektskapande. 75. Återställningsbar papperskorg för raderade egna profiler/mallar i *Inställningar → Profiler*.
