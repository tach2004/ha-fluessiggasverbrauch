# Flüssiggasverbrauch für Home Assistant

Füllstand, Verbrauch, Kosten und eine **saisonal gerechnete Leer-Prognose** für
einen oberirdischen Flüssiggastank – gebaut auf den Gasverbrauchssensoren, die
die Heizung ohnehin schon liefert (hier: Viessmann Vitodens über die
ViCare-Integration).

Kein Füllstandssensor am Tank nötig: Der Füllstand wird aus dem letzten
bekannten Stand minus dem gemessenen Verbrauch fortgeschrieben und beim Tanken
oder beim Ablesen der Tankuhr wieder auf die Realität gesetzt.

![Vorschau der Karte](vorschau.png)

## Was drin ist

| Baustein | Datei | Zweck |
|---|---|---|
| **Package** | `packages/fluessiggas.yaml` | Helfer, Zähler, Sensoren, Skripte, Automationen |
| **Prognose-Makros** | `custom_templates/fluessiggas.jinja` | Monat-für-Monat-Simulation bis der Tank leer ist |
| **Karte** | `www/lpg-tank-card.js` | grafischer Tank, Restverlauf, Betankungsformular |
| **Dashboard** | `dashboards/gastank.yaml` | fertige Ansicht inkl. Einstellungsseite |
| **Statistik-Tool** | `tools/monatsprofil.py` | Monatsprofil aus der HA-Langzeitstatistik erzeugen |

## Schnellstart

1. `packages/`, `custom_templates/` und `www/` in den Home-Assistant-Konfigurationsordner kopieren.
2. In `configuration.yaml`:
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
3. In `packages/fluessiggas.yaml` die vier `# <<< ANPASSEN`-Zeilen auf die
   eigenen Gasverbrauchssensoren setzen.
4. Home Assistant neu starten.
5. Karte als Ressource eintragen: **Einstellungen → Dashboards → ⋮ → Ressourcen →
   Hinzufügen**, URL `/local/lpg-tank-card.js`, Typ *JavaScript-Modul*.
6. Einmal **„Gastank: Füllstand korrigieren"** ausführen und den aktuellen Wert
   der mechanischen Tankuhr eintragen. Ab jetzt läuft alles von selbst.

Ausführlich: [docs/INSTALLATION.md](docs/INSTALLATION.md).
Warum es so gebaut ist und was noch kommen könnte: [docs/KONZEPT.md](docs/KONZEPT.md).

## Kennzahlen dieses Tanks

| Größe | Wert |
|---|---|
| Nennvolumen | 4.850 L |
| Maximaler Füllgrad | 85 % → 4.122 L nutzbar |
| Energieinhalt | 7,0 kWh/L → **28.840 kWh** bei voller Füllung |
| Umrechnung | 1 m³ Gas ≈ 3,92 L Flüssiggas |

Alle vier Werte sind Helfer und lassen sich in der UI ändern – die Vorgaben
stammen aus Propan nach DIN 51622.

## Wichtigste Entitäten

| Entität | Bedeutung |
|---|---|
| `sensor.gastank_inhalt` | Füllstand in Litern |
| `sensor.gastank_inhalt_prozent` | wie die mechanische Tankuhr (% vom Nennvolumen) |
| `sensor.gastank_inhalt_nutzbar_prozent` | 100 % = randvoll getankt |
| `sensor.gastank_restenergie` | verbleibende kWh |
| `sensor.gastank_restwert` | Warenwert in EUR |
| `sensor.gastank_tagesverbrauch` | Ø Liter pro Tag seit der letzten Betankung |
| `sensor.gastank_reichweite` | Tage bis leer |
| `sensor.gastank_leer_am` | Datum, an dem der Tank rechnerisch leer ist |
| `sensor.gastank_reserve_erreicht_am` | Datum, an dem die Reserve erreicht wird |
| `sensor.gastank_bestellen_bis` | letzter sinnvoller Bestelltermin |
| `sensor.gastank_prognose` | Tage bis leer, Attribut `monate` enthält den Verlauf |

## Wie die Prognose rechnet

Ein Jahresmittel hilft nicht: Im Januar geht rund zehnmal so viel Gas weg wie im
Juli. Die Prognose nutzt deshalb ein **Monatsprofil** – zwölf Zahlen mit dem
erwarteten Verbrauch je Kalendermonat – und simuliert damit Monat für Monat in
die Zukunft, bis der Tank leer ist. Innerhalb des Monats wird linear
interpoliert, dadurch kommt ein taggenaues Datum heraus.

Das Profil pflegt sich selbst: Am ersten Tag jedes Monats trägt die Automation
*„Gastank: Monatsmittel lernen"* den Vormonat als gleitenden Mittelwert ein,
gewichtet über die eingestellte Anzahl Jahre. Mit `tools/monatsprofil.py` lässt
sich das Profil direkt aus der vorhandenen Langzeitstatistik befüllen, statt
zwei Winter zu warten.

## Selbstkalibrierung

Ob die m³ der Heizung wirklich 3,92 L Flüssiggas entsprechen, weiß man erst,
wenn man einmal nachgetankt hat. Deshalb hat das Betankungsformular ein Feld
*„Tankuhr direkt vor dem Tanken"*: Aus abgelesenem Verbrauch und gezählten m³
berechnet das Skript den tatsächlichen Faktor und schreibt ihn zurück. Nach der
ersten Betankung stimmt die Rechnung damit auf die eigene Anlage.

## Lizenz

MIT
