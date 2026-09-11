# Konzept & Entscheidungen

## HACS oder Integration – was ist der Unterschied?

Das sind zwei verschiedene Dinge, deshalb ist die Antwort „beides":

* **Integration** ist das *Was*: Python-Code in `custom_components/fluessiggas`,
  den Home Assistant beim Start lädt. Er bringt den Einrichtungsdialog, die
  Entitäten und die Dienste mit.
* **HACS** ist das *Wie*: ein Downloader mit Update-Benachrichtigung. HACS
  kopiert lediglich den Ordner `custom_components/fluessiggas` an die richtige
  Stelle und sagt Bescheid, wenn es eine neue Version gibt.

Die JUDO-ZEWA-Integration ist genau dieses Muster: eine custom integration, die
über HACS verteilt wird. Dieses Repo ist jetzt genauso gebaut – deshalb liegt
`hacs.json` im Wurzelverzeichnis und die Integration in
`custom_components/fluessiggas/`.

Die Alternative war die erste Ausbaustufe: ein YAML-Package mit Hilfsentitäten
und Template-Sensoren. Das lief, war aber der falsche Weg für ein Repo, das
andere nutzen sollen – jeder hätte YAML editieren müssen, und über HACS lässt
sich so etwas nicht als Integration installieren. Deshalb ist es ersetzt worden;
in der Git-Historie liegt es noch.

**Ein Repo, beides drin:** HACS kennt pro Repository nur eine Kategorie. Die
Lovelace-Karte wandert deshalb mit in den Integrationsordner
(`custom_components/fluessiggas/frontend/`), und die Integration meldet sie
beim Start selbst beim Frontend an. Für dich heißt das: installieren,
einrichten, fertig – kein Eintrag unter *Dashboards → Ressourcen*.

## Warum kein utility_meter mehr

Home Assistant führt für jeden Verbrauchszähler ohnehin eine Statistik mit, und
darin steht eine bereinigte Summe (`sum`), in der Zählerrückstellungen bereits
herausgerechnet sind. Damit gilt schlicht:

```
Verbrauch seit Betankung = Summe(jetzt) − Summe(zum Zeitpunkt der Betankung)
```

Das ist derselbe Datenbestand, den du im Energie-Dashboard siehst. Der
`utility_meter` hätte diese Arbeit nur ein zweites Mal gemacht – mit eigener
Zählweise, eigenen Rundungsfehlern und einer Hilfsentität mehr.

Zwei Dinge werden dadurch überhaupt erst möglich:

* **Rückwirkende Betankungen.** Weil die Statistik nach Zeitpunkt abfragbar
  ist, kann eine Lieferung mit Datum von vorletzter Woche eingetragen werden –
  der Verbrauch seither wird korrekt weitergezählt. Ein `utility_meter` kennt
  nur „jetzt zurücksetzen".
* **Das Monatsprofil.** Der Verbrauch der letzten Jahre steht bereits in der
  Datenbank; er muss nicht erst gesammelt werden.

Voraussetzung ist, dass die Quellsensoren `state_class: total_increasing` (oder
`total`) haben. Das haben sie, sobald sie im Energie-Dashboard auftauchen.

## Reicht ein Jahreswert statt der Monate?

Nein – und die Sorge, dass Monatsdaten fehlen, ist unbegründet.

**Zur Datenlage:** Die Integration liest beim Start die Langzeitstatistik der
letzten Jahre. Ab Juli 2024 aufgezeichnet und heute im September 2026 bedeutet:
Jeder Kalendermonat ist mindestens zweimal vorhanden (Januar 2025 und 2026,
Juli 2024 und 2025, …). Es fehlt nichts, und es muss auch nichts erst
gesammelt werden – die Prognose ist ab der ersten Minute vollständig.

**Zur Rechenweise:** Ein Jahreswert würde die Frage falsch beantworten. 3.000 L
Restmenge sind Anfang Oktober noch keine sieben Monate, sondern gut fünf –
weil Oktober bis März zusammen etwa 70 % des Jahresverbrauchs ausmachen. Mit
Jahresmittel wäre die Prognose im Herbst systematisch zu optimistisch und im
Frühjahr zu pessimistisch, also genau dann falsch, wenn es darauf ankommt.

**Und wenn doch Monate fehlen** (bei jemandem mit kürzerer Historie): Sie
werden nicht mit 0 angesetzt, sondern über die Form einer typischen Heizkurve
ergänzt und auf das Niveau der gemessenen Monate skaliert. Wer nur Januar bis
April gemessen hat – 48,5 % der Kurve –, bekommt daraus einen hochgerechneten
Jahresverbrauch statt einer Prognose, die im Mai in die Unendlichkeit läuft.
Das Attribut `gemessene_jahre` am Sensor *Jahresverbrauch* zeigt für jeden
Monat, ob er gemessen oder geschätzt ist.

Die Anzahl der Mittelungsjahre ist einstellbar: 1 = nur das letzte Jahr zählt,
3 = über drei Jahre glätten. Damit ist ein einzelner Extremwinter entweder
maßgeblich oder eben nicht.

## Wie der Füllstand sinkt

Genau so, wie vermutet – in vier Schritten:

1. Home Assistant führt für jeden Verbrauchszähler eine Statistik mit einer
   bereinigten Summe (`sum`). Die Integration liest sie alle fünf Minuten.
2. `Summe(jetzt) − Summe(bei der Betankung)` ergibt den Verbrauch seither, in
   der Einheit des Zählers – bei einer Viessmann also m³.
3. Diese m³ werden mit dem Faktor (Vorgabe 3,92) in Liter Flüssiggas
   umgerechnet. Zählt eine Quelle in kWh, wird stattdessen durch den
   Energieinhalt je Liter geteilt; zählt sie in Litern, entfällt die Umrechnung.
   Die Einheit kommt aus den Statistik-Metadaten, nicht aus der Anzeige – bei
   einer abweichend eingestellten Anzeigeeinheit wäre die Rechnung sonst still
   falsch.
4. `Referenzstand − verbrauchte Liter` ist der Füllstand. Die Prozentanzeige ist
   davon abgeleitet: durch das Nennvolumen für die Tankuhr, durch die nutzbare
   Menge für die Füllung.

Die 51 % auf der Tankuhr werden also nicht direkt fortgeschrieben, sondern
immer aus den Litern neu berechnet. Das ist wichtig, weil der Zusammenhang
zwischen Höhe und Volumen im liegenden Zylinder nicht linear ist – die Karte
berücksichtigt das beim Zeichnen des Flüssigkeitsspiegels.

## Woher die Statistikwerte kommen

Nicht über eigenes SQL auf der Datenbank, sondern über die offizielle
Recorder-Schnittstelle: `statistics_during_period` und
`get_last_short_term_statistics`. Die Aufrufe laufen im Executor des Recorders,
also auf demselben Thread, der auch sonst auf die Datenbank zugreift – kein
paralleler Zugriff, keine Annahmen über SQLite oder MariaDB, keine eigenen
Verbindungen.

Gelesen wird nicht der Zustand der Sensoren, sondern deren aufsummierte
Statistik. Der Unterschied ist wichtig: Der Zustand deiner „dieses Jahr"-Sensoren
springt zum Jahreswechsel auf 0 zurück, die Statistiksumme läuft durch, weil
Home Assistant den Rücksprung bereits als Zählerreset erkannt und
herausgerechnet hat.

## Wie oft die Datenbank gefragt wird – und wie wenig

Die Integration **liest** ausschließlich. Sie schreibt keine Zeile in die
Recorder-Datenbank, ändert kein Schema, räumt nichts auf. Ihr eigener Zustand
(Referenzstand, Bezugspunkt, Lieferhistorie, Rücknahmeschritte) liegt in
`.storage/fluessiggas.<eintrag>` – einer JSON-Datei, nicht in der Datenbank.

| Abfrage | Takt | Umfang |
|---|---|---|
| `get_last_short_term_statistics` je Quelle | alle 15 min, **nur wenn sich der Zähler bewegt hat** | eine Zeile je Quelle, über den Index |
| `statistics_during_period`, Monatsprofil | 1× täglich, im Hintergrund | N Jahre je Quelle |
| `statistics_during_period`, Preisverlauf | 1× täglich, im Hintergrund | bis 6 Jahre, ein Sensor |
| `async_list_statistic_ids`, Einheiten | alle 12 h, dazu 1× täglich für den Preis-Sensor | Metadatentabelle, wenige Zeilen |
| `statistics_during_period`, Bezugspunkt Jahresanfang | 1× im Jahr | 36-Stunden-Fenster, Stundenwerte |
| `statistics_during_period`, Stundenwerte | nur als Notnagel | siehe unten |

### Die kleine Abfrage: alle 15 Minuten, oft gar nicht

Der Füllstand braucht genau eine Zahl je Quelle: die aktuelle Statistiksumme.
`get_last_short_term_statistics` holt sie über den Index – eine Zeile, kein
Suchen. Das ist weniger Last, als ein einziges Verlaufsdiagramm im Dashboard
erzeugt.

Zwei Bremsen sitzen davor:

**Der Takt.** Der Recorder schreibt die Kurzzeitstatistik alle fünf Minuten;
häufiger zu fragen kann gar nichts Neues bringen. Für einen Tank, der Monate
hält, wären selbst fünf Minuten sinnlos genau – die Vorgabe sind deshalb 15.
Einstellbar in den Optionen (*Abfrageintervall der Statistik*, 5 bis 240 min).

**Der Stillstand.** Die Statistik einer Quelle kann sich nur bewegen, wenn sich
der Sensor bewegt hat. Die Integration hört deshalb auf die Zustandsänderungen
der Zählersensoren – nicht um daraus zu rechnen, sondern um zu wissen, wann
eine Abfrage garantiert dasselbe Ergebnis liefern würde. Steht der Zähler,
unterbleibt die Abfrage ganz. Im Sommer, wenn die Heizung tagelang aus ist,
fällt damit praktisch der gesamte Grundtakt weg.

Ein Sicherheitsnetz bleibt: Einmal pro Stunde wird auf jeden Fall gelesen. Das
fängt die Fälle ab, in denen Statistik ohne Zustandsänderung entsteht –
importierte Statistik etwa, oder nachträglich korrigierte Summen.

### Die große Abfrage: einmal am Tag, nebenher

Monatsprofil und Preisverlauf sind die teuren Abfragen. Der Grund steckt in der
Struktur des Recorders: Er führt zwei Tabellen, `statistics_short_term` mit
Fünf-Minuten-Werten und `statistics` mit Stundenwerten. Monats- und Tageswerte
gibt es **nicht** fertig – `statistics_during_period` mit `period="month"`
faltet sie aus den Stundenzeilen zusammen. Zwei Jahre über zwei Quellen sind
damit rund 35.000 Stundenzeilen, die zu 24 Monatswerten werden. Das ist die
Größenordnung, nach der du gefragt hast.

Deshalb zwei Vorkehrungen:

1. Die Abfrage läuft **nie** im Aktualisierungspfad, sondern in einer
   Hintergrundaufgabe. Hängt sie, hängt weder die Karte noch die Einrichtung.
2. Sie läuft **einmal am Tag**. Mehr wäre Verschwendung: Ein Monatswert ändert
   sich innerhalb des laufenden Monats nur am Rand, und die Monate davor sind
   fest. Wer das Ergebnis sofort will, ruft `fluessiggas.profil_neu_berechnen`
   auf.

Das Ergebnis liegt anschließend im Speicher der Integration. Die Karte fragt
nie selbst die Datenbank – sie liest nur Attribute von Entitäten.

### Warum nicht einmalig beim Start?

Naheliegend, aber es hielte nicht: Der Preisverlauf bekommt jeden Monat einen
neuen Punkt, das Monatsprofil wächst mit jedem abgeschlossenen Monat, und wer
die Zahl der Mittelungsjahre ändert, will das Ergebnis sehen. Eine Instanz, die
monatelang durchläuft, zeigte sonst dauerhaft veraltete Zahlen. Einmal täglich
ist der Kompromiss: zwei große Abfragen am Tag statt acht wie vorher, und das
Ergebnis nie älter als 24 Stunden.

### Der Notnagel

Zweimal wird zusätzlich gelesen, beides selten:

* Liefert die Kurzzeitstatistik nichts – sie reicht nur rund zehn Tage zurück,
  etwa nach einem längeren Ausfall –, holt ein Griff in die Stundenwerte der
  letzten 30 Tage den letzten bekannten Stand.
* Eine Betankung mit zurückliegendem Datum braucht die Statistiksumme von genau
  diesem Tag. Das ist ein Fenster von 36 Stunden, und es passiert nur, wenn du
  eine Betankung einträgst.

Derselbe Weg holt einmal im Jahr den Bezugspunkt für den Jahresverbrauch
(1. Januar 00:00 Uhr). Schlägt das fehl, weil noch keine Statistik so weit
zurückreicht, bleibt der Jahresverbrauch unbekannt und es wird stündlich erneut
versucht – nicht bei jedem Durchlauf.

### Und die SQL-Fehler?

Falls du je Datenbankfehler im Protokoll siehst: Von hier kommen sie nicht.
Lesende Zugriffe über die Recorder-Schnittstelle können eine Datenbank weder
beschädigen noch sperren – sie laufen im Executor des Recorders, also auf
demselben Thread, der ohnehin schreibt. Ein Test dauert eine Minute: Ordner
`custom_components/fluessiggas` umbenennen, Home Assistant neu starten.

## Jahreszähler, die auf 0 zurückfallen

Die Zähler einer Viessmann Vitodens heißen „Gasverbrauch Heizung dieses Jahr"
und „… Warmwasser dieses Jahr". Sie zählen ein Kalenderjahr hoch und springen
zum Jahreswechsel auf 0. Genau deshalb liest diese Integration **nicht den
Zustand** dieser Sensoren, sondern ihre Statistiksumme.

Der Unterschied ist der ganze Punkt:

| | 31.12. 23:00 | 01.01. 01:00 |
|---|---|---|
| Zustand des Sensors | 362 m³ | 0 m³ |
| Statistiksumme (`sum`) | 1.184 m³ | 1.184 m³ |

Home Assistant erkennt den Rücksprung als Zählerreset und hält ihn aus der
Summe heraus – die läuft durch, über Jahre. Ein Verbrauch ist damit immer die
Differenz zweier Summen, und die kann nicht negativ werden. Das ist der Grund,
warum es hier kein `utility_meter` und keine Sonderbehandlung zum Silvester
braucht: Der Jahreswechsel ist für diese Rechnung ein Tag wie jeder andere.

### Woran es hängt – und wie du es prüfst

An genau einer Sache: Die Quellsensoren müssen `state_class: total_increasing`
(oder `total`) tragen. Nur dann führt Home Assistant überhaupt eine
Statistiksumme und erkennt den Reset. Bei `measurement` gibt es keine Summe,
und die Integration meldet das im Protokoll.

Nachsehen kannst du es im Attribut `quellen` des Sensors *Verbrauch dieses
Jahr*. Dort steht je Zähler, was tatsächlich anliegt:

```yaml
quellen:
  - entity_id: sensor.heizgas_dieses_jahr
    statistik_einheit: m³
    gelesen_als: m3
    state_class: total_increasing     # ← darauf kommt es an
    liter_je_einheit: 3.87
```

### Der Verbrauch des laufenden Jahres

Er ergibt sich als Differenz zur Statistiksumme am 1. Januar 00:00 Uhr
Ortszeit. Dieser Bezugspunkt wird **einmal im Jahr** gelesen und dann gemerkt;
der Rest ist eine Subtraktion von der Summe, die für den Füllstand ohnehin
alle 15 Minuten kommt.

Der naheliegende Alternativweg wäre, die Monatswerte des laufenden Jahres zu
addieren – das Monatsprofil liest sie ohnehin täglich. Er ist aber schlechter,
und zwar genau am Monatsersten: Der letzte Monat käme dann aus einem Profillauf
vom Vortag und wäre um einen Tag zu klein, während der laufende Monat noch bei
0 steht. Der Wert würde also kurz **sinken** – und ein Rückgang ist für einen
Zähler das Signal für einen Reset. Die Langzeitstatistik hätte den
Jahresverbrauch doppelt gezählt. Über die Differenz zur Summe kann das nicht
passieren, weil die Summe selbst nie sinkt.

### Die Zeitzonen-Falle beim Jahresanfang

`year_start` ist ein UTC-Zeitpunkt, weil Home Assistant für `last_reset` genau
das erwartet. Zum Anzeigen taugt er nicht: Die lokale Mitternacht des
1. Januar 2026 ist in Mitteleuropa `2025-12-31T23:00:00Z`. Ein `.year` darauf
liefert **2025**.

Genau das ist in 2.0.0 passiert – die Karte zeigte „Verbrauch 2025", während
2026 lief. Der gerechnete Wert war richtig, die Beschriftung nicht. Das
Kalenderjahr wird deshalb getrennt in Ortszeit mitgeführt, und das Attribut
`seit` steht als lokale Zeit da (`2026-01-01T00:00:00+01:00`) statt als
UTC-Zeitpunkt vom Vorjahr.

### Warum `total` mit `last_reset` und nicht `total_increasing`

Die drei Jahressensoren melden den 1. Januar ausdrücklich als `last_reset`.
Home Assistant muss den Jahreswechsel damit nicht aus einem Rückgang erraten.

Das ist keine Feinheit: Der Liter-Wert hängt am Faktor L/m³, und der
kalibriert sich bei einer Betankung nach. Sinkt er dabei von 3,92 auf 3,87,
sinkt auch der Jahresverbrauch in Litern um gut ein Prozent. Bei
`total_increasing` wäre jeder Rückgang ein Reset-Kandidat; mit einem
ausdrücklichen `last_reset` ist es schlicht ein neuer Messwert im selben Jahr.

(Der m³-Wert ist davon übrigens gar nicht betroffen: Bei m³-Zählern kürzt sich
der Faktor wieder heraus – Liter durch Faktor ergibt genau die gezählten
Kubikmeter.)

## Was in der Langzeitstatistik landet

Nicht alles, und das mit Absicht. Home Assistant führt eine Langzeitstatistik
nur für Entitäten mit `state_class`:

| Sensor | `state_class` | Statistik |
|---|---|---|
| Füllstand, Tankuhr, Füllung | `measurement` | min/Ø/max je Stunde |
| Restenergie, Restwert | `measurement` | min/Ø/max |
| Gaspreis, Umrechnungsfaktor | `measurement` | min/Ø/max |
| Tagesverbrauch | `measurement` | min/Ø/max |
| Erwarteter Jahresverbrauch, Reichweite | `measurement` | min/Ø/max |
| Verbrauch seit Betankung | `total_increasing` | Summe |
| Verbrauch dieses Jahr (L, m³, kWh) | `total` + `last_reset` | Summe je Jahr |
| Leer am, Reserve erreicht am, Bestellen bis | – | keine |
| Letzte Betankung | – | keine |

Die vier Datums-Sensoren sind Zeitstempel; für die gibt es in Home Assistant
keine Statistik, und eine gemittelte Bestellfrist wäre auch keine sinnvolle
Größe. Was von ihnen bleibt, ist die normale Zustandshistorie der letzten
Tage.

`Reichweite` und `Erwarteter Jahresverbrauch` haben ihre `state_class` erst
seit Version 2.0.0 – damit sich nachvollziehen lässt, wie sich die Prognose
über die Monate verschoben hat.

## Mehr Mittelungsjahre einstellen, als Daten vorhanden sind

Das ist ausdrücklich vorgesehen. Die Einstellung ist eine Obergrenze, kein
Anspruch: Je Kalendermonat werden die *bis zu* n jüngsten Jahre genommen. Bei
zwei Jahren Historie und der Einstellung 5 fließen eben zwei Jahre ein.

Was dabei nicht passiert: Fehlende Jahre werden nicht als 0 mitgemittelt – sie
kommen gar nicht erst in die Rechnung. Und Monate, für die es überhaupt keine
Messwerte gibt, werden über die Form der Standard-Heizkurve ergänzt statt
genullt. Das Attribut `gemessene_jahre` am Sensor *Jahresverbrauch* zeigt für
jeden Monat, worauf er beruht.

## Betankung: auch teilweise

Der neue Füllstand ist **Stand vor der Lieferung + Liefermenge**, gedeckelt auf
den maximalen Füllgrad. Wer 1.000 L auf einen halbleeren Tank tankt, landet bei
halbleer plus 1.000 L – „voll setzen" gibt es nicht als Automatismus.

Drei Angaben, frei kombinierbar:

| Angabe | Wirkung |
|---|---|
| `liter` | Liefermenge, wird auf den Stand davor addiert |
| `fuellstand_vorher_prozent` | korrigiert den Stand davor auf den abgelesenen Wert **und** kalibriert die Umrechnung |
| `fuellstand_nachher_prozent` | setzt den Stand absolut; hat Vorrang, weil direkt gemessen |

Jede Lieferung landet mit Datum, Menge, Preis und Kosten in der Historie
(Attribut `lieferungen` am Sensor *Letzte Betankung*).

## Warum die Karte nach einem Neustart fehlte

Ein echter Fehler in 1.0.0, behoben in 1.1.0. Home Assistant liefert
Lovelace-Zusatzmodule nicht per Websocket nach, sondern backt sie beim
Ausliefern der Seite als `<script type="module">` in das HTML – die Liste dafür
kommt aus `hass.data[DATA_EXTRA_MODULE_URL]`.

In 1.0.0 wurde die Karte erst in `async_setup_entry` angemeldet, und zwar *nach*
`async_config_entry_first_refresh()`. Dieser erste Durchlauf las unter anderem
das Monatsprofil – mehrere Jahre Statistik über alle Quellen, beim Start
zusätzlich hinter dem Rückstand des Recorders eingereiht. Lud der Browser die
Seite vorher, fehlte das Skript-Tag komplett: „custom element doesn't exist",
und die Kartenauswahl wartete auf ein Modul, das nie kam.

Zwei Änderungen, beide nötig:

* Die Karte wird jetzt in `async_setup` angemeldet, also bevor überhaupt ein
  Tank eingerichtet wird. Die Route steht damit auch dann, wenn die Einrichtung
  später scheitert – vorher lief eine bereits gecachte Seite mit Skript-Tag in
  einen 404, was denselben Effekt hatte.
* Das Monatsprofil wird nicht mehr im Aktualisierungspfad gelesen, sondern in
  einer Hintergrundaufgabe. Die Einrichtung wartet nicht mehr darauf; bis das
  Profil da ist, rechnet die Prognose mit der Standardkurve weiter.

Unvermeidbar bleibt: Direkt nach der *Erst*installation muss die Seite einmal
neu geladen werden (Strg+F5). Ein bereits ausgeliefertes HTML kann kein
Skript-Tag nachwachsen lassen.

### Das Zwei-Sekunden-Fenster

Damit war es aber nicht erledigt: Die Karte fiel weiterhin sporadisch aus und
kam nach ein- bis zweimal Neuladen wieder – unabhängig von Browser, Gerät und
davon, ob HTTP oder HTTPS. Die Erklärung steht im Frontend-Quelltext
(`create-element-base.ts`):

```js
const timer = window.setTimeout(() => { … }, TIMEOUT);   // TIMEOUT = 2000
customElements.whenDefined(tag).then(() => { clearTimeout(timer); … });
```

Eine Custom Card hat **zwei Sekunden**, um sich zu registrieren. Danach
erscheint „custom element doesn't exist". Kommt sie später doch noch, wird die
Karte zwar neu aufgebaut – aber der Fehler war zwischenzeitlich sichtbar, und
in der Kartenauswahl bleibt er stehen.

Der Fehler lag bei der Auslieferung: Die statische Route war mit
`cache_headers=False` angemeldet, Home Assistant sendete also **gar keine**
Cache-Header. Der Browser lud die knapp 40 kB bei *jedem* Seitenaufruf neu. Auf
einem beschäftigten Home Assistant – etwa direkt nach dem Start, wenn der
Recorder arbeitet – reichen zwei Sekunden dafür nicht zuverlässig.

Mit `cache_headers=True` liefert Home Assistant langlebige Cache-Header
(`public, max-age=2678400`, also 31 Tage). Das ist hier gefahrlos, weil die URL
die Version trägt (`?v=1.4.0`): Nach einem Update ändert sich die URL, der
Browser holt die Datei neu, und dazwischen kommt sie aus dem lokalen Cache
statt über das Netz.

### Und wenn der Cache nicht greift: 16 statt 53 kB

Der Cache hilft nur beim zweiten Aufruf. Beim ersten – und nach jedem Update,
weil die URL sich ändert – zählt die reine Übertragungszeit, und die iOS-App
ist nach einem „nach unten ziehen" genau in diesem Fall. Seit 2.0.1 liegt
deshalb neben der Karte ein vorkomprimiertes `lpg-tank-card.js.gz`.

Ausgeliefert wird es ohne jedes Zutun: aiohttp – und damit Home Assistant –
sucht bei einer `FileResponse` nach einem Geschwisterfile mit der Endung
`.gz` (oder `.br`), sobald der Browser die Kodierung akzeptiert, und setzt
`Content-Encoding: gzip` samt `Vary: Accept-Encoding`. Gemessen an der echten
Bibliothek:

| Anfrage | Übertragen | Header |
|---|---|---|
| `Accept-Encoding: gzip` | 15.726 B | `Content-Encoding: gzip`, `Vary: Accept-Encoding` |
| `Accept-Encoding: identity` | 52.844 B | – |

Also **70 % weniger** im entscheidenden Fenster. Und ohne Risiko: Fehlt die
Datei oder kann der Browser kein gzip, wird die unkomprimierte Karte
ausgeliefert. Das `Vary` verhindert, dass ein vorgeschalteter nginx die
gepackte Antwort an einen Client ohne gzip weitergibt.

Der Preis ist eine erzeugte Datei im Repository, und die könnte veralten –
stillschweigend, denn sie würde alten Code genau an die Browser ausliefern,
die gzip können, also an alle. Dagegen steht ein Test, der sie entpackt und
byteweise mit der Karte vergleicht. Neu erzeugt wird sie mit:

```bash
python3 scripts/karte_komprimieren.py
```

### Warum `add_extra_js_url` der Fehler war

Auch damit war es nicht erledigt. Auf dem iPhone erschien weiter sporadisch
„custom element doesn't exist: lpg-tank-card" – nur diese eine Karte, andere
Karten aus HACS liefen tadellos, und im Firefox war nie etwas. Vier Anläufe
lang habe ich am falschen Ende gesucht: Cache-Header, Ressourcenliste,
Dateigröße. Alles half ein bisschen, nichts half wirklich.

Die Spur kam aus dem Protokoll – und zwar von einer **fremden** Karte:

```
Failed to execute 'define' on 'CustomElementRegistry': the name
"homematicip-local-climate-schedule-card" has already been used with this registry
  node_modules/@webcomponents/scoped-custom-element-registry/…
```

Zwei Dinge stehen darin. Erstens: Module werden in diesem Frontend **mehrfach
ausgeführt**. Zweitens, und das war der Schlüssel: Home Assistant installiert
**`scoped-custom-element-registry`**, einen Polyfill, der
`window.customElements` ersetzt.

Ein Blick in dessen Quelltext erklärt alles:

```ts
get(tagName: string) {
  const definition = this._definitionsByTag.get(tagName);
  return definition?.elementClass;
}
```

`get()` und `whenDefined()` befragen **ausschließlich die eigene Map**. Was vor
der Installation des Polyfills in der nativen Registry angemeldet wurde, ist
danach unsichtbar – der Polyfill übernimmt nichts.

Und genau dort lag unsere Karte. Sie war die einzige, die über
`add_extra_js_url` **zusätzlich als Skript-Tag im HTML** steckte. Ein solches
Modul läuft, sobald das HTML geparst ist – womöglich also, bevor das Frontend
den Polyfill nachgeladen hat. Dann passiert dies:

| Schritt | Ergebnis |
|---|---|
| Unser Modul läuft, `customElements.define(…)` | Karte ist in der **nativen** Registry |
| Frontend installiert den Polyfill | `window.customElements` ist ersetzt |
| Lovelace fragt `customElements.get("lpg-tank-card")` | **undefined** → „custom element doesn't exist" |
| Frontend wartet auf `whenDefined("lpg-tank-card")` | löst **nie** aus → der Fehler bleibt stehen |

Der letzte Punkt erklärt, warum der Fehler nicht von selbst verschwand, obwohl
das Frontend bei einem nachträglich definierten Element eigentlich
`ll-rebuild` feuert. Und ob unser Modul vor oder nach dem Polyfill läuft, ist
ein Rennen – daher „manchmal beim ersten Mal, manchmal nach dem dritten".

Alle anderen Karten kommen ausschließlich über die Lovelace-Ressourcenliste.
Die lädt das Frontend erst, wenn es selbst läuft, also **nach** dem Polyfill –
sie melden sich damit in genau der Registry an, die Lovelace anschließend
befragt. Deshalb funktionierten sie.

Die Behebung ist entsprechend schlicht: **`add_extra_js_url` fällt weg.** Die
Ressourcenliste ist der einzige Weg, so wie im gesamten Ökosystem. Das
Nachgemessene aus dem Browser, mit einem nachgebildeten Polyfill:

| Situation | `customElements.get()` |
|---|---|
| nativ angemeldet, vor dem Polyfill | `true` |
| … danach, aus Sicht des Polyfills | **`false`** ← der Fehler |
| … nach erneuter Ausführung des Moduls | `true` |

Dazu eine Hygienemaßnahme in der Karte: Angemeldet wird jetzt in einem
`try`/`catch`, statt vorher `customElements.get()` zu befragen. Unter dem
Polyfill kann diese Abfrage in beide Richtungen lügen, und ein ungefangener
Doppeleintrag bricht die Ausführung des Moduls ab – so verabschiedet sich die
Karte im Protokoll oben. Sie ist aber nur die Absicherung, nicht die Behebung:
Läuft das Modul überhaupt nur einmal und zu früh, hilft kein `catch`. Dagegen
hilft, gar nicht mehr zu früh zu laufen.

Eine Nebenwirkung bleibt: In YAML-verwaltetem Lovelace gibt es keine
Ressourcen-Sammlung, in die sich die Integration eintragen könnte. Dort muss
die Ressource von Hand angelegt werden – die Integration schreibt die
fertige URL dafür ins Protokoll. Das entspricht dem, was dort für jede
Custom Card ohnehin nötig ist.

## Vertippt: warum Rückgängig und nicht Bearbeiten

Beim Eintragen einer Betankung verstellt die Integration vier Dinge auf einmal:
den Referenzstand, den Bezugspunkt der Zählung (die Statistiksummen zum
Zeitpunkt der Lieferung), den Zeitstempel dazu und die Historie. Dazu kommt
womöglich ein neu kalibrierter Faktor L/m³ und ein zurückgeschriebener Preis.

Eine Bearbeitungsmaske müsste all das rückwärts auseinandernehmen – und der
Nutzer müsste verstehen, welches Feld was verstellt. Deshalb der andere Weg:
Vor jeder Änderung wird der Zustand davor weggeschrieben, und *Rückgängig* holt
ihn komplett zurück. Zehn Schritte tief, ein paar hundert Byte pro Schritt.

Der Reiz daran ist, dass die Rücknahme nicht altert. Zurückgeholt wird nicht
der damalige Füllstand, sondern der damalige Bezugspunkt – der Stand rechnet
sich daraus wieder auf. Eine Betankung, die vor drei Tagen falsch eingetragen
wurde, lässt sich heute zurücknehmen, ohne den Verbrauch dieser drei Tage zu
verlieren. Danach trägst du sie richtig ein.

Zwei Dinge kann die Rücknahme nicht:

* **Fremde Entitäten.** Ist der Preis an einen `input_number` gebunden,
  schreibt eine Betankung ihren Preis dorthin. Das gehört jemand anderem, und
  die Integration stellt es nicht heimlich zurück.
* **Den kalibrierten Faktor.** Er steht in den Optionen des
  Konfigurationseintrags, nicht im eigenen Speicher. Wer eine Betankung mit
  Tankuhr-Angabe zurücknimmt, korrigiert ihn bei Bedarf von Hand.

Davon getrennt steht das **Löschen** eines Historieneintrags. Es räumt nur die
Liste auf, aus der der Preisverlauf gezeichnet wird, und lässt den Füllstand in
Ruhe – gedacht für falsch nachgetragene alte Lieferungen. Dass der Füllstand
davon unberührt bleibt, ist kein Versehen, sondern die Trennung, die schon
`lieferung_nachtragen` von `betankung` unterscheidet.

Angesprochen wird ein Eintrag über eine Kennung, nicht über seine Position oder
sein Datum. Zwei Lieferungen am selben Tag sind sonst nicht zu unterscheiden,
und eine Position verschiebt sich, sobald ein Eintrag herausfällt. Ältere
Einträge bekommen ihre Kennung beim ersten Laden nachträglich.

## Gaspreis: vorhandener Helfer oder eigene Entität

Der Preis ist überall EUR je Liter – Anzeige wie Eingabe. Woher er kommt, ist
konfigurierbar:

* Ist im Feld *Vorhandener Preis-Helfer* eine Entität angegeben, ist sie die
  Quelle. Steht sie in EUR/m³, wird mit dem konfigurierten Faktor in Liter
  umgerechnet. Ein beim Tanken eingegebener Preis wird dorthin zurückgeschrieben
  – bei `input_number` und `number` per `set_value`, bei einem Sensor nicht,
  weil der sich nicht setzen lässt.
* Ohne Angabe legt die Integration die Zahl *Gaspreis* an.

In beiden Fällen gibt es zusätzlich den **Sensor** *Gaspreis* mit
`state_class: measurement`. Das ist der eigentliche Kniff: Eine `input_number`
hat nur Kurzzeit-Historie, die nach `purge_keep_days` (Vorgabe 10 Tage)
verschwindet. Ein Sensor mit `state_class` landet in der Langzeitstatistik und
bleibt jahrelang erhalten. Damit lässt sich der Preisverlauf auch in einer
`statistics-graph`-Karte darstellen, nicht nur in der Tankkarte.

Die Karte selbst zeichnet allerdings nicht diesen Sensor, sondern die
**tatsächlich bezahlten Preise** aus der Lieferhistorie. Das ist die Reihe, die
die Frage „gut oder schlecht eingekauft" beantwortet – der laufende Marktpreis
zwischen zwei Lieferungen ist dafür Rauschen.

## Selbstkalibrierung

Ob die m³ deiner Heizung wirklich 3,92 L Flüssiggas entsprechen, weiß niemand
vorher – die Heizung rechnet sie aus Brennerlaufzeit und Düsenleistung hoch.
Gibst du beim Tanken die Tankuhr *vor* der Lieferung an, rechnet die
Integration:

```
neuer Faktor = (letzter Referenzstand − abgelesener Stand) / gezählte m³
```

und schreibt ihn in die Optionen. Plausibilitätsgrenzen (2 bis 6 L/m³) und eine
Mindestmenge von 20 m³ verhindern, dass ein Tippfehler die Anlage verstellt.
Nach der ersten Betankung stimmt die Rechnung für deine Anlage statt für die
Norm.

Damit das nicht im Verborgenen passiert, gibt es den Faktor als eigenen Sensor
– als Messwert, damit Home Assistant ihn aufzeichnet. Verstellt eine Betankung
ihn, siehst du den Sprung im Verlauf, und die Attribute sagen, wann und von
welchem Wert aus. Ein eigener Speicher war dafür nicht nötig: Jede Betankung
hält alten und neuen Faktor ohnehin in ihrem Historieneintrag fest, die jüngste
mit Eintrag ist die Antwort.

Er ist bewusst kein `number` zum Verstellen. Der Faktor gehört zur Konfiguration
des Tanks, und zwei Wege, ihn zu ändern – Optionen und Entität – liefen
auseinander, sobald die nächste Betankung kalibriert. Ändern also weiterhin
unter *Konfigurieren*.

## Die Zahlen hinter den Vorgaben

| Größe | Wert | Herkunft |
|---|---|---|
| Dichte flüssig | ca. 0,51 kg/L | Propan bei 15 °C |
| Gasdichte | ca. 2,0 kg/m³ | Propan im Normzustand |
| **1 m³ Gas** | **≈ 3,92 L flüssig** | 2,0 / 0,51 |
| Heizwert Hu | 12,87 kWh/kg = 6,57 kWh/L | |
| Brennwert Ho | 13,95 kWh/kg = 7,11 kWh/L | |
| **Vorgabe** | **7,0 kWh/L** | 4.120 L × 7,0 = 28.840 kWh |

Der 85-%-Grenzwert ist keine Marotte: Flüssiges Propan dehnt sich stark aus, der
Gasraum darüber ist Sicherheitsvolumen. Die mechanische Tankuhr zeigt Prozent
vom **Nennvolumen**, „voll" sind also 85 %. Die Integration liefert beides:
*Tankuhr* entspricht der mechanischen Anzeige, *Füllung* rechnet 100 % =
randvoll getankt.

## Warum keine Wettervorhersage

Für die Frage „wann ist der Tank leer" bräuchte man das Wetter der nächsten ein
bis zwei Jahre – das weiß niemand. Was man weiß: wie kalt der Februar
*üblicherweise* ist. Und genau das steckt bereits im gemessenen Monatsverbrauch
der Vorjahre. Das Monatsprofil ist damit die empirische Variante einer
Gradtagzahl-Rechnung, ohne Zusatzdaten und ohne Wetterdienst.

## Genauigkeit

| Fehlerquelle | Größenordnung | Gegenmittel |
|---|---|---|
| Umrechnungsfaktor L/m³ | bis ±10 % vor der ersten Kalibrierung | Tankuhr vor dem Tanken eintragen |
| Ablesegenauigkeit der Tankuhr | ±2 % vom Nennvolumen ≈ ±100 L | mehrfach über die Zeit korrigieren |
| Milder oder harter Winter | ±15 % beim Jahresverbrauch | über mehrere Jahre mitteln |
| Zählung der Heizung selbst | 2–5 % | Kalibrierung fängt es mit ein |

Realistisch ist die Leer-Prognose ein Jahr im Voraus auf wenige Wochen genau –
für „muss ich diesen Herbst bestellen?" mehr als genug. Deshalb gibt es
zusätzlich *Bestellen bis*: Reservedatum minus Lieferzeit, das ist der Termin,
der wirklich zählt.

## Was noch kommen könnte

* **Preisentwicklung.** Die Lieferhistorie speichert bereits €/L je Lieferung.
  Daraus ließe sich ein Diagramm und die Frage „gut oder schlecht eingekauft"
  beantworten.
* **Kosten je Heizperiode** (Juli–Juni statt Kalenderjahr) – die für Heizungen
  eigentlich richtige Betrachtung.
* **Gradtagzahl-Korrektur.** Statt „Januar verbraucht üblicherweise 217 L" dann
  „Januar hat üblicherweise 520 Gradtage, wir brauchen 0,42 L je Gradtag". Damit
  ließe sich der *laufende* Winter mitkorrigieren: Sind bis Ende Dezember 15 %
  mehr Gradtage aufgelaufen als im Mittel, steigt die Restprognose entsprechend
  – rein aus Vergangenheitsdaten. Nötig: Außentemperatur-Historie (hat die
  Heizung) und ein Klimamittel für den Standort.
* **Warmwasser getrennt modellieren.** Warmwasser ist konstante Grundlast,
  Heizung ist saisonal. Getrennte Profile wären etwas genauer und würden zeigen,
  was der Sommerbetrieb kostet.
* **Kalendereintrag statt Meldung:** Bestelltermin in einen `local_calendar`
  schreiben.
* **Soll-Ist-Vergleich der Prognose:** Was hat die Prognose vor sechs Monaten für
  heute vorhergesagt? Macht das Vertrauen in die Zahl messbar.
* **Ein Füllstandssensor am Tank**, falls doch mal einer angeschraubt wird, wird
  einfach zum dritten Weg, den Bezugspunkt zu setzen – das Modell bleibt gleich.

## Marktpreise aus dem Netz – Einschätzung

Technisch machbar, aber nicht als Dauerabfrage empfehlenswert.

Portale haben keine offene Schnittstelle. Man müsste das
Angebotsformular nachbauen: Postleitzahl, Bestellmenge, Füllstand und
Tankeigentum als Formularfelder abschicken und den Preis aus der Antwortseite
herauslesen. Das funktioniert – bis zum nächsten Umbau der Seite, und dann
liefert es entweder nichts mehr oder, schlimmer, eine falsche Zahl.

Dazu kommen zwei Punkte, die schwerer wiegen als der Aufwand:

* Ein Angebotsrechner ist keine Preisliste. Der Preis hängt an Menge,
  Liefergebiet und Tagesform; ein einzelner abgefragter Wert ist eine
  unverbindliche Momentaufnahme für genau diese Eingaben.
* Eine Integration, die bei jedem Nutzer regelmäßig automatisiert Angebote
  abruft, erzeugt bei den Betreibern Last, der niemand zugestimmt hat. Die
  Nutzungsbedingungen solcher Portale untersagen automatisierte Abfragen in aller
  Regel ausdrücklich.

Wenn, dann so: als Dienst, den man **von Hand auslöst**, wenn man ohnehin
bestellen will – nicht als Fünf-Minuten-Abfrage. Und mit einer klaren Trennung
je Anbieter, damit ein Umbau nur einen Abrufer lahmlegt statt der Integration.

Der ehrlichere Weg für „soll ich jetzt tanken?" ist ohnehin schon eingebaut:
Der eigene Preisverlauf aus den Lieferungen zeigt die Bandbreite, in der man
tatsächlich einkauft, und *Bestellen bis* sagt, wie viel Zeit zum Vergleichen
bleibt. Wer eine echte Marktreihe will, ist mit einer veröffentlichten
Preisstatistik als Quelle besser bedient als mit einem abgegriffenen
Angebotsformular.
