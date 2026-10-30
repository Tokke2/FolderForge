# FolderForge

## Start i systemfältet

Appen startar alltid minimerad i systemfältet utan att huvudfönstret
blinkar till. Öppna via tray-ikonen eller snabbtangenten. Det finns inte
längre någon inställning för att starta med synligt huvudfönster. En andra
start visar inte automatiskt en redan körande app.

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
knappar där utrymmet kräver det. Appikonen har en egen mapp-/strukturdesign.
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

I projektdialogen ligger **Skapa** och **Avbryt** direkt under det
förhandsvisade slutnamnet, i samma scrollbara innehåll utan tomrum till botten.


## Manuell uppdateringskontroll och ändringslista

**Sök uppdatering nu** finns i Hjälp-menyn, i fönstret Uppdateringsstatus och
i tray-menyn. Den kör en kontroll direkt i bakgrunden, oavsett när den
schemalagda kontrollen kördes senast. Samtidiga kontroller spärras.
Nästa automatiska kontroll förfaller 12 timmar efter den manuella kontrollen.
Tray-valet öppnar appens uppdateringsstatus. Samma statusfönster återanvänds.

Releasens ändringslista visas i Uppdateringsstatus när en uppdatering har
hämtats. Texten hör till den väntande hämtningen och ligger kvar tills den
installerats. Saknas releasebeskrivning visas ett tydligt besked om detta.
Ingen pågående session avbryts och ingen automatisk omstart görs.

Årsväljaren är redigerbar: välj ett förslag eller skriv valfritt fyrsiffrigt
år, exempelvis `2010`. Tomt fält eller `—` betyder inget år. Eget årtal
behålls när förslagen uppdateras vid årsskifte. Ogiltigt år stoppas före skapande.

En synlig **Sök uppdatering nu**-knapp finns även direkt under huvudfönstrets
rubrik och är tillgänglig oavsett vald flik.


## Samma ikon i Windows och autostart

Appen använder nu en gemensam gul mapp med turkos struktur i rubrik,
fönster, dialoger, systemfält och startgenvägar. Ikonen återappliceras efter
CustomTkinter:s fördröjda standardikon, även på inmatningsdialoger.

När autostart aktiveras i Windows byggs ett litet grafiskt startprogram,
`data/launcher/FolderForge.exe`, med FolderForge-ikonen inbäddad. Register,
Start-mapp och eventuell Schemaläggare använder denna exe med `--tray`.
En `FolderForge.lnk` med samma ikon skapas också bredvid appfilerna.
Sökvägar med mellanslag hanteras som en hel sökväg.

Startprogrammet byggs lokalt med Windows .NET Frameworks `csc.exe`; ingen
kompilator laddas ned. Python och `pythonw.exe` behövs fortfarande bakom
kulisserna. Startprogrammet är **inte ett fristående Python-fritt bygge**.
Saknas kompilator, ikon eller pythonw visas fel när autostart aktiveras;
appen registrerar ingen ny .pyw- eller .bat-reserv med generisk ikon.
Vid automatisk migrering av redan aktiverad autostart loggas eventuella fel
utan att den befintliga fungerande autostarten raderas.

Launcher-filen återanvänds och byggs om vid ändrad ikon eller Python-sökväg.
Varken rensning av cache eller releaseuppdateringar raderar denna fil.
Använd den brandade `FolderForge.lnk` istället för att fästa `.pyw`-filen i
aktivitetsfältet. En gammal redan fäst Python-genväg måste lossas och ersättas
manuellt; appen ändrar inte Windows globala filassociation för `.pyw`.
Windows-körning och den lokala kompileringen måste verifieras på Windows.


### Kontroll av både commit och filer

Uppdateringskontrollen jämför releasens commit-ID **och SHA-256 för installerade
appfiler och ikoner**. Samma versionsnummer stoppar inte uppdateringen.
Saknade eller lokalt ändrade appfiler hämtas på nytt även när commit-ID:t
är oförändrat. Detta ersätter alltså egna kodändringar med releasekoden.
Användardata, mallar, historik och inställningar ingår inte i filjämförelsen.

Filmanifestet sparas efter installation. Hämtade filer verifieras också mot
manifestet före installation. Oförändrad commit med matchande filer ger ingen
ny arkivhämtning. Äldre tillstånd utan filmanifest jämförs mot releasearkivet
en gång. Automatisk kontroll sker var 12:e timme och manuell kontroll kan
startas direkt; installation sker fortfarande vid nästa appstart.


## Obligatorisk konsolfri start

Windows-genvägen och den brandade `FolderForge.exe` startar alltid dolt med
`--tray`, utan konsolfönster. Även gamla `start_minimized: false` korrigeras
till `true`. Uppdateringsomstarten följer samma regel.

Om appen råkar startas via `python.exe` kopplar den loss sin konsolanslutning
och startar om via `pythonw.exe`/`pyw.exe`. Saknas en fönsterfri tolk eller
misslyckas omstarten avbryts starten i stället för att fortsätta i konsolläge.
Använd `FolderForge.lnk` eller `FolderForge.exe`: en konsol som Windows redan
har skapat för ett manuellt `python.exe`-anrop kan kort synas innan appkoden
hinner köras. Appen gömmer eller stänger inte användarens terminal.
Självtest behåller stdout för diagnostik, men normal start är dold.


## Samlad fellogg för snabb felsökning

**Hjälp → Öppna fellogg** öppnar `data/logs/folderforge-errors.log` i
Anteckningar på Windows (utan konsolfönster). Den samlar WARNING, ERROR och
CRITICAL från alla appmoduler via den gemensamma rotloggaren: GUI,
historik, uppdaterare, autostart och cacherensning. Tid, modul/radnummer,
trådnamn och traceback när sådant finns följer med. Vanliga INFO/DEBUG
behålls endast i den fullständiga `folderforge.log`.

Ofångade huvudtråds-, bakgrundstråds- och Tkinter-callbackfel fångas.
Det native Windows-startprogrammet skriver även startfel direkt till samma
fellogg om Python ännu inte hunnit starta. Första gången felloggen skapas
importeras gamla varningar/fel inklusive flerradiga spår från befintliga
`folderforge.log` och dess tre roterade arkiv. Importen görs inte om vid
vanliga omstarter. Det är appens egna loggar, inte Windows eller andra
programs loggar, som samlas.

Felloggen roteras vid 512 KiB med fem arkiv (`.1`–`.5`); appens smarta
cacherensning lämnar dem orörda. Loggar kan innehålla filnamn och sökvägar;
granska innehållet innan du delar det vid felsökning. Öppna via menyn eller
ange felloggens sökväg i en felrapport. Filen skapas även när inga fel finns.


## Förfinad layout och tydligare uppdateringsflöde

Gränssnittet har gemensamma neutrala ytor för ljust/mörkt tema, tydligare
textkontrast, kompakt rubrik och separata kort för standardmall respektive
egen struktur. Tom resultatrad och inaktiv Ångra-knapp tar inte längre plats.
Den aktuella standardmallen visas i skapavyn.

Uppdateringsfönstret visar kontroll, commit-upplösning, filjämförelse,
hämtning och verifiering. En förloppsindikator visar hämtade KiB och procent
när servern anger total storlek. Ändringslistan har en egen läsbar textyta;
knappar och fellogg ligger i den fasta knappfoten. Manuella kontrollknappar
inaktiveras medan en kontroll redan pågår.

Hämtningen strömmas med storleksgräns, upp till tre försök vid tillfälliga
nätverks-/serverfel och kontroll av ofullständiga svar. Permanenta fel som
404 återförsöks inte. GitHubs begränsning av anrop förklaras i statusvyn.
Tillstånd skrivs atomiskt med fsync. Ett tidigare verifierat hämtat paket
behålls tills dess ersättare har förberetts och registrerats; avbruten
förberedelse kan återställas. En avbruten kontroll behöver inte vänta tolv
timmar före nästa försök. Normalt automatiskt intervall är fortsatt tolv
timmar och installation sker vid nästa appstart.

Filhashar och commit-ID kontrolleras fortfarande även inom samma
versionsnummer. Visuell Windows-kontroll krävs utöver de headless testerna.
