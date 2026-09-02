"""Datenhaltung: Füllstand und Prognose aus der Langzeitstatistik.

Kein utility_meter, keine Hilfsentitäten: Home Assistant führt für jeden
Verbrauchszähler ohnehin eine bereinigte Summe mit (``sum`` in der Statistik),
die Zählerrückstellungen bereits berücksichtigt. Der Verbrauch seit der letzten
Betankung ist damit schlicht die Differenz zweier Summen – und weil die
Statistik rückwirkend abfragbar ist, lassen sich Betankungen auch nachträglich
mit korrektem Datum eintragen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_list_statistic_ids,
    get_last_short_term_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CAPACITY,
    CONF_CORRECTION,
    CONF_KWH_PER_LITER,
    CONF_LEAD_TIME,
    CONF_LITER_PER_M3,
    CONF_MAX_FILL,
    CONF_PRICE,
    CONF_PROFILE_YEARS,
    CONF_RESERVE,
    CONF_SOURCE_UNIT,
    CONF_SOURCES,
    DEFAULT_CAPACITY,
    DEFAULT_CORRECTION,
    DEFAULT_KWH_PER_LITER,
    DEFAULT_LEAD_TIME,
    DEFAULT_LITER_PER_M3,
    DEFAULT_MAX_FILL,
    DEFAULT_PRICE,
    DEFAULT_PROFILE_YEARS,
    DEFAULT_RESERVE,
    STORAGE_KEY,
    STORAGE_VERSION,
    STORE_BASELINE,
    STORE_DELIVERIES,
    STORE_LEVEL,
    STORE_REFERENCE_AT,
    UNIT_AUTO,
    UNIT_KWH,
    UNIT_LITER,
    UNIT_M3,
)
from .forecast import Forecast, Profile, build_profile, simulate

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=5)
PROFILE_INTERVAL = timedelta(hours=6)
UNIT_INTERVAL = timedelta(hours=1)
MAX_DELIVERIES = 50

#: Kalibrierung erst ab dieser gezählten Menge – darunter ist der Ablesefehler
#: der Tankuhr größer als der Effekt.
MIN_UNITS_FOR_CALIBRATION = 20.0
FACTOR_LIMITS = (2.0, 6.0)

UNIT_ALIASES = {
    "m³": UNIT_M3, "m3": UNIT_M3, "nm³": UNIT_M3,
    "l": UNIT_LITER, "liter": UNIT_LITER, "ltr": UNIT_LITER,
    "kwh": UNIT_KWH, "wh": "wh", "mwh": "mwh",
}


@dataclass(slots=True)
class TankState:
    """Alles, was die Sensoren anzeigen."""

    level: float = 0.0
    level_percent: float = 0.0
    usable_percent: float = 0.0
    usable_capacity: float = 0.0
    energy_kwh: float = 0.0
    value_eur: float = 0.0
    consumed_liters: float = 0.0
    consumed_units: float = 0.0
    per_day: float | None = None
    days_since_reference: float = 0.0
    reference_at: datetime | None = None
    profile: Profile | None = None
    forecast: Forecast = field(default_factory=Forecast)
    last_delivery: dict[str, Any] | None = None
    missing_sources: list[str] = field(default_factory=list)


class TankCoordinator(DataUpdateCoordinator[TankState]):
    """Liest die Statistik und hält Füllstand, Profil und Prognose aktuell."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry
        self._store: Store = Store(
            hass, STORAGE_VERSION, STORAGE_KEY.format(entry_id=entry.entry_id)
        )
        self._data: dict[str, Any] = {}
        self._profile: Profile | None = None
        self._profile_read: datetime | None = None
        self._units: dict[str, str] = {}
        self._units_read: datetime | None = None
        self._gemeldet: set[str] = set()

    # ------------------------------------------------------------ Konfiguration

    def option(self, key: str, default: Any) -> Any:
        """Optionen haben Vorrang vor den Einrichtungsdaten."""
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

    @property
    def sources(self) -> list[str]:
        quellen = self.option(CONF_SOURCES, [])
        return list(quellen) if isinstance(quellen, (list, tuple)) else [quellen]

    @property
    def capacity(self) -> float:
        return float(self.option(CONF_CAPACITY, DEFAULT_CAPACITY))

    @property
    def usable_capacity(self) -> float:
        return self.capacity * float(self.option(CONF_MAX_FILL, DEFAULT_MAX_FILL)) / 100

    @property
    def liter_per_m3(self) -> float:
        return float(self.option(CONF_LITER_PER_M3, DEFAULT_LITER_PER_M3))

    @property
    def kwh_per_liter(self) -> float:
        return float(self.option(CONF_KWH_PER_LITER, DEFAULT_KWH_PER_LITER))

    @property
    def price(self) -> float:
        return float(self.option(CONF_PRICE, DEFAULT_PRICE))

    @property
    def reserve(self) -> float:
        return float(self.option(CONF_RESERVE, DEFAULT_RESERVE))

    @property
    def lead_time(self) -> int:
        return int(self.option(CONF_LEAD_TIME, DEFAULT_LEAD_TIME))

    @property
    def profile_years(self) -> int:
        return int(self.option(CONF_PROFILE_YEARS, DEFAULT_PROFILE_YEARS))

    @property
    def correction(self) -> float:
        return float(self.option(CONF_CORRECTION, DEFAULT_CORRECTION)) / 100

    @property
    def deliveries(self) -> list[dict[str, Any]]:
        return list(self._data.get(STORE_DELIVERIES, []))

    # ------------------------------------------------------------ Einheiten

    async def _async_read_units(self) -> None:
        """Einheiten aus den Statistik-Metadaten holen.

        Wichtig, weil alle Werte hier in der Einheit der Statistik gelesen
        werden (nicht in der Anzeigeeinheit). Wer für einen Sensor eine
        abweichende Anzeigeeinheit einstellt, bekommt sonst eine stille
        Fehlrechnung.
        """
        jetzt = dt_util.utcnow()
        if self._units_read and (jetzt - self._units_read) < UNIT_INTERVAL:
            return
        try:
            metadaten = await async_list_statistic_ids(self.hass, set(self.sources), "sum")
        except Exception:  # pragma: no cover - Recorder noch nicht bereit
            _LOGGER.debug("Statistik-Metadaten noch nicht lesbar", exc_info=True)
            return
        self._units = {
            eintrag["statistic_id"]: eintrag.get("statistics_unit_of_measurement") or ""
            for eintrag in metadaten
        }
        self._units_read = jetzt

    def _unit_of(self, entity_id: str) -> str:
        """Einheit einer Quelle bestimmen – konfiguriert, aus der Statistik, sonst geraten."""
        gewaehlt = self.option(CONF_SOURCE_UNIT, UNIT_AUTO)
        if gewaehlt != UNIT_AUTO:
            return gewaehlt
        einheit = self._units.get(entity_id)
        if not einheit:
            zustand = self.hass.states.get(entity_id)
            einheit = (zustand.attributes.get("unit_of_measurement") if zustand else "") or ""
        return UNIT_ALIASES.get(einheit.strip().lower(), UNIT_M3)

    def _liter_factor(self, entity_id: str) -> float:
        """Umrechnung einer Zählereinheit in Liter Flüssiggas."""
        einheit = self._unit_of(entity_id)
        if einheit == UNIT_LITER:
            return 1.0
        if einheit == UNIT_KWH:
            return 1.0 / max(self.kwh_per_liter, 0.1)
        if einheit == "wh":
            return 0.001 / max(self.kwh_per_liter, 0.1)
        if einheit == "mwh":
            return 1000.0 / max(self.kwh_per_liter, 0.1)
        return self.liter_per_m3

    @property
    def all_sources_are_volume(self) -> bool:
        """Nur bei reinen m³-Zählern lässt sich der Faktor L/m³ kalibrieren."""
        return bool(self.sources) and all(
            self._unit_of(eid) == UNIT_M3 for eid in self.sources
        )

    # ------------------------------------------------------------ Statistik

    async def _async_current_sums(self) -> tuple[dict[str, float], list[str]]:
        """Aktuelle kumulierte Statistiksumme je Quelle."""
        recorder = get_instance(self.hass)
        summen: dict[str, float] = {}
        fehlend: list[str] = []

        for entity_id in self.sources:
            zeilen = await recorder.async_add_executor_job(
                get_last_short_term_statistics, self.hass, 1, entity_id, False, {"sum"}
            )
            wert = self._first_sum(zeilen.get(entity_id))
            if wert is None:
                # Kurzzeitstatistik reicht nur ~10 Tage zurück
                wert = await self._async_sum_from_long_term(entity_id)
            if wert is None:
                fehlend.append(entity_id)
                if entity_id not in self._gemeldet:
                    self._gemeldet.add(entity_id)
                    _LOGGER.warning(
                        "Für %s gibt es keine Statistik. Der Sensor braucht "
                        "state_class 'total_increasing' oder 'total' – solange das "
                        "fehlt, bleiben die Tankwerte nicht verfügbar",
                        entity_id,
                    )
            else:
                summen[entity_id] = wert
                self._gemeldet.discard(entity_id)
        return summen, fehlend

    async def _async_sum_from_long_term(self, entity_id: str) -> float | None:
        recorder = get_instance(self.hass)
        start = dt_util.utcnow() - timedelta(days=30)
        zeilen = await recorder.async_add_executor_job(
            statistics_during_period,
            self.hass, start, None, {entity_id}, "hour", None, {"sum"},
        )
        reihe = zeilen.get(entity_id) or []
        return self._first_sum(reihe[-1:] if reihe else None)

    async def async_sums_at(self, moment: datetime) -> dict[str, float]:
        """Statistiksummen zu einem Zeitpunkt in der Vergangenheit."""
        if moment >= dt_util.utcnow() - timedelta(hours=2):
            summen, _ = await self._async_current_sums()
            return summen

        recorder = get_instance(self.hass)
        zeilen = await recorder.async_add_executor_job(
            statistics_during_period,
            self.hass,
            moment - timedelta(hours=6),
            moment + timedelta(hours=30),
            set(self.sources),
            "hour",
            None,
            {"sum"},
        )
        ziel = moment.timestamp()
        summen: dict[str, float] = {}
        for entity_id, reihe in zeilen.items():
            passend = [z for z in reihe if z.get("start", 0) <= ziel and z.get("sum") is not None]
            quelle = passend[-1:] if passend else reihe[:1]
            wert = self._first_sum(quelle)
            if wert is not None:
                summen[entity_id] = wert
        return summen

    @staticmethod
    def _first_sum(zeilen: Any) -> float | None:
        if not zeilen:
            return None
        wert = zeilen[0].get("sum")
        return float(wert) if wert is not None else None

    async def _async_read_profile(self) -> Profile:
        """Monatsverbrauch der letzten Jahre aus der Langzeitstatistik lesen."""
        await self._async_read_units()
        jahre = self.profile_years
        start = dt_util.utcnow() - timedelta(days=365 * jahre + 62)
        recorder = get_instance(self.hass)
        zeilen = await recorder.async_add_executor_job(
            statistics_during_period,
            self.hass, start, None, set(self.sources), "month", None, {"change"},
        )

        monatlich: dict[tuple[int, int], float] = {}
        for entity_id, reihe in zeilen.items():
            faktor = self._liter_factor(entity_id)
            for zeile in reihe:
                aenderung = zeile.get("change")
                if aenderung is None:
                    continue
                zeitpunkt = dt_util.as_local(dt_util.utc_from_timestamp(zeile["start"]))
                schluessel = (zeitpunkt.year, zeitpunkt.month)
                monatlich[schluessel] = monatlich.get(schluessel, 0.0) + max(
                    0.0, float(aenderung)
                ) * faktor

        profil = build_profile(monatlich, jahre, dt_util.now().date())
        _LOGGER.debug(
            "Monatsprofil neu gelesen: %s L/a aus %s gemessenen Monaten",
            round(profil.annual), profil.measured_months,
        )
        return profil

    # ------------------------------------------------------------ Speicher

    async def async_load(self) -> None:
        self._data = await self._store.async_load() or {}

    async def _async_save(self) -> None:
        await self._store.async_save(self._data)

    # ------------------------------------------------------------ Aktualisierung

    async def _async_update_data(self) -> TankState:
        await self._async_read_units()
        summen, fehlend = await self._async_current_sums()
        basis: dict[str, float] = dict(self._data.get(STORE_BASELINE, {}))
        geaendert = False

        # Erststart oder neu hinzugefügte Quelle: ab jetzt zählen
        for entity_id, wert in summen.items():
            if entity_id not in basis:
                basis[entity_id] = wert
                geaendert = True

        verbrauch_einheiten = 0.0
        verbrauch_liter = 0.0
        for entity_id, wert in summen.items():
            delta = wert - basis[entity_id]
            if delta < 0:
                # Statistik wurde gelöscht oder neu aufgebaut – neu ansetzen
                _LOGGER.warning(
                    "Statistiksumme von %s ist gesunken (%.1f < %.1f); "
                    "Bezugspunkt wird nachgezogen",
                    entity_id, wert, basis[entity_id],
                )
                basis[entity_id] = wert
                geaendert = True
                delta = 0.0
            verbrauch_einheiten += delta
            verbrauch_liter += delta * self._liter_factor(entity_id)

        if geaendert:
            self._data[STORE_BASELINE] = basis
            self._data.setdefault(STORE_REFERENCE_AT, dt_util.utcnow().isoformat())
            await self._async_save()

        referenz = float(self._data.get(STORE_LEVEL, 0.0))
        stand = min(max(referenz - verbrauch_liter, 0.0), self.usable_capacity)

        # Profil höchstens alle paar Stunden neu lesen
        jetzt = dt_util.utcnow()
        if self._profile is None or self._profile_read is None or (
            jetzt - self._profile_read
        ) > PROFILE_INTERVAL:
            try:
                self._profile = await self._async_read_profile()
            except Exception:
                _LOGGER.warning(
                    "Monatsprofil konnte nicht aus der Statistik gelesen werden; "
                    "es wird vorerst geschätzt", exc_info=True,
                )
                if self._profile is None:
                    self._profile = build_profile({}, self.profile_years, dt_util.now().date())
            self._profile_read = jetzt

        referenz_zeit = self._reference_at()
        tage = (
            max((dt_util.utcnow() - referenz_zeit).total_seconds() / 86400, 0.0)
            if referenz_zeit
            else 0.0
        )

        return TankState(
            level=round(stand, 1),
            level_percent=round(stand / max(self.capacity, 1) * 100, 1),
            usable_percent=round(stand / max(self.usable_capacity, 1) * 100, 1),
            usable_capacity=round(self.usable_capacity, 1),
            energy_kwh=round(stand * self.kwh_per_liter),
            value_eur=round(stand * self.price, 2),
            consumed_liters=round(verbrauch_liter, 1),
            consumed_units=round(verbrauch_einheiten, 3),
            per_day=round(verbrauch_liter / tage, 2) if tage >= 1 else None,
            days_since_reference=round(tage, 1),
            reference_at=referenz_zeit,
            profile=self._profile,
            forecast=simulate(
                stand,
                self._profile,
                self.reserve,
                self.lead_time,
                dt_util.now().date(),
                self.correction,
            ),
            last_delivery=self.deliveries[-1] if self.deliveries else None,
            missing_sources=fehlend,
        )

    def _reference_at(self) -> datetime | None:
        roh = self._data.get(STORE_REFERENCE_AT)
        return dt_util.parse_datetime(roh) if roh else None

    # ------------------------------------------------------------ Aktionen

    async def async_set_level(
        self, *, percent: float | None = None, liters: float | None = None
    ) -> float:
        """Füllstand direkt setzen (Tankuhr abgelesen) und Zählung neu starten."""
        if percent is None and liters is None:
            raise ValueError("Es muss Prozent oder Liter angegeben werden")
        neu = liters if liters is not None else (percent or 0) / 100 * self.capacity
        neu = min(max(float(neu), 0.0), self.usable_capacity)

        summen, _ = await self._async_current_sums()
        self._data[STORE_LEVEL] = round(neu, 1)
        self._data[STORE_BASELINE] = summen
        self._data[STORE_REFERENCE_AT] = dt_util.utcnow().isoformat()
        await self._async_save()
        await self.async_request_refresh()
        return neu

    async def async_register_delivery(
        self,
        *,
        liters: float | None = None,
        level_before_percent: float | None = None,
        level_after_percent: float | None = None,
        price: float | None = None,
        moment: datetime | None = None,
        calibrate: bool = True,
    ) -> dict[str, Any]:
        """Betankung eintragen – auch eine Teilbetankung.

        Der neue Stand ergibt sich aus dem Stand *vor* der Lieferung plus der
        Liefermenge; wer nur 1.000 L tankt, landet also nicht bei "voll".
        Eine abgelesene Tankuhr nach der Betankung hat Vorrang, weil sie die
        direkte Messung ist.
        """
        zeitpunkt = moment or dt_util.utcnow()
        summen = await self.async_sums_at(zeitpunkt)
        referenz = float(self._data.get(STORE_LEVEL, 0.0))

        # Verbrauch zwischen letztem Bezugspunkt und der Betankung
        basis = self._data.get(STORE_BASELINE, {})
        einheiten = 0.0
        liter_verbraucht = 0.0
        for entity_id, wert in summen.items():
            delta = max(wert - float(basis.get(entity_id, wert)), 0.0)
            einheiten += delta
            liter_verbraucht += delta * self._liter_factor(entity_id)

        gerechneter_stand = max(referenz - liter_verbraucht, 0.0)

        vorher = (
            level_before_percent / 100 * self.capacity
            if level_before_percent is not None
            else gerechneter_stand
        )

        # Kalibrierung: abgelesener Verbrauch gegen gezählte Einheiten
        faktor_alt = self.liter_per_m3
        faktor_neu: float | None = None
        if (
            calibrate
            and level_before_percent is not None
            and self.all_sources_are_volume
            and einheiten >= MIN_UNITS_FOR_CALIBRATION
        ):
            echt = referenz - vorher
            if echt > 0:
                kandidat = round(echt / einheiten, 3)
                if FACTOR_LIMITS[0] <= kandidat <= FACTOR_LIMITS[1]:
                    faktor_neu = kandidat
                else:
                    _LOGGER.warning(
                        "Kalibrierung ergäbe %.3f L/m³ – außerhalb des plausiblen "
                        "Bereichs %s, daher verworfen", kandidat, FACTOR_LIMITS,
                    )

        if level_after_percent is not None:
            neu = level_after_percent / 100 * self.capacity
        else:
            neu = vorher + float(liters or 0.0)
        neu = min(max(neu, 0.0), self.usable_capacity)

        eintrag = {
            "datum": dt_util.as_local(zeitpunkt).date().isoformat(),
            "liter": round(float(liters), 1) if liters is not None else None,
            "stand_vorher": round(vorher, 1),
            "stand_nachher": round(neu, 1),
            "preis_pro_liter": price if price is not None else None,
            "kosten": round(float(liters) * price, 2)
            if liters is not None and price is not None
            else None,
            "faktor_alt": faktor_alt,
            "faktor_neu": faktor_neu,
        }

        lieferungen = self.deliveries
        lieferungen.append(eintrag)
        self._data[STORE_DELIVERIES] = lieferungen[-MAX_DELIVERIES:]
        self._data[STORE_LEVEL] = round(neu, 1)
        self._data[STORE_BASELINE] = summen
        self._data[STORE_REFERENCE_AT] = zeitpunkt.isoformat()
        await self._async_save()

        if faktor_neu is not None:
            _LOGGER.info(
                "Kalibriert: %.1f Einheiten entsprachen %.0f L → %.3f L/m³ (vorher %.3f)",
                einheiten, referenz - vorher, faktor_neu, faktor_alt,
            )
            optionen = dict(self.entry.options)
            optionen[CONF_LITER_PER_M3] = faktor_neu
            # löst das Neuladen des Eintrags aus – Speicher ist schon geschrieben
            self.hass.config_entries.async_update_entry(self.entry, options=optionen)
        else:
            await self.async_request_refresh()
        return eintrag

    async def async_refresh_profile(self) -> Profile:
        """Monatsprofil sofort neu aus der Statistik lesen."""
        self._profile = await self._async_read_profile()
        self._profile_read = dt_util.utcnow()
        await self.async_request_refresh()
        return self._profile
