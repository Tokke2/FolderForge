# FolderForge v0.0.2

## Ändringar
- Windows väljer en fungerande installerad Python: aktuell PATH-tolk först, 3.14 som första reserv och därefter andra installerade Python 3.11+. Ett kort lokalt GUI-prov hoppar över exempelvis 3.15 utan customtkinter. Upptäckt via PATH, Python-launchern och Windows Python-register. Inga nedladdningar, installationer eller uppgraderingar; ingen konsolreserv. Val och avvisningsorsaker loggas.
- Native startprogram går även vid uppdateringsåterställning via samma tolkval, så en gammal inbyggd Python-sökväg inte kringgår reserven.
- Rättat konstruktionsrace i tillgänglighetskoden: Map-händelser skjuts upp med timer och halvbyggda textrutor färgsätts inte via sina föräldrar innan båda rullningslisterna finns. Regressionstest provocerar felet under riktig CTkTextbox-konstruktion.
- Startloggen visar exakt Python-tolk, version och miljö. Normala importfel ger ett manuellt installationskommando för samma tolk; ingenting installeras eller uppgraderas automatiskt. Saknat Tkinter förväxlas inte med ett pip-paket.
- Windows-testmatrisen utökad med Python 3.14, utöver 3.11 och 3.13.
- Högerklick på tray-ikonen → Öppna appens mapp öppnar installationsmappen i operativsystemets filhanterare utan att återställa huvudfönstret.
- Tydligare tray-ikon: mörk marinblå bakgrund, kraftig guldkontur och större turkos struktur. Anpassad för liten storlek och ljusa/mörka aktivitetsfält; appens logotyp är oförändrad.
- Omgjord dialog för nytt standardprojekt: breda etiketter utan smal vertikal radbrytning, kompakt formulär, lokal och år på samma rad samt alltid synligt slutnamn med Skapa/Avbryt direkt under. Formuläret kan rullas utan att åtgärderna försvinner.
- Multi-OS: portabel dold start med befintlig Python, macOS menyradsintegration på huvudtråden, Linux X11-tray och lås för säkrare uppdateringsåterställning. macOS öppnar filer/mappar med Finder. Wayland och företagsbehörigheter har uttryckliga begränsningar.
- Generera lokala `.app`-/`.desktop`-genvägar med egen ikon, utan installation eller automatisk aktivering av autostart. Nativ Windows-start behålls. macOS/Linux använder operativsystemets egna inloggningsobjekt.
- Kort svensk README med logotyp, ikonöversikt, OS-guide, tydliga förutsättningar och felsökning. Detaljer flyttade till docs/TEKNISK_GUIDE.md.
- Matchande ljusa/mörka navigations- och sektionsikoner i hela appen, enhetlig marinblå/turkos profil samt macOS ICNS/Dock-ikon. Universell Arkiv → Avsluta-meny för skrivbord utan traymenyer.
- Startbekräftad appuppdatering: full backup före filbytet, bevarad fönsterlös övervakare och kontroll av process/starttoken, SHA-256 samt levande GUI/tray. Återställning erbjuds vid misslyckad start; vid timeout behålls backup utan att någon process tvångsavslutas. Projekt, inställningar och historik lämnas orörda. Gäller uppdateringar som installeras av denna uppdaterare.
- Windows-CI för Python 3.11/3.13 med riktig dold GUI/tray, native/VBS/PowerShell-start, dubbelstart, visa/dölj/avsluta och avsiktligt trasig uppdatering med återställning. Synliga konsoler och oavsiktligt visade Tk-fönster övervakas; ingen universell konsolfrihetsgaranti påstås.
- Matchande FolderForge-logotyp och förnyad ikon, korrekta bildproportioner i rubriken. Windows-specifika testfel och blandade CRLF/LF-rader i felgrupperingen rättade; logginitiering serialiserad mellan processer.
- Renare gemensam ikon: guldfärgad mapp med turkos struktur utan bakgrundsplatta, transparent bakgrund och sju ICO-storlekar. Samma motiv i app, dialoger, systemfält, genvägar och startprogram. Begränsningen för Python-processikonen i Aktivitetshanteraren kvarstår.
- Alltid minimerad start. Även extra starter lämnar befintligt fönster oförändrat och öppnar ingen ny instans. Öppna uttryckligen via systemfält/snabbtangent. Windows-låsfel stoppar ny start; säker hälsokontroll behålls.
- Tangentbordsnavigering med Tab/Skift+Tab i visuell ordning, synlig fokusmarkering, Enter/mellanslag för åtgärder och Alt+ned för vallistor. Fokus hålls i modala dialoger och rullas fram; Ctrl+Page Up/Down byter synlig sida och Skift+F10 öppnar sidomenyns snabbmeny.
- Tillgänglighet i Inställningar: 100/110/125/150 % text- och gränssnittsstorlek samt reversibel hög kontrast, direkt tillämpning och sparade val. Radbrytning/växande knappar, rullbar sidomeny och läsbara namn på infällda sidoknappar. Windows egna dialoger följer systeminställningarna.
- Python-/paketkontrollen och veckounderhållet borttagna. Systemets befintliga Python används utan nyinstallation, pip eller uppgradering; fungerande installerad tolk väljs lokalt. Saknade paket installeras inte vid start.
- Den felande Python check-rutan och runtime-state-skrivningen används inte längre. Gamla veckouppgiften för aktuell appmapp tas bort när tillåtet; kvarvarande underhållsanrop är verkningslösa och öppnar ingen app.
- Start sker konsolfritt med befintlig pythonw.exe och alltid minimerat. Systemmiljön måste redan ha Python 3.11+ och nödvändiga paket. Biblioteks-/startfel loggas i logs/. Appens egna releasekontroller är oförändrade.
- Maskin tillagd bredvid Husbil och Lastbil i projektdialogen, med samma valfria enkelval och direkt förhandsvisning av mappnamnet.
- Copyright Rickard Längkvist tydliggjord i Om FolderForge och README; befintlig sidfot behålls.
- Hälsokontroll via färskt svar från Tk-loopen vid extra start. Windows kan efter strikt processidentifiering och uttrycklig varning/bekräftelse återstarta en instans som inte svarar; andra Python-program lämnas orörda. Ny instans måste ta det riktiga instanslåset och startar minimerad.
- Sökning och nivå-/modulfilter i fellistan, tydlig markering och automatisk uppdatering varannan sekund med bevarat val/rulläge. Uppdatering pausas under åtgärdsbekräftelse och stoppas när fönstret stängs.
- Fellista i Hjälp: grupperade fel med antal, första/senaste förekomst och traceback; markera ett enskilt fel åtgärdat med skydd mot nytillkomna fel. Återkommande fel visas på nytt.
- Mindre Pillow-brus, tillfällig detaljloggning i 15 minuter och lokal ZIP-export av utvalda loggar/diagnostik efter integritetsvarning. Inga inställnings- eller projektfiler exporteras.
- Rättad pynput-formatering bakom <m>-varningen. Backendvalidering före sparning, bevarad tidigare kombination vid skrivfel, Ctrl-bokstavsnormalisering och synlig status för snabbkommandot.
- All loggning ligger nu i logs/ direkt under appmappen, även native startfel. Befintlig data/logs-historik flyttas säkert vid start, utan att skriva över befintliga arkiv eller tappa olösta fel. Loggar undantas helt från cacherensning.
- Datumarkiv för vanliga loggar från tidigare dagar, inklusive äldre blandade/roterade filer. Arkivering vid start och över midnatt, även utan nya loggrader.
- Separat beständig fellogg utan automatisk rensning eller storleksrotation. Alla loggade fel kan efter uttrycklig bekräftelse markeras åtgärdade via Hjälp och sparas då i permanent arkiv; nya fel under bekräftelsen stoppar arkiveringen.
- Automatisk minimerad omstart direkt efter verifierad uppdatering. Öppna dialoger/export får avslutas först; installationsfel spärrar omstartsloopar och kan prövas igen via Sök uppdatering nu.
- Snabbknappar för Husbil, Lastbil och Maskin (Personbil borttagen) i projektdialogen. Ett frivilligt val åt gången; visas i mappnamnet före lokal och år.
- Förfinad layout: neutrala ljusa/mörka ytor, kompakt rubrik, tydliga projektkort och färre tomma statusytor. Läsbar text och primärknappar med kontrastkontroll.
- Ny uppdateringsvy med arbetssteg, förloppsindikator, hämtade KiB/procent när storleken är känd, separat ändringslista och snabbåtkomst till felloggen.
- Strömmad hämtning med begränsade återförsök vid tillfälliga fel, tydligare GitHub-fel, atomisk tillståndsskrivning och återställning av tidigare verifierat uppdateringspaket vid avbruten förberedelse.
- Samlad beständig fellogg för varningar, fel och kraschspår från appmoduler, GUI-callbacks och startprogram; engångsimport av gamla appfel. Hjälp → Öppna fellogg ger snabb åtkomst.
- Alltid dold start i systemfältet, även med gammalt start_minimized=false. Alternativet för synlig start är borttaget. En andra start visar inte huvudfönstret.
- Konsolfri Windows-start är obligatorisk: koppla loss appens konsol och avbryt om fönsterfri omstart inte kan göras. Native launcher tvingar --tray.
- Uppdateraren kontrollerar både release-commit och SHA-256 för appfiler/ikoner. Samma versionsnummer tillåts; även saknade eller ändrade filer vid oförändrad commit återställs från releasen. Hämtade filer verifieras före installation.
- Ny gemensam gul/turkos mappstrukturikon i fönster, dialoger, systemfält, rubrik och Windows-genvägar.
- Autostart använder lokalt byggd FolderForge.exe med egen inbäddad ikon, inte .pyw-filassociationen. Python/pythonw och Windows .NET Framework-kompilator krävs fortfarande.
- Skydd mot att CustomTkinter ersätter ikonen med sin standardikon. Korrekt genvägscitering för sökvägar med mellanslag, ingen generisk .bat-reserv.
- Tydlig Sök uppdatering nu-knapp direkt under huvudfönstrets rubrik, synlig oavsett vald flik.
- År kan både väljas och skrivas manuellt. Egna fyrsiffriga årtal behålls när förslagslistan uppdateras; ogiltiga år stoppas före skapande.
- Sök uppdatering nu i appens Hjälp-meny, uppdateringsstatus och tray-meny; kontrollen sker i bakgrunden utan att invänta 12-timmarsintervallet.
- Ändringslista för hämtad uppdatering visas före nästa appstart. Samtidiga kontroller spärras.
- Skapa och Avbryt ligger direkt under det förhandsvisade mappnamnet, utan tomrummet till fönstrets nederkant.
- VINDRUTA finns nu som klickbar skadetyp vid skapande av standardprojekt.
- Uppdateraren upptäcker ny kod inom samma release via commit-ID, även utan högre versionsnummer. Bygg-ID visas i Uppdateringsstatus.
- Valfri årsväljare i projektdialogen: innevarande år och tre år bakåt, automatiskt vid årsskifte. Året läggs efter lokalen.
- Både X (stäng) och minimeringsknappen gömmer huvudfönstret i systemfältet.
- Appen fortsätter köra i bakgrunden; välj Avsluta i tray-menyn för att avsluta.
- Händelser från barnwidgetar och redan dolda/återställda fönster ignoreras.
- Separata dialogers X stänger fortfarande endast respektive dialog.

## Uppdatering och installation
Installerad v0.0.1 hämtar v0.0.2 vid nästa schemalagda kontroll (var 12:e
timme). Den nya uppdateraren hittar därefter även ändringar inom samma
v0.0.2 via releasens commit-ID. Hämtad kod installeras genom automatisk minimerad omstart.
Äldre v0.0.2-exemplar med enbart versionsjämförelse behöver installera den
här uppdateraren manuellt en gång; därefter fungerar ändringar inom samma
version automatiskt.
Status visas under Hjälp → Uppdateringsstatus.

För manuell installation: ladda ned Source code (zip) under Assets och packa
upp till en skrivbar plats. Starta Starta-FolderForge.vbs på Windows. Befintlig system-Python och nödvändiga paket måste redan finnas; ingenting installeras automatiskt. Appen kräver Python 3.11+ med Tkinter.
Detta är ett källkodspaket, inte en fristående Windows-exe.

## Verifiering
318 automatiserade tester godkända lokalt och Python-syntax kontrollerad. Tangentbord, stor text och hög kontrast behöver också provas visuellt på Windows.
Windows-CI godkänd för Python 3.11, 3.13 och 3.14; macOS/Cocoa och Linux/X11
med Python 3.13 också godkända. Linux-testet använder Xvfb och stalonetray.
Riktiga GUI-tester verifierar dold start, tray, dubbelstart, visa/dölj/avsluta,
fungerande uppdatering med Tk-bekräftelse och trasig uppdatering med återställning.
Användardata bevaras. Windows-testet övervakar synliga konsoler/Tk-fönster.
Wayland, alla OS-versioner och företagens IT-policyer är inte fullständigt verifierade.
Windows: https://github.com/Tokke2/FolderForge/actions/runs/42612238314
macOS/Linux: https://github.com/Tokke2/FolderForge/actions/runs/42612237680
Publicerad från arbetsgrenen; main är orörd.

---

# FolderForge v0.0.1

Första publicerade releasen i 0.0-serien.

## Nyheter
- Egen FolderForge-ikon med mapp, hammare och turkos accent; ICO i sju storlekar och PNG.
- Scrollbart dialoginnehåll med separat knappfot i projekt-, struktur-, mall-, export-, cache-, uppdaterings- och Om-dialogerna.
- Knappar i flerradslayout där det behövs, samt större och ändringsbar projektdialog.
- Sparade strukturmallar, valbar standardmall och tillfällig egen struktur.
- Automatiskt fokus och textmarkering i projektnamnsfältet.
- Beständig projekthistorik utan 20-postersgräns och spärr mot dubbletter.
- Stabil release-kontroll var 12:e timme och uppdateringsstatus i Hjälp-menyn.
- Smart cacherensning en gång per 24 timmar och manuell rensning via Hjälp-menyn.

## Installation
Ladda ned **Source code (zip)** under Assets på GitHub och packa upp hela
mappen till en skrivbar plats. Python 3.11 eller senare med Tkinter krävs. Starta `folder.pyw` på
Windows. Appen frågar om installation av saknade Pythonpaket.
Appen startar minimerad; öppna via ikonen i systemfältet.

Detta är ett **Python-källkodspaket, inte en fristående Windows-exe**.
GitHubs automatiska källkodsarkiv fungerar också för installation.

## Verifiering och begränsningar
30 automatiserade tester godkända, Python-syntax kontrollerad och
ikonformat verifierade. GUI-layoutens struktur testas utan skärm;
visuell kontroll, Windows-tray och uppdateringsinstallation måste fortfarande
verifieras i Windows. Releasen publiceras från arbetsgrenen, inte från main.

### Skärmanpassning och sparad placering
- Windows använder varje skärms arbetsyta (`rcWork`), så aktivitetsfält på valfri kant undantas. Full skärm används som reserv om arbetsytan inte kan läsas.
- Även Mallar, Exportera och Snabbtangent har rullbar reserv för små fönster. Gemensam radbrytning omfattar även korta etiketter; historiknamn får hela kortbredden och sökvägar förkortas inte längre. Sidfoten växer med innehållet i stället för att klippa det vid fast höjd.
- Huvudfönstrets normala storlek och placering sparas lokalt i data/window-placement.json. Dolda/maximerade fönster skriver inte över normalstorleken. Sparad placering begränsas till ansluten skärms arbetsyta vid start och återställning från tray. Starten är fortfarande minimerad.
- 328 lokala tester godkända, inklusive ogiltig placering, frånkopplad skärm, DPI-omräkning och dolt/maximerat fönster. Visuell kontroll på användarens skärmar återstår.

### Flikar i ovankant
- Huvudnavigeringen är nu namngivna flikar ovanför innehållet i stället för vänsterställd sidomeny. Flikarna får flera rader vid liten bredd; inga automatiskt dolda namn eller sidomenyrullning. Användarens val av synliga flikar bevaras.
- 330 lokala tester godkända, inklusive radbrytning av alla sex flikar vid olika bredder.

### Gemensam anpassning av knapprader
- Knappgrupper får en gemensam breddstyrd layout: lika breda kolumner och fler rader när knapptexter eller textskalning kräver mer plats. Befintliga specialanpassade rutnät lämnas orörda.
- Historikens rubrik/åtgärder, inställningarnas sparplats och fellistans filter anpassas också. Snabbtangentens inspelningsknappar får använda tillgänglig bredd. Dialogers knappgrupper anpassas via samma tillgänglighetskontroll.
- 334 lokala tester godkända, inklusive smal/bred layout, textskalning, oförändrade rutnät och skydd mot upprepade layoutuppdateringar.

### Läsbara flikar, text och ikoner
- Toppflikarna har större 24px-ikoner, fet 14px-text, 44px grundhöjd, centrerat innehåll och tydlig kant/markerad vald flik. Textstorleksval och DPI-skalning tillämpas fortfarande.
- Tomma/dolda rutnätskolumner tas ur uniform-gruppen så att de inte reserverar utrymme. Samma korrigering gäller gemensamma knappgrupper och projektval. Synliga flikar delar hela radens tillgängliga bredd och får fler rader när det behövs.
- 335 lokala tester godkända, inklusive tre synliga och tre dolda flikar utan reserverade tomkolumner.

### Rättad faktisk storleksanpassning av kontroller
- CustomTkinter skickar ramens Configure-händelser via sin interna canvas. Layoutvakterna accepterar nu både ramen och dess canvas; tidigare kunde omplaceringen utebli trots att dialogens bredd ändrades. Detta gäller toppflikar, gemensamma knapprader, projektval och lokal/år.
- Skapa/Avbryt får stretchande kolumner redan när de skapas och en extra första layoutpassering. Det hindrar att tillgänglighetskoden mäter knapparna som smala remsor och radbryter varje bokstav.
- GUI-testerna kontrollerar nu verklig bredd/höjd och placering för Skapa/Avbryt samt bredden för lokal/år, inte bara knappområdets ram. 336 lokala tester godkända.

### Layoutmatris, höjd och skärmdiagnostik
- Riktiga Linux/X11-GUI-tester vid 1366×768 och 1920×1080, inklusive 150 % textstorlek vid 1366×768. Windows 3.13 provar också 150 % textstorlek; övriga Windows-versioner och macOS behåller 100 %. Detta ersätter inte test av olika fysiska skärmar/DPI.
- Windows/Linux får kompaktare sidfot och mindre yttre marginaler; macOS behåller tidigare huvudfönsterlayout efter Cocoa-regressionstest. Standardprojektdialogen får lägre initial höjd på alla plattformar. Innehållet får fortfarande öka dialoghöjden inom arbetsytan; scrollning finns kvar som reserv.
- Felsökningspaketet får skärmstorlek, tillgängliga Windows-arbetsytor/DPI, skalningsfaktorer samt fönsterrektanglar utan titlar, inmatad text eller skärmbilder. Integritetsbekräftelsen beskriver tillägget.
- Separat förslagsbank med exakt 100 ej automatiskt godkända förbättringsförslag. 338 lokala tester godkända.

### Ny grafisk profil och tray-verifiering
- Ny sammanhängande marinblå/guld/turkos symbol och konturiserat ordmärke. Matchande app-, tray-, Windows ICO- och macOS ICNS-filer byggs från samma SVG-master. PNG-logotypen har vit läsbar bakgrund även på mörka GitHub-sidor.
- Äkta SVG-original för tryck: primär, inverterad och enfärgad logotyp samt fristående symbol. Inga rasterbilder eller externa typsnittsberoenden; typsnittslicens följer i metadata och separat dokument. sRGB-original, inte färdigseparerad CMYK.
- Uppdateraren tar även med SVG-filer i Icon/ med samma sökvägs- och hashkontroll som övriga tillgångar.
- GUI-testerna aktiverar huvudfönstrets verkliga WM_DELETE_WINDOW-handler för stäng-till-tray. Windows/macOS testar också OS-minimering och återställning. Linux/Xvfb testar stängning med riktig tray-manager; riktig OS-minimering kräver fönsterhanterare och täcks där av enhetstestet för iconic-hanteringen.
- 342 lokala tester godkända, inklusive vektororiginal, format/storlekar, SVG-manifest och minimeringsroutning.

### Färgstarkare ikon och logotyp
- Ny vald färgriktning: klarblått, turkos och orange med marinblå botten. Överlappande mappformer, kraftig strukturmarkering och orange gnista ger en tydligare och mer uttrycksfull symbol.
- Tvåfärgat ordmärke Folder/Forge med orange understreck. Samma konturiserade bokstäver i primär, inverterad och enfärgad SVG; PNG, ICO, ICNS och tray byggs från vektormastern.
- Tryckguiden beskriver aktuell sRGB-palett och begränsningar; inga inbäddade rasterbilder eller externa typsnittsberoenden. Appens beteende och minimerade start ändras inte.
