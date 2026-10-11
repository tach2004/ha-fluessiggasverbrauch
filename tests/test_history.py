"""Auswahl und Entfernen von Einträgen der Lieferhistorie.

    python3 tests/test_history.py     (oder: pytest tests/)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent / "custom_components" / "fluessiggas"
spec = importlib.util.spec_from_file_location("fg_history", WURZEL / "history.py")
history = importlib.util.module_from_spec(spec)
# Dataclasses schlagen ihr Modul in sys.modules nach – wie test_forecast.py
sys.modules["fg_history"] = history
spec.loader.exec_module(history)

KeinTreffer = history.KeinTreffer
ohne = history.ohne
waehle_eintraege = history.waehle_eintraege
mischpreis = history.mischpreis


def _liste() -> list[dict]:
    return [
        {"id": "aaa", "datum": "2024-08-12", "liter": 2500.0, "preis_pro_liter": 0.61},
        {"id": "bbb", "datum": "2025-09-02", "liter": 1000.0, "preis_pro_liter": 0.68},
        {"id": "ccc", "datum": "2025-09-02", "liter": 1000.0, "preis_pro_liter": 0.68},
    ]


def test_kennung_trifft_genau_einen_eintrag():
    eintraege = _liste()
    treffer = waehle_eintraege(eintraege, eintrag="bbb")
    assert [e["id"] for e in treffer] == ["bbb"]


def test_gleiche_eintraege_am_selben_tag_bleiben_unterscheidbar():
    """Der eigentliche Grund für die Kennung.

    Zwei Lieferungen am selben Tag mit gleicher Menge und gleichem Preis sind
    inhaltlich identisch. Gelöscht werden darf trotzdem nur die gemeinte.
    """
    eintraege = _liste()
    treffer = waehle_eintraege(eintraege, eintrag="ccc")
    uebrig = ohne(eintraege, treffer)
    assert [e["id"] for e in uebrig] == ["aaa", "bbb"]


def test_datum_trifft_alle_eintraege_des_tages():
    eintraege = _liste()
    treffer = waehle_eintraege(eintraege, datum="2025-09-02")
    assert [e["id"] for e in treffer] == ["bbb", "ccc"]
    assert [e["id"] for e in ohne(eintraege, treffer)] == ["aaa"]


def test_alle_raeumt_die_liste():
    eintraege = _liste()
    treffer = waehle_eintraege(eintraege, alle=True)
    assert ohne(eintraege, treffer) == []


def test_alle_hat_vorrang_und_braucht_keine_weiteren_angaben():
    eintraege = _liste()
    assert len(waehle_eintraege(eintraege, eintrag="bbb", alle=True)) == 3


def test_ohne_angabe_ist_ein_fehler():
    """Ein Dienstaufruf ohne Ziel darf nicht stillschweigend alles löschen."""
    try:
        waehle_eintraege(_liste())
    except KeinTreffer:
        pass
    else:
        raise AssertionError("leere Auswahl hätte auffallen müssen")


def test_unbekannte_kennung_ist_ein_fehler():
    try:
        waehle_eintraege(_liste(), eintrag="gibtsnicht")
    except KeinTreffer as fehler:
        assert "gibtsnicht" in str(fehler)
    else:
        raise AssertionError("unbekannte Kennung hätte auffallen müssen")


def test_leere_historie_meldet_sich():
    try:
        waehle_eintraege([], datum="2025-09-02")
    except KeinTreffer:
        pass
    else:
        raise AssertionError("leere Historie hätte auffallen müssen")


def test_ohne_laesst_die_ausgangsliste_unangetastet():
    eintraege = _liste()
    ohne(eintraege, waehle_eintraege(eintraege, eintrag="aaa"))
    assert len(eintraege) == 3



# ------------------------------------------------------------- Mischpreis

NUTZBAR = 4123.0


def _lieferung(datum, liter, preis, vorher=None, nachher=None):
    return {"datum": datum, "liter": liter, "preis_pro_liter": preis,
            "stand_vorher": vorher, "stand_nachher": nachher}


def test_mischpreis_beispiel():
    """900 L Rest zu 0,677 €, dazu 3.000 L zu 0,90 €."""
    ergebnis = mischpreis([
        _lieferung("2025-11-07", 2131.0, 0.677, vorher=1900.0),
        _lieferung("2026-09-01", 3000.0, 0.90, vorher=900.0),
    ], NUTZBAR)
    assert abs(ergebnis.preis - (900 * 0.677 + 3000 * 0.90) / 3900) < 1e-9
    assert round(ergebnis.preis, 3) == 0.849
    # jüngste zuerst, Anteile ergeben zusammen 100 %
    assert [a["datum"] for a in ergebnis.anteile] == ["2026-09-01", "2025-11-07"]
    assert abs(sum(a["anteil_prozent"] for a in ergebnis.anteile) - 100) < 0.2


def test_alte_lieferungen_verlieren_ihren_anteil_von_selbst():
    """Jede Betankung schrumpft alles Frühere um Rest / (Rest + Neu)."""
    lieferungen = [_lieferung("2020-01-01", 3000.0, 1.00)]
    for jahr in range(2021, 2026):
        lieferungen.append(_lieferung(f"{jahr}-01-01", 3000.0, 0.50, vorher=1000.0))
    ergebnis = mischpreis(lieferungen, NUTZBAR)
    anteil_2020 = (1000 / 4000) ** 5
    assert abs(ergebnis.preis - (anteil_2020 * 1.00 + (1 - anteil_2020) * 0.50)) < 1e-9
    # nach fünf Füllungen unter 0,1 % - aufgeführt wird es nicht mehr
    assert "2020-01-01" not in [a["datum"] for a in ergebnis.anteile]


def test_ein_grosser_rest_wirkt_lange_nach():
    """Darum keine feste Grenze "nur die letzten zwei Lieferungen": War der
    Tank beim Nachtanken noch halb voll, steckt die vorletzte Füllung
    deutlich mit drin."""
    ergebnis = mischpreis([
        _lieferung("2024-01-01", 3000.0, 1.00),
        _lieferung("2025-01-01", 1000.0, 0.60, vorher=3000.0),
        _lieferung("2026-01-01", 1000.0, 0.60, vorher=3000.0),
    ], NUTZBAR)
    assert abs(ergebnis.preis - (0.5625 * 1.00 + 0.4375 * 0.60)) < 1e-9


def test_zeit_spielt_nur_ueber_den_rest_hinein():
    """Derselbe Rest, egal wie lange die Lieferungen auseinanderliegen."""
    kurz = mischpreis([_lieferung("2026-01-01", 3000.0, 0.70),
                       _lieferung("2026-02-01", 2000.0, 0.90, vorher=2000.0)], NUTZBAR)
    lang = mischpreis([_lieferung("2020-01-01", 3000.0, 0.70),
                       _lieferung("2026-02-01", 2000.0, 0.90, vorher=2000.0)], NUTZBAR)
    assert kurz.preis == lang.preis == 0.80


def test_lieferung_ohne_preis_aendert_die_mischung_nicht():
    mit = mischpreis([_lieferung("2025-01-01", 3000.0, 0.70)], NUTZBAR)
    ohne_preis = mischpreis([_lieferung("2025-01-01", 3000.0, 0.70),
                             _lieferung("2026-01-01", 2000.0, None, vorher=1500.0)], NUTZBAR)
    assert mit.preis == ohne_preis.preis == 0.70


def test_nachgetragen_ohne_stand_nimmt_volltanken_an():
    ergebnis = mischpreis([
        _lieferung("2024-01-01", 3000.0, 1.00),
        _lieferung("2025-01-01", 3123.0, 0.50),           # kein Stand vorher
    ], NUTZBAR)
    # aufgefüllt auf 4.123 L: 1.000 L Rest + 3.123 L neu
    assert abs(ergebnis.preis - (1000 * 1.00 + 3123 * 0.50) / NUTZBAR) < 1e-9
    assert ergebnis.angenommen == ["2025-01-01"]


def test_liter_aus_tankuhr_staenden():
    """Betankung über die Tankuhr: Liter fehlen, Stände sind bekannt."""
    ergebnis = mischpreis([
        _lieferung("2025-01-01", 3000.0, 0.60),
        _lieferung("2026-01-01", None, 0.90, vorher=1000.0, nachher=4000.0),
    ], NUTZBAR)
    assert abs(ergebnis.preis - (0.25 * 0.60 + 0.75 * 0.90)) < 1e-9


def test_reihenfolge_nach_datum_nicht_nach_eintragung():
    """Nachgetragene Lieferungen landen nachträglich – gerechnet wird
    chronologisch."""
    a = _lieferung("2024-01-01", 3000.0, 1.00)
    b = _lieferung("2025-01-01", 3000.0, 0.50, vorher=1000.0)
    assert mischpreis([b, a], NUTZBAR).preis == mischpreis([a, b], NUTZBAR).preis


def test_ohne_preise_kein_mischpreis():
    assert mischpreis([], NUTZBAR) is None
    assert mischpreis([_lieferung("2025-01-01", 3000.0, None)], NUTZBAR) is None

if __name__ == "__main__":
    erfolge = 0
    for name, funktion in sorted(globals().items()):
        if name.startswith("test_") and callable(funktion):
            funktion()
            erfolge += 1
    print(f"{erfolge} Prüfungen bestanden")
