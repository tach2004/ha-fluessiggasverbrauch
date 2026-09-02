"""Verbrauchsprofil und Leer-Prognose.

Bewusst frei von Home-Assistant-Abhängigkeiten, damit die Rechnung ohne
laufende Instanz getestet werden kann.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from .const import DEFAULT_ANNUAL, STANDARD_SHARE

MAX_MONTHS = 72
MAX_LISTED_MONTHS = 36


@dataclass(slots=True)
class Profile:
    """Erwarteter Verbrauch je Kalendermonat in Litern (Januar … Dezember)."""

    liters: list[float]
    #: Aus wie vielen Jahren der jeweilige Monat gemittelt wurde (0 = geschätzt)
    counts: list[int]

    @property
    def annual(self) -> float:
        return sum(self.liters)

    @property
    def measured_months(self) -> int:
        return sum(1 for c in self.counts if c)


@dataclass(slots=True)
class Forecast:
    """Ergebnis der Vorwärtssimulation."""

    days_to_empty: int | None = None
    days_to_reserve: int | None = None
    empty_on: date | None = None
    reserve_on: date | None = None
    order_by: date | None = None
    months: list[dict] = field(default_factory=list)


def build_profile(
    monthly: dict[tuple[int, int], float],
    years: int,
    today: date,
) -> Profile:
    """Monatsprofil aus gemessenen Monatsverbräuchen bilden.

    ``monthly`` bildet (Jahr, Monat) auf den Verbrauch in Litern ab. Je
    Kalendermonat werden die letzten ``years`` Jahre gemittelt. Der laufende
    Monat bleibt außen vor, weil er noch nicht vollständig ist.

    Monate ohne Messwert werden nicht auf 0 gesetzt, sondern über die Form der
    Standard-Heizkurve ergänzt und dabei auf das Niveau der gemessenen Monate
    skaliert. Dadurch ist die Prognose schon mit einer halben Heizperiode
    brauchbar, statt erst nach zwei vollen Jahren.
    """
    je_monat: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for (jahr, monat) in sorted(monthly, reverse=True):
        if (jahr, monat) == (today.year, today.month):
            continue
        if len(je_monat[monat]) < max(1, years):
            je_monat[monat].append(monthly[(jahr, monat)])

    mittel: dict[int, float | None] = {}
    for monat, werte in je_monat.items():
        mittel[monat] = sum(werte) / len(werte) if werte else None

    bekannt = [m for m in range(1, 13) if mittel[m] is not None]
    if not bekannt:
        return Profile(
            liters=[round(anteil / 100 * DEFAULT_ANNUAL, 1) for anteil in STANDARD_SHARE],
            counts=[0] * 12,
        )

    # Niveau der Standardkurve an die gemessenen Monate anpassen
    bekannter_anteil = sum(STANDARD_SHARE[m - 1] for m in bekannt)
    bekannte_menge = sum(mittel[m] or 0.0 for m in bekannt)
    skala = bekannte_menge / bekannter_anteil if bekannter_anteil > 0 else 0.0
    if skala <= 0:
        skala = DEFAULT_ANNUAL / 100

    liters, counts = [], []
    for monat in range(1, 13):
        if mittel[monat] is None:
            liters.append(round(STANDARD_SHARE[monat - 1] * skala, 1))
            counts.append(0)
        else:
            liters.append(round(mittel[monat] or 0.0, 1))
            counts.append(len(je_monat[monat]))
    return Profile(liters=liters, counts=counts)


def simulate(
    level: float,
    profile: Profile,
    reserve: float,
    lead_days: int,
    today: date,
    correction: float = 1.0,
) -> Forecast:
    """Monat für Monat vorwärts rechnen, bis der Tank leer ist.

    Ein Jahresmittel taugt hier nicht: Im Januar geht rund zehnmal so viel weg
    wie im Juli. Innerhalb des angebrochenen Monats wird linear interpoliert,
    damit ein taggenaues Datum herauskommt.
    """
    ergebnis = Forecast()
    if profile.annual <= 0:
        return ergebnis

    rest = level
    jahr, monat = today.year, today.month
    tage = 0.0
    erste = True
    leer_nach: float | None = None
    reserve_nach: float | None = 0.0 if level <= reserve else None

    for _ in range(MAX_MONTHS):
        tage_im_monat = calendar.monthrange(jahr, monat)[1]
        rate = profile.liters[monat - 1] * correction / tage_im_monat
        segment = tage_im_monat - today.day + 1 if erste else tage_im_monat
        verbrauch = rate * segment

        if reserve_nach is None and rate > 0 and rest - verbrauch <= reserve:
            reserve_nach = tage + max((rest - reserve) / rate, 0.0)

        if len(ergebnis.months) < MAX_LISTED_MONTHS:
            ergebnis.months.append(
                {
                    "monat": f"{jahr:04d}-{monat:02d}",
                    "liter": round(min(verbrauch, max(rest, 0.0)), 1),
                    "rest": round(max(rest - verbrauch, 0.0), 1),
                }
            )

        if rate > 0 and rest - verbrauch <= 0:
            leer_nach = tage + max(rest / rate, 0.0)
            break

        rest -= verbrauch
        tage += segment
        erste = False
        monat += 1
        if monat == 13:
            monat, jahr = 1, jahr + 1

    if level <= 0:
        leer_nach, reserve_nach = 0.0, 0.0

    if leer_nach is not None:
        ergebnis.days_to_empty = round(leer_nach)
        ergebnis.empty_on = today + timedelta(days=ergebnis.days_to_empty)
    if reserve_nach is not None:
        ergebnis.days_to_reserve = round(reserve_nach)
        ergebnis.reserve_on = today + timedelta(days=ergebnis.days_to_reserve)
        ergebnis.order_by = today + timedelta(
            days=max(ergebnis.days_to_reserve - lead_days, 0)
        )
    return ergebnis
