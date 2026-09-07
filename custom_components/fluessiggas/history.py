"""Reine Logik der Lieferhistorie – bewusst ohne Home Assistant.

Was hier steht, entscheidet, welcher Eintrag beim Löschen verschwindet. Ein
Fehler darin trifft Daten, die der Nutzer von Hand eingetippt hat, deshalb
liegt das Stück in einem eigenen Modul und ist einzeln getestet.
"""

from __future__ import annotations

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
