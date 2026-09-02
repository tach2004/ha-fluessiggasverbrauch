# Installation

## 1. Dateien kopieren

In den Home-Assistant-Konfigurationsordner (dort, wo `configuration.yaml` liegt):

```
config/
├── configuration.yaml
├── packages/
│   └── fluessiggas.yaml
├── custom_templates/
│   └── fluessiggas.jinja
└── www/
    └── lpg-tank-card.js
```

Per Terminal-Add-on oder Samba, oder direkt im Ordner klonen:

```bash
cd /config
git clone https://github.com/tach2004/ha-fluessiggasverbrauch.git .gastank
mkdir -p packages custom_templates www
cp .gastank/packages/fluessiggas.yaml        packages/
cp .gastank/custom_templates/fluessiggas.jinja custom_templates/
cp .gastank/www/lpg-tank-card.js             www/
```

Für Updates später einfach `git -C /config/.gastank pull` und erneut kopieren.

## 2. Package aktivieren

In `configuration.yaml` – falls noch nicht vorhanden:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

> Hinweis: Wenn `automation:` in der `configuration.yaml` bereits als
> `automation: !include automations.yaml` eingebunden ist, funktioniert die
> Zusammenführung mit dem Package problemlos. Nur eine zweite *Liste* direkt in
> der `configuration.yaml` würde kollidieren.

## 3. Quellsensoren eintragen

In `packages/fluessiggas.yaml` stehen ganz oben vier Zeilen mit
`# <<< ANPASSEN`. Dort gehören die beiden Gasverbrauchssensoren der Heizung
hinein (jeweils zweimal – einmal für den Zähler seit der Betankung, einmal für
den Monatszähler).

Die eigenen IDs findest du unter **Entwicklerwerkzeuge → Zustände**, Filter
`gas`. Gesucht sind die kumulativen Zähler in m³, also die Entitäten, die auch
im Energie-Dashboard hinterlegt sind – typischerweise die Variante *„dieses
Jahr"*:

```
sensor.<geraet>_heizgasverbrauch_dieses_jahr
sensor.<geraet>_warmwasser_gasverbrauch_dieses_jahr
```

Dass diese Sensoren zum Jahreswechsel auf 0 zurückspringen, ist kein Problem:
Der `utility_meter` erkennt den Rücksprung und zählt normal weiter.

Wer nur *einen* Gassensor hat, trägt bei den Warmwasser-Zählern einfach
denselben Sensor **nicht** ein, sondern löscht die beiden Warmwasser-Blöcke und
entfernt sie aus dem Sensor `Gasverbrauch seit Betankung`.

## 4. Neu starten und prüfen

**Entwicklerwerkzeuge → YAML → Konfiguration prüfen**, danach neu starten.

Nach dem Start sollte es geben:

* `sensor.gastank_inhalt` (anfangs 0 L – das ist richtig, siehe Schritt 6)
* `sensor.gasverbrauch_seit_betankung`
* die Skripte `script.gastank_betankung` und `script.gastank_fuellstand_korrigieren`

Wenn `sensor.gastank_prognose` `unavailable` ist: Die Jinja-Makros wurden nicht
gefunden. Prüfen, ob `custom_templates/fluessiggas.jinja` existiert, dann
**Entwicklerwerkzeuge → YAML → Jinja2-Templates neu laden**.

## 5. Karte einbinden

**Einstellungen → Dashboards → ⋮ (oben rechts) → Ressourcen → Ressource hinzufügen**

| Feld | Wert |
|---|---|
| URL | `/local/lpg-tank-card.js` |
| Typ | JavaScript-Modul |

Danach den Browser-Cache leeren (Strg+F5). Im Dashboard:

```yaml
type: custom:lpg-tank-card
```

Alle Optionen sind vorbelegt; anpassbar sind unter anderem:

```yaml
type: custom:lpg-tank-card
name: Flüssiggastank
warn_prozent: 25      # ab hier gelb (% der nutzbaren Füllung)
alarm_prozent: 12     # ab hier rot
verlauf: true         # Restverlauf-Diagramm zeigen
betankung: true       # Betankungsformular anbieten
wellen: true          # Wellenanimation
```

Ein komplettes Dashboard liegt in [`dashboards/gastank.yaml`](../dashboards/gastank.yaml).

## 6. Einmalig einrichten

1. **Tankuhr ablesen.** Skript `Gastank: Füllstand korrigieren` ausführen und
   den abgelesenen Prozentwert eintragen (oder in der Karte oben rechts auf das
   Zapfsäulen-Symbol → *Tankuhr ablesen*).
   Das setzt den Referenzstand und startet die Verbrauchszählung bei 0.
2. **Preis prüfen:** `input_number.gastank_preis_pro_liter`.
3. **Monatsprofil befüllen** (optional, aber empfohlen – siehe unten).

## 7. Monatsprofil aus der Historie befüllen

Ohne eigene Daten startet die Prognose mit einem typischen deutschen Heizprofil
und 1.400 L Jahresverbrauch. Wer schon Statistiken hat, sollte sie nutzen:

```bash
pip install websockets
python3 tools/monatsprofil.py \
  --url http://homeassistant.local:8123 \
  --token <Langlebiges Zugriffstoken aus Profil → Sicherheit> \
  --entities sensor.<heizgas_dieses_jahr> sensor.<warmwassergas_dieses_jahr> \
  --jahre 2 \
  --schreiben
```

Das Skript liest die Langzeitstatistik, mittelt je Kalendermonat über die
gewünschte Anzahl Jahre, rechnet m³ in Liter um und schreibt das Ergebnis in
`input_text.gastank_monatsmittel_liter`.

Ohne `--schreiben` gibt es die Werte nur aus – die kann man dann per Skript
`Gastank: Monatsprofil setzen` oder direkt im Helfer eintragen.

Monate ohne Daten bekommen 0 L. Bei Historie ab Juli 2024 fehlt also nichts
mehr, sobald ein voller Jahreszyklus vorliegt; bis dahin die Lücken von Hand
mit plausiblen Werten füllen.

## 8. Betankung eintragen

Wenn der Tankwagen da war – in der Karte auf das Zapfsäulen-Symbol:

* **Getankte Menge:** Liter laut Lieferschein.
  Zusätzlich möglichst den Wert der Tankuhr **vor** dem Tanken eintragen – damit
  kalibriert sich die Umrechnung m³ → Liter automatisch nach.
* **Tankuhr ablesen:** einfach den neuen Prozentwert, ohne Liefermenge.

Beides setzt den Referenzstand neu und stellt die Verbrauchszähler auf 0.

## Fehlersuche

| Symptom | Ursache |
|---|---|
| `sensor.gastank_inhalt` bleibt 0 | Schritt 6 noch nicht gemacht |
| Füllstand sinkt nicht | Quellsensor falsch – prüfen, ob `sensor.gasverbrauch_seit_betankung` steigt |
| Füllstand sinkt zu schnell/langsam | Faktor `input_number.gastank_liter_pro_m3` – bei der nächsten Betankung kalibrieren lassen |
| `sensor.gastank_prognose` = `unknown` | Monatsprofil ergibt Jahresverbrauch 0 oder Reichweite > 6 Jahre |
| Karte zeigt „Entität nicht gefunden" | Package nicht geladen oder Sensoren anders benannt |
| Karte lädt gar nicht | Ressource fehlt oder Browser-Cache – Strg+F5 |
