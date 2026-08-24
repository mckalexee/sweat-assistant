"""Source tracking and calculations for Sweat."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_utc_time_change,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BODY_EXPOSURE,
    CONF_CLOTHING,
    CONF_DEW_POINT_ENTITY,
    CONF_DIFFUSE_ENTITY,
    CONF_DNI_ENTITY,
    CONF_FORECAST_DEW_POINT_ENTITY,
    CONF_FORECAST_DIFFUSE_ENTITY,
    CONF_FORECAST_DNI_ENTITY,
    CONF_FORECAST_GHI_ENTITY,
    CONF_FORECAST_TEMPERATURE_ENTITY,
    CONF_FORECAST_WIND_ENTITY,
    CONF_GHI_ENTITY,
    CONF_HUMIDITY_ENTITY,
    CONF_METABOLIC_RATE,
    CONF_POSTURE,
    CONF_SHARP,
    CONF_SKY_VIEW_FACTOR,
    CONF_SOLAR_ALTITUDE_ENTITY,
    CONF_SOLAR_TRANSMITTANCE,
    CONF_TEMPERATURE_ENTITY,
    CONF_WALKING_SPEED,
    CONF_WIND_SPEED_ENTITY,
    FORECAST_ENTITY_KEYS,
    FORECAST_LENGTH,
    OPTION_DEFAULTS,
    SOLAR_ENTITY_KEYS,
    UTCI_MAX_WIND_SPEED,
    UTCI_MIN_WIND_SPEED,
)
from .models.gagge import (
    relative_humidity_from_dew_point as gagge_rh_from_dew_point,
)
from .models.gagge import two_nodes_gagge
from .models.solarcal import solar_gain
from .models.utci import relative_humidity_from_dew_point as utci_rh_from_dew_point
from .models.utci import utci

_LOGGER = logging.getLogger(__name__)
_IRRADIANCE_TOLERANCE = 2.0


class InputError(ValueError):
    """An entity state cannot safely be used in a calculation."""


class SourceUnavailable(InputError):
    """A configured source explicitly reports unavailable."""


@dataclass(frozen=True, slots=True)
class SourceValue:
    """Primitive snapshot of a Home Assistant state."""

    value: str
    unit: str | None
    attributes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelOptions:
    """User-controlled model assumptions."""

    metabolic_rate: float
    clothing: float
    walking_speed: float
    posture: str
    sky_view_factor: float
    body_exposure: float
    solar_transmittance: float
    sharp: float


@dataclass(frozen=True, slots=True)
class EnvironmentResult:
    """Calculated values for one radiant environment."""

    wettedness: float
    utci_c: float | None
    attributes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ForecastResult:
    """A coherent 48-hour forecast generation."""

    epoch: int
    current_index: int
    wettedness: tuple[float, ...]
    utci_c: tuple[float | None, ...]
    compact_series: str
    local_times: tuple[str, ...]

    @property
    def current_wettedness(self) -> float:
        """Return the forecast value for the current UTC hour index."""
        return self.wettedness[self.current_index]


@dataclass(frozen=True, slots=True)
class SweatData:
    """Coordinator data with independent validity per output family."""

    shade: EnvironmentResult | None
    sun: EnvironmentResult | None
    solar_configured: bool
    forecast_shade: ForecastResult | None
    forecast_sun: ForecastResult | None
    forecast_configured: bool
    shade_available: bool
    sun_available: bool
    forecast_shade_available: bool
    forecast_sun_available: bool


def _finite_number(raw: str, label: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as err:
        raise InputError(f"{label} is not numeric") from err
    if not math.isfinite(value):
        raise InputError(f"{label} is not finite")
    return value


def temperature_to_celsius(value: float, unit: str | None) -> float:
    """Convert a supported temperature unit to Celsius."""
    normalized = unit.strip().casefold() if unit else ""
    if normalized in {"°c", "c", "degc", "celsius"}:
        return value
    if normalized in {"°f", "f", "degf", "fahrenheit"}:
        return (value - 32.0) * 5.0 / 9.0
    if normalized in {"k", "kelvin"}:
        return value - 273.15
    raise InputError(f"unsupported temperature unit: {unit or 'missing'}")


def wind_to_meters_per_second(value: float, unit: str | None) -> float:
    """Convert a supported wind-speed unit to meters per second."""
    normalized = unit.strip().casefold() if unit else ""
    if normalized in {"m/s", "mps"}:
        converted = value
    elif normalized in {"mph", "mi/h"}:
        converted = value * 0.44704
    elif normalized in {"km/h", "kph", "kmh"}:
        converted = value / 3.6
    elif normalized in {"kn", "kt", "kts", "knot", "knots"}:
        converted = value * 0.5144444444444445
    else:
        raise InputError(f"unsupported wind-speed unit: {unit or 'missing'}")
    if converted < 0:
        raise InputError("wind speed cannot be negative")
    return converted


def _irradiance(value: SourceValue, label: str) -> float:
    number = _finite_number(value.value, label)
    if number < 0:
        raise InputError(f"{label} cannot be negative")
    if value.unit and value.unit not in {"W/m²", "W/m2"}:
        raise InputError(f"unsupported irradiance unit: {value.unit}")
    return number


def _humidity(value: SourceValue) -> float:
    humidity = _finite_number(value.value, "humidity")
    if value.unit and value.unit not in {"%", "percent", "percentage"}:
        raise InputError(f"unsupported humidity unit: {value.unit}")
    if not 0.0 <= humidity <= 100.0:
        raise InputError("humidity must be between 0 and 100 percent")
    return humidity


def _altitude(value: SourceValue) -> float:
    raw = value.attributes.get("elevation", value.value)
    altitude = _finite_number(str(raw), "solar altitude")
    if altitude > 90.0:
        raise InputError("solar altitude cannot exceed 90 degrees")
    return altitude


def _derive_dni(ghi: float, diffuse: float, altitude: float) -> float:
    direct_horizontal = ghi - diffuse
    if direct_horizontal < -_IRRADIANCE_TOLERANCE:
        raise InputError("GHI cannot be lower than diffuse irradiance")
    direct_horizontal = max(direct_horizontal, 0.0)
    sine_altitude = math.sin(math.radians(altitude))
    if sine_altitude <= 0.01:
        if direct_horizontal <= _IRRADIANCE_TOLERANCE:
            return 0.0
        raise InputError("cannot derive DNI while the sun is at the horizon")
    return direct_horizontal / sine_altitude


def _model_humidity(
    temperature_c: float,
    humidity: float | None,
    dew_point_c: float | None,
) -> tuple[float, float]:
    if humidity is not None:
        return humidity, humidity
    assert dew_point_c is not None
    if dew_point_c > temperature_c + 0.2:
        raise InputError("dew point cannot exceed air temperature")
    dew_point_c = min(dew_point_c, temperature_c)
    gagge_rh = gagge_rh_from_dew_point(temperature_c, dew_point_c)
    utci_rh = utci_rh_from_dew_point(temperature_c, dew_point_c)
    return min(gagge_rh, 100.0), min(utci_rh, 100.0)


def _calculate_environment(
    *,
    temperature_c: float,
    humidity: float | None,
    dew_point_c: float | None,
    ambient_wind: float,
    delta_mrt: float,
    options: ModelOptions,
    solar_data: bool,
) -> EnvironmentResult:
    gagge_rh, utci_rh = _model_humidity(temperature_c, humidity, dew_point_c)
    gagge_air_speed = ambient_wind + options.walking_speed
    gagge = two_nodes_gagge(
        temperature_c,
        temperature_c + delta_mrt,
        gagge_air_speed,
        gagge_rh,
        options.metabolic_rate,
        options.clothing,
        position=options.posture,
    )
    utci_wind = max(ambient_wind, UTCI_MIN_WIND_SPEED)
    utci_value: float | None = None
    if utci_wind <= UTCI_MAX_WIND_SPEED:
        candidate = utci(
            temperature_c,
            temperature_c + delta_mrt,
            utci_wind,
            utci_rh,
        )
        if math.isfinite(candidate):
            utci_value = candidate
    if not math.isfinite(gagge.w):
        raise InputError("Gagge returned a nonfinite value")
    attributes = {
        "metabolic_rate": options.metabolic_rate,
        "clothing": options.clothing,
        "sky_view_factor": options.sky_view_factor,
        "air_speed": round(gagge_air_speed, 4),
        "observed_wind_speed": round(ambient_wind, 4),
        "utci_wind_speed": round(utci_wind, 4),
        "delta_mrt": round(delta_mrt, 4),
        "solar_data": solar_data,
        "posture": options.posture,
        "sharp": options.sharp,
        "f_bes": options.body_exposure,
        "sol_transmittance": options.solar_transmittance,
    }
    return EnvironmentResult(
        wettedness=min(max(gagge.w, 0.0), 1.0),
        utci_c=utci_value,
        attributes=attributes,
    )


def _calculate_solar_delta(
    *,
    altitude: float,
    dni: float | None,
    ghi: float | None,
    diffuse: float | None,
    options: ModelOptions,
) -> float:
    if (
        ghi is not None
        and diffuse is not None
        and diffuse - ghi > _IRRADIANCE_TOLERANCE
    ):
        raise InputError("diffuse irradiance cannot exceed GHI")
    if altitude < 0:
        if all(value is None or value <= 1.0 for value in (dni, ghi, diffuse)):
            return 0.0
        raise InputError("irradiance is nonzero while solar altitude is negative")
    if dni is None:
        if ghi is None or diffuse is None:
            raise InputError("DNI or both GHI and diffuse irradiance are required")
        dni = _derive_dni(ghi, diffuse, altitude)
    result = solar_gain(
        altitude,
        options.sharp,
        dni,
        options.solar_transmittance,
        options.sky_view_factor,
        options.body_exposure,
        posture=options.posture,
        diffuse_radiation=diffuse,
        global_horizontal_radiation=ghi,
    )
    if not math.isfinite(result.delta_mrt):
        raise InputError("SolarCal returned a nonfinite value")
    return result.delta_mrt


@dataclass(frozen=True, slots=True)
class ParsedSeries:
    """One canonical forecast input series."""

    epoch: int
    values: tuple[float, ...]


def parse_forecast_series(raw: str, label: str) -> ParsedSeries:
    """Parse `epoch,v1,...,v48` and reject incomplete/nonfinite input."""
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != FORECAST_LENGTH + 1:
        raise InputError(f"{label} must contain one epoch and 48 values")
    try:
        epoch = int(parts[0])
    except ValueError as err:
        raise InputError(f"{label} has an invalid epoch") from err
    if epoch % 3600:
        raise InputError(f"{label} epoch must be aligned to a UTC hour")
    values = tuple(_finite_number(part, label) for part in parts[1:])
    if any(not value.is_integer() for value in values):
        raise InputError(f"{label} values must be integers")
    return ParsedSeries(epoch=epoch, values=values)


def _forecast_altitude(dni: float, ghi: float, diffuse: float) -> float:
    if min(dni, ghi, diffuse) < 0:
        raise InputError("forecast irradiance cannot be negative")
    if diffuse - ghi > _IRRADIANCE_TOLERANCE:
        raise InputError("diffuse irradiance cannot exceed GHI")
    if dni <= 1.0:
        if abs(ghi - diffuse) > _IRRADIANCE_TOLERANCE:
            raise InputError("forecast irradiance components are inconsistent")
        return 0.0
    ratio = (ghi - diffuse) / dni
    if not -0.02 <= ratio <= 1.02:
        raise InputError("forecast irradiance components cannot yield solar altitude")
    return math.degrees(math.asin(min(max(ratio, 0.0), 1.0)))


def _compact_wettedness(epoch: int, values: tuple[float, ...]) -> str:
    scaled = (str(round(min(max(value, 0.0), 1.0) * 100.0)) for value in values)
    series = f"{epoch},{','.join(scaled)}"
    if len(series) > 255:
        raise InputError(
            "forecast output exceeds Home Assistant's 255-character budget"
        )
    return series


def _forecast_result(
    epoch: int,
    environments: list[EnvironmentResult],
    now_epoch: float,
    time_zone: Any,
) -> ForecastResult:
    index = math.floor((now_epoch - epoch) / 3600.0)
    if not 0 <= index < FORECAST_LENGTH:
        raise InputError("forecast epoch does not cover the current hour")
    wettedness = tuple(environment.wettedness for environment in environments)
    utci_values = tuple(environment.utci_c for environment in environments)
    local_times = tuple(
        datetime.fromtimestamp(epoch + hour * 3600, tz=UTC)
        .astimezone(time_zone)
        .isoformat()
        for hour in range(FORECAST_LENGTH)
    )
    return ForecastResult(
        epoch=epoch,
        current_index=index,
        wettedness=wettedness,
        utci_c=utci_values,
        compact_series=_compact_wettedness(epoch, wettedness),
        local_times=local_times,
    )


def calculate_forecast(
    series: dict[str, ParsedSeries],
    options: ModelOptions,
    now_epoch: float,
    time_zone: Any,
) -> tuple[ForecastResult, ForecastResult]:
    """Calculate coherent shade and sun forecasts from canonical SI series."""
    shade = calculate_forecast_shade(series, options, now_epoch, time_zone)
    sun = calculate_forecast_sun(series, options, now_epoch, time_zone)
    return shade, sun


def _forecast_epoch(series: dict[str, ParsedSeries]) -> int:
    epochs = {item.epoch for item in series.values()}
    if len(epochs) != 1:
        raise InputError("forecast entities do not contain the same generation epoch")
    return epochs.pop()


def calculate_forecast_shade(
    series: dict[str, ParsedSeries],
    options: ModelOptions,
    now_epoch: float,
    time_zone: Any,
) -> ForecastResult:
    """Calculate shade independently of all irradiance inputs."""
    epoch = _forecast_epoch(series)
    shade: list[EnvironmentResult] = []
    for index in range(FORECAST_LENGTH):
        temperature = series[CONF_FORECAST_TEMPERATURE_ENTITY].values[index]
        dew_point = series[CONF_FORECAST_DEW_POINT_ENTITY].values[index]
        wind = series[CONF_FORECAST_WIND_ENTITY].values[index]
        if wind < 0:
            raise InputError("forecast wind cannot be negative")
        shade.append(
            _calculate_environment(
                temperature_c=temperature,
                humidity=None,
                dew_point_c=dew_point,
                ambient_wind=wind,
                delta_mrt=0.0,
                options=options,
                solar_data=True,
            )
        )
    return _forecast_result(epoch, shade, now_epoch, time_zone)


def calculate_forecast_sun(
    series: dict[str, ParsedSeries],
    options: ModelOptions,
    now_epoch: float,
    time_zone: Any,
) -> ForecastResult:
    """Calculate the radiation-dependent sun forecast."""
    epoch = _forecast_epoch(series)
    sun: list[EnvironmentResult] = []
    for index in range(FORECAST_LENGTH):
        temperature = series[CONF_FORECAST_TEMPERATURE_ENTITY].values[index]
        dew_point = series[CONF_FORECAST_DEW_POINT_ENTITY].values[index]
        wind = series[CONF_FORECAST_WIND_ENTITY].values[index]
        if wind < 0:
            raise InputError("forecast wind cannot be negative")
        dni = series[CONF_FORECAST_DNI_ENTITY].values[index]
        ghi = series[CONF_FORECAST_GHI_ENTITY].values[index]
        diffuse = series[CONF_FORECAST_DIFFUSE_ENTITY].values[index]
        altitude = _forecast_altitude(dni, ghi, diffuse)
        delta_mrt = _calculate_solar_delta(
            altitude=altitude,
            dni=dni,
            ghi=ghi,
            diffuse=diffuse,
            options=options,
        )
        sun.append(
            _calculate_environment(
                temperature_c=temperature,
                humidity=None,
                dew_point_c=dew_point,
                ambient_wind=wind,
                delta_mrt=delta_mrt,
                options=options,
                solar_data=True,
            )
        )
    return _forecast_result(epoch, sun, now_epoch, time_zone)


def _options(entry: ConfigEntry) -> ModelOptions:
    values = {**OPTION_DEFAULTS, **entry.options}
    return ModelOptions(
        metabolic_rate=float(values[CONF_METABOLIC_RATE]),
        clothing=float(values[CONF_CLOTHING]),
        walking_speed=float(values[CONF_WALKING_SPEED]),
        posture=str(values[CONF_POSTURE]),
        sky_view_factor=float(values[CONF_SKY_VIEW_FACTOR]),
        body_exposure=float(values[CONF_BODY_EXPOSURE]),
        solar_transmittance=float(values[CONF_SOLAR_TRANSMITTANCE]),
        sharp=float(values[CONF_SHARP]),
    )


class SweatCoordinator(DataUpdateCoordinator[SweatData]):
    """Recalculate when any selected Home Assistant entity changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize a push-style coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="Sweat",
            update_interval=None,
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=0.1,
                immediate=False,
            ),
        )
        self.entry = entry

    @property
    def solar_configured(self) -> bool:
        """Return whether any current solar source was selected."""
        return any(self.entry.data.get(key) for key in SOLAR_ENTITY_KEYS)

    @property
    def forecast_configured(self) -> bool:
        """Return whether the complete forecast source set was selected."""
        return all(self.entry.data.get(key) for key in FORECAST_ENTITY_KEYS)

    async def async_setup(self) -> None:
        """Subscribe to selected sources and perform the initial calculation."""
        entity_ids = {
            value
            for key, value in self.entry.data.items()
            if key.endswith("_entity") and isinstance(value, str)
        }

        async def _source_changed(_event: Event) -> None:
            await self.async_request_refresh()

        @callback
        def _hour_changed(now: datetime) -> None:
            if self.data is None:
                return

            def reindex(forecast: ForecastResult | None) -> ForecastResult | None:
                if forecast is None:
                    return None
                index = math.floor((now.timestamp() - forecast.epoch) / 3600.0)
                if not 0 <= index < FORECAST_LENGTH:
                    return None
                return replace(forecast, current_index=index)

            self.async_set_updated_data(
                replace(
                    self.data,
                    forecast_shade=reindex(self.data.forecast_shade),
                    forecast_sun=reindex(self.data.forecast_sun),
                )
            )

        self.entry.async_on_unload(
            async_track_state_change_event(self.hass, entity_ids, _source_changed)
        )
        self.entry.async_on_unload(
            async_track_utc_time_change(
                self.hass, _hour_changed, minute=0, second=0
            )
        )
        await self.async_refresh()

    def _source(self, key: str) -> SourceValue:
        entity_id = self.entry.data.get(key)
        if not entity_id:
            raise InputError(f"{key} is not configured")
        state: State | None = self.hass.states.get(entity_id)
        if state is not None and state.state == STATE_UNAVAILABLE:
            raise SourceUnavailable(f"{entity_id} is unavailable")
        if state is None or state.state in {STATE_UNKNOWN, ""}:
            raise InputError(f"{entity_id} has no usable state")
        return SourceValue(
            value=state.state,
            unit=state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            attributes=dict(state.attributes),
        )

    def _optional_source(self, key: str) -> SourceValue | None:
        if not self.entry.data.get(key):
            return None
        return self._source(key)

    async def _async_update_data(self) -> SweatData:
        options = _options(self.entry)
        shade: EnvironmentResult | None = None
        sun: EnvironmentResult | None = None
        shade_available = True
        sun_available = True
        try:
            temperature_state = self._source(CONF_TEMPERATURE_ENTITY)
            temperature = temperature_to_celsius(
                _finite_number(temperature_state.value, "temperature"),
                temperature_state.unit,
            )
            wind_state = self._source(CONF_WIND_SPEED_ENTITY)
            wind = wind_to_meters_per_second(
                _finite_number(wind_state.value, "wind speed"), wind_state.unit
            )
            humidity: float | None = None
            dew_point: float | None = None
            if self.entry.data.get(CONF_HUMIDITY_ENTITY):
                humidity = _humidity(self._source(CONF_HUMIDITY_ENTITY))
            else:
                dew_state = self._source(CONF_DEW_POINT_ENTITY)
                dew_point = temperature_to_celsius(
                    _finite_number(dew_state.value, "dew point"), dew_state.unit
                )
            shade = _calculate_environment(
                temperature_c=temperature,
                humidity=humidity,
                dew_point_c=dew_point,
                ambient_wind=wind,
                delta_mrt=0.0,
                options=options,
                solar_data=self.solar_configured,
            )
        except SourceUnavailable as err:
            shade_available = False
            sun_available = False
            _LOGGER.debug("Current Sweat source unavailable: %s", err)
        except (InputError, OverflowError, RuntimeError, ZeroDivisionError) as err:
            _LOGGER.debug("Current Sweat calculation unknown: %s", err)

        if shade is not None and self.solar_configured:
            try:
                altitude = _altitude(self._source(CONF_SOLAR_ALTITUDE_ENTITY))
                dni_state = self._optional_source(CONF_DNI_ENTITY)
                ghi_state = self._optional_source(CONF_GHI_ENTITY)
                diffuse_state = self._optional_source(CONF_DIFFUSE_ENTITY)
                delta_mrt = _calculate_solar_delta(
                    altitude=altitude,
                    dni=_irradiance(dni_state, "DNI") if dni_state else None,
                    ghi=_irradiance(ghi_state, "GHI") if ghi_state else None,
                    diffuse=(
                        _irradiance(diffuse_state, "diffuse irradiance")
                        if diffuse_state
                        else None
                    ),
                    options=options,
                )
                sun = _calculate_environment(
                    temperature_c=temperature,
                    humidity=humidity,
                    dew_point_c=dew_point,
                    ambient_wind=wind,
                    delta_mrt=delta_mrt,
                    options=options,
                    solar_data=True,
                )
            except SourceUnavailable as err:
                sun_available = False
                _LOGGER.debug("Current Sweat solar source unavailable: %s", err)
            except (InputError, OverflowError, RuntimeError, ZeroDivisionError) as err:
                _LOGGER.debug("Current Sweat sun calculation unknown: %s", err)
        if shade is not None and self.solar_configured and sun is None:
            shade = EnvironmentResult(
                wettedness=shade.wettedness,
                utci_c=shade.utci_c,
                attributes={**shade.attributes, "solar_data": False},
            )

        forecast_shade: ForecastResult | None = None
        forecast_sun: ForecastResult | None = None
        forecast_shade_available = True
        forecast_sun_available = True
        if self.forecast_configured:
            try:
                meteorology = {
                    key: parse_forecast_series(self._source(key).value, key)
                    for key in (
                        CONF_FORECAST_TEMPERATURE_ENTITY,
                        CONF_FORECAST_DEW_POINT_ENTITY,
                        CONF_FORECAST_WIND_ENTITY,
                    )
                }
                forecast_shade = await self.hass.async_add_executor_job(
                    calculate_forecast_shade,
                    meteorology,
                    options,
                    dt_util.utcnow().timestamp(),
                    dt_util.get_time_zone(self.hass.config.time_zone) or UTC,
                )
            except SourceUnavailable as err:
                forecast_shade_available = False
                forecast_sun_available = False
                _LOGGER.debug("Sweat forecast source unavailable: %s", err)
            except (InputError, OverflowError, RuntimeError, ZeroDivisionError) as err:
                _LOGGER.debug("Sweat shade forecast unknown: %s", err)

            if forecast_shade is not None:
                try:
                    solar = {
                        key: parse_forecast_series(self._source(key).value, key)
                        for key in (
                            CONF_FORECAST_DNI_ENTITY,
                            CONF_FORECAST_GHI_ENTITY,
                            CONF_FORECAST_DIFFUSE_ENTITY,
                        )
                    }
                    forecast_sun = await self.hass.async_add_executor_job(
                        calculate_forecast_sun,
                        {**meteorology, **solar},
                        options,
                        dt_util.utcnow().timestamp(),
                        dt_util.get_time_zone(self.hass.config.time_zone) or UTC,
                    )
                except SourceUnavailable as err:
                    forecast_sun_available = False
                    _LOGGER.debug("Sweat solar forecast source unavailable: %s", err)
                except (
                    InputError,
                    OverflowError,
                    RuntimeError,
                    ZeroDivisionError,
                ) as err:
                    _LOGGER.debug("Sweat sun forecast unknown: %s", err)

        return SweatData(
            shade=shade,
            sun=sun,
            solar_configured=self.solar_configured,
            forecast_shade=forecast_shade,
            forecast_sun=forecast_sun,
            forecast_configured=self.forecast_configured,
            shade_available=shade_available,
            sun_available=sun_available,
            forecast_shade_available=forecast_shade_available,
            forecast_sun_available=forecast_sun_available,
        )
