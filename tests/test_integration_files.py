"""Prüft, dass Manifest, Dienste, Sensoren und Übersetzungen zusammenpassen.

    python3 tests/test_integration_files.py     (oder: pytest tests/)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

WURZEL = Path(__file__).resolve().parent.parent
INTEGRATION = WURZEL / "custom_components" / "fluessiggas"
SPRACHEN = ["de", "en"]


def _json(pfad: Path) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8"))


def _quelltext(name: str) -> str:
    return (INTEGRATION / name).read_text(encoding="utf-8")


def test_manifest_und_version_passen_zusammen():
    manifest = _json(INTEGRATION / "manifest.json")
    version = re.search(r'VERSION: Final = "([^"]+)"', _quelltext("const.py")).group(1)
    assert manifest["version"] == version, (manifest["version"], version)
    assert manifest["domain"] == "fluessiggas"
    assert set(manifest["dependencies"]) >= {"recorder", "http", "frontend"}


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
