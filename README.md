# Flüssiggastank für Home Assistant

Eine Integration, die aus dem Gasverbrauch deiner Heizung den Füllstand eines
Flüssiggastanks fortschreibt – mit saisonaler Prognose, wann er leer ist, und
einer grafischen Karte fürs Dashboard.

**Kein Sensor am Tank nötig.** Der Füllstand ergibt sich aus dem letzten
bekannten Stand minus dem gemessenen Verbrauch; beim Tanken oder beim Ablesen
der Tankuhr wird er wieder auf die Realität gesetzt.

![Die Karte in drei Füllzuständen](vorschau.png)

## Installation

### Über HACS (empfohlen)

1. HACS → ⋮ → **Benutzerdefinierte Repositories** → `https://github.com/tach2004/ha-fluessiggasverbrauch`, Kategorie **Integration**.
2. „Flüssiggastank" herunterladen, Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Flüssiggastank**.

### Von Hand

Ordner `custom_components/fluessiggas` nach `<config>/custom_components/`
kopieren und neu starten.

Die Lovelace-Karte bringt die Integration mit und meldet sie selbst an – ein
Eintrag unter *Dashboards → Ressourcen* ist **nicht** nötig. Sie trägt sich
dafür als Ressource ein und entfernt den Eintrag wieder, wenn der letzte Tank
gelöscht wird.

## Einrichtung

Alles läuft über die Oberfläche, es gibt kein YAML zu editieren:

| Schritt 1 | Schritt 2 |
|---|---|
| Verbrauchssensoren auswählen (mehrere werden addiert) | Umrechnung m³ → Liter |
| Einheit (automatisch erkannt: m³, L oder kWh) | Energieinhalt je Liter |
| Nennvolumen des Tanks | Gaspreis je Liter |
| Maximaler Füllgrad (bei Flüssiggas 85 %) | Reserve, Vorlaufzeit, Prognosejahre, Abfrageintervall |

Danach einmal den Dienst **Füllstand setzen** mit dem abgelesenen Wert der
mechanischen Tankuhr aufrufen – oder in der Karte oben rechts aufs
Zapfsäulen-Symbol. Ab da läuft alles allein.

Alle Werte sind später unter **Konfigurieren** änderbar.

## Die Karte

```yaml
type: custom:lpg-tank-card
```

Mehr braucht es nicht: Die Karte erkennt den Tank an Attributen, die die
Integration setzt – unabhängig von Sprache und Entity-IDs.

```yaml
type: custom:lpg-tank-card
tank: Gartenhaus       # nur nötig, wenn mehrere Tanks eingerichtet sind
verlauf: true          # Restverlauf der kommenden Monate
preisverlauf: true     # Preisentwicklung der eingetragenen Lieferungen
jahr: true             # Verbrauch des laufenden Jahres in L, m³ und kWh
betankung: true        # Betankungsformular
wellen: true           # Wellenanimation
```

Die Farbe des Tanks steuert die Integration, nicht die Karte: **rot**, sobald die
Reserve erreicht ist, **gelb** unterhalb der einstellbaren *Warnschwelle*
(Vorgabe 30 % der Tankuhr). Rot hat bewusst keine eigene Einstellung – sonst
könnten Farbe und Bestellfrist auseinanderlaufen.

Im Preisdiagramm trägt jede Betankung ihr Datum an der Achse, und ein Zeiger
darüber – Maus oder Finger – blendet ein Fadenkreuz mit Datum, Preis und
Liefermenge ein, wie in den Verlaufsdiagrammen von Home Assistant.

Die Karte zeigt sechs Kennzahlen unter dem Tank – Restenergie, Ø Verbrauch,
Verbrauch seit der Betankung, **Reserve erreicht**, voraussichtlich leer und
Bestellfrist. Beim Ø Verbrauch steht der erwartete Jahresverbrauch in Litern
*und* Kubikmetern.

Darunter der **Verbrauch des laufenden Kalenderjahres** in Litern, m³ und kWh –
drei anklickbare Felder, hinter jedem steckt eine eigene Entität mit
Langzeitstatistik. Daneben, was das Monatsprofil bis heute erwartet hätte:
`erwartet bis heute 1.180 L (+6 %)`. Bewusst keine Prozentangabe „vom Jahr" –
der verheizte Anteil läuft dem Kalender erst voraus und dann nachher (Anfang
Mai knapp 49 % bei einem Drittel Kalenderjahr, Anfang November 70 % bei 83 %).

Zuletzt die Preisentwicklung, sobald zwei Lieferungen mit Preis eingetragen sind.

Eine Kachel *Reichweite* gab es bis Version 1.6 auch. Die Tage stehen aber schon
unter „Reserve erreicht" und „Voraussichtlich leer" – der Sensor bleibt, nur die
Kachel ist weg.

## Entitäten

Je Tank entsteht ein Gerät mit 18 Sensoren:

| Sensor | Bedeutung |
|---|---|
| Füllstand | Liter im Tank |
| Tankuhr | % vom Nennvolumen – wie die mechanische Anzeige |
| Füllung | % der nutzbaren Menge, 100 % = randvoll getankt |
| Restenergie / Restwert | kWh und EUR |
| Gaspreis | EUR/L, mit Langzeitstatistik – daraus wird der Preisverlauf |
| Umrechnungsfaktor | L/m³, der gerade gültige Wert – siehe unten |
| Verbrauch seit Betankung | Liter seit dem letzten Bezugspunkt |
| Tagesverbrauch | Ø Liter pro Tag |
| Verbrauch dieses Jahr | Liter im laufenden Kalenderjahr – siehe unten |
| Verbrauch dieses Jahr (m³) | dasselbe in Kubikmetern |
| Verbrauch dieses Jahr (kWh) | dasselbe in Kilowattstunden |
| Erwarteter Jahresverbrauch | aus dem Monatsprofil, Attribut `monatsprofil` |
| Reichweite | Tage bis leer, Attribut `monate` mit dem Verlauf |
| Leer am / Reserve erreicht am / Bestellen bis | konkrete Daten |
| Letzte Betankung | Datum, Attribut `lieferungen` mit der Historie |

Dazu kommt die Zahl **Gaspreis** (EUR/L) zum Eintragen – außer du hast in der
Konfiguration einen eigenen Preis-Helfer angegeben, dann bleibt deiner die Quelle.

### Verbrauch dieses Jahr

Drei Entitäten für dieselbe Menge, weil Home Assistant für jede eine eigene
Langzeitstatistik führt – so lässt sich jede einzeln anklicken und über die
Jahre hinweg ansehen.

Gerechnet wird als Differenz der Statistiksumme zum Stand am 1. Januar 00:00
Uhr. Das kostet **eine Datenbankabfrage im Jahr**: Der Bezugspunkt steht fest,
sobald das Jahr begonnen hat, und der Rest ist eine Subtraktion von der Summe,
die für den Füllstand ohnehin gelesen wird.

Attribute am Liter-Sensor:

| Attribut | Bedeutung |
|---|---|
| `jahr` / `seit` | welches Jahr, und ab wann gezählt wird |
| `erwartet_bis_heute` | was das Monatsprofil bis heute erwartet hätte |
| `quellen` | je Zähler: Einheit, `state_class` und der verwendete Liter-Faktor |

Die drei Sensoren tragen `state_class: total` und melden den 1. Januar als
`last_reset`. Home Assistant muss den Jahreswechsel damit nicht aus einem
Rückgang erraten – siehe [KONZEPT](docs/KONZEPT.md#jahreszähler-die-auf-0-zurückfallen).

### Umrechnungsfaktor

Der Wert, mit dem aus den m³ deiner Heizung Liter Flüssiggas werden. Er steht
in der Konfiguration, kalibriert sich aber bei jeder Betankung mit
Tankuhr-Angabe selbst nach – deshalb gibt es ihn auch als Sensor: Als Messwert
zeichnet Home Assistant ihn auf, und der Sprung nach einer Nachkalibrierung
wird im Verlauf sichtbar.

| Attribut | Bedeutung |
|---|---|
| `quelle` | `Kalibrierung`, wenn der Wert gemessen ist, sonst `Konfiguration` |
| `kalibriert_am` / `vorher` | wann zuletzt, und von welchem Wert aus |
| `kalibrierungen` | wie oft bisher |
| `kalibrierbar` | ob deine Zähler in m³ zählen – nur dann geht es überhaupt |
| `abweichung_von_der_norm_prozent` | Abstand zu den 3,92 L/m³ nach DIN |
| `kwh_pro_liter` | die zweite Umrechnung, für die Energieanzeige |

In der Karte steht er unten in der Fußzeile, sobald deine Zähler in m³ zählen,
und die Zeile im Reiter *Korrigieren* zeigt bei einer Betankung, die ihn
verstellt hat, den Sprung: `kalibriert 3,920 → 3,870 L/m³`.

## Dienste

| Dienst | Zweck |
|---|---|
| `fluessiggas.betankung` | Lieferung eintragen – auch eine Teilbetankung |
| `fluessiggas.fuellstand_setzen` | Tankuhr abgelesen, Zählung neu starten |
| `fluessiggas.lieferung_nachtragen` | Zurückliegende Lieferung nur in die Historie schreiben |
| `fluessiggas.lieferung_loeschen` | Einen Eintrag aus der Lieferhistorie entfernen |
| `fluessiggas.rueckgaengig` | Die letzte Änderung zurücknehmen, bis zu zehn Schritte weit |
| `fluessiggas.profil_neu_berechnen` | Monatsprofil sofort neu aus der Statistik lesen |

### Teilbetankung

Der neue Stand ist **Stand davor + Liefermenge**, nicht „voll". Wer 1.000 L auf
einen halbleeren Tank tankt, landet auch bei halbleer plus 1.000 L. Drei
Angaben, alle optional kombinierbar:

* `liter` – Liefermenge laut Lieferschein
* `fuellstand_vorher_prozent` – Tankuhr vor der Lieferung; damit kalibriert
  sich die Umrechnung m³ → Liter automatisch an deiner Anlage
* `fuellstand_nachher_prozent` – Tankuhr danach; hat Vorrang, weil direkt gemessen

`datum` trägt eine Betankung auch nachträglich ein: Die Integration holt sich
die Statistiksumme von genau diesem Tag, der Verbrauch danach bleibt korrekt.

### Alte Lieferungen nachtragen

Für den Preisverlauf möchte man oft Lieferungen von früher eintragen. Dafür gibt
es `fluessiggas.lieferung_nachtragen` mit Datum, Liefermenge und Preis: Der
Eintrag landet **nur** in der Historie, Füllstand und Bezugspunkt bleiben
unangetastet. `betankung` mit altem Datum würde dagegen den aktuellen Stand neu
berechnen – zum Nachtragen ist sie deshalb der falsche Dienst.

In der Karte sitzt das als dritter Reiter im Betankungsformular:
**Getankt · Tankuhr · Nachtragen · Korrigieren**.

### Vertippt? Zwei Wege zurück

Der vierte Reiter **Korrigieren** listet die eingetragenen Lieferungen, jüngste
zuerst. Beide Wege gibt es auch als Dienst, falls du lieber automatisierst.

**Rückgängig** (`fluessiggas.rueckgaengig`) nimmt die letzte Änderung komplett
zurück – Betankung, Tankuhr, Nachtrag oder Löschung, jeweils samt Füllstand und
Bezugspunkt der Zählung. Zehn Schritte weit. Das ist der Weg für „Ich habe mich
beim Tanken vertippt".

Und zwar auch dann noch, wenn es erst Tage später auffällt: Zurückgeholt wird
nicht der damalige Füllstand, sondern der damalige *Bezugspunkt*. Der Stand
rechnet sich daraus neu auf, der Verbrauch der Zwischenzeit bleibt also drin.

**Löschen** (`fluessiggas.lieferung_loeschen`, das ✕ in der Zeile) entfernt
einen Eintrag nur aus der Historie und damit aus dem Preisverlauf. Der Füllstand
bleibt, wie er ist – der hängt nicht an dieser Liste, sondern am Referenzstand.
Gedacht ist das für falsch nachgetragene alte Lieferungen.

Jeder Eintrag hat eine Kennung (`id`), zu sehen im Attribut `lieferungen` des
Sensors *Letzte Betankung*. Damit trifft der Dienst genau einen Eintrag, auch
wenn zwei Lieferungen auf denselben Tag fallen. `datum` trifft stattdessen alle
Einträge dieses Tages, `alle: true` leert die Historie.

Ein Sonderfall bleibt: Ist der Gaspreis an einen eigenen Helfer
(`input_number`) gebunden, schreibt eine Betankung ihren Preis dorthin. Das
Rückgängig fasst fremde Entitäten nicht an – den Helfer stellst du bei Bedarf
selbst zurück.

## Gaspreis

Der Preis ist immer **EUR je Liter** – in der Anzeige wie in der Eingabe.

* **Ohne eigenen Helfer** legt die Integration die Zahl *Gaspreis* an.
* **Mit eigenem Helfer** (Feld *Vorhandener Preis-Helfer*) bleibt deine
  `input_number` die Quelle. Steht sie in EUR/m³, rechnet die Integration mit dem
  konfigurierten Faktor selbst in Liter um.

> Der Helfer muss eine **beschreibbare Zahl** sein – eine `input_number` oder
> eine `number`-Entität. Ein **Template-Sensor funktioniert nicht**: Der
> berechnet sich selbst, lässt sich nicht setzen, und ein beim Tanken
> eingegebener Preis liefe dort ins Leere. Die Auswahl im Einrichtungsdialog
> zeigt deshalb nur die beiden zulässigen Domains an.

In beiden Fällen gibt es zusätzlich den **Sensor** *Gaspreis* mit
`state_class: measurement`. Anders als eine `input_number` landet der in der
Langzeitstatistik – der Preisverlauf bleibt damit über Jahre erhalten.

Änderst du deinen Helfer von Hand, folgt die Integration **sofort**: Sie hört
auf die Entität, statt auf den nächsten Durchlauf zu warten. Preis-Sensor und
Restwert sind unmittelbar aktuell.

Trägst du beim Tanken einen Preis ein, wird er in den Helfer zurückgeschrieben.
Jede Lieferung landet mit Datum, Menge, Preis und Kosten in der Historie – und
zwar als **fester Schnappschuss**: Der Preis einer vergangenen Lieferung ändert
sich nie mehr, auch wenn der aktuelle Gaspreis später steigt oder fällt. Genau
das macht die Preisentwicklung in der Karte aussagekräftig.

### Preisverlauf aus vorhandener Statistik

Wer schon einen Preis-Sensor mit Langzeitstatistik pflegt – etwa für das
Energiedashboard –, trägt ihn im Feld *Preis-Statistik* ein. Die Karte zeichnet
den Verlauf dann aus dessen Historie statt aus den Lieferungen.

Die Einheit wird dabei erkannt und umgerechnet – aus den Statistik-Metadaten,
nicht aus der Anzeige:

| Einheit | Umrechnung |
|---|---|
| `EUR/L`, `€/L`, ohne Einheit | unverändert |
| `EUR/m³` | geteilt durch den Faktor L/m³ |
| `EUR/kWh` | mal dem Energieinhalt je Liter |
| `ct/…` | zusätzlich durch 100 |

Alles andere – etwa `EUR/kg` oder das mehrdeutige `kWh/m³` – wird **nicht**
stillschweigend geraten: Die Integration nimmt EUR/L an und schreibt eine
Warnung ins Log, damit eine falsche Einheit auffällt. Dieselbe Erkennung gilt
für den Preis-Helfer, auch beim Zurückschreiben. Die eingetragenen Betankungen liegen als Punkte auf
der Linie: Man sieht auf einen Blick, ob man über oder unter dem Verlauf gekauft
hat.

Der Sensor wird dabei **ausschließlich gelesen** und nie verändert – Sensoren
lassen sich in Home Assistant grundsätzlich nicht beschreiben. Den Preis selbst
setzt weiterhin der Preis-Helfer. Ohne Eintrag bleibt alles wie gehabt und die
Karte zeichnet die Lieferungen.

## Wie die Prognose rechnet

Ein Tagesdurchschnitt taugt nicht – im Januar geht rund zehnmal so viel weg wie
im Juli. Die Integration liest deshalb den Monatsverbrauch der letzten Jahre aus
der Langzeitstatistik, mittelt ihn je Kalendermonat und simuliert damit Monat
für Monat in die Zukunft. Innerhalb des angebrochenen Monats wird linear
interpoliert – heraus kommt ein Datum, kein „ungefähr acht Monate".

Monate ohne Messwerte werden nicht mit 0 angesetzt, sondern über die Form einer
typischen Heizkurve ergänzt und auf das Niveau der gemessenen Monate skaliert.
Dadurch ist die Prognose schon nach einer halben Heizperiode brauchbar.

Details und die Entscheidungen dahinter: [docs/KONZEPT.md](docs/KONZEPT.md).

## Vorgaben für Propan (DIN 51622)

| Größe | Wert |
|---|---|
| 1 m³ Gas | ≈ 3,92 L flüssig |
| Energieinhalt | 7,0 kWh/L (Heizwert 6,57 / Brennwert 7,11) |
| Maximaler Füllgrad | 85 % – der Rest ist Ausdehnungsraum |
| Reserve (Vorgabe) | 970 L = 20 % vom Nennvolumen |
| Warnschwelle (Vorgabe) | 30 % der Tankuhr |

Beispiel: 4.850 L Nennvolumen → 4.122 L nutzbar → rund **28.800 kWh**.

## Logo

Home Assistant lädt Integrations-Logos ausschließlich von
`brands.home-assistant.io`; eine custom integration kann ihres nicht
mitliefern. Das fertige Symbol liegt in [`brands/`](brands/) samt Anleitung zum
Eintragen. Die Symbole der Entitäten und Dienste bestimmt die Integration
dagegen selbst – die wirken sofort.

## Entwicklung

Die Karte wird vorkomprimiert mit ausgeliefert – aiohttp nimmt das
`.gz`-Geschwisterfile automatisch, sobald der Browser gzip akzeptiert. Nach
jeder Änderung an `lpg-tank-card.js` deshalb:

```bash
python3 scripts/karte_komprimieren.py
```

Ein Test vergleicht das Archiv byteweise mit der Karte und schlägt fehl, wenn
es veraltet ist.

## Tests

```bash
python3 tests/test_forecast.py           # Prognoserechnung
python3 tests/test_units.py              # Preiseinheiten und Umrechnung
python3 tests/test_integration_files.py  # Manifest, Dienste, Icons, Übersetzungen
```

## Lizenz

MIT
