"""Prüft, dass Manifest, Dienste, Sensoren und Übersetzungen zusammenpassen.

    python3 tests/test_integration_files.py     (oder: pytest tests/)
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

WURZEL = Path(__file__).resolve().parent.parent
INTEGRATION = WURZEL / "custom_components" / "fluessiggas"
SPRACHEN = ["de", "en"]


def _json(pfad: Path) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8"))


def _quelltext(name: str) -> str:
    return (INTEGRATION / name).read_text(encoding="utf-8")


def test_manifest_ist_die_einzige_versionsquelle():
    """Die Version darf nur in der manifest.json stehen.

    Stand sie zusätzlich im Code, zeigten Geräteinfo und Karten-URL nach einem
    Release die alte Nummer, bis jemand daran denkt - genau das ist passiert.
    """
    manifest = _json(INTEGRATION / "manifest.json")
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"]), manifest["version"]
    assert manifest["domain"] == "fluessiggas"
    assert set(manifest["dependencies"]) >= {"recorder", "http", "frontend"}

    for datei in ("const.py", "sensor.py", "number.py", "__init__.py"):
        assert 'VERSION: Final = "' not in _quelltext(datei), datei
        assert not re.search(r'=\s*"\d+\.\d+\.\d+"', _quelltext(datei)), (
            f"{datei} enthält eine fest verdrahtete Version"
        )

    # Gelesen wird sie beim Start aus der Integration selbst
    assert "async_get_integration" in _quelltext("__init__.py")
    assert "DATA_VERSION" in _quelltext("const.py")

    # Auch die Karte pflegt keine eigene Nummer, sondern liest sie aus ihrer URL
    karte = (INTEGRATION / "frontend" / "lpg-tank-card.js").read_text(encoding="utf-8")
    assert "import.meta.url" in karte
    assert not re.search(r'LPG_VERSION = "\d+\.\d+\.\d+"', karte)


def test_alle_sensoren_sind_uebersetzt():
    schluessel = set(re.findall(r'translation_key="([a-z_]+)"', _quelltext("sensor.py")))
    assert len(schluessel) >= 13, schluessel
    for sprache in SPRACHEN:
        texte = _json(INTEGRATION / "translations" / f"{sprache}.json")["entity"]["sensor"]
        assert schluessel <= set(texte), (sprache, schluessel - set(texte))
        assert set(texte) <= schluessel, (sprache, set(texte) - schluessel)


def test_dienste_und_felder_sind_uebersetzt():
    dienste = yaml.safe_load((INTEGRATION / "services.yaml").read_text(encoding="utf-8"))
    for sprache in SPRACHEN:
        texte = _json(INTEGRATION / "translations" / f"{sprache}.json")["services"]
        assert set(dienste) == set(texte), (sprache, set(dienste) ^ set(texte))
        for name, aufbau in dienste.items():
            felder = set((aufbau or {}).get("fields", {}))
            uebersetzt = set(texte[name].get("fields", {}))
            assert felder == uebersetzt, (sprache, name, felder ^ uebersetzt)


def test_dienstnamen_stimmen_mit_dem_code_ueberein():
    dienste = set(yaml.safe_load((INTEGRATION / "services.yaml").read_text(encoding="utf-8")))
    const = _quelltext("const.py")
    im_code = set(re.findall(r'SERVICE_\w+: Final = "([a-z_]+)"', const))
    assert dienste == im_code, dienste ^ im_code

    # Die Feldnamen der Dienste müssen den ATTR_-Konstanten entsprechen
    attribute = set(re.findall(r'ATTR_\w+: Final = "([a-z_]+)"', const))
    felder = set()
    for aufbau in yaml.safe_load(
        (INTEGRATION / "services.yaml").read_text(encoding="utf-8")
    ).values():
        felder |= set((aufbau or {}).get("fields", {}))
    assert felder <= attribute, felder - attribute


def test_jeder_dienst_ist_auch_registriert():
    """services.yaml beschreibt nur die Oberfläche – ohne Registrierung passiert nichts."""
    dienste = set(yaml.safe_load((INTEGRATION / "services.yaml").read_text(encoding="utf-8")))
    const = _quelltext("const.py")
    quelle = _quelltext("__init__.py")
    for name in dienste:
        konstante = next(
            k for k, v in re.findall(r'(SERVICE_\w+): Final = "([a-z_]+)"', const)
            if v == name
        )
        assert re.search(rf"async_register\(\s*\n?\s*DOMAIN, {konstante}\b", quelle), name


def test_datenbank_wird_nur_im_koordinator_gelesen():
    """Alle Statistikabfragen an einer Stelle – sonst ist die Last nicht mehr abschätzbar."""
    abfragen = ("statistics_during_period", "get_last_short_term_statistics",
                "async_list_statistic_ids")
    for datei in ("__init__.py", "sensor.py", "number.py", "config_flow.py", "history.py"):
        for abfrage in abfragen:
            assert abfrage not in _quelltext(datei), (datei, abfrage)

    koordinator = _quelltext("coordinator.py")
    # Jede Abfrage läuft über den Recorder-Thread, nie über eine eigene Verbindung
    assert koordinator.count("async_add_executor_job") == koordinator.count(
        "recorder.async_add_executor_job"
    )
    # Geschrieben wird in die Datenbank nichts
    for verboten in ("session.add", "DELETE FROM", "execute(", "async_purge"):
        assert verboten not in koordinator, verboten


def test_regelmaessige_abfrage_geht_ueber_den_zwischenspeicher():
    """Der Aktualisierungspfad darf nicht an der Ersparnis vorbeilesen."""
    koordinator = _quelltext("coordinator.py")
    pfad = koordinator[koordinator.index("async def _async_update_data"):]
    pfad = pfad[: pfad.index("    def _profil_anfordern")]
    assert "await self._async_sums()" in pfad
    assert "_async_current_sums" not in pfad

    # Die teuren Abfragen laufen nebenher, nicht im Aktualisierungspfad
    for teuer in ("_async_read_profile", "_async_read_price_history"):
        assert teuer not in pfad, teuer


def test_konfigurationsfelder_sind_beschriftet():
    const = _quelltext("const.py")
    schluessel = set(re.findall(r'CONF_\w+: Final = "([a-z_0-9]+)"', const))
    schluessel.discard("source_unit_placeholder")
    for sprache in SPRACHEN:
        texte = _json(INTEGRATION / "translations" / f"{sprache}.json")
        beschriftet = set(texte["options"]["step"]["init"]["data"])
        assert schluessel == beschriftet, (sprache, schluessel ^ beschriftet)


def test_einheitenauswahl_ist_uebersetzt():
    const = _quelltext("const.py")
    einheiten = set(re.findall(r'UNIT_\w+: Final = "([a-z0-9]+)"', const))
    for sprache in SPRACHEN:
        texte = _json(INTEGRATION / "translations" / f"{sprache}.json")
        optionen = set(texte["selector"]["source_unit"]["options"])
        assert einheiten == optionen, (sprache, einheiten ^ optionen)


def test_icons_decken_alle_entitaeten_und_dienste_ab():
    icons = _json(INTEGRATION / "icons.json")
    sensoren = set(re.findall(r'translation_key="([a-z_]+)"', _quelltext("sensor.py")))
    assert set(icons["entity"]["sensor"]) == sensoren, (
        set(icons["entity"]["sensor"]) ^ sensoren
    )

    nummern = set(re.findall(r'_attr_translation_key = "([a-z_]+)"', _quelltext("number.py")))
    assert set(icons["entity"]["number"]) == nummern, (
        set(icons["entity"]["number"]) ^ nummern
    )

    dienste = set(yaml.safe_load((INTEGRATION / "services.yaml").read_text(encoding="utf-8")))
    assert set(icons["services"]) == dienste, set(icons["services"]) ^ dienste

    # Icons gehören in icons.json, nicht mehr in die Entitätsbeschreibung
    assert 'icon="mdi:' not in _quelltext("sensor.py")


def test_number_entitaet_ist_uebersetzt():
    nummern = set(re.findall(r'_attr_translation_key = "([a-z_]+)"', _quelltext("number.py")))
    assert nummern, "number.py sollte einen translation_key setzen"
    for sprache in SPRACHEN:
        texte = _json(INTEGRATION / "translations" / f"{sprache}.json")["entity"]
        assert set(texte.get("number", {})) == nummern, sprache


def test_karte_kennt_alle_entitaetskennungen():
    """Die Karte findet ihre Werte über die Kennungen – sie müssen vollständig sein."""
    karte = (INTEGRATION / "frontend" / "lpg-tank-card.js").read_text(encoding="utf-8")
    block = re.search(r"const KENNUNGEN = \[(.*?)\];", karte, re.S).group(1)
    in_karte = set(re.findall(r'"([a-z_]+)"', block))
    sensoren = set(re.findall(r'translation_key="([a-z_]+)"', _quelltext("sensor.py")))
    assert in_karte == sensoren, in_karte ^ sensoren


def test_strings_entspricht_englisch():
    assert _json(INTEGRATION / "strings.json") == _json(
        INTEGRATION / "translations" / "en.json"
    )


def test_karte_bietet_das_korrigieren_an():
    """Löschen und Rückgängig müssen aus der Karte erreichbar sein."""
    karte = (INTEGRATION / "frontend" / "lpg-tank-card.js").read_text(encoding="utf-8")
    assert 'callService("fluessiggas", "lieferung_loeschen"' in karte
    assert 'callService("fluessiggas", "rueckgaengig"' in karte
    assert 'id="block-verlauf"' in karte
    # Die Karte spricht Einträge über ihre Kennung an, nicht über die Position
    assert "eintrag: eintrag.id" in karte


def test_umrechnungsfaktor_ist_sichtbar():
    """Der Faktor kalibriert sich selbst – dann muss man ihn auch sehen können."""
    sensor = _quelltext("sensor.py")
    assert 'translation_key="umrechnungsfaktor"' in sensor
    # als Messwert, sonst zeichnet Home Assistant den Sprung nicht auf
    block = sensor[sensor.index('key="umrechnungsfaktor"'):]
    block = block[: block.index("TankSensorDescription(", 10)]
    assert "SensorStateClass.MEASUREMENT" in block
    assert 'native_unit_of_measurement="L/m³"' in block

    karte = (INTEGRATION / "frontend" / "lpg-tank-card.js").read_text(encoding="utf-8")
    assert '_zustand("umrechnungsfaktor")' in karte
    # In der Lieferhistorie steht der Sprung, den eine Betankung ausgelöst hat
    assert "eintrag.faktor_neu" in karte


def test_jahreswerte_sind_zaehler_mit_bekanntem_nullpunkt():
    """Die Jahreswerte fallen zum Jahreswechsel auf 0 – das muss ausdrücklich
    hinterlegt sein.

    Mit state_class TOTAL und einem last_reset muss Home Assistant den
    Rücksprung nicht aus einem Rückgang erraten. Bei TOTAL_INCREASING würde
    ein kleiner Rückgang mitten im Jahr – etwa nach einer Nachkalibrierung des
    Faktors – womöglich als Jahreswechsel gelesen und die Langzeitstatistik
    verdoppelte den Jahresverbrauch.
    """
    sensor = _quelltext("sensor.py")
    for schluessel in ("jahr_liter", "jahr_kubik", "jahr_energie"):
        anfang = sensor.index(f'key="{schluessel}"')
        block = sensor[anfang:]
        block = block[: block.index("TankSensorDescription(", 10)]
        assert "SensorStateClass.TOTAL," in block, schluessel
        assert "last_reset_fn=lambda s, c: s.year_start" in block, schluessel
        assert "device_class=" in block, schluessel

    # Die Entität muss last_reset auch tatsächlich melden
    assert "def last_reset" in sensor
    assert "last_reset_fn" in sensor

    # Drei Einheiten, jede einzeln – sonst gibt es keine drei Statistiken
    einheiten = {"UnitOfVolume.LITERS", "UnitOfVolume.CUBIC_METERS",
                 "UnitOfEnergy.KILO_WATT_HOUR"}
    assert einheiten <= set(re.findall(r"native_unit_of_measurement=(\S+?),", sensor))


def test_jahresbezugspunkt_kostet_eine_abfrage_im_jahr():
    """Der Verbrauch des Jahres darf nicht aus Monatswerten zusammengesetzt
    werden.

    Aus der Differenz zur Statistiksumme am Jahresanfang kann er nicht
    zurückspringen, weil die Summe selbst nie sinkt. Zusammengesetzt aus einem
    täglich gelesenen Monatsprofil plus laufendem Monat wäre er am
    Monatsersten kurz kleiner – und ein Rückgang ist für einen Zähler das
    Signal für einen Reset.
    """
    koordinator = _quelltext("coordinator.py")
    pfad = koordinator[koordinator.index("async def _async_year_start_sums"):]
    pfad = pfad[: pfad.index("    def _year_liters")]
    assert "if self._year_for == jahr:" in pfad      # einmal im Jahr, dann gemerkt
    assert "YEAR_RETRY" in pfad                      # Fehlversuch nicht in Endlosschleife
    assert "async_sums_at" in pfad                   # vorhandener, getesteter Weg


def test_karte_zeigt_die_jahreswerte_statt_der_reichweite():
    karte = (INTEGRATION / "frontend" / "lpg-tank-card.js").read_text(encoding="utf-8")
    for kennung in ("jahr_liter", "jahr_kubik", "jahr_energie"):
        assert f'kennung: "{kennung}"' in karte, kennung
    # Die Kachel ist weg, der Sensor bleibt: aus seinem Attribut "monate"
    # zeichnet die Karte den Restverlauf.
    assert 'label: "Reichweite"' not in karte
    assert '_zustand("reichweite")' in karte
    # Erwarteter Jahresverbrauch zusätzlich in m³
    assert "kubikmeter" in karte


def test_jahr_wird_in_ortszeit_angezeigt():
    """Die angezeigte Jahreszahl darf nicht aus dem UTC-Zeitpunkt kommen.

    year_start ist bewusst ein UTC-Instant, weil Home Assistant genau das für
    last_reset erwartet. Zum Anzeigen taugt er nicht – siehe die Falle unten.
    """
    sensor = _quelltext("sensor.py")
    anfang = sensor.index('key="jahr_liter"')
    block = sensor[anfang:]
    block = block[: block.index("TankSensorDescription(", 10)]

    assert '"jahr": s.year,' in block
    assert "year_start.year" not in block, "Jahr aus dem UTC-Instant gelesen"
    assert 'dt_util.as_local(s.year_start).isoformat()' in block

    # Das Jahr kommt aus der Ortszeit
    assert "year=dt_util.now().year," in _quelltext("coordinator.py")


def test_utc_instant_des_jahresanfangs_traegt_das_vorjahr():
    """Die Falle, wegen der es das Feld "year" überhaupt gibt.

    Die lokale Mitternacht des 1. Januar ist in Mitteleuropa in UTC noch der
    31. Dezember. Ein .year auf diesem Zeitpunkt liefert das Vorjahr – die
    Karte zeigte deshalb "Verbrauch 2025", während 2026 lief. Der gerechnete
    Wert war richtig, nur die Beschriftung nicht.
    """
    berlin = ZoneInfo("Europe/Berlin")
    anfang_lokal = datetime(2026, 1, 1, tzinfo=berlin)
    assert anfang_lokal.year == 2026
    assert anfang_lokal.astimezone(timezone.utc).year == 2025


def test_kubikmeter_werden_mit_nachkommastelle_gezeigt():
    """Ein m³ sind rund 3,9 Liter – ganze m³ wären bis zu zwei Liter daneben."""
    karte = (INTEGRATION / "frontend" / "lpg-tank-card.js").read_text(encoding="utf-8")
    for stelle in ('this._fmt(kubik, 1, "m³")',
                   'this._fmt(zahl(this._zustand("jahr_kubik"), null), 1, "m³")'):
        assert stelle in karte, stelle


def test_karte_kommt_nur_ueber_die_ressourcenliste():
    """Kein add_extra_js_url – das war die Ursache des Ladefehlers.

    Ein so eingebundenes Modul steckt im HTML und kann laufen, bevor das
    Frontend scoped-custom-element-registry installiert hat. Der Polyfill
    ersetzt window.customElements, und sein get()/whenDefined() kennt nur die
    eigene Map: Was vorher in der nativen Registry landete, ist danach
    unsichtbar. Lovelace meldet dann "custom element doesn't exist", und weil
    whenDefined() nie auslöst, bleibt der Fehler auch stehen.

    Die Lovelace-Ressource wird dagegen erst geladen, wenn das Frontend läuft -
    also nach dem Polyfill, in der Registry, die Lovelace auch befragt.
    """
    quelle = _quelltext("__init__.py")
    assert "add_extra_js_url(" not in quelle
    assert "from homeassistant.components.frontend import" not in quelle
    # Der verbleibende Weg muss vorhanden sein
    assert "async_create_item" in quelle
    assert '"res_type": "module"' in quelle

    # Lovelace muss vor uns laufen, sonst greift die Anmeldung zu früh ins Leere
    manifest = _json(INTEGRATION / "manifest.json")
    assert "lovelace" in manifest.get("after_dependencies", [])


def test_karte_meldet_sich_unabhaengig_von_der_registry_an():
    """customElements.get() taugt nicht als Wächter.

    Unter dem Polyfill kann get() "nicht angemeldet" melden, obwohl die Karte
    in der nativen Registry steht – und umgekehrt. Angemeldet wird deshalb
    immer, ein Doppeleintrag in derselben Registry wird geschluckt. Ungefangen
    bräche er die Ausführung des Moduls ab; genau so verabschieden sich andere
    Karten im Protokoll.
    """
    karte = (INTEGRATION / "frontend" / "lpg-tank-card.js").read_text(encoding="utf-8")
    anmeldung = karte[karte.index("customElements.define(\"lpg-tank-card\"") - 400:]

    assert 'if (!customElements.get("lpg-tank-card"))' not in karte
    assert "try {" in anmeldung
    assert "} catch (" in anmeldung
    # Kein Doppeleintrag in der Kartenauswahl bei doppelter Ausführung
    assert 'window.customCards.some((karte) => karte.type === "lpg-tank-card")' in karte


def test_karte_wird_komprimiert_mitgeliefert():
    """Neben der Karte muss ein aktuelles .gz liegen.

    aiohttp – und damit Home Assistant – liefert das Geschwisterfile
    automatisch aus, sobald der Browser gzip akzeptiert (mit Content-Encoding
    und Vary: Accept-Encoding). Das drückt die Übertragung von rund 52 kB auf
    rund 16 kB, und genau darauf kommt es an: Das Frontend gibt einer Custom
    Card nur zwei Sekunden, bis sie sich registriert hat.

    Der Inhaltsvergleich ist der eigentliche Punkt dieses Tests. Ein
    veraltetes .gz würde stillschweigend alten Code ausliefern, und zwar nur
    an Browser mit gzip – also praktisch an alle. Neu erzeugen mit:

        python3 scripts/karte_komprimieren.py
    """
    karte = INTEGRATION / "frontend" / "lpg-tank-card.js"
    gepackt = INTEGRATION / "frontend" / "lpg-tank-card.js.gz"
    assert gepackt.is_file(), "python3 scripts/karte_komprimieren.py ausführen"

    assert gzip.decompress(gepackt.read_bytes()) == karte.read_bytes(), (
        "lpg-tank-card.js.gz ist veraltet – "
        "python3 scripts/karte_komprimieren.py ausführen"
    )
    anteil = gepackt.stat().st_size / karte.stat().st_size
    assert anteil < 0.5, f"Kompression bringt nur {anteil:.0%}"


def test_karte_wird_mit_ausgeliefert():
    karte = INTEGRATION / "frontend" / "lpg-tank-card.js"
    assert karte.is_file(), "Die Karte muss im Integrationsordner liegen (HACS kopiert nur diesen)"
    assert "customElements.define" in karte.read_text(encoding="utf-8")


def test_hacs_konfiguration():
    hacs = _json(WURZEL / "hacs.json")
    assert hacs["content_in_root"] is False
    assert "homeassistant" in hacs


if __name__ == "__main__":
    fehler = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok    {name}")
            except AssertionError as e:
                fehler += 1
                print(f"  FEHLER {name}: {e}")
    print("\nAlle Tests bestanden." if not fehler else f"\n{fehler} Test(s) fehlgeschlagen.")
    sys.exit(1 if fehler else 0)
