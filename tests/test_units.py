"""Tests der Preiseinheiten-Erkennung – laufen ohne Home Assistant.

    python3 tests/test_units.py      (oder: pytest tests/)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent / "custom_components" / "fluessiggas"
spec = importlib.util.spec_from_file_location("fg_units", WURZEL / "units.py")
units = importlib.util.module_from_spec(spec)
spec.loader.exec_module(units)

L_PRO_M3 = 3.92
KWH_PRO_L = 7.0


def faktor(einheit):
    return units.price_factor(einheit, L_PRO_M3, KWH_PRO_L)


def test_liter_bleibt_unveraendert():
    for einheit in ["EUR/L", "€/L", "eur/l", " €/l ", "EUR/Liter"]:
        f, erkannt = faktor(einheit)
        assert (f, erkannt) == (1.0, True), einheit


def test_kubikmeter_wird_geteilt():
    for einheit in ["EUR/m³", "€/m3", "eur/M³", "EUR/Nm³"]:
        f, erkannt = faktor(einheit)
        assert erkannt, einheit
        assert abs(f - 1 / L_PRO_M3) < 1e-9, (einheit, f)


def test_kilowattstunde_wird_multipliziert():
    f, erkannt = faktor("EUR/kWh")
    assert erkannt
    assert abs(f - KWH_PRO_L) < 1e-9, f
    # 0,10 EUR/kWh entsprechen 0,70 EUR/L
    assert abs(0.10 * f - 0.70) < 1e-9


def test_cent_wird_erkannt():
    assert faktor("ct/L") == (0.01, True)
    f, erkannt = faktor("ct/m³")
    assert erkannt and abs(f - 0.01 / L_PRO_M3) < 1e-9
    f, erkannt = faktor("Cent/kWh")
    assert erkannt and abs(f - 0.01 * KWH_PRO_L) < 1e-9


def test_ohne_bezugsgroesse_gilt_liter():
    """Ein Gaspreis ohne Einheit ist praktisch immer je Liter gemeint."""
    for einheit in ["EUR", "€", "", None]:
        assert faktor(einheit) == (1.0, True), einheit
    assert faktor("ct") == (0.01, True)


def test_unbekannte_einheit_wird_gemeldet():
    """Nicht still falsch rechnen: der Aufrufer muss warnen können."""
    for einheit in ["EUR/kg", "kWh/m³", "Dollar pro Gallone"]:
        f, erkannt = faktor(einheit)
        assert not erkannt, einheit
        assert f in (1.0, 0.01), einheit


def test_hin_und_zurueck():
    """Zurückschreiben teilt durch denselben Faktor – ohne Rundungsdrift."""
    for einheit in ["EUR/L", "EUR/m³", "ct/L", "EUR/kWh"]:
        f, _ = faktor(einheit)
        preis_je_liter = 0.677
        roh = preis_je_liter / f
        assert abs(roh * f - preis_je_liter) < 1e-9, einheit


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
