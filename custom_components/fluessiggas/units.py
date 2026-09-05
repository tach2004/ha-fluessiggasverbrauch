"""Preiseinheiten auf EUR je Liter zurückführen.

Bewusst ohne Home-Assistant-Abhängigkeiten, damit die Erkennung ohne laufende
Instanz getestet werden kann.
"""

from __future__ import annotations

#: Bezugsgrößen, die sich sauber in Liter umrechnen lassen
_JE_KUBIKMETER = ("m³", "m3", "nm³", "nm3")
_JE_KILOWATTSTUNDE = ("kwh",)
_JE_LITER = ("/l", "/liter", "/ltr")
#: Einheiten ohne Bezugsgröße – bei einem Gaspreis ist EUR je Liter gemeint
_NUR_WAEHRUNG = ("eur", "euro", "ct", "cent", "")


def normalisiere(unit: str | None) -> str:
    """Einheit auf eine vergleichbare Form bringen."""
    return (unit or "").strip().lower().replace("€", "eur").replace(" ", "")


def price_factor(
    unit: str | None,
    liter_per_m3: float,
    kwh_per_liter: float,
) -> tuple[float, bool]:
    """Faktor, mit dem ein Preis in dieser Einheit zu EUR je Liter wird.

    Gibt zusätzlich zurück, ob die Einheit erkannt wurde. Wird sie es nicht,
    nimmt der Aufrufer zwar EUR je Liter an, sollte aber warnen – eine still
    falsch umgerechnete Einheit fällt sonst nie auf.

    >>> price_factor("EUR/m³", 3.92, 7.0)[0] == 1 / 3.92
    True
    >>> price_factor("ct/L", 3.92, 7.0)
    (0.01, True)
    """
    norm = normalisiere(unit)
    # Cent statt Euro erkennen, bevor die Bezugsgröße geprüft wird
    cent = 0.01 if norm.startswith(("ct", "cent")) else 1.0

    treffer = []
    if any(marke in norm for marke in _JE_KUBIKMETER):
        treffer.append("m3")
    if any(marke in norm for marke in _JE_KILOWATTSTUNDE):
        treffer.append("kwh")
    if any(norm.endswith(marke) for marke in _JE_LITER):
        treffer.append("l")

    # Mehrere Bezugsgrößen ergeben keinen Preis, sondern etwas anderes -
    # "kWh/m³" etwa ist ein Energiegehalt. Lieber melden als raten.
    if len(treffer) != 1:
        return (cent, True) if not treffer and norm in _NUR_WAEHRUNG else (cent, False)
    if treffer[0] == "m3":
        return cent / max(liter_per_m3, 0.1), True
    if treffer[0] == "kwh":
        return cent * max(kwh_per_liter, 0.1), True
    return cent, True
