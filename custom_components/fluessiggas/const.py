"""Konstanten der Flüssiggastank-Integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "fluessiggas"

# ----------------------------------------------------------------- Konfiguration
CONF_SOURCES: Final = "sources"
CONF_SOURCE_UNIT: Final = "source_unit"
CONF_CAPACITY: Final = "capacity"
CONF_MAX_FILL: Final = "max_fill"
CONF_LITER_PER_M3: Final = "liter_per_m3"
CONF_KWH_PER_LITER: Final = "kwh_per_liter"
CONF_PRICE: Final = "price_per_liter"
CONF_PRICE_ENTITY: Final = "price_entity"
CONF_PRICE_STATS: Final = "price_stats_entity"
CONF_RESERVE: Final = "reserve"
CONF_LEAD_TIME: Final = "lead_time"
CONF_PROFILE_YEARS: Final = "profile_years"
CONF_CORRECTION: Final = "correction"
CONF_WARN_PERCENT: Final = "warn_percent"

UNIT_AUTO: Final = "auto"
UNIT_M3: Final = "m3"
UNIT_LITER: Final = "liter"
UNIT_KWH: Final = "kwh"
SOURCE_UNITS: Final = [UNIT_AUTO, UNIT_M3, UNIT_LITER, UNIT_KWH]

# ----------------------------------------------------------------- Vorgabewerte
DEFAULT_NAME: Final = "Flüssiggastank"
DEFAULT_CAPACITY: Final = 4850.0        # L Nennvolumen
DEFAULT_MAX_FILL: Final = 85.0          # % – Sicherheitsgrenze für die Ausdehnung
DEFAULT_LITER_PER_M3: Final = 3.92      # 1 m³ Propan im Normzustand ≈ 3,92 L flüssig
DEFAULT_KWH_PER_LITER: Final = 7.0      # zwischen Heizwert 6,57 und Brennwert 7,11
DEFAULT_PRICE: Final = 0.70             # EUR/L
DEFAULT_RESERVE: Final = 970.0          # L – 20 % von 4850 L
DEFAULT_LEAD_TIME: Final = 21           # Tage Vorlaufzeit der Lieferung
DEFAULT_PROFILE_YEARS: Final = 2
DEFAULT_CORRECTION: Final = 100.0       # %
DEFAULT_WARN_PERCENT: Final = 30.0      # % der Tankuhr – darunter wird die Karte gelb

# Typische deutsche Heizkurve, Anteil am Jahresverbrauch je Monat in %.
# Dient als Form für Monate, für die noch keine Messwerte vorliegen.
STANDARD_SHARE: Final = [15.5, 13.5, 11.5, 8.0, 4.5, 2.5, 2.0, 2.0, 3.5, 7.5, 12.0, 17.5]
DEFAULT_ANNUAL: Final = 1400.0          # L/a – nur solange gar keine Daten da sind

# ----------------------------------------------------------------- Speicher
STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = "fluessiggas.{entry_id}"

STORE_LEVEL: Final = "level"
STORE_BASELINE: Final = "baseline"
STORE_REFERENCE_AT: Final = "reference_at"
STORE_DELIVERIES: Final = "deliveries"
STORE_PRICE: Final = "price"

# ----------------------------------------------------------------- Dienste
SERVICE_DELIVERY: Final = "betankung"
SERVICE_SET_LEVEL: Final = "fuellstand_setzen"
SERVICE_REFRESH_PROFILE: Final = "profil_neu_berechnen"
SERVICE_ADD_HISTORY: Final = "lieferung_nachtragen"

ATTR_LITERS: Final = "liter"
ATTR_LEVEL_BEFORE: Final = "fuellstand_vorher_prozent"
ATTR_LEVEL_AFTER: Final = "fuellstand_nachher_prozent"
ATTR_PRICE: Final = "preis_pro_liter"
ATTR_DATE: Final = "datum"
ATTR_CALIBRATE: Final = "kalibrieren"
ATTR_PERCENT: Final = "prozent"

# Karte, die von der Integration mit ausgeliefert wird
CARD_URL: Final = "/fluessiggas/lpg-tank-card.js"
CARD_FILENAME: Final = "lpg-tank-card.js"

#: Domains, in die die Integration einen Preis zurückschreiben darf
PRICE_WRITABLE_DOMAINS: Final = ("input_number", "number")

VERSION: Final = "1.2.0"
