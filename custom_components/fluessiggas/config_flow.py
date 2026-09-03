"""Einrichtung des Flüssiggastanks über die Oberfläche."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CAPACITY,
    CONF_CORRECTION,
    CONF_KWH_PER_LITER,
    CONF_LEAD_TIME,
    CONF_LITER_PER_M3,
    CONF_MAX_FILL,
    CONF_PRICE,
    CONF_PRICE_ENTITY,
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
    DEFAULT_NAME,
    DEFAULT_PRICE,
    DEFAULT_PROFILE_YEARS,
    DEFAULT_RESERVE,
    DOMAIN,
    SOURCE_UNITS,
    UNIT_AUTO,
)


def _zahl(
    minimum: float, maximum: float, schritt: float, einheit: str | None = None
) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=schritt,
            unit_of_measurement=einheit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _tank_schema(mit_name: bool) -> vol.Schema:
    """Tankdaten und Verbrauchsquellen."""
    felder: dict[Any, Any] = {}
    if mit_name:
        felder[vol.Required(CONF_NAME, default=DEFAULT_NAME)] = selector.TextSelector()
    felder.update(
        {
            vol.Required(CONF_SOURCES): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
            ),
            vol.Required(CONF_SOURCE_UNIT, default=UNIT_AUTO): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=SOURCE_UNITS,
                    translation_key="source_unit",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_CAPACITY, default=DEFAULT_CAPACITY): _zahl(100, 50000, 10, "L"),
            vol.Required(CONF_MAX_FILL, default=DEFAULT_MAX_FILL): _zahl(50, 100, 1, "%"),
        }
    )
    return vol.Schema(felder)


def _optionale_leeren(user_input: dict[str, Any]) -> dict[str, Any]:
    """Nicht ausgefüllte optionale Felder ausdrücklich auf None setzen."""
    daten = dict(user_input)
    daten.setdefault(CONF_PRICE_ENTITY, None)
    return daten


def _details_schema() -> vol.Schema:
    """Umrechnung, Preis und Prognoseverhalten."""
    return vol.Schema(
        {
            vol.Required(CONF_LITER_PER_M3, default=DEFAULT_LITER_PER_M3): _zahl(
                2, 6, 0.001, "L/m³"
            ),
            vol.Required(CONF_KWH_PER_LITER, default=DEFAULT_KWH_PER_LITER): _zahl(
                4, 9, 0.01, "kWh/L"
            ),
            vol.Required(CONF_PRICE, default=DEFAULT_PRICE): _zahl(0, 10, 0.001, "EUR/L"),
            vol.Optional(CONF_PRICE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["input_number", "number", "sensor"], multiple=False
                )
            ),
            vol.Required(CONF_RESERVE, default=DEFAULT_RESERVE): _zahl(0, 5000, 10, "L"),
            vol.Required(CONF_LEAD_TIME, default=DEFAULT_LEAD_TIME): _zahl(0, 180, 1, "d"),
            vol.Required(CONF_PROFILE_YEARS, default=DEFAULT_PROFILE_YEARS): _zahl(1, 10, 1, "a"),
            vol.Required(CONF_CORRECTION, default=DEFAULT_CORRECTION): _zahl(25, 250, 1, "%"),
        }
    )


class FluessiggasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtungsdialog."""

    VERSION = 1

    def __init__(self) -> None:
        self._daten: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schritt 1: Tank und Verbrauchsquellen."""
        fehler: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_SOURCES):
                fehler[CONF_SOURCES] = "keine_quelle"
            else:
                self._daten = dict(user_input)
                return await self.async_step_details()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _tank_schema(True), user_input or {}
            ),
            errors=fehler,
        )

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schritt 2: Umrechnung, Preis, Prognose."""
        if user_input is not None:
            name = self._daten.pop(CONF_NAME, DEFAULT_NAME)
            return self.async_create_entry(
                title=name, data={**self._daten, **_optionale_leeren(user_input)}
            )

        return self.async_show_form(
            step_id="details",
            data_schema=_details_schema(),
            description_placeholders={"tank": self._daten.get(CONF_NAME, DEFAULT_NAME)},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return FluessiggasOptionsFlow()


class FluessiggasOptionsFlow(OptionsFlow):
    """Nachträgliche Änderungen – alle Werte bleiben editierbar."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        fehler: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_SOURCES):
                fehler[CONF_SOURCES] = "keine_quelle"
            else:
                return self.async_create_entry(data=_optionale_leeren(user_input))

        aktuell = {**self.config_entry.data, **self.config_entry.options}
        aktuell.pop(CONF_NAME, None)
        aktuell = {k: v for k, v in aktuell.items() if v is not None}
        schema = _tank_schema(False).extend(_details_schema().schema)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, aktuell),
            errors=fehler,
        )
