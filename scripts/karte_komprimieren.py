#!/usr/bin/env python3
"""Erzeugt lpg-tank-card.js.gz neben der Karte.

    python3 scripts/karte_komprimieren.py

aiohttp – und damit Home Assistant – liefert ein Geschwisterfile mit der
Endung .gz automatisch aus, sobald der Browser gzip akzeptiert, und setzt
dabei Content-Encoding und Vary: Accept-Encoding. Fehlt die Datei oder kann
der Browser kein gzip, wird die unkomprimierte Karte ausgeliefert – die
Kompression ist also reine Zugabe und kann nichts kaputt machen.

Warum überhaupt: Das Frontend gibt einer Custom Card zwei Sekunden, bis sie
sich registriert hat. Über eine schwache Mobilverbindung ist der Unterschied
zwischen 52 kB und 11 kB genau in diesem Fenster entscheidend.

mtime=0: Sonst steckt der Zeitstempel im Gzip-Kopf und die Datei ändert sich
bei jedem Lauf, obwohl der Inhalt gleich bleibt – im Git wäre das Rauschen.
"""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

KARTE = (
    Path(__file__).resolve().parent.parent
    / "custom_components" / "fluessiggas" / "frontend" / "lpg-tank-card.js"
)


def komprimieren(quelle: Path = KARTE) -> Path:
    ziel = quelle.with_suffix(quelle.suffix + ".gz")
    roh = quelle.read_bytes()
    with gzip.GzipFile(filename="", mode="wb", compresslevel=9,
                       fileobj=ziel.open("wb"), mtime=0) as datei:
        datei.write(roh)
    return ziel


if __name__ == "__main__":
    if not KARTE.is_file():
        sys.exit(f"Karte nicht gefunden: {KARTE}")
    ziel = komprimieren()
    roh, klein = KARTE.stat().st_size, ziel.stat().st_size
    print(f"{KARTE.name}: {roh:,} B  ->  {ziel.name}: {klein:,} B "
          f"({klein / roh:.0%})".replace(",", "."))
