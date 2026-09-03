"""Gaspreis als bedienbare Zahl.

Nur vorhanden, wenn in der Konfiguration *kein* eigener Preis-Helfer angegeben
wurde. Wer bereits eine input_number mit seinem Gaspreis pflegt, soll sie
weiter benutzen – dann trägt die Integration dort ein und legt nichts Zweites an.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import TankCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Any,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TankCoordinator = entry.runtime_data
    if coordinator.price_entity:
        return
    async_add_entities([GaspreisNumber(coordinator, entry)])


class GaspreisNumber(CoordinatorEntity[TankCoordinator], NumberEntity):
    """Gaspreis in EUR je Liter."""

    _attr_has_entity_name = True
    _attr_translation_key = "gaspreis"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 10.0
    _attr_native_step = 0.001
    _attr_native_unit_of_measurement = "EUR/L"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: TankCoordinator, entry: Any) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_gaspreis"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Flüssiggas",
            model="Tank",
            entry_type=DeviceEntryType.SERVICE,
            sw_version=VERSION,
        )

    @property
    def native_value(self) -> float:
        return round(self.coordinator.price, 4)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_price(value)
