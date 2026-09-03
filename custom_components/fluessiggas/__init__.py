"""Flüssiggastank – Füllstand, Verbrauch und Leer-Prognose."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import LOVELACE_DATA, MODE_STORAGE
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CALIBRATE,
    ATTR_DATE,
    ATTR_LEVEL_AFTER,
    ATTR_LEVEL_BEFORE,
    ATTR_LITERS,
    ATTR_PERCENT,
    ATTR_PRICE,
    CARD_FILENAME,
    CARD_URL,
    DOMAIN,
    SERVICE_DELIVERY,
    SERVICE_ADD_HISTORY,
    SERVICE_REFRESH_PROFILE,
    SERVICE_SET_LEVEL,
    VERSION,
)
from .coordinator import TankCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.NUMBER, Platform.SENSOR]
KARTE_REGISTRIERT = f"{DOMAIN}_karte"
#: Versionsanhang, damit ein Update den Browser-Cache umgeht
KARTE_RESSOURCE = f"{CARD_URL}?v={VERSION}"


def _dienst_schema(felder: dict) -> vol.Schema:
    """Feldschema plus Zielangaben.

    Bewusst nicht cv.make_entity_service_schema: das erzwingt ein Ziel. Bei
    genau einem eingerichteten Tank soll ein Aufruf ohne Ziel funktionieren –
    das Ziel-Auswahlfeld in der Oberfläche kommt ohnehin aus services.yaml.
    """
    return vol.Schema({**felder, **cv.ENTITY_SERVICE_FIELDS}, extra=vol.REMOVE_EXTRA)


DELIVERY_FIELDS = (
    {
        vol.Optional(ATTR_LITERS): vol.All(vol.Coerce(float), vol.Range(min=0, max=50000)),
        vol.Optional(ATTR_LEVEL_BEFORE): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional(ATTR_LEVEL_AFTER): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional(ATTR_PRICE): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional(ATTR_DATE): cv.date,
        vol.Optional(ATTR_CALIBRATE, default=True): cv.boolean,
    }
)

ADD_HISTORY_FIELDS = (
    {
        vol.Required(ATTR_DATE): cv.date,
        vol.Optional(ATTR_LITERS): vol.All(vol.Coerce(float), vol.Range(min=0, max=50000)),
        vol.Optional(ATTR_PRICE): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    }
)

SET_LEVEL_FIELDS = (
    {
        vol.Optional(ATTR_PERCENT): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
        vol.Optional(ATTR_LITERS): vol.All(vol.Coerce(float), vol.Range(min=0, max=50000)),
    }
)

TankConfigEntry = ConfigEntry[TankCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Wird geladen, bevor der erste Tank eingerichtet wird.

    Die Karte hängt bewusst hier und nicht in async_setup_entry: Home Assistant
    backt die Liste der Zusatz-Module beim Ausliefern der Seite in das HTML.
    Wird sie erst nach dem ersten Statistiklauf angemeldet, lädt der Browser
    nach einem Neustart eine Seite ohne unser Skript – die Karte meldet dann
    "custom element doesn't exist" und die Kartenauswahl dreht sich endlos.
    Hier registriert, steht die Route auch dann, wenn die Einrichtung eines
    Tanks später scheitert oder wiederholt wird.
    """
    await _async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TankConfigEntry) -> bool:
    """Einen Tank einrichten."""
    await _async_register_card(hass)

    coordinator = TankCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    _async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TankConfigEntry) -> bool:
    """Tank wieder abbauen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: TankConfigEntry) -> None:
    """Beim Entfernen des letzten Tanks die Lovelace-Ressource mitnehmen."""
    if hass.config_entries.async_entries(DOMAIN):
        return
    await _async_remove_resource(hass)


async def _async_reload_entry(hass: HomeAssistant, entry: TankConfigEntry) -> None:
    """Nach geänderten Optionen neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_card(hass: HomeAssistant) -> None:
    """Die mitgelieferte Lovelace-Karte ausliefern und einbinden.

    Damit ist nach der Installation über HACS kein manueller Eintrag unter
    Einstellungen → Dashboards → Ressourcen mehr nötig.
    """
    if hass.data.get(KARTE_REGISTRIERT):
        return
    hass.data[KARTE_REGISTRIERT] = True

    pfad = Path(__file__).parent / "frontend" / CARD_FILENAME
    # Dateizugriff gehört nicht in den Event-Loop
    if not await hass.async_add_executor_job(pfad.is_file):
        _LOGGER.warning("Karte %s nicht gefunden – sie wird nicht eingebunden", pfad)
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(pfad), cache_headers=False)]
    )
    add_extra_js_url(hass, KARTE_RESSOURCE)
    await _async_register_resource(hass)
    _LOGGER.debug("Lovelace-Karte unter %s eingebunden", KARTE_RESSOURCE)


async def _async_register_resource(hass: HomeAssistant) -> None:
    """Die Karte zusätzlich als Lovelace-Ressource eintragen.

    add_extra_js_url allein genügt nicht: Der Service Worker des Frontends
    liefert jede Seite mit StaleWhileRevalidate aus einem 24-Stunden-Cache
    ("First access might bring stale data from cache"), und über HTTPS ist er
    aktiv. Ein in das HTML gebackenes Skript-Tag fehlt deshalb so lange, bis
    der Cache nachzieht – die Karte meldet "custom element doesn't exist",
    beim nächsten Laden geht es, beim übernächsten wieder nicht.

    Die Ressourcenliste holt das Frontend dagegen über den Websocket, und
    /api/* ist im Service Worker als NetworkOnly registriert. Sie ist damit
    immer aktuell. Beide Wege zeigen auf dieselbe URL, das Modul wird also
    trotzdem nur einmal geladen.
    """
    if (lovelace := hass.data.get(LOVELACE_DATA)) is None:
        return
    if lovelace.resource_mode != MODE_STORAGE:
        _LOGGER.info(
            "Lovelace läuft im YAML-Modus. Bitte '%s' von Hand als Ressource "
            "vom Typ 'module' eintragen",
            KARTE_RESSOURCE,
        )
        return

    ressourcen = lovelace.resources
    await ressourcen.async_get_info()
    for eintrag in ressourcen.async_items():
        if not str(eintrag.get("url", "")).startswith(CARD_URL):
            continue
        if eintrag.get("url") != KARTE_RESSOURCE:
            await ressourcen.async_update_item(
                eintrag["id"], {"res_type": "module", "url": KARTE_RESSOURCE}
            )
            _LOGGER.info("Lovelace-Ressource auf %s aktualisiert", KARTE_RESSOURCE)
        return

    await ressourcen.async_create_item({"res_type": "module", "url": KARTE_RESSOURCE})
    _LOGGER.info("Lovelace-Ressource %s angelegt", KARTE_RESSOURCE)


async def _async_remove_resource(hass: HomeAssistant) -> None:
    """Ressource entfernen, wenn der letzte Tank gelöscht wird.

    Bliebe sie stehen, zeigte sie nach der Deinstallation ins Leere – und eine
    tote Ressource kann die Kartenauswahl im Dashboard blockieren.
    """
    if (lovelace := hass.data.get(LOVELACE_DATA)) is None:
        return
    if lovelace.resource_mode != MODE_STORAGE:
        return
    ressourcen = lovelace.resources
    await ressourcen.async_get_info()
    for eintrag in list(ressourcen.async_items()):
        if str(eintrag.get("url", "")).startswith(CARD_URL):
            await ressourcen.async_delete_item(eintrag["id"])
            _LOGGER.debug("Lovelace-Ressource %s entfernt", eintrag.get("url"))


def _async_register_services(hass: HomeAssistant) -> None:
    """Dienste einmalig registrieren."""
    if hass.services.has_service(DOMAIN, SERVICE_DELIVERY):
        return

    def _entry_ids(call: ServiceCall) -> set[str]:
        """Ziel des Dienstaufrufs auf Konfigurationseinträge abbilden.

        Bewusst über die Registries statt über einen Ziel-Helfer: Der ist in
        Home Assistant schon zwischen Modulen umgezogen, die Registries nicht.
        """
        entities = er.async_get(hass)
        devices = dr.async_get(hass)
        gefunden: set[str] = set()

        def merke(eintrag) -> None:
            if eintrag and eintrag.platform == DOMAIN and eintrag.config_entry_id:
                gefunden.add(eintrag.config_entry_id)

        for entity_id in cv.ensure_list(call.data.get("entity_id") or []):
            merke(entities.async_get(entity_id))
        for device_id in cv.ensure_list(call.data.get("device_id") or []):
            for eintrag in er.async_entries_for_device(entities, device_id, True):
                merke(eintrag)
        for area_id in cv.ensure_list(call.data.get("area_id") or []):
            for eintrag in er.async_entries_for_area(entities, area_id):
                merke(eintrag)
            for geraet in dr.async_entries_for_area(devices, area_id):
                for eintrag in er.async_entries_for_device(entities, geraet.id, True):
                    merke(eintrag)
        return gefunden

    async def _coordinators(call: ServiceCall) -> list[TankCoordinator]:
        """Aus dem Ziel des Dienstaufrufs die betroffenen Tanks bestimmen."""
        eintraege: list[TankCoordinator] = []
        entry_ids = _entry_ids(call)

        if not entry_ids:
            # Kein Ziel angegeben: bei genau einem Tank ist die Sache eindeutig
            geladen = hass.config_entries.async_loaded_entries(DOMAIN)
            if len(geladen) == 1:
                entry_ids.add(geladen[0].entry_id)
            else:
                raise ServiceValidationError(
                    "Bitte einen Tank als Ziel angeben – es sind mehrere eingerichtet."
                )

        for entry_id in entry_ids:
            eintrag = hass.config_entries.async_get_entry(entry_id)
            if eintrag and hasattr(eintrag, "runtime_data"):
                eintraege.append(eintrag.runtime_data)
        return eintraege

    async def betankung(call: ServiceCall) -> None:
        datum: datetime | None = None
        if (tag := call.data.get(ATTR_DATE)) is not None:
            datum = dt_util.as_utc(
                dt_util.start_of_local_day(tag) + timedelta(hours=12)
            )
        for coordinator in await _coordinators(call):
            await coordinator.async_register_delivery(
                liters=call.data.get(ATTR_LITERS),
                level_before_percent=call.data.get(ATTR_LEVEL_BEFORE),
                level_after_percent=call.data.get(ATTR_LEVEL_AFTER),
                price=call.data.get(ATTR_PRICE),
                moment=datum,
                calibrate=call.data.get(ATTR_CALIBRATE, True),
            )

    async def fuellstand_setzen(call: ServiceCall) -> None:
        if call.data.get(ATTR_PERCENT) is None and call.data.get(ATTR_LITERS) is None:
            raise ServiceValidationError("Bitte Prozent oder Liter angeben.")
        for coordinator in await _coordinators(call):
            await coordinator.async_set_level(
                percent=call.data.get(ATTR_PERCENT),
                liters=call.data.get(ATTR_LITERS),
            )

    async def lieferung_nachtragen(call: ServiceCall) -> None:
        datum = dt_util.as_utc(
            dt_util.start_of_local_day(call.data[ATTR_DATE]) + timedelta(hours=12)
        )
        for coordinator in await _coordinators(call):
            await coordinator.async_add_history(
                moment=datum,
                liters=call.data.get(ATTR_LITERS),
                price=call.data.get(ATTR_PRICE),
            )

    async def profil_neu_berechnen(call: ServiceCall) -> None:
        for coordinator in await _coordinators(call):
            await coordinator.async_refresh_profile()

    hass.services.async_register(
        DOMAIN, SERVICE_DELIVERY, betankung, schema=_dienst_schema(DELIVERY_FIELDS)
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_LEVEL, fuellstand_setzen,
        schema=_dienst_schema(SET_LEVEL_FIELDS),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_HISTORY, lieferung_nachtragen,
        schema=_dienst_schema(ADD_HISTORY_FIELDS),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH_PROFILE, profil_neu_berechnen,
        schema=_dienst_schema({}),
    )
