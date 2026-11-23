# 25 utvecklingsförslag för FolderForge

Förslagen är inte beställda implementationer. De utgår från arbetsflödet i FolderForge och tänkbara användarproblem – inte från genomförda användarintervjuer eller en verifierad konkurrentkartläggning. Ingen konkurrensunikhet eller efterfrågan är därmed fastställd. Prioriteringen är preliminär.

| # | Förslag | Nytta och möjlig differentiering | Validera före implementation |
|---|---|---|---|
| 1 | Förhandsgranska hela skapandet | Visa exakt vilka mappar som skapas, redan finns eller krockar innan något skrivs. | Minskar det fel vid riktiga projekt? |
| 2 | Säker ångra-funktion | Ångra en skapning, men ta aldrig bort mappar som fått innehåll eller förändrats sedan dess. | Testa konflikter, nätverksfel och återställning. |
| 3 | Torrkörning av masskapande | Läs CSV/Excel och visa radvisa fel och resultat före bekräftelse. | Vilka indataformat används faktiskt? |
| 4 | Villkorsstyrda profiler | Olika undermappar för Husbil, Lastbil och Maskin utan dubblerade profiler. | Kan reglerna förstås utan programmering? |
| 5 | Namnregler per profil | Validera registreringsnummer, ärendenummer och obligatoriska fält innan skapandet. | Samla verkliga regler och undantag. |
| 6 | Dubblettvarning över flera destinationer | Hitta tidigare ärenden på samma identifierare, inte bara exakt samma sökväg. | Definiera träffsäkerhet och tillåtna sökområden. |
| 7 | Offlinekö för nätverksmål | Spara ett uppdrag och erbjud ny bekräftelse när målet blir nåbart; inget tyst dubbelskapande. | Behövs detta där nätverksavbrott förekommer? |
| 8 | Förkontroll av destination | Kontrollera åtkomst, sökvägslängd och tillgängligt utrymme före skapandet. | Testa verkliga delningar och rättigheter. |
| 9 | Versionshanterade profiler | Visa profilversion, ändringshistorik och möjlighet att återgå. | Behöver team spårbarhet mellan profilversioner? |
| 10 | Jämför projekt mot profil | Visa saknade och extra mappar, utan att ändra befintligt innehåll. | Testa på äldre projekt med avsiktliga avvikelser. |
| 11 | Säker komplettering | Lägg till enbart godkända, saknade mappar i ett äldre projekt. | Kräver tydlig förhandsgranskning och konflikttest. |
| 12 | Dela profiler med granskning | Importera profilpaket med visad destination och ändringslista; inget körbart innehåll. | Vilka inställningar får en mottagare ärva? |
| 13 | Organisationsregler utan persondata | Gemensamma namnregler med personliga lokala inställningar separat. | Kontrollera IT-policy och ägarskap. |
| 14 | Projektspecifik checklista | Koppla arbetsmoment till projektet och visa återstående steg. | Vill användare ha detta i FolderForge eller befintligt system? |
| 15 | Startdokument per profil | Kopiera godkända tomma blanketter tillsammans med mappstrukturen. | Kontrollera licenser och behov av versionsstyrning. |
| 16 | Saknade underlag | Uppmärksamma att exempelvis skadeanmälan eller bilder saknas, med tydliga kontroller användaren styr. | Definiera filtyper och undvik falska varningar. |
| 17 | Lokal QR-etikett för projekt | Skriv ut en etikett som öppnar rätt intern projektlänk; ingen extern QR-tjänst. | Vilka enheter kan öppna länken och med vilka rättigheter? |
| 18 | Sökbar projekttidslinje | Samla skapande, kompletteringar och profilversion utan att logga dokumentinnehåll. | Bestäm lagringstid och åtkomst. |
| 19 | Sekretessgranskad supportexport | Förhandsgranska och maskera namn, identifierare och sökvägar innan diagnostik delas. | Testa att inget känsligt följer med av misstag. |
| 20 | Lokal säkerhetskopia av inställningar | Återställ profiler och inställningar efter datorbyte, utan att kopiera projektdokument. | Prova återställning mellan riktiga datorer. |
| 21 | Tillgänglighetsassistent | Guidad inställning av textstorlek, kontrast och tangentbord med direkt förhandsvisning. | Testa med användare och hjälpmedel, inte enbart automatiska tester. |
| 22 | Skärmvisa arbetslägen | Kom ihåg en säker layout för dockad laptop respektive ensam skärm. | Prova blandad DPI, urkoppling och fjärrskrivbord. |
| 23 | Uppdateringsprov före omstart | Kontrollera nedladdade filer och startbarhet isolerat innan den aktiva installationen ersätts. | Testa trasiga paket, avbrott och rollback. |
| 24 | Överlämningspaket med innehållslista | Exportera bara valda projektfiler och skapa en tydlig förteckning över vad som ingår. | Validera sekretess, filstorlekar och mottagarkrav. |
| 25 | Lokal återkoppling om arbetsflödet | Frivillig lokal översikt över återkommande fel och tidskrävande steg, utan telemetri. | Kan översikten ge nytta utan att mäta enskilda anställda? |

## Föreslagen första omgång

1. **Förhandsgranskning (#1)** – tydlig nytta och begränsad påverkan på befintliga arbetsflöden.
2. **Förkontroll av destination (#8)** – förebygger fel innan projekt skapas.
3. **Jämför projekt mot profil (#10)** – hjälper med äldre projekt utan att ändra något.
4. **Säker ångra-funktion (#2)** – stor potentiell nytta, men kräver noggranna säkerhetsvillkor.
5. **Sekretessgranskad supportexport (#19)** – kompletterar befintlig diagnostikexport, ersätter den inte.

## Så prövas efterfrågan och konkurrensläget

- Intervjua användare i aktuella roller med riktiga, avidentifierade arbetsuppgifter. Be om exempel på inträffade problem, inte bara om en funktion låter bra.
- Jämför daterade produktversioner av relevanta konkurrenter och alternativ, inklusive inbyggda operativsystemfunktioner och skript. Dokumentera källa och eventuella betalnivåer.
- Skilj mellan ”saknas”, ”finns delvis”, ”finns med annan benämning” och ”okänt”. Dokumentation som inte nämner en funktion bevisar inte att den saknas.
- Prova en enkel prototyp och mät färre fel eller snabbare arbete innan implementation prioriteras.
