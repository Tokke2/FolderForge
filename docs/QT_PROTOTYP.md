# Qt-standardgränssnitt

Qt är nu standard. Det tidigare prototypnamnet på denna fil behålls för gamla länkar.
Se README för aktuella start- och felsökningsinstruktioner. Tk används endast när
användaren uttryckligen väljer reservstarten.

## Verifiering

- Enhetstester omfattar delad kärna, instanslås, uppdatering/återställning,
  standarddispatch, diagnostikens databegränsning och verkliga snabbtangentsfunktioner.
- Qt-CI provar riktiga widgets, projekt/mappar/historik, fokus, textstorlek,
  dialoggeometri och diagnostik på Windows/macOS/Linux.
- Separata skrivbordstester startar vanliga startfilen, kontrollerar dold Qt-start
  utan Tk-import, extra start, återställning, projektnamnsfokus, minimera/stäng till
  systemfältet, Avsluta och en övervakad uppdatering med verklig Qt-startbekräftelse.
- Tk-reserven har separata regressionssviter för start och uppdateringsåterställning.

Kvar för kontroll på användarens egen dator: två fysiska bildskärmar med olika DPI,
IT-policy, verklig macOS/Wayland-behörighet för global snabbtangent, skärmläsare,
och autostart efter faktisk OS-inloggning. CI är inte en garanti för dessa miljöer.
Appen ändrar inte ikonen för systemets delade Python-programfil i Aktivitetshanteraren.

## Arkitektur och säkerhet

`folder.pyw` behåller sin process-/uppdateringsidentitet men skickar standardstarten
till `gui_entry.py` innan någon Tk-import. `workspace.py`, `app_core.py`,
`instance_lock.py` och `os_startup.py` delas mellan gränssnitten. Ett OS-lås tas
innan lagring öppnas. Ingen automatisk Tk-reserv, paketinstallation, radering eller
upprepning av projektåtgärder sker vid fel.

Qt:s nativa fel hamnar i samma fellogg. Startdiagnostiken skriver bara specificerade
system-/paketuppgifter och appfilernas hash, inte miljövariabler eller projektinnehåll.
Loggexport kan innehålla sökvägar från de vanliga loggarna och ska granskas före delning.
