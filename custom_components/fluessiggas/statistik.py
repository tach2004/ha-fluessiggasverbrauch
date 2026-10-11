"""Reine Auswertung von Statistikzeilen – bewusst ohne Home Assistant.

Welche Zeile den Stand um Mitternacht trägt, entscheidet über den ganzen
Tagesverbrauch: Eine Zeile daneben, und der Bezugspunkt gilt bis zum nächsten
Tag falsch. Deshalb liegt das Stück einzeln und ist einzeln getestet.
"""

from __future__ import annotations

from typing import Any


def stand_um(reihe: list[dict[str, Any]], ziel: float) -> float | None:
    """Statistiksumme zum Zeitpunkt ``ziel`` (Unix-Zeit) aus einer Reihe.

    "sum" einer Zeile ist der Stand an ihrem *Ende*. Die letzte Zeile, die vor
    ``ziel`` beginnt, endet also bei ``ziel`` – oder, wenn Home Assistant da
    nicht lief, beim letzten Stand davor, was dasselbe ist: Ohne laufendes
    Home Assistant wurde nichts gezählt. Gibt es davor nichts, weil die Quelle
    erst danach dazukam, zählt ihre erste Zeile.
    """
    mit_summe = [z for z in reihe if z.get("sum") is not None]
    davor = [z for z in mit_summe if z.get("start", 0) < ziel]
    zeile = davor[-1] if davor else (mit_summe[0] if mit_summe else None)
    return float(zeile["sum"]) if zeile is not None else None
