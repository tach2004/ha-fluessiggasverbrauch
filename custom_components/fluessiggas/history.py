"""Reine Logik der Lieferhistorie – bewusst ohne Home Assistant.

Was hier steht, entscheidet, welcher Eintrag beim Löschen verschwindet. Ein
Fehler darin trifft Daten, die der Nutzer von Hand eingetippt hat, deshalb
liegt das Stück in einem eigenen Modul und ist einzeln getestet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class KeinTreffer(ValueError):
    """Die Auswahl passt auf keinen Eintrag."""


def waehle_eintraege(
    eintraege: list[dict[str, Any]],
    *,
    eintrag: str | None = None,
    datum: str | None = None,
    alle: bool = False,
) -> list[dict[str, Any]]:
    """Die zu löschenden Einträge bestimmen.

    Die Kennung ist der genaue Weg: Zwei Lieferungen am selben Tag lassen sich
    über das Datum nicht auseinanderhalten, über die Kennung schon. Das Datum
    bleibt als bequemer Weg für Dienstaufrufe von Hand – es trifft dann
    ausdrücklich alle Einträge dieses Tages.
    """
    if alle:
        return list(eintraege)
    if eintrag:
        treffer = [e for e in eintraege if e.get("id") == eintrag]
    elif datum:
        treffer = [e for e in eintraege if e.get("datum") == datum]
    else:
        raise KeinTreffer("Bitte eine Kennung, ein Datum oder 'alle' angeben.")
    if not treffer:
        raise KeinTreffer(f"Kein Eintrag gefunden ({eintrag or datum}).")
    return treffer


def ohne(
    eintraege: list[dict[str, Any]], treffer: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Liste ohne die getroffenen Einträge.

    Verglichen wird die Identität, nicht der Inhalt: Zwei inhaltsgleiche
    Einträge (gleicher Tag, gleiche Menge, gleicher Preis) sollen nicht
    gemeinsam verschwinden, wenn nur einer gemeint war.
    """
    weg = {id(e) for e in treffer}
    return [e for e in eintraege if id(e) not in weg]


# ------------------------------------------------------------- Mischpreis

#: Anteile darunter werden nicht mehr einzeln aufgeführt – sie sind im Preis
#: enthalten, aber eine Liste mit zwanzig Lieferungen à 0,1 % hilft niemandem.
ANTEIL_ANZEIGEN_AB = 0.005


@dataclass(slots=True)
class Mischpreis:
    """Was das Gas, das gerade im Tank ist, gekostet hat."""

    #: EUR je Liter
    preis: float
    #: je Lieferung ihr Anteil am Tankinhalt, jüngste zuerst
    anteile: list[dict[str, Any]] = field(default_factory=list)
    #: Lieferungen, bei denen der Stand vor der Betankung angenommen wurde
    angenommen: list[str] = field(default_factory=list)


def _zahl(wert: Any) -> float | None:
    try:
        return float(wert) if wert is not None else None
    except (TypeError, ValueError):
        return None


def mischpreis(eintraege: list[dict[str, Any]], nutzbar: float) -> Mischpreis | None:
    """Gewichteter Preis des Gases im Tank.

    Flüssiggas mischt sich im Tank: Neues Gas wird nicht hinten angestellt,
    jeder verheizte Liter ist ein Liter der Mischung. Bei jeder Betankung gilt
    deshalb

        Anteil des Alten  = Rest im Tank / (Rest + getankte Liter)
        Anteil des Neuen  = getankte Liter / (Rest + getankte Liter)

    und alle früheren Anteile schrumpfen mit dem Faktor des Alten. Der
    Verbrauch zwischen zwei Betankungen ändert am Preis nichts – er nimmt von
    allem gleich viel weg. Die Zeit spielt deshalb nur über den Rest im Tank
    hinein: Wer länger wartet, hat weniger Altes im Tank.

    Gerechnet wird über die ganze Historie. Ältere Lieferungen verlieren mit
    jeder Betankung ihren Anteil von selbst – nach drei, vier Füllungen steckt
    von ihnen kaum noch etwas im Tank. Eine feste Grenze ("nur die letzten
    zwei") wäre dagegen falsch, wenn der Rest bei einer Betankung groß war.

    - Lieferung ohne Preis: Die Mischung bleibt, wie sie ist. Über das neue
      Gas ist nichts bekannt, also wird es zum bisherigen Preis gerechnet.
    - Nachgetragene Lieferung ohne "Stand vorher": angenommen wird, dass auf
      die nutzbare Menge (85 %) aufgefüllt wurde – so liefern die Lieferanten.
    - Die erste Lieferung mit Preis setzt den Anfang; was davor im Tank war,
      ist unbekannt und zählt zu ihrem Preis.

    Ohne eine einzige Lieferung mit Preis gibt es keinen Mischpreis (None).
    """
    # Stabil nach Datum: zwei Einträge am selben Tag bleiben in der Reihenfolge,
    # in der sie eingetragen wurden.
    reihe = sorted(eintraege, key=lambda e: str(e.get("datum") or ""))
    anteile: list[tuple[dict[str, Any], float]] = []
    angenommen: list[str] = []

    for eintrag in reihe:
        preis = _zahl(eintrag.get("preis_pro_liter"))
        vorher = _zahl(eintrag.get("stand_vorher"))
        nachher = _zahl(eintrag.get("stand_nachher"))
        liter = _zahl(eintrag.get("liter"))
        if liter is None and vorher is not None and nachher is not None:
            liter = nachher - vorher
        if liter is None or liter <= 0 or preis is None or preis <= 0:
            continue
        if not anteile:
            anteile = [(eintrag, 1.0)]
            continue
        if vorher is None:
            vorher = max(nutzbar - liter, 0.0)
            angenommen.append(str(eintrag.get("datum")))
        alt = max(vorher, 0.0) / (max(vorher, 0.0) + liter)
        anteile = [(e, a * alt) for e, a in anteile] + [(eintrag, 1.0 - alt)]

    if not anteile:
        return None
    return Mischpreis(
        preis=sum(a * float(e["preis_pro_liter"]) for e, a in anteile),
        anteile=[
            {
                "datum": e.get("datum"),
                "preis_pro_liter": float(e["preis_pro_liter"]),
                "anteil_prozent": round(a * 100, 1),
            }
            for e, a in reversed(anteile)
            if a >= ANTEIL_ANZEIGEN_AB
        ],
        angenommen=angenommen,
    )
