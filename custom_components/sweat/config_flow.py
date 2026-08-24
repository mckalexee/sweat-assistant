"""Config and options flows for Sweat."""

from __future__ import annotations

import math
from typing import Any

import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ADVANCED,
    CONF_BODY_EXPOSURE,
    CONF_CLOTHING,
    CONF_DEW_POINT_ENTITY,
    CONF_DIFFUSE_ENTITY,
    CONF_DNI_ENTITY,
    CONF_FORECAST,
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
    CONF_SOLAR,
    CONF_SOLAR_ALTITUDE_ENTITY,
    CONF_SOLAR_TRANSMITTANCE,
    CONF_TEMPERATURE_ENTITY,
    CONF_WALKING_SPEED,
    CONF_WIND_SPEED_ENTITY,
    DOMAIN,
    FORECAST_ENTITY_KEYS,
    OPTION_DEFAULTS,
    POSTURES,
    SOLAR_ENTITY_KEYS,
)


def _entity_selector(
    *, domain: str | list[str] | None = None, device_class: str | None = None
) -> selector.EntitySelector:
    config: selector.EntitySelectorConfig = {}
    if domain is not None:
        config["domain"] = domain
    if device_class is not None:
        config["device_class"] = device_class
    return selector.EntitySelector(config)


def _advanced_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_METABOLIC_RATE,
                default=OPTION_DEFAULTS[CONF_METABOLIC_RATE],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5,
                    max=10.0,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="met",
                )
            ),
            vol.Required(
                CONF_CLOTHING, default=OPTION_DEFAULTS[CONF_CLOTHING]
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=3.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="clo",
                )
            ),
            vol.Required(
                CONF_WALKING_SPEED,
                default=OPTION_DEFAULTS[CONF_WALKING_SPEED],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=5.0,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="m/s",
                )
            ),
            vol.Required(
                CONF_POSTURE, default=OPTION_DEFAULTS[CONF_POSTURE]
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(POSTURES),
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="posture",
                )
            ),
            vol.Required(
                CONF_SKY_VIEW_FACTOR,
                default=OPTION_DEFAULTS[CONF_SKY_VIEW_FACTOR],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=1.0,
                    step=0.05,
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_BODY_EXPOSURE,
                default=OPTION_DEFAULTS[CONF_BODY_EXPOSURE],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=1.0,
                    step=0.05,
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_SOLAR_TRANSMITTANCE,
                default=OPTION_DEFAULTS[CONF_SOLAR_TRANSMITTANCE],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=1.0,
                    step=0.05,
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_SHARP, default=OPTION_DEFAULTS[CONF_SHARP]
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=180.0,
                    step=5.0,
                    mode=selector.NumberSelectorMode.SLIDER,
                    unit_of_measurement="°",
                )
            ),
        }
    )


def _source_schema(default_sun_entity: str | None = None) -> vol.Schema:
    solar_fields: dict[Any, Any] = {
        vol.Optional(CONF_DNI_ENTITY): _entity_selector(),
        vol.Optional(CONF_GHI_ENTITY): _entity_selector(),
        vol.Optional(CONF_DIFFUSE_ENTITY): _entity_selector(),
    }
    altitude_marker = vol.Optional(CONF_SOLAR_ALTITUDE_ENTITY)
    if default_sun_entity is not None:
        altitude_marker = vol.Optional(
            CONF_SOLAR_ALTITUDE_ENTITY, default=default_sun_entity
        )
    solar_fields[altitude_marker] = _entity_selector()

    return vol.Schema(
        {
            vol.Required(CONF_TEMPERATURE_ENTITY): _entity_selector(
                device_class=SensorDeviceClass.TEMPERATURE
            ),
            vol.Optional(CONF_HUMIDITY_ENTITY): _entity_selector(),
            vol.Optional(CONF_DEW_POINT_ENTITY): _entity_selector(
                device_class=SensorDeviceClass.TEMPERATURE
            ),
            vol.Required(CONF_WIND_SPEED_ENTITY): _entity_selector(),
            vol.Required(CONF_SOLAR, default={}): data_entry_flow.section(
                vol.Schema(solar_fields), {"collapsed": True}
            ),
            vol.Required(CONF_FORECAST, default={}): data_entry_flow.section(
                vol.Schema(
                    {
                        vol.Optional(
                            CONF_FORECAST_TEMPERATURE_ENTITY
                        ): _entity_selector(domain="input_text"),
                        vol.Optional(CONF_FORECAST_DEW_POINT_ENTITY): _entity_selector(
                            domain="input_text"
                        ),
                        vol.Optional(CONF_FORECAST_WIND_ENTITY): _entity_selector(
                            domain="input_text"
                        ),
                        vol.Optional(CONF_FORECAST_DNI_ENTITY): _entity_selector(
                            domain="input_text"
                        ),
                        vol.Optional(CONF_FORECAST_GHI_ENTITY): _entity_selector(
                            domain="input_text"
                        ),
                        vol.Optional(CONF_FORECAST_DIFFUSE_ENTITY): _entity_selector(
                            domain="input_text"
                        ),
                    }
                ),
                {"collapsed": True},
            ),
        }
    )


def _initial_schema(default_sun_entity: str | None = None) -> vol.Schema:
    source = _source_schema(default_sun_entity).schema
    return vol.Schema(
        {
            **source,
            vol.Required(CONF_ADVANCED, default={}): data_entry_flow.section(
                _advanced_schema(), {"collapsed": True}
            ),
        }
    )


def _flatten_sources(user_input: dict[str, Any]) -> dict[str, Any]:
    flattened = {
        key: value
        for key, value in user_input.items()
        if key not in {CONF_SOLAR, CONF_FORECAST, CONF_ADVANCED}
    }
    flattened.update(user_input.get(CONF_SOLAR, {}))
    flattened.update(user_input.get(CONF_FORECAST, {}))
    return flattened


def _nested_sources(data: dict[str, Any]) -> dict[str, Any]:
    nested = {
        key: value
        for key, value in data.items()
        if key
        not in {
            *SOLAR_ENTITY_KEYS,
            CONF_SOLAR_ALTITUDE_ENTITY,
            *FORECAST_ENTITY_KEYS,
        }
    }
    nested[CONF_SOLAR] = {
        key: data[key]
        for key in (*SOLAR_ENTITY_KEYS, CONF_SOLAR_ALTITUDE_ENTITY)
        if key in data
    }
    nested[CONF_FORECAST] = {
        key: data[key] for key in FORECAST_ENTITY_KEYS if key in data
    }
    return nested


def _validate_sources(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    humidity_count = sum(
        bool(data.get(key)) for key in (CONF_HUMIDITY_ENTITY, CONF_DEW_POINT_ENTITY)
    )
    if humidity_count != 1:
        errors["base"] = "choose_one_humidity_source"

    solar = {key for key in SOLAR_ENTITY_KEYS if data.get(key)}
    solar_supported = (
        not solar
        or CONF_DNI_ENTITY in solar
        or solar == {CONF_GHI_ENTITY, CONF_DIFFUSE_ENTITY}
    )
    if not solar_supported:
        errors["base"] = "unsupported_solar_combination"
    elif solar and not data.get(CONF_SOLAR_ALTITUDE_ENTITY):
        errors["base"] = "solar_altitude_required"

    forecast_count = sum(bool(data.get(key)) for key in FORECAST_ENTITY_KEYS)
    if forecast_count not in {0, len(FORECAST_ENTITY_KEYS)}:
        errors["base"] = "forecast_all_or_none"
    return errors


def _validate_live_sources(hass: Any, data: dict[str, Any]) -> dict[str, str]:
    """Reject present, readable sources that cannot satisfy the runtime contract."""
    from homeassistant.const import (
        ATTR_UNIT_OF_MEASUREMENT,
        STATE_UNAVAILABLE,
        STATE_UNKNOWN,
    )

    def state_for(key: str) -> Any | None:
        entity_id = data.get(key)
        state = hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE, ""}:
            return None
        return state

    def finite(state: Any, *, attribute: str | None = None) -> float:
        raw = state.attributes.get(attribute) if attribute else state.state
        number = float(raw)
        if not math.isfinite(number):
            raise ValueError
        return number

    temperature_units = {
        "°c",
        "c",
        "degc",
        "celsius",
        "°f",
        "f",
        "degf",
        "fahrenheit",
        "k",
        "kelvin",
    }
    wind_units = {
        "m/s",
        "mps",
        "mph",
        "mi/h",
        "km/h",
        "kph",
        "kmh",
        "kn",
        "kt",
        "kts",
        "knot",
        "knots",
    }

    for key in (CONF_TEMPERATURE_ENTITY, CONF_DEW_POINT_ENTITY):
        state = state_for(key)
        if state is None:
            continue
        unit = str(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT, "")).casefold()
        try:
            finite(state)
            if unit not in temperature_units:
                raise ValueError
        except (TypeError, ValueError):
            return {"base": "invalid_temperature_source"}

    humidity_state = state_for(CONF_HUMIDITY_ENTITY)
    if humidity_state is not None:
        unit = str(
            humidity_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT, "")
        ).casefold()
        try:
            value = finite(humidity_state)
            if unit not in {"%", "percent", "percentage"} or not 0 <= value <= 100:
                raise ValueError
        except (TypeError, ValueError):
            return {"base": "invalid_humidity_source"}

    wind_state = state_for(CONF_WIND_SPEED_ENTITY)
    if wind_state is not None:
        unit = str(wind_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT, "")).casefold()
        try:
            if finite(wind_state) < 0 or unit not in wind_units:
                raise ValueError
        except (TypeError, ValueError):
            return {"base": "invalid_wind_source"}

    for key in SOLAR_ENTITY_KEYS:
        state = state_for(key)
        if state is None:
            continue
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        try:
            if finite(state) < 0 or (unit and unit not in {"W/m²", "W/m2"}):
                raise ValueError
        except (TypeError, ValueError):
            return {"base": "invalid_irradiance_source"}

    altitude_state = state_for(CONF_SOLAR_ALTITUDE_ENTITY)
    if altitude_state is not None:
        try:
            value = finite(
                altitude_state,
                attribute="elevation"
                if "elevation" in altitude_state.attributes
                else None,
            )
            if value > 90:
                raise ValueError
        except (TypeError, ValueError):
            return {"base": "invalid_altitude_source"}

    if all(data.get(key) for key in FORECAST_ENTITY_KEYS):
        from .coordinator import (
            InputError,
            _forecast_altitude,
            parse_forecast_series,
        )

        parsed = {}
        for key in FORECAST_ENTITY_KEYS:
            state = state_for(key)
            if state is None:
                continue
            try:
                parsed[key] = parse_forecast_series(state.state, key)
            except InputError:
                return {"base": "invalid_forecast_source"}
        if len({series.epoch for series in parsed.values()}) > 1:
            return {"base": "invalid_forecast_source"}
        wind = parsed.get(CONF_FORECAST_WIND_ENTITY)
        if wind is not None and any(value < 0 for value in wind.values):
            return {"base": "invalid_forecast_source"}
        temperature = parsed.get(CONF_FORECAST_TEMPERATURE_ENTITY)
        dew_point = parsed.get(CONF_FORECAST_DEW_POINT_ENTITY)
        if temperature is not None and dew_point is not None and any(
            dew > air + 0.2
            for air, dew in zip(temperature.values, dew_point.values, strict=True)
        ):
            return {"base": "invalid_forecast_source"}
        solar = (
            parsed.get(CONF_FORECAST_DNI_ENTITY),
            parsed.get(CONF_FORECAST_GHI_ENTITY),
            parsed.get(CONF_FORECAST_DIFFUSE_ENTITY),
        )
        if all(series is not None for series in solar):
            try:
                for values in zip(
                    *(series.values for series in solar if series is not None),
                    strict=True,
                ):
                    _forecast_altitude(*values)
            except InputError:
                return {"base": "invalid_forecast_source"}
    return {}


class SweatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Sweat config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SweatOptionsFlow:
        """Return the options flow."""
        return SweatOptionsFlow()

    def _default_sun_entity(self) -> str | None:
        sun_entities = self.hass.states.async_entity_ids("sun")
        return sun_entities[0] if len(sun_entities) == 1 else None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial configuration."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _flatten_sources(user_input)
            errors = _validate_sources(data)
            if not errors:
                errors = _validate_live_sources(self.hass, data)
            if not errors:
                options = {**OPTION_DEFAULTS, **user_input.get(CONF_ADVANCED, {})}
                return self.async_create_entry(
                    title="Sweat", data=data, options=options
                )
        schema = _initial_schema(self._default_sun_entity())
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow source entities to be changed."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _flatten_sources(user_input)
            errors = _validate_sources(data)
            if not errors:
                errors = _validate_live_sources(self.hass, data)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data=data,
                    reload_even_if_entry_is_unchanged=False,
                )
        schema = self.add_suggested_values_to_schema(
            _source_schema(), _nested_sources(dict(entry.data))
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )


class SweatOptionsFlow(config_entries.OptionsFlowWithReload):
    """Handle mutable physiological and solar assumptions."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and save options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input.get(CONF_ADVANCED, {}))
        values = {**OPTION_DEFAULTS, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(CONF_ADVANCED, default={}): data_entry_flow.section(
                    _advanced_schema(), {"collapsed": True}
                )
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, {CONF_ADVANCED: values}
            ),
        )
