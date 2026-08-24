"""Dependency-free model adapter tests."""

import math
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.sweat.const import (
    CONF_FORECAST_DEW_POINT_ENTITY,
    CONF_FORECAST_DIFFUSE_ENTITY,
    CONF_FORECAST_DNI_ENTITY,
    CONF_FORECAST_GHI_ENTITY,
    CONF_FORECAST_TEMPERATURE_ENTITY,
    CONF_FORECAST_WIND_ENTITY,
)
from custom_components.sweat.coordinator import (
    InputError,
    ModelOptions,
    ParsedSeries,
    _calculate_solar_delta,
    _forecast_altitude,
    calculate_forecast,
    parse_forecast_series,
    temperature_to_celsius,
    wind_to_meters_per_second,
)
from custom_components.sweat.models.gagge import two_nodes_gagge
from custom_components.sweat.models.solarcal import solar_gain
from custom_components.sweat.models.utci import utci

OPTIONS = ModelOptions(2.6, 0.36, 1.1, "standing", 0.4, 1.0, 1.0, 90.0)


def test_golden_model_values_without_reference_dependency() -> None:
    """Keep immutable oracle-generated values runnable on Python 3.14."""
    gagge = two_nodes_gagge(27.7778, 58.8158, 1.1, 55.0, 2.6, 0.36)
    assert gagge.w == pytest.approx(0.557084122275928, rel=1e-12)
    assert utci(25.0, 25.0, 1.0, 50.0) == pytest.approx(
        24.6414473879, rel=1e-10
    )
    assert solar_gain(
        60.0, 90.0, 800.0, 1.0, 0.4, 1.0, posture="standing"
    ).delta_mrt == pytest.approx(31.0380538762, rel=1e-9)


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [(32.0, "°F", 0.0), (20.0, "°C", 20.0), (293.15, "K", 20.0)],
)
def test_temperature_conversion(value: float, unit: str, expected: float) -> None:
    assert temperature_to_celsius(value, unit) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (1.0, "m/s", 1.0),
        (10.0, "mph", 4.4704),
        (36.0, "km/h", 10.0),
        (10.0, "kn", 5.144444444444445),
    ],
)
def test_wind_conversion(value: float, unit: str, expected: float) -> None:
    assert wind_to_meters_per_second(value, unit) == pytest.approx(expected)


def test_forecast_parser_requires_exactly_48_values() -> None:
    valid = "1787587200," + ",".join("1" for _ in range(48))
    parsed = parse_forecast_series(valid, "test")
    assert parsed.epoch == 1787587200
    assert len(parsed.values) == 48
    with pytest.raises(InputError):
        parse_forecast_series("1787587200,1,2", "test")
    unaligned = "1787587260," + ",".join("1" for _ in range(48))
    with pytest.raises(InputError, match="aligned"):
        parse_forecast_series(unaligned, "test")


def test_forecast_is_same_epoch_dst_safe_and_under_character_budget() -> None:
    epoch = int(datetime(2026, 11, 1, 4, tzinfo=UTC).timestamp())
    values = {
        CONF_FORECAST_TEMPERATURE_ENTITY: (28.0,) * 48,
        CONF_FORECAST_DEW_POINT_ENTITY: (18.0,) * 48,
        CONF_FORECAST_WIND_ENTITY: (1.0,) * 48,
        CONF_FORECAST_DNI_ENTITY: (0.0,) * 48,
        CONF_FORECAST_GHI_ENTITY: (0.0,) * 48,
        CONF_FORECAST_DIFFUSE_ENTITY: (0.0,) * 48,
    }
    series = {key: ParsedSeries(epoch, item) for key, item in values.items()}
    eastern = ZoneInfo("America/New_York")
    shade, sun = calculate_forecast(series, OPTIONS, epoch + 5 * 3600, eastern)
    assert shade.current_index == 5
    assert shade.wettedness == pytest.approx(sun.wettedness)
    assert len(shade.compact_series) <= 255
    assert shade.local_times[0].endswith("-04:00")
    assert shade.local_times[2].endswith("-05:00")


def test_measured_solar_components_match_upstream_fallback_identity() -> None:
    """Measured components obey the documented SolarCal component equations."""
    dni = 800.0
    altitude = 60.0
    diffuse = 0.2 * dni
    ghi = dni * math.sin(math.radians(altitude)) + diffuse
    fallback = solar_gain(altitude, 90.0, dni, 1.0, 0.4, 1.0)
    measured = solar_gain(
        altitude,
        90.0,
        dni,
        1.0,
        0.4,
        1.0,
        diffuse_radiation=diffuse,
        global_horizontal_radiation=ghi,
    )
    assert measured.delta_mrt == pytest.approx(fallback.delta_mrt, rel=1e-9)


def test_daylight_forecast_recovers_altitude_from_coherent_components() -> None:
    """A coherent daylight triple exercises forecast altitude inference."""
    epoch = 1787587200
    dni = 800.0
    diffuse = 160.0
    ghi = dni * math.sin(math.radians(60.0)) + diffuse
    values = {
        CONF_FORECAST_TEMPERATURE_ENTITY: (28.0,) * 48,
        CONF_FORECAST_DEW_POINT_ENTITY: (18.0,) * 48,
        CONF_FORECAST_WIND_ENTITY: (1.0,) * 48,
        CONF_FORECAST_DNI_ENTITY: (dni,) * 48,
        CONF_FORECAST_GHI_ENTITY: (ghi,) * 48,
        CONF_FORECAST_DIFFUSE_ENTITY: (diffuse,) * 48,
    }
    series = {key: ParsedSeries(epoch, item) for key, item in values.items()}
    shade, sun = calculate_forecast(series, OPTIONS, epoch, UTC)
    assert sun.wettedness[0] > shade.wettedness[0]
    assert sun.utci_c[0] > shade.utci_c[0]


def test_ghi_and_diffuse_only_derive_the_expected_dni() -> None:
    """The current-data GHI/DHI branch recovers the same solar result as DNI."""
    altitude = 30.0
    dni = 600.0
    diffuse = 120.0
    ghi = dni * math.sin(math.radians(altitude)) + diffuse
    derived = _calculate_solar_delta(
        altitude=altitude,
        dni=None,
        ghi=ghi,
        diffuse=diffuse,
        options=OPTIONS,
    )
    explicit = _calculate_solar_delta(
        altitude=altitude,
        dni=dni,
        ghi=ghi,
        diffuse=diffuse,
        options=OPTIONS,
    )
    assert derived == pytest.approx(explicit, rel=1e-12)


@pytest.mark.parametrize(
    ("dni", "ghi", "diffuse"),
    [
        (800.0, 100.0, 200.0),
        (800.0, 1000.0, 0.0),
        (0.0, 10.0, 0.0),
        (0.0, 0.0, 100.0),
    ],
)
def test_forecast_rejects_inconsistent_solar_components(
    dni: float, ghi: float, diffuse: float
) -> None:
    with pytest.raises(InputError, match="irradiance"):
        _forecast_altitude(dni, ghi, diffuse)


def test_forecast_accepts_low_sun_rounding_tolerance() -> None:
    assert _forecast_altitude(800.0, 8.0, 0.0) == pytest.approx(
        math.degrees(math.asin(0.01))
    )


def test_current_solar_rejects_diffuse_greater_than_ghi() -> None:
    with pytest.raises(InputError, match="diffuse"):
        _calculate_solar_delta(
            altitude=30.0,
            dni=600.0,
            ghi=0.0,
            diffuse=100.0,
            options=OPTIONS,
        )


def test_forecast_rejects_mixed_generation() -> None:
    values = (0.0,) * 48
    series = {
        key: ParsedSeries(1000 + index, values)
        for index, key in enumerate(
            (
                CONF_FORECAST_TEMPERATURE_ENTITY,
                CONF_FORECAST_DEW_POINT_ENTITY,
                CONF_FORECAST_WIND_ENTITY,
                CONF_FORECAST_DNI_ENTITY,
                CONF_FORECAST_GHI_ENTITY,
                CONF_FORECAST_DIFFUSE_ENTITY,
            )
        )
    }
    with pytest.raises(InputError, match="same generation"):
        calculate_forecast(series, OPTIONS, 1000, UTC)


def test_model_results_are_finite_at_calm_wind() -> None:
    result = two_nodes_gagge(25.0, 25.0, 0.0, 50.0, 2.6, 0.36)
    assert math.isfinite(result.w)
