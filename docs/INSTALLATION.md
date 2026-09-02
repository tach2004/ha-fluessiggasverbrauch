# Installation und Einrichtung

## 1. Integration installieren

### HACS

HACS → ⋮ → **Benutzerdefinierte Repositories**:

| Feld | Wert |
|---|---|
| Repository | `https://github.com/tach2004/ha-fluessiggasverbrauch` |
| Kategorie | Integration |

Dann „Flüssiggastank" herunterladen und Home Assistant neu starten.

### Von Hand

```bash
cd /config
git clone https://github.com/tach2004/ha-fluessiggasverbrauch.git .gastank
mkdir -p custom_components
cp -r .gastank/custom_components/fluessiggas custom_components/
```

Neu starten. Für Updates: `git -C /config/.gastank pull` und erneut kopieren.

## 2. Tank anlegen

**Einstellungen → Geräte & Dienste → Integration hinzufügen → Flüssiggastank**

### Schritt 1 – Tank und Quellen

| Feld | Hinweis |
|---|---|
| **Gasverbrauchs-Sensoren** | Die kumulativen Zähler deiner Heizung. Mehrere werden addiert – bei einer Viessmann typischerweise Heizgas und Warmwassergas. |
| **Einheit** | „Automatisch erkennen" nimmt die Einheit der Sensoren (m³, L oder kWh). |
| **Nennvolumen** | Gesamtvolumen laut Typenschild, z. B. 4850 L. |
| **Maximaler Füllgrad** | Bei Flüssiggas 85 %. |

Welche Sensoren die richtigen sind, siehst du unter **Entwicklerwerkzeuge →
Zustände**, Filter `gas`: gesucht sind die kumulativen Zähler, die auch im
Energie-Dashboard hinterlegt sind – typischerweise die Variante „dieses Jahr".

Dass diese Sensoren zum Jahreswechsel auf 0 zurückspringen, ist kein Problem:
Die Integration liest die Statistiksumme, in der Home Assistant Rückstellungen
bereits herausgerechnet hat.

> Achtung bei Viessmann: „Heizenergieverbrauch" ist der **Strom**verbrauch der
> Anlage, nicht das Gas. Nimm die Sensoren in m³.

### Schritt 2 – Umrechnung und Prognose

| Feld | Vorgabe | Hinweis |
|---|---|---|
| Liter je m³ Gas | 3,92 | Propan im Normzustand. Wird bei der ersten Betankung automatisch nachkalibriert. |
| Energieinhalt je Liter | 7,0 kWh | Heizwert 6,57 – Brennwert 7,11. |
| Gaspreis je Liter | – | Nur für die Wertanzeige. |
| Reserve | 400 L | Ab hier gilt der Tank als leer. |
| Vorlaufzeit | 21 d | Zeit vom Bestellen bis zum Tankwagen. |
| Mittelung über Jahre | 2 | Über wie viele Jahre je Kalendermonat gemittelt wird. |
| Korrekturfaktor | 100 % | Skaliert die ganze Prognose, z. B. nach einer Dämmung. |

Alles später unter **Konfigurieren** änderbar.

## 3. Füllstand einmalig setzen

Direkt nach dem Anlegen steht der Tank auf 0 L – die Integration weiß ja noch
nicht, was drin ist. Zwei Wege:

* **In der Karte:** oben rechts aufs Zapfsäulen-Symbol → *Tankuhr ablesen* →
  Prozentwert eintragen.
* **Als Dienst:** Entwicklerwerkzeuge → Aktionen →
  `fluessiggas.fuellstand_setzen`, Ziel = ein Sensor des Tanks, `prozent: 62`.

Damit ist der Bezugspunkt gesetzt und die Verbrauchszählung startet bei 0.

## 4. Karte ins Dashboard

Die Karte wird von der Integration automatisch ausgeliefert und angemeldet.
Falls sie im Kartenpicker fehlt: einmal Strg+F5.

```yaml
type: custom:lpg-tank-card
```

Ein vollständiges Dashboard mit Verlauf und Monatsprofil liegt in
[`dashboards/gastank.yaml`](../dashboards/gastank.yaml).

Die Entity-IDs folgen dem Tanknamen: Aus „Flüssiggastank" wird
`sensor.flussiggastank_fullstand` (Home Assistant macht aus „ü" ein „u").
Die Karte selbst braucht keine Entity-IDs.

## 5. Betankung eintragen

In der Karte aufs Zapfsäulen-Symbol, oder als Dienst `fluessiggas.betankung`:

| Fall | Eingabe |
|---|---|
| Voll getankt, Lieferschein da | `liter: 2500` |
| Nur 1.000 L getankt | `liter: 1000` – der neue Stand ist alter Stand + 1.000 |
| Tankuhr abgelesen | `fuellstand_nachher_prozent: 80` |
| Mit Kalibrierung | zusätzlich `fuellstand_vorher_prozent: 22` |
| Nachträglich | zusätzlich `datum: 2026-08-14` |
| Mit Preis | zusätzlich `preis_pro_liter: 0.677` |

Die Kalibrierung lohnt sich: Sie vergleicht den abgelesenen Verbrauch mit den
gezählten m³ und schreibt den echten Faktor zurück. Danach stimmt die Rechnung
für deine Anlage statt für die Norm.

## 6. Monatsprofil prüfen

Der Sensor **Jahresverbrauch** trägt die Attribute `monatsprofil` (Liter je
Monat) und `gemessene_jahre`. Steht dort überall eine 0, gab es noch keine
Statistik – dann ist die Kurve geschätzt. Mit
`fluessiggas.profil_neu_berechnen` liest die Integration sofort neu ein;
sonst passiert das alle sechs Stunden von allein.

## Fehlersuche

| Symptom | Ursache |
|---|---|
| Alle Sensoren `unavailable` | Für mindestens eine Quelle gibt es keine Statistik. Der Sensor braucht `state_class: total_increasing` oder `total`. |
| Füllstand bleibt 0 | Schritt 3 fehlt. |
| Füllstand sinkt nicht | Falscher Quellsensor – prüfe, ob *Verbrauch seit Betankung* steigt. |
| Füllstand sinkt zu schnell | Faktor L/m³ – bei der nächsten Betankung die Tankuhr vorher angeben. |
| Reichweite `unknown` | Rechnerisch mehr als sechs Jahre, oder Jahresverbrauch 0. |
| Karte nicht im Picker | Browser-Cache: Strg+F5. |
| „Keine Integration gefunden" | Der Tank ist noch nicht eingerichtet. |
| Meldung „Statistiksumme gesunken" | Die Statistik der Quelle wurde gelöscht oder neu aufgebaut; die Integration setzt den Bezugspunkt nach. Danach den Füllstand einmal korrigieren. |
