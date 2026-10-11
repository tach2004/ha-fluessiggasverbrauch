"""Welche Statistikzeile den Stand um Mitternacht trägt.

    python3 tests/test_statistik.py     (oder: pytest tests/)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent / "custom_components" / "fluessiggas"
spec = importlib.util.spec_from_file_location("fg_statistik", WURZEL / "statistik.py")
statistik = importlib.util.module_from_spec(spec)
spec.loader.exec_module(statistik)

stand_um = statistik.stand_um

MITTERNACHT = 1_760_133_600.0      # beliebiger Zeitpunkt, nur relativ verwendet
FUENF = 300.0


def _reihe(*paare: tuple[float, float | None]) -> list[dict]:
    """Zeilen (Beginn relativ zu Mitternacht in Minuten, Summe am Ende)."""
    return [{"start": MITTERNACHT + minuten * 60, "sum": summe} for minuten, summe in paare]


def test_zeile_bis_mitternacht_traegt_den_stand():
    # 23:50–23:55 endet bei 100, 23:55–00:00 bei 101, 00:00–00:05 bei 103
    reihe = _reihe((-10, 100.0), (-5, 101.0), (0, 103.0), (5, 104.0))
    assert stand_um(reihe, MITTERNACHT) == 101.0


def test_nicht_die_zeile_die_um_mitternacht_beginnt():
    """Ihr "sum" ist der Stand um 00:05 – das Gas der ersten fünf Minuten
    fehlte sonst den ganzen Tag."""
    reihe = _reihe((-5, 101.0), (0, 103.0))
    assert stand_um(reihe, MITTERNACHT) != 103.0


def test_home_assistant_lief_um_mitternacht_nicht():
    # Letzte Zeile 22:00, danach Lücke bis 06:00: der Stand von 22:05 gilt
    reihe = _reihe((-120, 90.0), (360, 95.0))
    assert stand_um(reihe, MITTERNACHT) == 90.0


def test_quelle_kam_erst_heute_dazu():
    reihe = _reihe((600, 7.0), (605, 7.5))
    assert stand_um(reihe, MITTERNACHT) == 7.0


def test_zeilen_ohne_summe_zaehlen_nicht():
    reihe = _reihe((-10, 100.0), (-5, None), (0, 103.0))
    assert stand_um(reihe, MITTERNACHT) == 100.0


def test_leere_reihe():
    assert stand_um([], MITTERNACHT) is None
    assert stand_um(_reihe((-5, None)), MITTERNACHT) is None


if __name__ == "__main__":
    for name, funktion in list(globals().items()):
        if name.startswith("test_"):
            funktion()
            print("ok ", name)
