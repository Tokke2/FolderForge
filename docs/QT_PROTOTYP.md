> **Aktuellt läge:** start utan flagga öppnar den funktionella Qt-testklienten med riktiga data och gemensamt instanslås. Använd `--preview` för det tidigare skrivskyddade testläget. Se etapp 2 längre ned; första avsnittet beskriver endast `--preview`.

# Stegvis övergång till PySide6 – första, isolerade prototypen

**Tk är fortfarande standard och reserv. Ingen vanlig startfil är ändrad.**
Denna prototyp är en fristående gränssnittsförhandsvisning, inte en färdig Qt-app.
Huvudfönster och standardprojektdialog kan provas med fokus/Tab-ordning,
namnförhandsvisning, större OS-textskalning och olika skärmar.

## Prova manuellt

Använd en separat virtuell miljö och Python 3.11+ som stöds av PySide6. Följ IT-policy.
Inget installeras av startfilen. Exempel från appmappen:

Windows:
```powershell
py -3.14 -m venv .venv-qt
.\.venv-qt\Scripts\python.exe -m pip install -r requirements-qt.txt
.\.venv-qt\Scripts\pythonw.exe Starta-FolderForge-Qt.py
```
Använd en installerad, stödd Python i stället för 3.14 om den saknas.
Vid felsökning: kör med `python.exe` i samma miljö så syns felmeddelanden.

macOS/Linux:
```sh
python3 -m venv .venv-qt
.venv-qt/bin/python -m pip install -r requirements-qt.txt
.venv-qt/bin/python Starta-FolderForge-Qt.py
```
Linux kan behöva Qt:s OS-bibliotek för skrivbordsmiljön. Den vanliga Tk-appens
requirements behöver inte installeras i Qt-miljön. Saknas PySide6 avbryts försöket
med instruktioner – inga paket installeras och Tk importeras aldrig i Qt-processen.

**Starten är dold i systemfältet/menyraden.** Välj *Öppna Qt-prototypen* där.
Stäng/minimera gömmer huvudfönstret. *Avsluta Qt-prototypen* avslutar på riktigt.
Utan tillgängligt systemfält avbryts starten, så inget osynligt program lämnas kvar.
Ingen OS-autostart eller genväg registreras. Vanliga startfilen öppnar fortfarande Tk.

## Säkerhetsgränser i första steget

- **Ingen mapp skapas. Ingen inmatning sparas.** Dialogen är tydligt märkt testläge.
- Inga produktionsinställningar, projekt, mallar, historik, loggar eller uppdateringstillstånd öppnas.
- Endast en Qt-prototyp per appmapp via ett separat lås i OS:ets temporärmapp.
- Den kan provas bredvid Tk enbart eftersom prototypen inte läser/skriver produktionsdata.
  Detta är **inte** ett gemensamt produktionslås; ett sådant krävs innan riktig lagring aktiveras.
- Ingen automatisk övergång mellan Qt och Tk efter en krasch; inga användaråtgärder upprepas.
- Namnförhandsvisningen är ett UI-exempel, inte appens fullständiga namn-/projektvalidering.
- Ingen donationshantering, tray-migrering av Tk eller uppdatering från Qt ännu.

## Nästa steg – inte genomfört eller automatiskt beställt

1. Flytta ut befintliga domänfunktioner till GUI-oberoende moduler med oförändrade regressionstester.
2. Införa gemensamt instanslås innan Qt får tillgång till riktiga data.
3. Koppla samma testade logik till Qt-dialogen, därefter mallar/historik/inställningar.
4. Verifiera fysiska skärmbyten, DPI, fokus, tillgänglighet, tray och uppdatering/återställning.
5. Först efter godkännande kan Qt bli standard; Tk-startfilen finns kvar som reserv.

## Licens

PySide6/Qt har LGPL-/GPL-/kommersiella licensalternativ. Detta ändrar inte
FolderForges egna licensvillkor. Före paketerad distribution behövs korrekt
licensgranskning, licenstexter/notiser och uppfyllda villkor för de Qt-moduler som
faktiskt distribueras. Inga Qt-binärer levereras i detta källkodspaket.

# Nästa etapp: fungerande Qt-klient med gemensamma data

**Den vanliga Tk-starten är fortfarande standard. Qt är valfri och ännu inte funktionslikvärdig.**

`Starta-FolderForge-Qt.py` startar nu den fungerande Qt-klienten. Lägg till
`--preview` för den ursprungliga, skrivskyddade gränssnittsförhandsvisningen.
Installationskommandona ovan är oförändrade. Qt-klienten startar dold i tray.

## Genomfört

- `app_core.py`: faktiskt utbruten, GUI-oberoende kod för inställningsschema,
  namn/regnr/år, mallar, strukturtolkning och säker trälexport. Tk och Qt använder samma kod.
- `instance_lock.py`: det befintliga, testade instanslåset är utbrutet utan ändrade
  låsnamn. **Riktig Qt och Tk kan inte köras samtidigt.** En extra start visar inte
  befintligt fönster. Låset tas före produktionsdata öppnas och släpps vid avslut/fel.
- `create_project_tree`: samma skapandefunktion i båda gränssnitten. Hela strukturen
  kontrolleras före skapande. Ingen hopslagning eller överskrivning av befintliga
  projekt, även vid skillnad enbart i stora/små bokstäver. Delvis skapad struktur
  vid disk-/behörighetsfel behålls för inspektion – appen raderar inte automatiskt.
- Qt kan skapa riktiga standardprojekt med vald mall eller tillfällig egen struktur,
  fordon/lokal/år och namnförhandsvisning. Explicit bekräftelse före skapande.
- Samma beständiga historik, samma mallfiler och inställningsformat som Tk.
  Okända inställningsnycklar bevaras när Qt sparar. Sparplats, regnr-läge och
  öppna-efter-skapande kan ändras. Inbyggda/egna mallar kan laddas och egna sparas,
  samt väljas som standard. Historikmappar kan öppnas.
- Struktur kan exporteras till text med gemensam begränsad trälexportmotor.
- Donationsdialog med lokal Swish-QR och fasta PayPal-/Ko-fi-knappar.
- Bakgrundskontroll av releaser, manuell kontroll och uppdateringsstatus.
  **Installation/återställning går ännu via den vanliga Tk-startfilen efter att Qt avslutats.**

## Kvar innan Qt får bli standard

- Ångra/radering med samtliga befintliga säkerhetsflöden; komplett mall-/historikadministration.
- Global snabbtangent, OS-autostart och befintliga specialflöden för drag & drop.
- Full tillgänglighetsparitet, sparad skärmplacering och fysiska skärm-/DPI-byten.
  Grundläggande tema (ljust/mörkt/system), 100/110/125/150 % text och hög kontrast finns i Qt-inställningarna.
- Detaljerad fellista, arkivhantering, diagnostikexport och cacheadministration i Qt.
- Egen komplett Qt-startbekräftelse, säker uppskjuten omstart och återställning för uppdateringar.
- Fullständig GUI-paritet och praktiska tester av riktig tray på alla stödda skrivbord.

Detta är därför **inte en färdig ersättning för Tk ännu**. Använd Tk för funktionerna
ovan tills de har migrerats och verifierats. Ingen automatisk konvertering av data
eller automatisk övergång mellan ramverken har lagts till.
