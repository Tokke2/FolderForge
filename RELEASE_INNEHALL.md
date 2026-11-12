# Ett releasepaket – app, ikoner och tryckoriginal

Hämta **Source code (zip)** under Assets på FolderForge **v0.0.2**:
https://github.com/Tokke2/FolderForge/releases/tag/v0.0.2

**Inget separat grafikpaket behövs.** Samma ZIP innehåller både appen och tryckoriginalen. Packa upp hela paketet; projekt och inställningar i en befintlig `data/` ska bevaras vid manuell uppdatering.

## Tryckoriginal – redan med i ZIP

- `Icon/folderforge-logo.svg` – färglogotyp för ljust underlag, med vektortoningar.
- `Icon/folderforge-logo-inverse.svg` – vit/turkos text för mörkt underlag.
- `Icon/folderforge-logo-mono.svg` – enfärgad svart, utan toningar.
- `Icon/folderforge-symbol.svg` – fristående vektorsymbol.
- `docs/VARUMARKE_OCH_TRYCK.md` – tryckguide, färger och begränsningar.
- `docs/WORDMARK_FONT_LICENSE.txt` – licens för ordmärkets typsnittskonturer; informationen finns även i SVG-metadata.

Alla SVG-original består av vektorformer och konturiserade bokstäver, inte inbäddade PNG-bilder. De kräver inget installerat typsnitt. Originalen är sRGB; tryckeriet behöver göra eventuell CMYK-/ICC-konvertering. Inga metallic-, folie- eller neonmaterial garanteras av färgoriginalets skärmutseende.

## Appikoner – i samma ZIP

`Icon/` innehåller också PNG-logotyp, 1024px-symbol, en förenklad 64px-tray-ikon, Windows ICO och macOS ICNS. Appens automatiska uppdaterare tar med SVG- och rastertillgångarna i `Icon/`. Dokumentationen följer med den fullständiga release-ZIP:en.

Detta är fortfarande ett källkodspaket med befintlig system-Python, inte en fristående installerare. Starta `Starta-FolderForge.vbs` på Windows eller följ README för macOS/Linux. Inga nya Python-/paketinstallationer sker vid appstart.
