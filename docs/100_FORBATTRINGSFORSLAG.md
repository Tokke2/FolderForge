# 100 nya förbättringsförslag för FolderForge

Detta är en förslagslista, inte beställning eller genomförda funktioner. De separat valda arbetena med layouttester, höjdanvändning och skärmdiagnostik ingår inte i de 100 förslagen nedan. Inga nya installationer, externa tjänster eller ändringar av main förutsätts. Säkerhets- och IT-policy behöver bedömas innan funktioner som påverkar filer eller operativsystem införs.

## Projekt och namn
1. Förhandsvisa normaliserat namn med tydlig markering av exakt vad som ändras.
2. Förklara varje namnändring, exempelvis borttaget otillåtet tecken, före skapande.
3. Föreslå närliggande befintliga projekt när ett namn skrivs in, utan att välja automatiskt.
4. Visa en explicit konfliktvy med befintlig mappstruktur om målmappen redan finns.
5. Erbjud en redigerbar kontrollista över mapparna innan ett större projekt skapas.
6. Tillåt förhandsvisning av flera projektnamn i en batch utan att skapa dem direkt.
7. Validera hela batchen och visa samtliga problem före något filarbete.
8. Visa ungefärlig längsta fullständiga sökväg innan projektet skapas.
9. Varna om ett namn bara skiljer sig i versaler från ett befintligt namn.
10. Erbjud en engångsnotering till ett projekt, separat från själva mappnamnet.

## Mallar
11. Visa en jämförelse mellan två mallars mappträd.
12. Visa vilka mappar som tillkommer eller försvinner när en mall redigeras.
13. Spara lokala revisionsnummer för mallar med möjlighet att jämföra revisioner.
14. Förhandsgranska en återställning av en tidigare mallrevision.
15. Erbjud en kontrollerad mallimport som visar innehållet före sparning.
16. Exportera en mall med formatversion och kontrollsumma för säker återimport.
17. Markera mallar med egna färgetiketter, utan att ändra projektnamn.
18. Sök efter en viss undermapp i alla sparade mallar.
19. Visa vilka projekt i historiken som skapades med en viss mallrevision.
20. Erbjud ett separat malltest som bara validerar trädet, utan att skapa filer.

## Historik
21. Fäst utvalda projekt överst i historiken.
22. Filtrera historiken på fordonsslag, mall och år.
23. Visa historiken grupperad per vecka eller månad.
24. Lägg till frivilliga lokala projektetiketter som går att söka på.
25. Visa en specifik förklaring när en historikmapp inte längre kan nås.
26. Erbjud en förhandsgranskad omlänkning när ett projekt har flyttats.
27. Exportera ett filtrerat historikurval som CSV efter val av kolumner.
28. Visa en sessionsöversikt över dagens skapade projekt.
29. Tillåt flerval för öppning av projekt med bekräftelse vid många fönster.
30. Erbjud en papperskorg för borttagna historikposter, utan att röra projektmapparna.

## Filsäkerhet
31. Testa skrivbehörighet i vald sparplats med en egen tillfällig provfil och säker städning.
32. Identifiera frånkopplad nätverksplats innan skapandet börjar.
33. Visa ett separat besked för behörighetsfel, låst fil och frånkopplad enhet.
34. Visa en kvittens över exakt vilka mappar ett skapande lyckades skapa.
35. Spara en lokal operationsjournal för att kunna förklara ett delvis misslyckat skapande.
36. Låt användaren återuppta en avbruten operation efter ny kontroll av målet.
37. Avvisa mappträd som lämnar vald rot och visa vilken rad som orsakar problemet.
38. Varna för symboliska länkar eller junctions som kan leda utanför projektroten.
39. Upptäck namn som är olämpliga för synkning mellan Windows och macOS före export.
40. Kontrollera att en föreslagen ångring inte tar bort innehåll som skapats av andra program.

## Export och import
41. Förhandsgranska exporterad text med radnummer innan den sparas.
42. Låt användaren välja maximal djupnivå vid export av mappträd.
43. Erbjud en provvisning av vilka objekt ett exportfilter kommer att utesluta.
44. Lägg till ett JSON-format för strukturer med dokumenterad formatversion.
45. Låt användaren välja om tomma undermappar ska markeras särskilt i exporten.
46. Visa antal inkluderade och uteslutna objekt före export.
47. Erbjud en avbrytbar analys av mycket stora träd med bevarat gammalt exportresultat.
48. Kontrollera att en importerad struktur kan exporteras igen utan informationsförlust.
49. Jämför ett importerat träd med en befintlig projektmapp utan att ändra något.
50. Tillåt kopiering av bara den markerade grenen i en trädöversikt.

## Gränssnitt och läsbarhet
51. Erbjud ett val mellan kompakt och rymlig visuell täthet, oberoende av textstorlek.
52. Visa ett kort exempel direkt vid fält som har ett särskilt formatkrav.
53. Visa valideringsfel intill det berörda fältet och behåll sammanfattningen överst.
54. Låt användaren återställa en enda sidas layoutval utan att återställa andra inställningar.
55. Erbjud en lugn vy som minskar dekorativa färger men behåller status och kontrast.
56. Använd separata former och texter för varning, fel och lyckat resultat, inte bara färg.
57. Visa tydliga tomlägen med en relevant åtgärd i stället för stora tomma ytor.
58. Erbjud en tillfällig större förhandsvisning av det slutliga projektnamnet.
59. Visa förklarande verktygstips för förkortade tekniska begrepp.
60. Tillåt egen ordning på toppflikarna utan att ändra vilka som är synliga.

## Tangentbord och tillgänglighet
61. Lägg till en sökbar kommandopalett med samma åtgärder som knappar och menyer.
62. Gör kommandopaletten helt användbar utan mus.
63. Erbjud en utskrivbar översikt över de snabbkommandon som faktiskt är aktiva.
64. Visa en valfri hjälpöverlagring som markerar tangentbordets genvägar i aktuell dialog.
65. Behåll senaste logiska tangentbordsfokus när en modal dialog stängs.
66. Granska kontrollernas tillgängliga namn med riktiga skärmläsartester.
67. Lägg till ett läge för reducerade rörelser och visuella övergångar.
68. Erbjud större klickytor utan att samtidigt förstora all text.
69. Ge en tydlig förklaring när en knapp är inaktiverad och hur den kan aktiveras.
70. Gör kontrastpaletten mätbar med automatiska kontroller av relevanta färgpar.

## Uppdateringar och driftsäkerhet
71. Visa en före/efter-jämförelse av bygg-ID när samma release uppdateras.
72. Visa en kort installationskvittens först när den nya appstarten verkligen bekräftats.
73. Skilj tydligt mellan hämtad, verifierad, installerad och startbekräftad uppdatering.
74. Låt användaren välja ett underhållsfönster för appuppdateringar utan att ändra Python.
75. Erbjud en engångspaus av appuppdatering medan ett viktigt arbete pågår.
76. Visa konkret vilken aktiv operation som skjuter upp en uppdateringsomstart.
77. Beräkna och visa utrymmesbehov för hämtning och säkerhetskopia före filbytet.
78. Erbjud en kontrollerad verifiering av installerade appfiler utan ominstallation.
79. Visa en läsbar tidslinje över senaste uppdatering och eventuell återställning.
80. Testa uppdateringar från fler äldre bygg-ID:n, inte bara från senaste föregående bygge.

## Diagnostik och support
81. Skapa ett support-ID per felgrupp som kan kopieras utan hela tracebacken.
82. Låt användaren granska exakt vilka filer som ska ingå innan diagnostikexporten skapas.
83. Erbjud en förhandsvisning av identifierade personliga sökvägar i loggarna.
84. Erbjud frivillig maskering av användarnamn i exporterade loggar och visa begränsningarna.
85. Skapa en kort svensk felsammanfattning med separat teknisk detaljdel.
86. Visa skillnad mellan ett nytt fel och ett gammalt fel som återkommit efter åtgärd.
87. Erbjud en valbar, kort händelsetidslinje runt ett fel utan att spela in tangenttryckningar.
88. Testa att diagnostikexport fortfarande fungerar när en av loggfilerna är låst.
89. Visa vilken appkomponent som svarade senast vid en hälsokontroll.
90. Dokumentera en säker supportprocedur för företagsdatorer utan administratörsrättigheter.

## Prestanda, kvalitet och kompatibilitet
91. Mät starttid per steg lokalt utan att sända telemetri.
92. Ladda stora historiklistor i omgångar för att hålla gränssnittet responsivt.
93. Återanvänd oförändrade historikkort i stället för att bygga om hela listan.
94. Undvik att läsa filstorlekar för hela historiken innan användaren efterfrågar dem.
95. Lägg till ett långkörningstest som växlar flikar och öppnar/stänger dialoger upprepade gånger.
96. Mät minnesförbrukning före och efter många dialogöppningar för att hitta läckor.
97. Testa faktisk skärmflytt mellan olika Windows-DPI med automatiserad fönsterhantering.
98. Testa frånkoppling och återanslutning av en nätverksplats under pågående analys.
99. Testa appstart från en sökväg med svenska tecken, långa namn och mellanslag samtidigt.
100. Publicera en tydlig kompatibilitetsmatris som skiljer faktiskt testade kombinationer från förväntat stöd.
