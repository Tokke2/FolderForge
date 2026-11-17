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
