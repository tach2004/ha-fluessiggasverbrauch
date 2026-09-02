# Konzept & Entscheidungen

## Die Ausgangsfrage: eigene Integration oder direkt in Home Assistant?

Kurz: **beides – aber in dieser Reihenfolge.**

Die eigentliche Arbeit steckt nicht in der Technik drumherum, sondern in drei
Dingen: der Umrechnung m³ → Liter → kWh, dem saisonalen Verbrauchsmodell und
einer Karte, die den Tank vernünftig zeigt. Davon ist genau **eines** an die
Verpackung gebunden – die anderen beiden funktionieren in einem YAML-Package
identisch wie in einer Integration.

Deshalb Stufe 1 als Package:

* läuft heute, ohne HACS, ohne Python, ohne Custom Component
* jede Formel ist sichtbar und in fünf Sekunden änderbar
* die Umrechnungsfaktoren müssen sowieso erst an der eigenen Anlage kalibriert
  werden – das geht mit sichtbarem YAML deutlich schneller
* das Repo bleibt trotzdem die Quelle der Wahrheit, alles ist versioniert

Was eine echte Integration später wirklich besser könnte, steht unten unter
[Ausbaustufe 2](#ausbaustufe-2-echte-integration). Overengineered ist das Vorhaben
nicht – aber mit einer Integration **anzufangen** wäre der teurere Weg gewesen.

Die Karte (`www/lpg-tank-card.js`) ist bewusst unabhängig gebaut: Sie liest nur
Entitäten und ruft Skripte auf. Bei einem Umstieg auf eine Integration bleibt sie
unverändert.

## Das Rechenmodell

### Füllstand ohne Füllstandssensor

```
Füllstand [L] = Referenzstand [L] − Verbrauch seit Betankung [m³] × Faktor [L/m³]
```

Der Referenzstand kommt vom Menschen (Tankuhr ablesen oder Lieferschein), der
Verbrauch von der Heizung. Zwei `utility_meter` zählen Heizung und Warmwasser
seit der letzten Betankung; beim Eintragen einer Betankung werden sie per
`utility_meter.calibrate` auf 0 gesetzt.

Der Vorteil gegenüber einem Füllstandssensor am Tank: Es gibt keinen. Der
Nachteil: Der Wert driftet mit dem Umrechnungsfaktor. Deshalb die
Selbstkalibrierung bei jeder Betankung – nach dem ersten Tanken stimmt der
Faktor für die eigene Anlage.

### Die Zahlen hinter den Vorgaben

| Größe | Wert | Herkunft |
|---|---|---|
| Dichte flüssig | ca. 0,51 kg/L | Propan bei 15 °C |
| Gasdichte | ca. 2,0 kg/m³ | Propan im Normzustand |
| **1 m³ Gas** | **≈ 3,92 L flüssig** | 2,0 / 0,51 |
| Heizwert Hu | 12,87 kWh/kg = 6,57 kWh/L | |
| Brennwert Ho | 13,95 kWh/kg = 7,11 kWh/L | |
| **Vorgabe hier** | **7,0 kWh/L** | 4.120 L × 7,0 = 28.840 kWh |

Der 85-%-Grenzwert ist keine Marotte: Flüssiges Propan dehnt sich stark aus, der
Gasraum darüber ist Sicherheitsvolumen. Die mechanische Tankuhr zeigt Prozent
vom **Nennvolumen**, „voll" sind also 85 %. Die Karte zeigt beides:
`sensor.gastank_inhalt_prozent` entspricht der Tankuhr,
`sensor.gastank_inhalt_nutzbar_prozent` rechnet 100 % = randvoll getankt.

Ob die m³ der Heizung tatsächlich Normkubikmeter Propan sind, hängt von der
Brennerkonfiguration ab – die Heizung rechnet sie aus Brennerlaufzeit und
Düsenleistung hoch. Genau deshalb ist der Faktor ein Helfer und keine Konstante.

### Warum ein Monatsprofil und keine Wetterprognose

Ein simples „Restmenge ÷ Tagesdurchschnitt" ist im Sommer katastrophal
optimistisch und im Winter unnötig pessimistisch. Der Verbrauch schwankt über
das Jahr etwa um den Faktor 10.

Die Außentemperatur direkt heranzuziehen bringt dagegen nichts, weil niemand
weiß, wie kalt der Februar in 14 Monaten wird. Was man weiß: wie kalt der Februar
**üblicherweise** ist – und genau das steckt bereits im gemessenen
Monatsverbrauch der Vorjahre. Das Monatsprofil ist damit die empirische Variante
einer Gradtagzahl-Rechnung, nur ohne Zusatzdaten.

Die Simulation läuft Monat für Monat vorwärts:

```
Tagesrate im Monat m = Monatsmittel[m] × Korrekturfaktor / Tage im Monat
```

Restmenge abziehen, Monat weiterzählen, und sobald sie unter 0 fällt, im
angebrochenen Monat linear auf den Tag interpolieren. Ergebnis: ein konkretes
Datum, nicht nur „noch ca. 8 Monate". Nebenbei fällt der komplette Restverlauf
ab, den die Karte als Kurve zeichnet.

### Woher das Profil kommt

Drei Wege, in dieser Reihenfolge:

1. **Startwert:** typisches deutsches Heizprofil, skaliert auf 1.400 L/Jahr.
   Damit ist die Prognose ab Minute eins plausibel, wenn auch nicht persönlich.
2. **Aus der Historie:** `tools/monatsprofil.py` liest die Langzeitstatistik über
   die WebSocket-API, mittelt je Kalendermonat über *n* Jahre und schreibt das
   Ergebnis in den Helfer. Ab Juli 2024 vorhandene Daten reichen dafür aus.
3. **Selbstlernend:** Am ersten Tag jedes Monats trägt eine Automation den
   Vormonat als gleitenden Mittelwert nach:

   ```
   neu = alt + (gemessen − alt) / min(Zähler + 1, Jahre)
   ```

   `input_number.gastank_prognose_jahre` ist damit exakt die gewünschte
   Eingabemaske: 1 = nur das letzte Jahr zählt, 3 = über drei Jahre glätten.

`input_number.gastank_prognose_korrektur_prozent` skaliert das ganze Profil –
praktisch, wenn sich etwas Grundsätzliches geändert hat (neue Dämmung,
Wärmepumpe für die Übergangszeit, jemand zieht aus).

## Genauigkeit – womit man rechnen muss

| Fehlerquelle | Größenordnung | Gegenmittel |
|---|---|---|
| Umrechnungsfaktor L/m³ | bis ±10 % vor der ersten Kalibrierung | Tankuhr vor dem Tanken eintragen |
| Ablesegenauigkeit der Tankuhr | ±2 % vom Nennvolumen ≈ ±100 L | mehrfach über die Zeit korrigieren |
| Milder oder harter Winter | ±15 % beim Jahresverbrauch | Profil über mehrere Jahre mitteln |
| Zählung der Heizung selbst | 2–5 % | Kalibrierung fängt es mit ein |

Realistisch ist die Leer-Prognose damit ein Jahr im Voraus auf wenige Wochen
genau – für die Frage „muss ich diesen Herbst bestellen?" mehr als ausreichend.
Deshalb gibt es zusätzlich `sensor.gastank_bestellen_bis`: Reservedatum minus
Lieferzeit, das ist der Termin, der wirklich zählt.

## Ausbaustufen

### Ausbaustufe 1 – umgesetzt

Package, Prognose-Makros, Karte, Dashboard, Statistik-Tool, Warnmeldungen bei
Reserve und Bestellfrist.

### Ausbaustufe 2 – echte Integration

Lohnt sich, sobald Stufe 1 einen Winter lang stabil gelaufen ist. Was sie besser
kann:

* **Einrichtung per UI** (Config Flow): Tankdaten und Sensoren auswählen statt
  YAML editieren; Optionen später änderbar.
* **Statistik direkt lesen:** Das Monatsprofil käme bei jedem Neustart frisch aus
  dem Recorder, statt in zwei `input_text` zu leben. Das 255-Zeichen-Limit und
  die Lern-Automation entfielen.
* **Lieferhistorie als echtes Datenmodell:** Datum, Menge, Preis, Lieferant je
  Betankung – Grundlage für Preisentwicklung, Kosten je Heizperiode und einen
  ehrlichen Soll-Ist-Vergleich der letzten Prognose.
* **Mehrere Tanks / mehrere Häuser.**
* **HACS-fähig**, damit auch andere es installieren können.

Realistischer Aufwand: ein Wochenende für die Basis, plus Tests. Die Mathematik
wandert dabei 1:1 aus dem Jinja-Makro nach Python.

### Ausbaustufe 3 – Gradtagzahlen

Statt „Januar verbraucht üblicherweise 217 L" dann „Januar hat üblicherweise
520 Gradtage, wir verbrauchen 0,42 L je Gradtag". Vorteile:

* Der laufende Winter lässt sich mitkorrigieren: Sind bis Ende Dezember 15 % mehr
  Gradtage aufgelaufen als im Mittel, wird die Restprognose entsprechend
  angehoben – aus Vergangenheitsdaten, ohne Wetterprognose.
* Ein einzelner Ausreißerwinter verfälscht das Profil nicht mehr, weil er sich
  über die Gradtagzahl herausrechnet.

Nötig dafür: Historie der Außentemperatur (ist über die Heizung vorhanden) und
ein langjähriges Klimamittel für den Standort. Sinnvoll erst innerhalb der
Integration.

## Weitere Ideen für später

* **Kalendereintrag statt Push:** Bestelltermin automatisch in einen
  `local_calendar` schreiben – taucht dann im normalen Kalender auf.
* **Preisentwicklung:** je Lieferung €/L speichern, daraus ein Chart und der
  Vergleich „gut oder schlecht eingekauft".
* **Kosten je Heizperiode** (Juli–Juni statt Kalenderjahr) – die für Heizungen
  eigentlich richtige Betrachtung.
* **Soll-Ist-Vergleich der Prognose:** Was hat die Prognose vor 6 Monaten für
  heute vorhergesagt? Macht das Vertrauen in die Zahl messbar.
* **Warmwasser getrennt modellieren:** Warmwasser ist eine nahezu konstante
  Grundlast, Heizung ist saisonal. Getrennte Profile wären etwas genauer und
  würden zeigen, was der Sommerbetrieb kostet.
* **Anbindung ans Energie-Dashboard:** ein Verbrauchssensor in kWh aus den m³,
  damit Gas dort mit dem korrekten Flüssiggas-Energiegehalt und Preis auftaucht.
* **Vergleichbarkeit:** Verbrauch je Gradtag als Kennzahl über die Jahre – zeigt
  Dämmmaßnahmen und Heizungsoptimierungen sauberer als der reine Jahresverbrauch.
* **Zweite Meinung:** Wenn irgendwann doch ein Funk-Füllstandssensor am Tank
  hängt, wird er einfach zum dritten Weg, den Referenzstand zu setzen – das
  Modell bleibt gleich.
