"""Restverlauf der Karte und sein Fadenkreuz.

Die beiden Rechenfunktionen werden aus der Karte gelöst und in Node
ausgeführt – geprüft wird also das, was im Browser tatsächlich läuft.

    python3 tests/test_karte_verlauf.py     (oder: pytest tests/)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

KARTE = (
    Path(__file__).resolve().parent.parent
    / "custom_components" / "fluessiggas" / "frontend" / "lpg-tank-card.js"
).read_text(encoding="utf-8")

NODE = shutil.which("node")


def _funktion(name: str) -> str:
    treffer = re.search(rf"^function {name}\(.*?^\}}$", KARTE, flags=re.S | re.M)
    assert treffer, f"function {name} nicht gefunden"
    return treffer.group(0)


def _js(ausdruck: str):
    """Ausdruck mit den Funktionen der Karte in Node auswerten (Ortszeit Berlin)."""
    quelltext = (
        _funktion("restVerlauf") + "\n" + _funktion("restAm") + "\n"
        + f"process.stdout.write(JSON.stringify({ausdruck}));"
    )
    ergebnis = subprocess.run(
        [NODE, "-e", quelltext], capture_output=True, text=True, check=True,
        env={"TZ": "Europe/Berlin", "PATH": ""},
    )
    return json.loads(ergebnis.stdout)


MONATE = json.dumps([
    {"monat": "2026-10", "rest": 2800},
    {"monat": "2026-11", "rest": 2600},
    {"monat": "2026-12", "rest": 2300},
    {"monat": "2027-01", "rest": 0},
])
HEUTE = "new Date(2026, 9, 16)"          # 16.10.2026, 0 Uhr


def test_reihe_beginnt_heute_und_endet_an_monatsenden():
    if not NODE:
        return print("node fehlt – übersprungen")
    reihe = _js(f"restVerlauf({MONATE}, 2888, {HEUTE}, null)"
                ".map(p => [new Date(p.t).toLocaleDateString('de-DE'), p.rest])")
    assert reihe == [
        ["16.10.2026", 2888],          # heute mit dem aktuellen Stand
        ["1.11.2026", 2800],           # Ende Oktober = 1. November 0 Uhr
        ["1.12.2026", 2600],
        ["1.1.2027", 2300],            # Dezember läuft ins neue Jahr
        ["1.2.2027", 0],
    ]


def test_leer_mitten_im_monat_endet_dort_um_0_uhr():
    """Das Leerdatum kommt als Mittag; die Kurve endet am Tagesbeginn, damit
    das Fadenkreuz am angekündigten Tag "leer" zeigt."""
    if not NODE:
        return print("node fehlt – übersprungen")
    ende = _js(f"(r => [new Date(r.at(-1).t).toLocaleString('de-DE'), r.at(-1).rest])("
               f"restVerlauf({MONATE}, 2888, {HEUTE}, new Date(2027, 0, 20, 12)))")
    assert ende == ["20.1.2027, 00:00:00", 0]


def test_fadenkreuz_liest_linear_zwischen_den_punkten():
    """Die Prognose verbraucht innerhalb eines Monats gleichmäßig - die Mitte
    zwischen zwei Monatsenden ist also genau der Mittelwert."""
    if not NODE:
        return print("node fehlt – übersprungen")
    werte = _js(
        f"(r => [restAm(r, r[0].t), restAm(r, (r[1].t + r[2].t) / 2), "
        f"restAm(r, r[0].t - 864e5), restAm(r, r.at(-1).t + 864e5)])("
        f"restVerlauf({MONATE}, 2888, {HEUTE}, null))"
    )
    assert werte[0] == 2888                       # heute
    assert abs(werte[1] - 2700) < 1e-9            # Mitte November
    assert werte[2] == 2888                       # vor heute: geklemmt
    assert werte[3] == 0                          # nach dem Ende: leer


def test_unbrauchbare_monate_werden_uebergangen():
    if not NODE:
        return print("node fehlt – übersprungen")
    laenge = _js(f"restVerlauf([{{monat: 'kaputt', rest: 5}}, {{monat: '2026-10', rest: 2800}}], "
                 f"2888, {HEUTE}, null).length")
    assert laenge == 2


def test_fadenkreuz_ist_angebunden():
    code = re.sub(r"//[^\n]*|/\*.*?\*/", "", KARTE, flags=re.S)
    assert "e.verlauf.addEventListener(typ, (ev) => this._verlaufMarker(ev))" in code
    assert "e.verlauf.addEventListener(typ, () => this._verlaufMarkerAus())" in code
    # Senkrecht wischen muss auf dem Handy weiter die Seite scrollen
    assert "#verlauf { margin: 0 -4px; touch-action: pan-y; }" in code
    marker = code[code.index("  _verlaufMarker(ev) {"):]
    marker = marker[: marker.index("\n  }\n")]
    assert "restAm(d.reihe, t)" in marker          # stufenlos, nicht am Datenpunkt
    assert "kwh_pro_liter" in marker               # Energie mit dem gültigen Wert
    assert "v-unter" in marker                     # unter der Reserve rot


if __name__ == "__main__":
    erfolge = 0
    for name, funktion in sorted(globals().items()):
        if name.startswith("test_") and callable(funktion):
            funktion()
            erfolge += 1
    print(f"{erfolge} Prüfungen bestanden")
