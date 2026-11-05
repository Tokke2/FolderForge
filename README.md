# FolderForge

© 2026 Rickard Längkvist

## Python och gemensamma tillägg — veckovis, måndag kl. 08.00

Appen använder **befintlig gemensam Python och dess paket**, inte en egen
venv. Inga nya privata Python-miljöer skapas. Tidigare appmiljöer används
inte av den nya primära instansen och lämnas orörda på disk för manuell
hantering. En extra start kan tillfälligt använda en fortfarande körande
äldre instans miljö enbart för hälsokontroll/återställning under övergången.

**Python- och paketuppdateringar kontrolleras en gång i veckan, måndagar
kl. 08.00 enligt datorns lokala klocka.** Det registreras som en uppgift för
inloggad användare i Windows Schemaläggaren. Den startar utan konsolfönster
via VBS och öppnar inte själva appen. Missad körning startar när det är
möjligt efter att datorn/inloggningen är tillgänglig igen. Första planerade
kontrollen ligger efter att veckoschemat aktiverats; historiska veckor körs
inte vid första installationen.

Vanliga starter söker **inte** efter nyare Python-/paketversioner. De väljer
lokalt befintlig Python och kontrollerar att startnödvändiga paket finns.
Om veckokontrollen är förfallen kan den tas igen vid nästa appstart. Ett
veckoförsök sparas före nätverksanrop och upprepas inte vid varje start,
heller inte om nätverket saknas. Ett misslyckat försök loggas och nästa
ordinarie uppdateringsförsök sker följande vecka.

Om appen eller andra Python-processer körs skjuts ändringarna upp, utan
att några processer avslutas. En uppskjuten körning räknas inte som veckans
uppdateringsförsök. Schemaläggaren kan försöka igen var 15:e minut upp till
tolv gånger vid upptagen Python; därefter finns återtagning vid nästa start.
Inga nya nätverks-/paketuppdateringar körs under dessa rena väntelägen.
Om schemaregistrering nekas av IT-policy används förfallen kontroll vid
nästa vanliga start i stället. Datorn väcks inte av uppgiften.

Vid veckounderhåll används winget **upgrade för samma befintliga Python-serie**,
inte installation av en parallell serie. Uppgraderingsfel ger aldrig någon
nyinstallation som reserv. Bara när Python faktiskt saknas får en stabil
version installeras. En trasig, för gammal eller otillgänglig installation
kräver reparation/uttryckligt byte, inte automatiskt en andra Python.

Appens paket från `settings.REQUIRED_PACKAGES` och pip uppdateras i den
**gemensamma** installationen med nödvändiga kompatibla beroenden.
**Det kan påverka andra Python-program och det finns ingen isolerad
kandidatmiljö eller automatisk miljöåterställning.** Fel och beroendekonflikter
loggas. Övriga program avinstalleras eller stoppas aldrig. Konflikter mellan
andra gemensamma paket rapporteras men blockerar inte appen om dess egna
importer fortfarande fungerar.

Saknad Python och saknade startnödvändiga paket kan installeras även vid
första start — det är inte en uppdateringskontroll. När endast saknade
paket installeras låses versionerna av redan installerade paket med
constraints för att inte uppgradera dem utanför veckoschemat. Vid konflikt
avbryts installationen med felbesked i stället för att ändra befintliga
versioner. Andra Python-processer måste då vara stängda.

Starta **`Starta-FolderForge.vbs`** om Python saknas. Eget `FolderForge.exe`,
autostart och direkt `folder.pyw`-start använder samma startflöde.
Interna omstarter och självtest startar ingen ny underhållsrunda; en gammal
privat miljö migreras dock till gemensam Python vid nästa riktiga omstart.
State/schemainformation sparas i `data/python-runtime.json`, alla loggar i
`logs/`. Winget, internet och tillåtna Windows-skript behövs för installation
eller uppgradering; inga rättigheter eller företagspolicyer kringgås.

Detta veckoschema gäller **Python och tillägg**. FolderForges egen kontroll
av GitHub-releaser behåller sitt separata 12-timmarsschema. Windows-flödet
behöver verifieras på Windows; tester och syntaxkontroll ersätter inte det.

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
  `historik.py`, `logg.py`, `updater.py`, `cache_cleanup.py`,
  `Starta-FolderForge.ps1` och `Starta-FolderForge.vbs`. Pythonfiler syntaxkontrolleras
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
- Loggar och loggarkiv undantas från automatisk cacherensning.

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
Automatisk omstart väntar tills öppna dialoger och pågående export är avslutade.

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

**Hjälp → Öppna fellogg** öppnar `logs/folderforge-errors.log` i
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

Felloggen är **beständig**: den storleksroteras inte och rensas inte vid
midnatt, omstart, uppdatering eller cacherensning. Även äldre roterade
felloggar (`.1`–`.5`) förs tillbaka till den aktiva felloggen, så att olösta
fel inte försvinner på grund av ålder eller filstorlek.

När **samtliga** listade varningar/fel faktiskt är åtgärdade kan du välja
**Hjälp → Markera alla loggade fel som åtgärdade…** och bekräfta. Detta
reparerar inte orsaken automatiskt. Posterna flyttas till
`logs/resolved-errors/ÅÅÅÅ-MM-DD/` i stället för att raderas. Om nya
fel tillkommer medan bekräftelsen visas avbryts åtgärden och du får granska
dem först. Återkommande fel loggas som olösta på nytt.

Du kan fortfarande ange felloggens sökväg i en felrapport. Filen skapas
även när inga fel finns.


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


## Fordonsslag när projektmapp skapas

Under projektnamnet finns snabbknapparna **Husbil**, **Lastbil** och **Maskin**.
Utan något val läggs inget fordonsslag till i mappnamnet. Ett fordonsslag åt gången kan väljas; klicka på samma knapp igen
för att avmarkera. Valet är frivilligt och gäller bara projektet som skapas.
Det syns direkt i förhandsvisningen och placeras före lokal och år, exempelvis
`ABC123 VINDRUTA HUSBIL LAXÅ 2026`. En annan vald fordonstyp ersätter eventuella
handskrivna fordonsslag i namnfältet, så att mappnamnet inte får dubbla typer.


## Automatisk omstart efter uppdatering

När ett nytt paket är hämtat och SHA-256-verifierat startar appen om
**automatiskt**, utan att du behöver avsluta den manuellt. Kontroll görs varje
sekund när appen körs. Inställningarna sparas, bakgrundstjänster stoppas,
Tk-loopen avslutas och instanslåset släpps innan processen startas om med
`--tray`. Uppdateringen installeras före GUI-start och de nya modulerna läses
in i en ren process. Appen kommer tillbaka minimerad utan konsolfönster.

Om en projekt-/mall-/exportdialog är öppen, en native dialog är aktiv eller
export pågår väntar omstarten tills arbetet är avslutat. Uppdateringsstatus
hindrar däremot inte omstart. Ingen omstart sker bara för att en kontroll
hittar oförändrad kod. Ändrade hämtade filer får inte utlösa omstart.

Om installationen misslyckas används den återställda befintliga versionen.
Automatisk omstart blockeras då för att undvika en omstartsloop. Felet syns
i uppdateringsstatus/felloggen; välj **Sök uppdatering nu** för ett nytt
installationsförsök. Windows-omstarten behöver verifieras på Windows.


## Datumarkiv för den vanliga loggen

`logs/folderforge.log` behåller dagens poster. Alla poster med äldre
lokalt kalenderdatum flyttas till `logs/archive/ÅÅÅÅ-MM-DD/`, även om
flera datum blandats i en äldre logg. För den 4 november 2026 arkiveras
alltså den 3 november och tidigare datum. Traceback och fortsättningsrader
följer med respektive post. Framtidsdaterade poster raderas inte vid felställd
klocka.

Arkivering sker vid start, vid första loggrad efter datumbyte och inom en
minut efter midnatt även när appen inte skriver nya loggrader. Äldre
storleksroterade vanliga loggar tas också om hand. Filerna i datumarkivet
har innehållsbaserade namn så att ett avbrutet försök kan upprepas utan
att skapa dubbla arkiv. Atomisk skrivning och ett gemensamt fillås skyddar
mot avbrutna skrivningar och samtidiga appstarter. Datumarkiv och arkiv
för åtgärdade fel rensas inte av den smarta cacherensningen.

**Felloggen är separat och påverkas inte av datumarkiveringen.**


## Loggmapp direkt under appmappen

All app-loggning samlas i **`<appmapp>/logs/`**, exempelvis
`D:\Program\FolderForge\logs\`. Vanlig logg, beständig fellogg,
datumarkiv och arkiv för åtgärdade fel finns under denna mapp.
Även det native Windows-startprogrammets fel använder samma mapp.

Vid nästa start flyttas tidigare `data/logs/` automatiskt hit. Inga befintliga
målarkiv skrivs över; olika innehåll sparas separat, och befintliga aktiva
loggar slås samman. Original tas bort först efter en lyckad atomisk kopiering.
Om flytten misslyckas behålls originalet och appen gör ett nytt försök vid
nästa start. En tom äldre mapp med låsfil kan finnas kvar, men nya loggar
skrivs endast i `logs/`. Loggmappen ingår inte i Git eller appuppdateringar.


## Fellista, tillfällig detaljloggning och felsökningspaket

**Hjälp → Fellista och felsökning** visar aktiva varningar/fel grupperade
på modul, nivå, meddelande och eventuell exception-detalj. Varje grupp visar
antal förekomster samt första/senaste tid. Välj en post för senaste traceback.
Listan uppdateras automatiskt varannan sekund; **Uppdatera listan** kan också användas manuellt.

**Markera valt fel åtgärdat** kräver bekräftelse och flyttar endast den valda
gruppens förekomster till `logs/resolved-errors/`. Övriga fel ligger kvar.
Om felloggen ändrats efter att du läste listan måste du granska den igen.
Återkommer felet hamnar det automatiskt i den aktiva listan på nytt.
Detta är en manuell kvittens, inte en automatisk reparation. Alternativet
för att bekräfta samtliga fel finns också kvar i Hjälp-menyn.

Pillows DEBUG/INFO-brus döljs i normalt loggläge, men WARNING och högre
loggas alltid. **Hjälp → Detaljerad loggning i 15 minuter** gör att även
biblioteksdetaljer sparas under en begränsad tid. Läget stängs automatiskt
av efter 15 minuter eller omstart; **Återgå till normal loggning** stänger
av det tidigare. Appens egen diagnostik behålls även i normalt läge.

**Hjälp → Exportera felsökningspaket…** skapar en ZIP efter integritetsvarning
och val av målfil. Den innehåller aktuell vanlig logg/fellogg, upp till tre
senaste datumarkiv och `diagnostic.json` med app-/Python-/OS-version och
uppdateringsstatus. Varje logg begränsas till de sista 2 MiB; begränsningar
redovisas i JSON-filen. Inställningsfiler, projekt, historik och miljövariabler
exporteras inte. **Loggtexten kan ändå innehålla personliga sökvägar och
felmeddelanden: granska paketet före delning.** Ingen automatisk uppladdning.

## Snabbkommandots registrering

Bokstavstangenter skickas utan vinkelparenteser till pynput, exempelvis
`<ctrl>+<alt>+m`, vilket rättar felet `Ogiltig hotkey-kombination: <m>`.
Ctrl-kodade bokstäver från inspelning normaliseras och kombinationen
valideras både lokalt och med pynputs parser innan den sparas. Misslyckad
sparning lämnar tidigare kombination kvar. Inställningarna visar om
snabbkommandot registrerats eller stoppats, med möjlighet att spela in ett
nytt via befintlig knapp. Ogiltig sparad konfiguration använder standard
med synlig förklaring. Gamla varningar ligger kvar tills du kvitterar dem.


## Hälsokontroll av bakgrundsappen och säker återstart

En extra start skickar en unik hälsoförfrågan till den befintliga instansen.
Svaret hanteras i Tk-huvudtrådens poll-loop, även när appen är minimerad.
En gammal heartbeat eller enbart ett levande PID räknas inte som ett svar.
En svarande instans lämnas orörd och den extra starten avslutas dold, utan
att visa eller fokusera huvudfönstret.

Om svar saknas (normalt efter åtta sekunder) kan Windows erbjuda återstart.
Det bevisar inte att appen har hängt sig: långvarigt arbete eller en äldre
version utan hälsokontroll kan ge samma resultat. Innan ett avslut erbjuds
verifieras PID, Python-programfil, exakt skriptsökväg och processens starttid
med Windows-processhandtag och CIM via konsolfri PowerShell. Annan
installation/annat Python-program, okänd identitet eller saknade rättigheter
innebär att inget avslut görs. Inga nya Python-paket krävs.

**Tvångsavslut sker bara efter uttrycklig bekräftelse, med Nej som standard.**
Osparad inmatning kan gå förlorad och pågående arbete avbrytas. Om appen
börjar svara efter bekräftelsen lämnas den ändå orörd. Samma verifierade
processhandtag används för avslut; processnamn eller PID ensamt används
aldrig för att avsluta program. Ersättaren startar minimerad först när den
gamla processen avslutats och det riktiga instanslåset åter tagits. Om en
annan start hunnit ta låset skapas ingen extra instans. Windows-flödet
behöver verifieras på en Windows-dator.

## Filtrering och automatisk uppdatering av fellistan

I **Hjälp → Fellista och felsökning** finns sökning i meddelande och
traceback samt filter för modul och **Varningar / Fel / Kritiska**.
Fel-filtret inkluderar ERROR och CRITICAL. Vald post markeras tydligt.
Listan uppdateras varannan sekund, behåller markerad feltyp och rulläge när
posten fortfarande är synlig, och skriver inte om oförändrad detaljtext.
Om posten filtreras bort eller inte längre är aktiv rensas markeringen.

Automatisk uppdatering pausas under bekräftelse av åtgärdat fel. Den
snapshot som du faktiskt granskade används för arkiveringen; nya fel under
bekräftelsen kan alltså inte kvitteras av misstag. Pollningen stoppas när
fönstret stängs. Tillfälliga läsfel ger ett diskret besked och nytt försök,
inte upprepade dialogrutor.


Utveckling: efter ändringar i startskripten körs
`python tools/sync_runtime_bootstrap.py`. Det uppdaterar återställningskopian
i `updater.py`, så äldre sexfilersinstallationer också får de nya startfilerna.
Tester kontrollerar att skripten och den inbäddade kopian överensstämmer.
