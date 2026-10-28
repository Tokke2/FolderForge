# FolderForge

## Start i systemfältet

Appen startar som standard minimerad i systemfältet utan att huvudfönstret
blinkar till. Öppna via tray-ikonen, snabbtangenten eller genom att starta
appen igen. Inställningen **Starta alltid minimerad i systemfältet** kan
stängas av; `--tray` tvingar minimerad start.

## Automatiska release-uppdateringar

- Kontrollerar senaste stabila publicerade release i `Tokke2/FolderForge`
  vid första start och därefter var 12:e timme när appen körs.
- Senaste kontrolltid sparas, så omstarter inte orsakar extra kontroller.
  Efter nätverksfel görs nästa försök efter 12 timmar.
- Hämtar endast nyare numeriska releasetaggar, exempelvis `v5.1.0`.
  Prereleaser, utkast och grenen `main` används inte.
- Uppdateringen hämtas i bakgrunden och installeras automatiskt **vid nästa
  appstart**. Ingen pågående session avbryts.
- Releasens källkodsarkiv måste innehålla `folder.pyw`, `settings.py`,
  `historik.py`, `logg.py`, `updater.py` och `cache_cleanup.py`. Pythonfiler syntaxkontrolleras
  innan installation. Ikoner i `Icon/` följer också med.
- Användardata i `data/` och Git-filer skrivs inte över. Tidigare appfiler
  sparas i `data/update-backup/`; skrivfel under installation återställs.
- Saknad release, nätverksfel eller ogiltigt paket loggas utan att stoppa appen.

Releaser måste publiceras separat på GitHub för att nå installerade appar.
Denna ändring publicerar ingen release och ändrar inte `main`.

## Tester

```sh
python -m unittest discover -s tests -v
python -m py_compile folder.pyw updater.py settings.py historik.py logg.py
```

GUI och Windows-tray behöver dessutom verifieras på Windows.

## Mallar, tillfälliga strukturer och historik

- Öppna **Projektmallar**, välj **Ny mall**, skriv eller klistra in strukturen
  och välj **Spara som mall**. Ange rotmappen på första raden och indentera
  undermapparna, till exempel:

  ```text
  projektnamn/
      Bilder/
      Dokument/
          Rapport.txt
  ```

- Välj en sparad mall och klicka **Ange som standard**. Valet sparas mellan
  starter och används av **Skapa Standardprojekt**. Första standarden är
  Skaderapport, som motsvarar de tidigare fasta standardmapparna.
- För ett enstaka projekt: använd **Klistra in Struktur**, eller redigera
  strukturtexten under Projektmallar och välj **Skapa (tillfälligt)**.
  Det ändrar varken sparade mallar eller standardvalet.
- Varje skapat projekt sparas i **Historik** och kan öppnas därifrån.
  Historiken har inte längre en gräns på 20 projekt. Saknade mappar behålls
  i listan och markeras som saknade; poster kan tas bort manuellt.
- En befintlig projektmapp återanvänds inte för skapande och slås inte ihop
  med en ny struktur. Namn med enbart olika stora/små bokstäver räknas som
  samma namn i samma rotmapp. Du erbjuds att öppna den befintliga mappen.

## Uppdateringsstatus

Öppna **Hjälp → Uppdateringsstatus** för att se installerad version,
senaste kontrollförsök (lokal tid), senast hittade release och eventuella fel.
Om en uppdatering är hämtad visas att den väntar på nästa appstart.
Fönstret uppdateras automatiskt varannan sekund utan extra nätverksanrop.
Ingen kontroll startas bara för att statusfönstret öppnas; kontrollintervallet
är fortfarande 12 timmar. En saknad publicerad release visas separat från
nätverksfel.


## Smart cacherensning

Öppna **Hjälp → Rensa cache (smartfilter)** för att se reglerna, senaste
rensningen, antal borttagna filer och frigjorda byte. **Rensa nu med
smartfilter** kör samma försiktiga filter manuellt efter bekräftelse.

Automatisk rensning körs vid första start och därefter högst en gång per
24 timmar medan appen körs (förfallotiden kontrolleras varje timme).
Senaste körning sparas mellan starter. Om appen är stängd sker förfallen
rensning vid nästa start, inte genom någon separat Windows-tjänst.

Smartfiltret tar endast bort:

- Filer som är minst 24 timmar gamla i appens `data/cache/` och `data/tmp/`.
- Roterade loggarkiv `folderforge.log.1`–`.3` som är minst 14 dagar gamla.

Den aktiva loggen, färska filer, länkar/junctions, okända filer utanför
cacheområdena, mallar, historik, inställningar och uppdateringsfiler lämnas
kvar. Konfigurerad projektrot och projekt i historiken skyddas även om de
placerats inne i ett cacheområde. Cachefiler ska därför bara lagras i de
avsatta cachemapparna; detta rensar inte Windows eller andra programs cache.
Låsta filer hoppas över och rapporteras utan att stoppa appen.

## Release v0.0.1

Se [RELEASE_NOTES.md](RELEASE_NOTES.md) för installation och ändringslista.
Dialogerna har nu scrollbart innehåll och separat knappfot, med flerradiga
knappar där utrymmet kräver det. Appikonen har en egen mapp-/hammardesign.
Ikonerna kan återskapas med `python tools/build_icon.py` (kräver Pillow).

## Stäng och minimera

Både huvudfönstrets **X** och **minimeringsknapp** gömmer appen i systemfältet,
inte som en minimerad knapp i aktivitetsfältet. Appen fortsätter köra i
bakgrunden. Öppna via tray-ikonen eller snabbtangenten; välj **Avsluta** i
tray-menyn för att avsluta programmet. Separata dialogers X stänger bara dialogen.


## Publicering av kodändringar

Färdiga kodändringar testas och pushas till arbetsgrenen
`arena/319fd9b1-folderforge`, med ny versionsbeteckning och stabil GitHub-release.
Appen uppdaterar från publicerade releaser, inte direkt från en branch.
`main` ändras eller mergas inte som del av publiceringen.
Senaste version: **v0.0.2**. Se RELEASE_NOTES.md för ändringslista.

## År i projektnamnet

Dialogen **Nytt Standardprojekt** har en valfri årsväljare. Den visar
innevarande år och de tre föregående åren (2026: 2026, 2025, 2024, 2023).
Året placeras efter vald lokal, exempelvis `ABC123 SIDORUTA LAXÅ 2025`.
Välj `—` för inget år. Listan räknas om för varje ny dialog och kontrolleras
även varje minut om dialogen hålls öppen över ett årsskifte.


## Ändringar inom samma release

Uppdateraren jämför både versionsnummer och det commit-ID som den stabila
releasens tagg pekar på. Om `v0.0.2` publiceras om med ny kod hämtas även
den ändringen, utan ett nytt versionsnummer. Arkivet hämtas från det exakta
commit-ID:t, så att en flyttad tagg under hämtningen inte ger fel kod.
Installerat, senaste och väntande bygg-ID visas i Uppdateringsstatus.

Efter installation sparas bygg-ID:t; samma kod hämtas inte upprepade gånger.
Installationer utan känt bygg-ID jämför först appfilerna med releasearkivet.
Enbart redigering av releasebeskrivningen räknas inte som ny programkod.
Ändringar direkt på en branch hämtas inte förrän releasens tagg uppdaterats.
Kontrollintervallet är fortfarande 12 timmar, med installation vid nästa start.

**Engångsövergång:** exemplar som fortfarande kör den äldre, enbart
versionsbaserade uppdateraren måste uppdateras manuellt till denna kod en gång.
Ändringar i GitHub kan inte i sig ändra logiken i en redan installerad gammal
uppdaterare. Därefter fungerar uppdateringar inom samma version automatiskt.
