# Qt-layout jämförd med den tidigare Tk/ttk-appen

Qt behålls som standard. Den äldre appens sex huvudområden och arbetsflöden återförs:

| Tidigare arbetsflöde | Qt |
| --- | --- |
| Skapa: standardmall och egen struktur | Två separata kort på startsidan; egen struktur öppnar projektfönstret med strukturinmatningen fokuserad |
| Projektnamn, fordon, lokal, år, mall | Samma delade namngivning och validering; Skapa/Avbryt direkt efter förhandsvisningen |
| Historik | Namn, sökväg och tid, filtrering, öppna, export, ta bort post och rensa alla med bekräftelse; inga projektmappar raderas |
| Mallar | Välj/redigera, spara egen mall, sätt standard och ta bort egen mall |
| Exportera | Välj mapp eller släpp mapp, bakgrundsinläsning, kopiera och spara text |
| Inställningar | Sparplats, öppna efter skapande, registreringsnormalisering, tema, textstorlek, kontrast och OS-autostart |
| Snabbtangent | Egen sjätte flik, status, textinmatning, tangentbordsinspelning, standardkombination och explicit spara |
| Visa-menyn | Visa/dölj sidor med samma sparade synlighet, visa alla; minst en sida förblir tillgänglig |
| Hjälp | Fellista, diagnostikexport, normal/utförlig loggning, öppna fellogg, smart cacherensning, uppdatering, donationer och Om |
| Systemfält | Öppna, uppdateringskontroll, uppdateringsstatus och verkligt Avsluta |

## Säkerhet och skillnader

- Fortsatt dold start till systemfältet, även efter uppdatering. Ingen automatisk visning vid dubbelstart.
- Endast en GUI-händelseloop; Tk-reserven startas uttryckligen i separat process.
- Toppflikar som bryts i rader i stället för sidomeny. Qt använder egna native kontroller,
  inte en pixelidentisk kopia av Tk. Scroll finns som säkerhetsreserv vid låg skärmhöjd/stor text.
- Befintliga projekt-, historik-, mall- och uppdateringsformat behålls.
- Bekräftelser krävs för historikradering, cacherensning, autostart och ångra projekt.
- Fysiska dubbelskärmar/DPI, skärmläsare, OS-inloggning och IT-policy behöver även kontrolleras på användarens dator.

Automatiska tester verifierar den delade kärnan, sex sidor och ikoner, historikfilter,
borttagning utan projektradering, sidors synlighet, projektfokus, diagnostik,
donationsdialog och native dold start/uppdateringsbekräftelse på tre operativsystem.
Det är inte ett påstående om att varje OS-/hårdvarukombination har verifierats.
