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
Ladda ned `FolderForge-0.0.1.zip` och packa upp hela mappen till en skrivbar
plats. Python 3.11 eller senare med Tkinter krävs. Starta `folder.pyw` på
Windows. Appen frågar om installation av saknade Pythonpaket.
Appen startar minimerad; öppna via ikonen i systemfältet.

Detta är ett **Python-källkodspaket, inte en fristående Windows-exe**.
GitHubs automatiska källkodsarkiv fungerar också för installation.

## Verifiering och begränsningar
30 automatiserade tester godkända, Python-syntax kontrollerad och
ikonformat verifierade. GUI-layoutens struktur testas utan skärm;
visuell kontroll, Windows-tray och uppdateringsinstallation måste fortfarande
verifieras i Windows. Releasen publiceras från arbetsgrenen, inte från main.
