"""Constants for the Sweat integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "sweat"

CONF_TEMPERATURE_ENTITY: Final = "temperature_entity"
CONF_HUMIDITY_ENTITY: Final = "humidity_entity"
CONF_DEW_POINT_ENTITY: Final = "dew_point_entity"
CONF_WIND_SPEED_ENTITY: Final = "wind_speed_entity"
CONF_DNI_ENTITY: Final = "dni_entity"
CONF_GHI_ENTITY: Final = "ghi_entity"
CONF_DIFFUSE_ENTITY: Final = "diffuse_entity"
CONF_SOLAR_ALTITUDE_ENTITY: Final = "solar_altitude_entity"

CONF_FORECAST_TEMPERATURE_ENTITY: Final = "forecast_temperature_entity"
CONF_FORECAST_DEW_POINT_ENTITY: Final = "forecast_dew_point_entity"
CONF_FORECAST_WIND_ENTITY: Final = "forecast_wind_entity"
CONF_FORECAST_DNI_ENTITY: Final = "forecast_dni_entity"
CONF_FORECAST_GHI_ENTITY: Final = "forecast_ghi_entity"
CONF_FORECAST_DIFFUSE_ENTITY: Final = "forecast_diffuse_entity"

CONF_ADVANCED: Final = "advanced"
CONF_SOLAR: Final = "solar"
CONF_FORECAST: Final = "forecast"
CONF_METABOLIC_RATE: Final = "metabolic_rate"
CONF_CLOTHING: Final = "clothing"
CONF_WALKING_SPEED: Final = "walking_speed"
CONF_POSTURE: Final = "posture"
CONF_SKY_VIEW_FACTOR: Final = "sky_view_factor"
CONF_BODY_EXPOSURE: Final = "f_bes"
CONF_SOLAR_TRANSMITTANCE: Final = "sol_transmittance"
CONF_SHARP: Final = "sharp"

DEFAULT_METABOLIC_RATE: Final = 2.6
DEFAULT_CLOTHING: Final = 0.36
DEFAULT_WALKING_SPEED: Final = 1.1
DEFAULT_POSTURE: Final = "standing"
DEFAULT_SKY_VIEW_FACTOR: Final = 0.4
DEFAULT_BODY_EXPOSURE: Final = 1.0
DEFAULT_SOLAR_TRANSMITTANCE: Final = 1.0
DEFAULT_SHARP: Final = 90.0

# The Gagge model supports standing and sitting. SolarCal also implements supine,
# but exposing it here would combine supine SolarCal with standing Gagge physiology.
POSTURES: Final = ("standing", "sitting")
FORECAST_LENGTH: Final = 48
UTCI_MIN_WIND_SPEED: Final = 0.5
UTCI_MAX_WIND_SPEED: Final = 17.0

SOLAR_ENTITY_KEYS: Final = (
    CONF_DNI_ENTITY,
    CONF_GHI_ENTITY,
    CONF_DIFFUSE_ENTITY,
)
FORECAST_ENTITY_KEYS: Final = (
    CONF_FORECAST_TEMPERATURE_ENTITY,
    CONF_FORECAST_DEW_POINT_ENTITY,
    CONF_FORECAST_WIND_ENTITY,
    CONF_FORECAST_DNI_ENTITY,
    CONF_FORECAST_GHI_ENTITY,
    CONF_FORECAST_DIFFUSE_ENTITY,
)

OPTION_DEFAULTS: Final = {
    CONF_METABOLIC_RATE: DEFAULT_METABOLIC_RATE,
    CONF_CLOTHING: DEFAULT_CLOTHING,
    CONF_WALKING_SPEED: DEFAULT_WALKING_SPEED,
    CONF_POSTURE: DEFAULT_POSTURE,
    CONF_SKY_VIEW_FACTOR: DEFAULT_SKY_VIEW_FACTOR,
    CONF_BODY_EXPOSURE: DEFAULT_BODY_EXPOSURE,
    CONF_SOLAR_TRANSMITTANCE: DEFAULT_SOLAR_TRANSMITTANCE,
    CONF_SHARP: DEFAULT_SHARP,
}
