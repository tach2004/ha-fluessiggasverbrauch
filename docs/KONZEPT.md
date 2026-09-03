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

Portale wie 123-fluessiggas.de haben keine offene Schnittstelle. Man müsste das
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
