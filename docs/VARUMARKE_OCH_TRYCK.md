# FolderForge – ikon, logotyp och tryckoriginal

## Levererade original

| Fil i `Icon/` | Användning |
|---|---|
| `folderforge-logo.svg` | Primär logotyp med mörk text, transparent bakgrund. För ljusa underlag och tryck. |
| `folderforge-logo-inverse.svg` | Vit/turkos text på transparent bakgrund, för mörka underlag. |
| `folderforge-logo-mono.svg` | Enfärgat svart original, med öppna negativa ytor i symbolen. |
| `folderforge-symbol.svg` | Fristående symbol, samma original som appikonerna bygger på. |
| `folderforge-logo.png` | Högupplöst skärmvariant på vit bakgrund, läsbar även i mörk GitHub-vy. |
| `folderforge-master.png` | 1024×1024 symbol med transparenta ytterhörn. |
| `folderforge-tray.png` | 64×64 mörk, kontrastrik symbol för systemfält/menyrad. |
| `projektmapp.ico` | Windows-ikon med 16, 24, 32, 48, 64, 128 och 256 px. |
| `folderforge.icns` | macOS-ikon med flera rasterstorlekar. |

SVG-filerna är **äkta vektorer**: geometriska former och konturer för bokstäverna. De innehåller inga inbäddade rasterbilder, externa länkar eller krav på installerade typsnitt. De är inte en automatiskt spårad PNG. Bokstäverna är konturer och därför inte redigerbara som vanlig text.

## Tryck

- Använd SVG-originalet, inte PNG, ICO eller ICNS. Skala proportionellt via dokumentets viewBox.
- Originalen använder sRGB: marinblå `#12223D`, klarblå `#2864F0`, turkos `#21D4BF` och orange `#FF8040`, med en ljusblå accent `#3D7BFF`. Färgerna är platta; inga metallic-, neon- eller folieeffekter förutsätts i tryck.
- Be tryckeriet konvertera färgerna enligt sin CMYK-/ICC-profil och göra ett provtryck. SVG:n är inte ett färdigseparerat CMYK-/PDF-X-original.
- Använd den enfärgade varianten för en färg, stämpel eller liknande. Invertering, skärlinjer, minsta linjebredd och material måste avtalas med leverantören.
- Behåll luft runt logotypen och kontrollera läsbarheten i den faktiska tryckstorleken. Ingen generell garanti ges för mycket små tryck, gravyr eller brodyr.
- Typsnittet vid byggandet är DejaVu Sans Bold. Konturerna är inkluderade i SVG:n; licensinformationen finns i `WORDMARK_FONT_LICENSE.txt`. Ingen typsnittsfil följer med.

## Återskapa tillgångarna

Detta är ett utvecklarverktyg, inte något som körs vid appstart:

```sh
python -m pip install pillow fonttools resvg-py
python tools/build_icon.py --font /sökväg/till/DejaVuSans-Bold.ttf
```

Verktyget hämtar inga typsnitt och installerar ingenting självt. Samma SVG-master används till PNG, Windows ICO och macOS ICNS. Andra typsnitt kan ha annan licens och ge ett annat ordmärke.

## Systemfält och flera operativsystem

- **Windows:** huvudfönstrets X och minimera skickar till systemfältet. Öppna och Avsluta finns i ikonens meny.
- **macOS:** ikonen ligger i menyraden. Tk/Cocoa hanteras i huvudtråden. Appens huvudfönster kan döljas till menyradsikonen; Arkiv → Avsluta är ett alternativ för verkligt avslut.
- **Linux:** ett kompatibelt systemfält behövs. X11 testas med en verklig tray-manager; CI:s Xvfb utan fönsterhanterare kan testa stängning till tray men inte ett riktigt OS-minimeringsklick. Wayland och skrivbord utan tray-stöd är inte universellt stödda.

Att stänga en separat dialog stänger fortfarande bara dialogen. Start förblir minimerad. En andra start öppnar inte ett extra appfönster. Vi ändrar inte systemets Python-installation eller den delade Python-processens ikon i Aktivitetshanterarens detaljvy.

## Färgstark profil
Den aktuella symbolen använder överlappande mappformer, en kraftig strukturmarkering och en orange gnista. Ordmärket delar Folder och Forge i marinblått/klarblått med orange understreck. Den enfärgade varianten behåller konturer och negativa ytor i stället för att bara göra alla fyllningar svarta. Tray-ikonen använder samma mörka botten för tydliga färgytor på både ljusa och mörka skrivbord.
