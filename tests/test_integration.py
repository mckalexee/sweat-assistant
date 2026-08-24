"""Home Assistant state-machine tests for Sweat."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.sweat.const import (
    CONF_DEW_POINT_ENTITY,
    CONF_DNI_ENTITY,
    CONF_FORECAST_DEW_POINT_ENTITY,
    CONF_FORECAST_DIFFUSE_ENTITY,
    CONF_FORECAST_DNI_ENTITY,
    CONF_FORECAST_GHI_ENTITY,
    CONF_FORECAST_TEMPERATURE_ENTITY,
    CONF_FORECAST_WIND_ENTITY,
    CONF_SOLAR_ALTITUDE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    CONF_WIND_SPEED_ENTITY,
    DOMAIN,
    OPTION_DEFAULTS,
)

FORECAST_IDS = {
    CONF_FORECAST_TEMPERATURE_ENTITY: "input_text.sweat_temperature",
    CONF_FORECAST_DEW_POINT_ENTITY: "input_text.sweat_dew_point",
    CONF_FORECAST_WIND_ENTITY: "input_text.sweat_wind",
    CONF_FORECAST_DNI_ENTITY: "input_text.sweat_dni",
    CONF_FORECAST_GHI_ENTITY: "input_text.sweat_ghi",
    CONF_FORECAST_DIFFUSE_ENTITY: "input_text.sweat_diffuse",
}


def _set_sources(hass, temperature: float = 82.0) -> None:
    hass.states.async_set(
        "sensor.weather_temperature",
        str(temperature),
        {"unit_of_measurement": "°F", "device_class": "temperature"},
    )
    hass.states.async_set(
        "sensor.weather_dew_point",
        "65",
        {"unit_of_measurement": "°F", "device_class": "temperature"},
    )
    hass.states.async_set(
        "sensor.weather_wind",
        "0",
        {"unit_of_measurement": "mph"},
    )


async def _setup_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sweat",
        data={
            CONF_TEMPERATURE_ENTITY: "sensor.weather_temperature",
            CONF_DEW_POINT_ENTITY: "sensor.weather_dew_point",
            CONF_WIND_SPEED_ENTITY: "sensor.weather_wind",
        },
        options=OPTION_DEFAULTS,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _series(epoch: int, values: tuple[int, ...]) -> str:
    return f"{epoch},{','.join(str(value) for value in values)}"


async def _setup_forecast_entry(
    hass, epoch: int, *, inconsistent_solar: bool = False
) -> MockConfigEntry:
    _set_sources(hass)
    values = {
        CONF_FORECAST_TEMPERATURE_ENTITY: tuple(range(20, 68)),
        CONF_FORECAST_DEW_POINT_ENTITY: (10,) * 48,
        CONF_FORECAST_WIND_ENTITY: (1,) * 48,
        CONF_FORECAST_DNI_ENTITY: (0,) * 48,
        CONF_FORECAST_GHI_ENTITY: ((100,) if inconsistent_solar else (0,)) * 48,
        CONF_FORECAST_DIFFUSE_ENTITY: (0,) * 48,
    }
    for key, entity_id in FORECAST_IDS.items():
        hass.states.async_set(entity_id, _series(epoch, values[key]))
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sweat",
        data={
            CONF_TEMPERATURE_ENTITY: "sensor.weather_temperature",
            CONF_DEW_POINT_ENTITY: "sensor.weather_dew_point",
            CONF_WIND_SPEED_ENTITY: "sensor.weather_wind",
            **FORECAST_IDS,
        },
        options=OPTION_DEFAULTS,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_no_solar_path_and_units(hass) -> None:
    """No irradiance still produces shade wettedness and UTCI only."""
    _set_sources(hass)
    await _setup_entry(hass)
    shade = hass.states.get("sensor.sweat_shade")
    assert shade is not None
    assert 0.0 <= float(shade.state) <= 1.0
    assert shade.attributes["solar_data"] is False
    assert hass.states.get("sensor.sweat_utci_shade") is not None
    assert hass.states.get("sensor.sweat_sun") is None


async def test_recovers_after_more_than_three_source_updates(hass) -> None:
    """Regression for repeated push-coordinator source changes."""
    _set_sources(hass)
    await _setup_entry(hass)
    initial = hass.states.get("sensor.sweat_shade").state
    for temperature in (84, 86, 88, 90, 92):
        _set_sources(hass, temperature)
        await asyncio.sleep(0.12)
        await hass.async_block_till_done()
    final = hass.states.get("sensor.sweat_shade").state
    assert final != initial
    assert final not in {"unknown", "unavailable"}


async def test_missing_source_is_unknown_then_recovers(hass) -> None:
    """Startup ordering does not fail config-entry setup."""
    entry = await _setup_entry(hass)
    assert hass.states.get("sensor.sweat_shade").state == "unknown"
    _set_sources(hass)
    await asyncio.sleep(0.12)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sweat_shade").state not in {
        "unknown",
        "unavailable",
    }
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_explicitly_unavailable_source_marks_entity_unavailable(hass) -> None:
    _set_sources(hass)
    await _setup_entry(hass)
    hass.states.async_set("sensor.weather_temperature", "unavailable")
    await asyncio.sleep(0.12)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sweat_shade").state == "unavailable"


async def test_solar_path_creates_sun_entities(hass) -> None:
    """DNI-only uses reference SolarCal fallbacks and keeps shade independent."""
    _set_sources(hass)
    hass.states.async_set(
        "sensor.weather_dni", "800", {"unit_of_measurement": "W/m²"}
    )
    hass.states.async_set("sun.home", "above_horizon", {"elevation": 60.0})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sweat",
        data={
            CONF_TEMPERATURE_ENTITY: "sensor.weather_temperature",
            CONF_DEW_POINT_ENTITY: "sensor.weather_dew_point",
            CONF_WIND_SPEED_ENTITY: "sensor.weather_wind",
            CONF_DNI_ENTITY: "sensor.weather_dni",
            CONF_SOLAR_ALTITUDE_ENTITY: "sun.home",
        },
        options=OPTION_DEFAULTS,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sun = hass.states.get("sensor.sweat_sun")
    assert sun is not None
    assert float(sun.attributes["delta_mrt"]) == pytest.approx(31.0381, abs=1e-4)
    assert hass.states.get("sensor.sweat_utci_sun") is not None


async def test_broken_solar_keeps_shade_available(hass) -> None:
    _set_sources(hass)
    hass.states.async_set("sun.home", "above_horizon", {"elevation": 60.0})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sweat",
        data={
            CONF_TEMPERATURE_ENTITY: "sensor.weather_temperature",
            CONF_DEW_POINT_ENTITY: "sensor.weather_dew_point",
            CONF_WIND_SPEED_ENTITY: "sensor.weather_wind",
            CONF_DNI_ENTITY: "sensor.missing_dni",
            CONF_SOLAR_ALTITUDE_ENTITY: "sun.home",
        },
        options=OPTION_DEFAULTS,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sweat_shade").state not in {
        "unknown",
        "unavailable",
    }
    assert hass.states.get("sensor.sweat_shade").attributes["solar_data"] is False
    assert hass.states.get("sensor.sweat_sun").state == "unknown"


async def test_invalid_solar_forecast_keeps_shade_forecast(hass, freezer) -> None:
    now = datetime(2026, 8, 24, 13, tzinfo=UTC)
    freezer.move_to(now)
    await _setup_forecast_entry(
        hass, int(now.timestamp()), inconsistent_solar=True
    )
    assert hass.states.get("sensor.sweat_forecast_shade").state not in {
        "unknown",
        "unavailable",
    }
    assert hass.states.get("sensor.sweat_forecast_sun").state == "unknown"


async def test_forecast_advances_hourly_and_expires(hass, freezer) -> None:
    now = datetime(2026, 8, 24, 13, tzinfo=UTC)
    freezer.move_to(now)
    await _setup_forecast_entry(hass, int(now.timestamp()))
    shade = hass.states.get("sensor.sweat_forecast_shade")
    assert shade.attributes["current_index"] == 0
    initial = shade.state

    next_hour = now + timedelta(hours=1)
    freezer.move_to(next_hour)
    async_fire_time_changed(hass, next_hour)
    await hass.async_block_till_done()
    shade = hass.states.get("sensor.sweat_forecast_shade")
    assert shade.attributes["current_index"] == 1
    assert shade.state != initial

    expired = now + timedelta(hours=49)
    freezer.move_to(expired)
    async_fire_time_changed(hass, expired)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sweat_forecast_shade").state == "unknown"
