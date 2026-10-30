# FolderForge v0.0.2

## Ändringar
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
v0.0.2 via releasens commit-ID. Hämtad kod installeras vid nästa appstart.
Äldre v0.0.2-exemplar med enbart versionsjämförelse behöver installera den
här uppdateraren manuellt en gång; därefter fungerar ändringar inom samma
version automatiskt.
Status visas under Hjälp → Uppdateringsstatus.

För manuell installation: ladda ned Source code (zip) under Assets och packa
upp till en skrivbar plats. Python 3.11+ med Tkinter krävs; starta folder.pyw.
Detta är ett källkodspaket, inte en fristående Windows-exe.

## Verifiering
71 automatiserade tester godkända och Python-syntax kontrollerad.
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
