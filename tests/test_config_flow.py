"""Config-flow tests for Sweat."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sweat.const import (
    CONF_ADVANCED,
    CONF_DEW_POINT_ENTITY,
    CONF_DIFFUSE_ENTITY,
    CONF_FORECAST,
    CONF_GHI_ENTITY,
    CONF_HUMIDITY_ENTITY,
    CONF_METABOLIC_RATE,
    CONF_SOLAR,
    CONF_SOLAR_ALTITUDE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    CONF_WIND_SPEED_ENTITY,
    DOMAIN,
)


async def test_user_flow_creates_entry(hass) -> None:
    """A no-solar configuration is a supported primary path."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TEMPERATURE_ENTITY: "sensor.outdoor_temperature",
            CONF_DEW_POINT_ENTITY: "sensor.outdoor_dew_point",
            CONF_WIND_SPEED_ENTITY: "sensor.outdoor_wind",
            CONF_SOLAR: {},
            CONF_FORECAST: {},
            CONF_ADVANCED: {},
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TEMPERATURE_ENTITY] == "sensor.outdoor_temperature"
    assert result["options"]["metabolic_rate"] == 2.6


async def test_user_flow_requires_exactly_one_humidity_source(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TEMPERATURE_ENTITY: "sensor.outdoor_temperature",
            CONF_HUMIDITY_ENTITY: "sensor.outdoor_humidity",
            CONF_DEW_POINT_ENTITY: "sensor.outdoor_dew_point",
            CONF_WIND_SPEED_ENTITY: "sensor.outdoor_wind",
            CONF_SOLAR: {},
            CONF_FORECAST: {},
            CONF_ADVANCED: {},
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "choose_one_humidity_source"


async def test_user_flow_rejects_incomplete_solar_and_forecast(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TEMPERATURE_ENTITY: "sensor.outdoor_temperature",
            CONF_DEW_POINT_ENTITY: "sensor.outdoor_dew_point",
            CONF_WIND_SPEED_ENTITY: "sensor.outdoor_wind",
            CONF_SOLAR: {CONF_GHI_ENTITY: "sensor.ghi"},
            CONF_FORECAST: {},
            CONF_ADVANCED: {},
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "unsupported_solar_combination"


async def test_user_flow_accepts_ghi_and_diffuse_pair(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TEMPERATURE_ENTITY: "sensor.outdoor_temperature",
            CONF_DEW_POINT_ENTITY: "sensor.outdoor_dew_point",
            CONF_WIND_SPEED_ENTITY: "sensor.outdoor_wind",
            CONF_SOLAR: {
                CONF_GHI_ENTITY: "sensor.ghi",
                CONF_DIFFUSE_ENTITY: "sensor.diffuse",
                CONF_SOLAR_ALTITUDE_ENTITY: "sun.home",
            },
            CONF_FORECAST: {},
            CONF_ADVANCED: {},
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_GHI_ENTITY] == "sensor.ghi"


async def test_options_flow_saves_advanced_values(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    with patch.object(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    ) as reload_entry:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ADVANCED: {CONF_METABOLIC_RATE: 3.0}},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_METABOLIC_RATE] == 3.0
    reload_entry.assert_awaited_once_with(entry.entry_id)


async def test_user_flow_aborts_when_entry_already_exists(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_user_flow_rejects_live_source_with_wrong_unit(hass) -> None:
    hass.states.async_set(
        "sensor.outdoor_wind", "500", {"unit_of_measurement": "kWh"}
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TEMPERATURE_ENTITY: "sensor.outdoor_temperature",
            CONF_DEW_POINT_ENTITY: "sensor.outdoor_dew_point",
            CONF_WIND_SPEED_ENTITY: "sensor.outdoor_wind",
            CONF_SOLAR: {},
            CONF_FORECAST: {},
            CONF_ADVANCED: {},
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_wind_source"


async def test_reconfigure_updates_sources_and_reloads(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TEMPERATURE_ENTITY: "sensor.old_temperature",
            CONF_DEW_POINT_ENTITY: "sensor.old_dew_point",
            CONF_WIND_SPEED_ENTITY: "sensor.old_wind",
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM
    with patch.object(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    ) as reload_entry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_TEMPERATURE_ENTITY: "sensor.new_temperature",
                CONF_DEW_POINT_ENTITY: "sensor.new_dew_point",
                CONF_WIND_SPEED_ENTITY: "sensor.new_wind",
                CONF_SOLAR: {},
                CONF_FORECAST: {},
            },
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_TEMPERATURE_ENTITY] == "sensor.new_temperature"
    reload_entry.assert_awaited_once_with(entry.entry_id)
