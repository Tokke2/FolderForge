<p align="center">
  <img src="Icon/folderforge-logo.png" alt="FolderForge" width="440">
</p>
<p align="center"><b>Skapa projektmappar med rätt struktur – på några sekunder.</b></p>
<p align="center">Windows · macOS · Linux &nbsp; | &nbsp; v0.0.2</p>

## Vad gör appen?

- **Skapa projekt** från din standardmall eller en tillfällig egen struktur.
- **Spara flera mallar** och välj vilken som ska vara standard.
- **Hitta tillbaka** till skapade mappar via historiken.
- **Exportera ett mappträd** som text, även med drag och släpp.
- Anpassa **ljust/mörkt tema, textstorlek och hög kontrast**.

<p align="center">
  <img src="Icon/projektmapp_icon_256.png" alt="FolderForge-appikon" width="84">
</p>

<p align="center">
  <img src="Icon/nav-create-light.png" alt="Skapa" width="32"> &nbsp;
  <img src="Icon/nav-history-light.png" alt="Historik" width="32"> &nbsp;
  <img src="Icon/nav-templates-light.png" alt="Mallar" width="32"> &nbsp;
  <img src="Icon/nav-export-light.png" alt="Exportera" width="32"> &nbsp;
  <img src="Icon/nav-settings-light.png" alt="Inställningar" width="32"> &nbsp;
  <img src="Icon/nav-keyboard-light.png" alt="Snabbtangent" width="32">
</p>

## Kom igång

1. [Hämta senaste v0.0.2](https://github.com/Tokke2/FolderForge/releases/tag/v0.0.2) → **Source code (zip)**.
2. Packa upp **hela** mappen till en plats där du har skrivbehörighet.
3. Python **3.11+ med Tkinter** och paketen i `requirements.txt` måste redan finnas.
4. Starta enligt ditt operativsystem nedan.

**FolderForge installerar eller uppgraderar aldrig Python eller paket automatiskt.**
På Windows provas systemets aktuella Python först (även 3.15). Om dess lokala
GUI-prov misslyckas väljs i första hand en redan installerad **3.14**, därefter
andra installerade Python 3.11+. Provet kontrollerar nödvändiga GUI-importer
samt en dold Tk-start, inte paketversioner eller tillgängliga uppgraderingar.
Vald och överhoppad tolk med orsak skrivs i `logs/folderforge.log`.
Om ingen fungerar avbryts starten utan konsolreserv eller installation.
Detta är ett Python-källkodspaket, inte en fristående signerad app.
På en arbetsdator: låt IT hantera installation och behörigheter.

### Windows

Dubbelklicka **`Starta-FolderForge.vbs`**.
Appen använder systemets `pythonw.exe`, startar dold i systemfältet och
öppnar inget konsolfönster som reserv.

### macOS och Linux

Starta med den befintliga Python som har appens paket:

```sh
python3 Starta-FolderForge.py
```

Startaren kopplar loss appen från terminalen och skriver fel till `logs/`.
Vill du starta med en ikon utan att öppna Terminal? Skapa en genväg:

```sh
python3 tools/create_shortcut.py
```

Verktyget skapar **FolderForge.app** på macOS eller **FolderForge.desktop** på
Linux bredvid appfilerna. Det installerar inget och aktiverar inte autostart.
Linux kan kräva att du markerar genvägen som betrodd. Behåll appmappen på
samma plats; skapa om genvägen om du flyttar den.

## Öppna och avsluta

**Appen startar alltid dold/minimerad.** Öppna den via FolderForge-ikonen i
systemfältet/menyraden. En extra start skapar inte en ny instans och visar
inte automatiskt huvudfönstret.

- **Öppna FolderForge** i ikonens meny visar fönstret.
- **Öppna appens mapp** öppnar installationsmappen utan att visa appfönstret.
- **Stäng/minimera** döljer fönstret igen.
- **Avsluta** i ikonens meny eller **Arkiv → Avsluta FolderForge** stänger appen helt.
- Linux X11 utan stöd för ikonmenyer: klicka på ikonen för att öppna, avsluta via Arkiv.
- Global snabbtangent är ett tillval och beror på skrivbordets behörigheter.

## Operativsystem och begränsningar

| | Windows | macOS | Linux |
|---|---|---|---|
| Projekt, mallar, historik och export | Ja | Ja | Ja |
| Startikon | Native startprogram | Genererad `.app` | Genererad `.desktop` |
| Dold start | Systemfält | Menyrad | Systemfält krävs |
| Inbyggd autostart-inställning | Ja | Använd OS inloggningsobjekt | Använd skrivbordets autostart |
| Global snabbtangent | Beror på policy | Kan kräva Hjälpmedel/Input Monitoring | X11; Wayland kan begränsa |

**Verifierat i CI:** Windows med Python 3.11/3.13/3.14, macOS med Python 3.13
samt Linux/X11 med Python 3.13, Xvfb och ett riktigt systemfält (stalonetray).
318 automatiserade tester och riktiga GUI-tester kontrollerar dold start,
dubbelstart, visa/dölj/avsluta samt fungerande och avsiktligt trasiga uppdateringar
med återställning och bevarade användardata.

[Windows-resultat](https://github.com/Tokke2/FolderForge/actions/runs/42612238314) ·
[macOS- och Linux-resultat](https://github.com/Tokke2/FolderForge/actions/runs/42612237680)

Detta verifierar inte alla macOS-versioner, Linux-skrivbord eller IT-policyer.

Linux behöver en grafisk session och ett fungerande systemfält. GNOME/Wayland
kan kräva en systemfältstillägg och/eller XWayland; ren Wayland stöds inte
fullständigt. Headless/server utan skrivbord stöds inte.
En genererad macOS-app är osignerad; företagets policy kan blockera den.
Appen kringgår inte Gatekeeper eller företagets säkerhetspolicy.

## Uppdateringar och dina filer

**Sök uppdatering nu** finns i huvudfönstret och ikonens meny.
Appen kontrollerar stabila GitHub-releaser var tolfte timme, även om
versionsnumret är oförändrat.

Före filbytet sparas en backup. Den nya appen måste bekräfta fungerande start;
vid misslyckande erbjuds återställning. Ingen upptagen process tvångsavslutas.
**Projekt, inställningar och historik återställs inte eller raderas.**

Vid manuell uppdatering: stäng appen, ersätt appfilerna och **behåll `data/`**.

## Om starten säger `No module named 'customtkinter'`

Det saknade paketet finns inte i **den Python som startaren använder**.
En annan Python kan ha paketet utan att det hjälper den här starten.

1. Läs **Starttolk** och **Python=** i `logs/`. Där står den fullständiga sökvägen.
2. Vid importfel loggas ett manuellt kommando för just den tolken och appens
   `requirements.txt`. Kör det bara om din IT-policy tillåter det, annars be IT.
3. Starta sedan med `Starta-FolderForge.vbs` på Windows.

Det lokala GUI-provet väljer bara bland redan installerade tolkar. Ingen
nedladdning, paketinstallation eller uppgradering körs automatiskt.
Tkinter/Tk är en del av Python-installationen och ska inte installeras med pip.
Om appen inte kan öppnas kan dess uppdateringsknapp inte användas:
packa i så fall upp appfilerna från v0.0.2 manuellt och **behåll `data/`**.

## Felsökning

- Saknas appikonen? Kontrollera att hela `Icon/` följde med.
- Startar appen inte? Kontrollera befintlig Python/Tkinter och nödvändiga paket.
- Öppna **Hjälp → Fellista och felsökning**, eller läs `logs/folderforge-errors.log`.
- Inställningar, mallar och historik ligger i **`data/`**. Radera inte den mappen.
- Python kan fortfarande visas som processikon i Aktivitetshanteraren; appens
  egna ikoner ändrar inte systemets delade Python-programfil.

[Mer om funktioner, tangentbord och felsökning](docs/TEKNISK_GUIDE.md) ·
[Ändringar i v0.0.2](RELEASE_NOTES.md)

© 2026 **Rickard Längkvist**

### Fönster på flera skärmar
På Windows anpassas fönstren till en skärms arbetsyta i taget, inklusive utrymmet som aktivitetsfältet tar. Huvudfönstrets normala storlek och läge sparas automatiskt och justeras om en skärm kopplats bort. Appen startar fortfarande minimerad. På små fönster finns scrollning som reserv; text och knappar radbryts. Sparat läge kan nollställas genom att radera `data/window-placement.json` och dess eventuella `.bak`-/`.bak2`-kopior när appen är avslutad.

Placeringen sparas först när huvudfönstret är synligt i normalläge; minimerad start ändrar inte det sparade läget.
