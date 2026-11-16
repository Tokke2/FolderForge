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
3. Appen kräver **Python 3.11+ med Tkinter** och paketen i `requirements.txt`.
   Om Python saknas kan startfilen erbjuda installation enligt nedan. Extra apppaket installeras inte av startfilen.
4. Starta enligt ditt operativsystem nedan.

**Ingen tyst installation, ingen automatisk Python-uppgradering och inga paketinstallationer vid vanlig start.**
Finns någon hittad Python erbjuds aldrig installation – även om den är gammal,
inte kan köras eller saknar GUI-paket. Bara när Python saknas visas ett erbjudande,
med **Nej/Avbryt som standard**. Ett nej hämtar och installerar ingenting.
Ingen separat `Installera senaste Python.bat` ingår och inget veckounderhåll körs.
Okända specialinstallationer utanför PATH/registrering/standardplatser kan inte
upptäckas säkert: avbryt erbjudandet om IT redan har en sådan installation.
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

### macOS

Dubbelklicka **Starta-FolderForge.app** direkt i den uppackade mappen.
Den kräver inte Python för att kunna visa erbjudandet och öppnar inte Terminal.
Om Python saknas och du godkänner används befintlig Homebrew (`brew install python`,
utan automatisk Homebrew-uppdatering). Finns inte Homebrew öppnas python.org för
manuell installation. Starta igen efter manuell installation. Appen installerar
inte Homebrew eller Apples utvecklarverktyg. Apples utvecklarstub utan installerade
verktyg räknas inte som en fungerande Python-installation.

### Linux

Öppna **Starta-FolderForge.sh** som program om filhanteraren stöder det, eller kör:

```sh
sh Starta-FolderForge.sh
```

Om Python saknas krävs Zenity eller KDialog för ett uttryckligt ja. Utan grafisk
dialog görs ingen installation. Med ditt ja används systemets paketkälla via
`pkexec`: apt, dnf, zypper eller pacman, inklusive Tkinter. Behörighetsdialog kan
visas; utan pkexec/stödd paketkälla hänvisas du till IT. Startaren kör inga
fjärrskript och uppdaterar inte paketlistor. Paketkällans version kan vara äldre
än senaste python.org, men appen kräver minst 3.11. macOS/Homebrew och Windows/winget
väljer den senaste stabila version som deras respektive källa erbjuder.

### Windows om Python saknas

Efter ett uttryckligt ja söker startfilen dynamiskt efter senaste stabila Python
3 i winget och visar dess installationsprogram (användarinstallation). Preview,
alfa, beta och RC väljs bort. Samtycket omfattar wingets käll-/paketvillkor.
Saknas winget öppnas python.org för manuell installation, först efter ditt ja.
Installation kan blockeras av IT-policy. Ingen befintlig Python tas bort eller
uppgraderas av FolderForge.

### Genvägar och beroenden

På macOS/Linux kan `python3 tools/create_shortcut.py` skapa en ikonbaserad genväg
som använder samma startfil: **FolderForge.app** respektive **FolderForge.desktop**.
Linux kan kräva att genvägen markeras betrodd. Startaren öppnar inte en ny terminal;
startar du själv från en terminal stängs den inte av appen. Loggar finns i `logs/`.
Om installationen avbryts eller misslyckas kan ett nytt erbjudande visas vid nästa
start så länge Python fortfarande saknas. **När Python hittas erbjuds det inte igen.**

Efter en ny Python-installation måste IT/användaren fortfarande ordna appens
beroenden enligt `requirements.txt`; startfilen installerar inte dessa automatiskt.
På macOS kan Gatekeeper och på Linux skrivbordets filregler kräva godkännande.
Det här är inte en signerad, fristående app och startfilerna kringgår inte IT-policy.

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

Navigeringen ligger i namngivna flikar ovanför innehållet. Flikarna får fler rader när fönstret är smalt eller texten förstoras. Vilka flikar som visas väljs fortfarande via Visa-menyn eller Inställningar.

Förslagsbank: [100 nya förbättringsförslag](docs/100_FORBATTRINGSFORSLAG.md). Förslag införs bara efter uttryckligt val. Felsökningspaketet innehåller även skärmmått, tillgängliga Windows-arbetsytor, DPI och textskalning, utan fönstertitlar eller skärmbilder.

Layoutmatrisen provar verkliga Xvfb-upplösningar 1366×768 och 1920×1080 samt 150 % textstorlek. Windows provar även 150 % textstorlek på runnerns skärm; test av fysisk flerskärms-DPI är fortfarande separat.

## Ny ikon och trycklogotyp
Samma vektormaster används i appen, systemfältet, Windows ICO och macOS ICNS.
- **Tryckoriginalen ingår i samma release-ZIP som appen**, i `Icon/`: `folderforge-logo.svg`, `folderforge-logo-inverse.svg`, `folderforge-logo-mono.svg` och `folderforge-symbol.svg`. Inget separat grafikpaket behöver hämtas.
- [Tryckguide, färger och begränsningar](docs/VARUMARKE_OCH_TRYCK.md)

SVG-originalen har konturiserade bokstäver och inga rasterbilder eller externa typsnittsberoenden. Färgerna är sRGB; tryckeriet behöver göra eventuell CMYK-/ICC-konvertering.
Huvudfönstrets X och minimera går till systemfält/menyrad på stödda skrivbord. Välj **Avsluta** för att stänga appen. Linux kräver kompatibel tray; Wayland stöds inte generellt.

Den aktuella färgstarka profilen kombinerar klarblått, turkos och orange mot mörk marinblå botten. Ordmärket är tvåfärgat; tryckoriginal och appikoner kommer från samma vektormaster.

Den senaste profilen använder vektorbaserat färgdjup, högdagrar och en orange blixt. Tray-varianten är avsiktligt enklare för liten storlek. Hela leveransen beskrivs i [RELEASE_INNEHALL.md](RELEASE_INNEHALL.md).
