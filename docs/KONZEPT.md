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
