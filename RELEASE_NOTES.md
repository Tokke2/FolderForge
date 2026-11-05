# FolderForge v0.0.2

## Ändringar
- Python-/paketkontroll en gång i veckan, måndagar kl. 08.00 lokalt, via konsolfri Windows-uppgift. Missad körning tas igen när möjligt; normal start gör ingen versions-/uppdateringssökning. Befintlig Python uppgraderas inom samma serie; installation bara om Python saknas.
- Gemensam Python och gemensamma paket används, utan egen venv eller kandidatmiljö. Veckoförsök sparas för att undvika omkontroll vid varje start; ändringar skjuts upp när Python används. Saknade startpaket installeras separat med låsta befintliga versioner. Gemensamma uppdateringar kan påverka andra program.
- Konsolfria Starta-FolderForge.vbs/ps1 för start även utan Python samt veckounderhåll utan att öppna appen. Branded exe/autostart och direkt pyw-start delar startflödet. Självtest/interna omstarter undantas.
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
upp till en skrivbar plats. Starta Starta-FolderForge.vbs på Windows. Saknas Python installeras en stabil version via winget; befintlig Python återanvänds. Appen kräver Python 3.11+ med Tkinter.
Detta är ett källkodspaket, inte en fristående Windows-exe.

## Verifiering
240 automatiserade tester godkända och Python-syntax kontrollerad.
Windows-tray och hela uppdateringsförloppet behöver fortfarande verifieras
på Windows. Publicerad från arbetsgrenen; main är orörd.

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
