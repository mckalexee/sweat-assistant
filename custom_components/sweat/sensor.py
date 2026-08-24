"""Sensor entities for Sweat."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import EnvironmentResult, ForecastResult, SweatCoordinator

_ATTRIBUTION = "Thermal models adapted from pythermalcomfort 4.4.2"


@dataclass(frozen=True, kw_only=True)
class SweatSensorDescription(SensorEntityDescription):
    """Describe a current-condition Sweat sensor."""

    environment: str
    metric: str


CURRENT_SENSORS = (
    SweatSensorDescription(
        key="shade",
        translation_key="shade",
        environment="shade",
        metric="wettedness",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SweatSensorDescription(
        key="utci_shade",
        translation_key="utci_shade",
        environment="shade",
        metric="utci",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SweatSensorDescription(
        key="sun",
        translation_key="sun",
        environment="sun",
        metric="wettedness",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SweatSensorDescription(
        key="utci_sun",
        translation_key="utci_sun",
        environment="sun",
        metric="utci",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
)


@dataclass(frozen=True, kw_only=True)
class ForecastSensorDescription(SensorEntityDescription):
    """Describe a compact forecast sensor."""

    environment: str


FORECAST_SENSORS = (
    ForecastSensorDescription(
        key="forecast_shade",
        translation_key="forecast_shade",
        environment="shade",
        suggested_display_precision=2,
    ),
    ForecastSensorDescription(
        key="forecast_sun",
        translation_key="forecast_sun",
        environment="sun",
        suggested_display_precision=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Sweat sensors from a config entry."""
    coordinator: SweatCoordinator = entry.runtime_data
    descriptions = [
        description
        for description in CURRENT_SENSORS
        if description.environment == "shade" or coordinator.solar_configured
    ]
    entities: list[SensorEntity] = [
        SweatCurrentSensor(coordinator, entry, description)
        for description in descriptions
    ]
    if coordinator.forecast_configured:
        entities.extend(
            SweatForecastSensor(coordinator, entry, description)
            for description in FORECAST_SENSORS
        )
    async_add_entities(entities)


class SweatCurrentSensor(CoordinatorEntity[SweatCoordinator], SensorEntity):
    """A current shade or sun calculation."""

    entity_description: SweatSensorDescription
    _attr_attribution = _ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SweatCoordinator,
        entry: ConfigEntry,
        description: SweatSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def _environment(self) -> EnvironmentResult | None:
        if self.entity_description.environment == "sun":
            return self.coordinator.data.sun
        return self.coordinator.data.shade

    @property
    def available(self) -> bool:
        """Mirror explicit source unavailability for this output family."""
        source_available = (
            self.coordinator.data.sun_available
            if self.entity_description.environment == "sun"
            else self.coordinator.data.shade_available
        )
        return super().available and source_available

    @property
    def native_value(self) -> float | None:
        """Return raw wettedness or UTCI."""
        environment = self._environment
        if environment is None:
            return None
        if self.entity_description.metric == "utci":
            return environment.utci_c
        return environment.wettedness

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the assumptions used for this state."""
        environment = self._environment
        return environment.attributes if environment else {}


class SweatForecastSensor(CoordinatorEntity[SweatCoordinator], SensorEntity):
    """A 48-hour wettedness forecast with compact and structured attributes."""

    entity_description: ForecastSensorDescription
    _attr_attribution = _ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SweatCoordinator,
        entry: ConfigEntry,
        description: ForecastSensorDescription,
    ) -> None:
        """Initialize the forecast sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def _forecast(self) -> ForecastResult | None:
        if self.entity_description.environment == "sun":
            return self.coordinator.data.forecast_sun
        return self.coordinator.data.forecast_shade

    @property
    def available(self) -> bool:
        """Mirror explicit source unavailability for this forecast family."""
        source_available = (
            self.coordinator.data.forecast_sun_available
            if self.entity_description.environment == "sun"
            else self.coordinator.data.forecast_shade_available
        )
        return super().available and source_available

    @property
    def native_value(self) -> float | None:
        """Return the forecast for the current UTC hour index."""
        forecast = self._forecast
        return forecast.current_wettedness if forecast else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return compact CSV and timestamped forecast values."""
        forecast = self._forecast
        if forecast is None:
            return {}
        return {
            "epoch": forecast.epoch,
            "current_index": forecast.current_index,
            "series": forecast.compact_series,
            "forecast": [
                {
                    "datetime": local_time,
                    "w": round(wettedness, 4),
                    "utci_c": round(utci_c, 2) if utci_c is not None else None,
                }
                for local_time, wettedness, utci_c in zip(
                    forecast.local_times,
                    forecast.wettedness,
                    forecast.utci_c,
                    strict=True,
                )
            ],
            "solar_data": True,
        }
