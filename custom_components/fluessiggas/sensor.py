"""Sensoren des Flüssiggastanks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, VERSION
from .coordinator import TankCoordinator, TankState

MONATSNAMEN = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
               "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def _als_datum(wert: Any) -> datetime | None:
    """Ein Datum aus der Prognose in einen Zeitstempel zur Mittagszeit wandeln."""
    if wert is None:
        return None
    return dt_util.start_of_local_day(wert).replace(hour=12)


@dataclass(frozen=True, kw_only=True)
class TankSensorDescription(SensorEntityDescription):
    """Beschreibt einen Tanksensor."""

    value_fn: Callable[[TankState, TankCoordinator], Any]
    attrs_fn: Callable[[TankState, TankCoordinator], dict[str, Any]] | None = None


SENSOREN: tuple[TankSensorDescription, ...] = (
    TankSensorDescription(
        key="inhalt",
        translation_key="inhalt",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda s, c: s.level,
        attrs_fn=lambda s, c: {
            "nennvolumen": round(c.capacity),
            "nutzbares_volumen": s.usable_capacity,
            "reserve": c.reserve,
            # von der Karte für die Einfärbung genutzt
            "warnschwelle_prozent": c.warn_percent,
        },
    ),
    TankSensorDescription(
        key="inhalt_prozent",
        translation_key="inhalt_prozent",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s, c: s.level_percent,
    ),
    TankSensorDescription(
        key="inhalt_nutzbar",
        translation_key="inhalt_nutzbar",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s, c: s.usable_percent,
    ),
    TankSensorDescription(
        key="restenergie",
        translation_key="restenergie",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda s, c: s.energy_kwh,
    ),
    TankSensorDescription(
        key="restwert",
        translation_key="restwert",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda s, c: s.value_eur,
    ),
    TankSensorDescription(
        key="gaspreis",
        translation_key="gaspreis",
        native_unit_of_measurement="EUR/L",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda s, c: s.price,
        attrs_fn=lambda s, c: {
            "quelle": c.price_entity or "integration",
            "preis_pro_m3": round(s.price * c.liter_per_m3, 4),
            # damit eigene Templates den kalibrierten Faktor mitbenutzen können
            "liter_pro_m3": round(c.liter_per_m3, 3),
            "statistik_quelle": c.price_stats_entity,
            "statistik_einheit": c.price_stats_unit or None,
            "preisverlauf": c.price_history,
        },
    ),
    TankSensorDescription(
        key="verbrauch_seit_betankung",
        translation_key="verbrauch_seit_betankung",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda s, c: s.consumed_liters,
        attrs_fn=lambda s, c: {
            "gezaehlte_einheiten": s.consumed_units,
            "tage": s.days_since_reference,
        },
    ),
    TankSensorDescription(
        key="tagesverbrauch",
        translation_key="tagesverbrauch",
        native_unit_of_measurement="L/d",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s, c: s.per_day,
    ),
    TankSensorDescription(
        key="jahresverbrauch",
        translation_key="jahresverbrauch",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        suggested_display_precision=0,
        value_fn=lambda s, c: round(s.profile.annual * c.correction) if s.profile else None,
        attrs_fn=lambda s, c: _profil_attribute(s, c),
    ),
    TankSensorDescription(
        key="reichweite",
        translation_key="reichweite",
        native_unit_of_measurement="d",
        suggested_display_precision=0,
        value_fn=lambda s, c: s.forecast.days_to_empty,
        attrs_fn=lambda s, c: {
            "tage_bis_reserve": s.forecast.days_to_reserve,
            "monate": s.forecast.months,
        },
    ),
    TankSensorDescription(
        key="leer_am",
        translation_key="leer_am",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s, c: _als_datum(s.forecast.empty_on),
    ),
    TankSensorDescription(
        key="reserve_am",
        translation_key="reserve_am",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s, c: _als_datum(s.forecast.reserve_on),
    ),
    TankSensorDescription(
        key="bestellen_bis",
        translation_key="bestellen_bis",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s, c: _als_datum(s.forecast.order_by),
    ),
    TankSensorDescription(
        key="letzte_betankung",
        translation_key="letzte_betankung",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s, c: (
            _als_datum(dt_util.parse_date(s.last_delivery["datum"]))
            if s.last_delivery and s.last_delivery.get("datum")
            else None
        ),
        attrs_fn=lambda s, c: {
            **(s.last_delivery or {}),
            "lieferungen": c.deliveries[-12:],
        },
    ),
)


def _profil_attribute(s: TankState, c: TankCoordinator) -> dict[str, Any]:
    """Das Monatsprofil in einer les- und darstellbaren Form."""
    if not s.profile:
        return {}
    return {
        "monatsprofil": {
            MONATSNAMEN[i]: round(liter * c.correction, 1)
            for i, liter in enumerate(s.profile.liters)
        },
        "gemessene_jahre": {
            MONATSNAMEN[i]: anzahl for i, anzahl in enumerate(s.profile.counts)
        },
        "gemessene_monate": s.profile.measured_months,
        "energie_kwh": round(s.profile.annual * c.correction * c.kwh_per_liter),
        "kosten_eur": round(s.profile.annual * c.correction * c.price),
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Any,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sensoren für einen Tank anlegen."""
    coordinator: TankCoordinator = entry.runtime_data
    async_add_entities(TankSensor(coordinator, entry, b) for b in SENSOREN)


class TankSensor(CoordinatorEntity[TankCoordinator], SensorEntity):
    """Ein einzelner Wert des Tanks."""

    _attr_has_entity_name = True
    entity_description: TankSensorDescription

    def __init__(
        self,
        coordinator: TankCoordinator,
        entry: Any,
        description: TankSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Flüssiggas",
            model="Tank",
            entry_type=DeviceEntryType.SERVICE,
            sw_version=VERSION,
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data, self.coordinator)

    @property
    def available(self) -> bool:
        if not super().available or self.coordinator.data is None:
            return False
        # Ohne lesbare Statistik ist jeder Wert geraten
        return not self.coordinator.data.missing_sources

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # tank_id und kennung machen die Entitäten für die Karte auffindbar,
        # unabhängig von Sprache und selbst vergebenen Entity-IDs.
        attribute: dict[str, Any] = {
            "tank_id": self._entry_id,
            "kennung": self.entity_description.key,
        }
        if self.entity_description.attrs_fn:
            attribute.update(
                self.entity_description.attrs_fn(self.coordinator.data, self.coordinator)
            )
        return attribute
