"""Tests der Prognoserechnung – laufen ohne Home Assistant.

    python3 tests/test_forecast.py      (oder: pytest tests/)
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date
from pathlib import Path

# custom_components/fluessiggas als Paket "fluessiggas" verfügbar machen
WURZEL = Path(__file__).resolve().parent.parent / "custom_components" / "fluessiggas"
paket = types.ModuleType("fluessiggas")
paket.__path__ = [str(WURZEL)]
sys.modules["fluessiggas"] = paket
for name in ("const", "forecast"):
    spec = importlib.util.spec_from_file_location(f"fluessiggas.{name}", WURZEL / f"{name}.py")
    modul = importlib.util.module_from_spec(spec)
    sys.modules[f"fluessiggas.{name}"] = modul
    spec.loader.exec_module(modul)

from fluessiggas.const import DEFAULT_ANNUAL, STANDARD_SHARE  # noqa: E402
from fluessiggas.forecast import build_profile, simulate  # noqa: E402

HEUTE = date(2026, 9, 2)


def _historie(von: date, bis: date, jahresverbrauch: float = 1400.0) -> dict:
    """Erzeugt eine Verbrauchshistorie nach der Standard-Heizkurve."""
    daten = {}
    jahr, monat = von.year, von.month
    while (jahr, monat) <= (bis.year, bis.month):
        daten[(jahr, monat)] = round(STANDARD_SHARE[monat - 1] / 100 * jahresverbrauch, 1)
        monat += 1
        if monat == 13:
            monat, jahr = 1, jahr + 1
    return daten


def test_profil_aus_zwei_vollen_jahren():
    historie = _historie(date(2024, 7, 1), date(2026, 8, 31))
    profil = build_profile(historie, years=2, today=HEUTE)
    assert profil.measured_months == 12, "ab Juli 2024 liegt jeder Monat vor"
    assert abs(profil.annual - 1400) < 1, profil.annual
    assert profil.counts[0] == 2, "Januar 2025 und 2026"
    assert profil.counts[8] == 2, "September 2024 und 2025"


def test_laufender_monat_wird_ignoriert():
    historie = _historie(date(2025, 1, 1), date(2026, 9, 30))
    profil = build_profile(historie, years=1, today=HEUTE)
    # September 2026 ist angebrochen -> September muss von 2025 kommen
    assert profil.liters[8] == round(STANDARD_SHARE[8] / 100 * 1400, 1)


def test_fehlende_monate_werden_geschaetzt_statt_genullt():
    """Nur eine halbe Heizperiode – die Lücken dürfen die Prognose nicht kippen."""
    historie = _historie(date(2026, 1, 1), date(2026, 4, 30))
    profil = build_profile(historie, years=2, today=HEUTE)
    assert profil.measured_months == 4
    assert all(w > 0 for w in profil.liters), "kein Monat darf 0 sein"
    # Jan-Apr sind 48,5 % der Standardkurve; hochgerechnet ergibt das wieder ~1400
    assert abs(profil.annual - 1400) < 30, profil.annual


def test_hoher_verbrauch_skaliert_die_luecken_mit():
    historie = _historie(date(2026, 1, 1), date(2026, 4, 30), jahresverbrauch=2800.0)
    profil = build_profile(historie, years=2, today=HEUTE)
    assert abs(profil.annual - 2800) < 60, profil.annual


def test_ohne_daten_kommt_das_standardprofil():
    profil = build_profile({}, years=2, today=HEUTE)
    assert profil.measured_months == 0
    assert abs(profil.annual - DEFAULT_ANNUAL) < 1


def test_simulation_verbraucht_genau_die_fuellung():
    profil = build_profile(_historie(date(2024, 7, 1), date(2026, 8, 31)), 2, HEUTE)
    p = simulate(3200.0, profil, reserve=400.0, lead_days=21, today=HEUTE)
    assert p.empty_on is not None
    verbraucht = sum(m["liter"] for m in p.months)
    assert abs(verbraucht - 3200.0) < 1.0, verbraucht


def test_reihenfolge_der_termine():
    profil = build_profile(_historie(date(2024, 7, 1), date(2026, 8, 31)), 2, HEUTE)
    p = simulate(3200.0, profil, reserve=400.0, lead_days=21, today=HEUTE)
    assert p.order_by < p.reserve_on < p.empty_on
    assert (p.reserve_on - p.order_by).days == 21


def test_leerer_tank():
    profil = build_profile(_historie(date(2024, 7, 1), date(2026, 8, 31)), 2, HEUTE)
    p = simulate(0.0, profil, reserve=400.0, lead_days=21, today=HEUTE)
    assert p.days_to_empty == 0
    assert p.empty_on == HEUTE


def test_unter_der_reserve():
    profil = build_profile(_historie(date(2024, 7, 1), date(2026, 8, 31)), 2, HEUTE)
    p = simulate(300.0, profil, reserve=400.0, lead_days=21, today=HEUTE)
    assert p.days_to_reserve == 0
    assert p.order_by == HEUTE
    assert p.empty_on > HEUTE


def test_saison_schlaegt_tagesmittel():
    """Im September reicht die Füllung viel kürzer als der Jahresschnitt suggeriert."""
    profil = build_profile(_historie(date(2024, 7, 1), date(2026, 8, 31)), 2, HEUTE)
    p = simulate(700.0, profil, reserve=0.0, lead_days=21, today=HEUTE)
    naiv = 700.0 / (profil.annual / 365)
    assert p.days_to_empty < naiv * 0.8, (p.days_to_empty, naiv)


def test_korrekturfaktor():
    profil = build_profile(_historie(date(2024, 7, 1), date(2026, 8, 31)), 2, HEUTE)
    normal = simulate(3200.0, profil, 0.0, 21, HEUTE)
    mehr = simulate(3200.0, profil, 0.0, 21, HEUTE, correction=1.3)
    assert mehr.days_to_empty < normal.days_to_empty


def test_reichweite_ueber_sechs_jahre_bleibt_offen():
    profil = build_profile({(2025, m): 1.0 for m in range(1, 13)}, 2, HEUTE)
    p = simulate(4120.0, profil, 400.0, 21, HEUTE)
    assert p.days_to_empty is None, "keine Fantasiedaten jenseits des Horizonts"


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
