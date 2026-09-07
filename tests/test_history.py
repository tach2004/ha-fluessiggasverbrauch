"""Auswahl und Entfernen von Einträgen der Lieferhistorie.

    python3 tests/test_history.py     (oder: pytest tests/)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent / "custom_components" / "fluessiggas"
spec = importlib.util.spec_from_file_location("fg_history", WURZEL / "history.py")
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)

KeinTreffer = history.KeinTreffer
ohne = history.ohne
waehle_eintraege = history.waehle_eintraege


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


if __name__ == "__main__":
    erfolge = 0
    for name, funktion in sorted(globals().items()):
        if name.startswith("test_") and callable(funktion):
            funktion()
            erfolge += 1
    print(f"{erfolge} Prüfungen bestanden")
