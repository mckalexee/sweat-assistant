"""Differential tests against the development-only pythermalcomfort oracle.

Run with Python 3.13 and requirements-reference-test.txt. The oracle cannot be
installed in Home Assistant's Python 3.14 runtime and is never a runtime dependency.
"""

from __future__ import annotations

import math
from itertools import product

import pytest
from pythermalcomfort.models import solar_gain as reference_solar_gain
from pythermalcomfort.models import two_nodes_gagge as reference_two_nodes_gagge
from pythermalcomfort.models import utci as reference_utci

from custom_components.sweat.models.gagge import (
    relative_humidity_from_dew_point as gagge_rh_from_dew_point,
)
from custom_components.sweat.models.gagge import two_nodes_gagge
from custom_components.sweat.models.solarcal import solar_gain
from custom_components.sweat.models.utci import (
    relative_humidity_from_dew_point as utci_rh_from_dew_point,
)
from custom_components.sweat.models.utci import utci

REL_TOL = 1e-6
# A tiny absolute floor is required when a correct output is exactly zero, where a
# relative tolerance is undefined. It is far below meaningful sensor precision.
ABS_TOL = 1e-9


def _celsius(fahrenheit: float) -> float:
    return (fahrenheit - 32.0) * 5.0 / 9.0


@pytest.mark.parametrize(
    ("temperature_f", "dew_point_f", "wind_mph", "dni", "altitude"),
    [
        case
        for case in product(
            (60.0, 70.0, 80.0, 90.0, 100.0),
            (40.0, 55.0, 70.0, 78.0),
            (0.0, 5.0, 15.0),
            (0.0, 300.0, 600.0, 900.0),
            (0.0, 30.0, 50.0, 70.0),
        )
        if case[1] < case[0]
    ],
)
def test_scalar_ports_match_reference_grid(
    temperature_f: float,
    dew_point_f: float,
    wind_mph: float,
    dni: float,
    altitude: float,
) -> None:
    """Sweep the requested weather grid with unrounded model outputs."""
    temperature_c = _celsius(temperature_f)
    dew_point_c = _celsius(dew_point_f)
    ambient_wind = wind_mph * 0.44704
    gagge_wind = ambient_wind + 1.1
    utci_wind = max(ambient_wind, 0.5)

    ours_solar = solar_gain(
        altitude,
        90.0,
        dni,
        1.0,
        0.4,
        1.0,
        posture="standing",
    )
    reference_solar = reference_solar_gain(
        altitude,
        90.0,
        dni,
        1.0,
        0.4,
        1.0,
        posture="standing",
        round_output=False,
    )
    assert math.isclose(
        ours_solar.delta_mrt,
        float(reference_solar.delta_mrt),
        rel_tol=REL_TOL,
        abs_tol=ABS_TOL,
    )

    gagge_rh = gagge_rh_from_dew_point(temperature_c, dew_point_c)
    for delta_mrt in (0.0, ours_solar.delta_mrt):
        ours_gagge = two_nodes_gagge(
            temperature_c,
            temperature_c + delta_mrt,
            gagge_wind,
            gagge_rh,
            2.6,
            0.36,
            position="standing",
        )
        reference_gagge = reference_two_nodes_gagge(
            temperature_c,
            temperature_c + delta_mrt,
            gagge_wind,
            gagge_rh,
            2.6,
            0.36,
            position="standing",
            round_output=False,
        )
        assert math.isclose(
            ours_gagge.w,
            float(reference_gagge.w),
            rel_tol=REL_TOL,
            abs_tol=ABS_TOL,
        )
        assert math.isclose(
            ours_gagge.m_rsw,
            float(reference_gagge.m_rsw),
            rel_tol=REL_TOL,
            abs_tol=ABS_TOL,
        )
        assert math.isclose(
            ours_gagge.e_max,
            float(reference_gagge.e_max),
            rel_tol=REL_TOL,
            abs_tol=ABS_TOL,
        )

        utci_rh = utci_rh_from_dew_point(temperature_c, dew_point_c)
        ours_utci = utci(
            temperature_c,
            temperature_c + delta_mrt,
            utci_wind,
            utci_rh,
        )
        reference_value = reference_utci(
            temperature_c,
            temperature_c + delta_mrt,
            utci_wind,
            utci_rh,
            round_output=False,
        ).utci
        assert math.isclose(
            ours_utci,
            float(reference_value),
            rel_tol=REL_TOL,
            abs_tol=ABS_TOL,
        )


@pytest.mark.parametrize(
    ("wind", "clothing", "position", "w_max"),
    [
        (0.05, 0.0, "standing", None),
        (0.1, 0.36, "sitting", None),
        (3.0, 0.36, "standing", 0.5),
    ],
)
def test_gagge_branch_cases_match_reference(
    wind: float,
    clothing: float,
    position: str,
    w_max: float | None,
) -> None:
    kwargs = {"w_max": w_max} if w_max is not None else {}
    ours = two_nodes_gagge(
        30.0,
        35.0,
        wind,
        60.0,
        2.0,
        clothing,
        position=position,
        **kwargs,
    )
    reference = reference_two_nodes_gagge(
        30.0,
        35.0,
        wind,
        60.0,
        2.0,
        clothing,
        position=position,
        round_output=False,
        **kwargs,
    )
    assert ours.w == pytest.approx(float(reference.w), rel=REL_TOL, abs=ABS_TOL)
    assert ours.m_rsw == pytest.approx(
        float(reference.m_rsw), rel=REL_TOL, abs=ABS_TOL
    )
    assert ours.e_max == pytest.approx(
        float(reference.e_max), rel=REL_TOL, abs=ABS_TOL
    )


@pytest.mark.parametrize(
    ("altitude", "sharp", "posture"),
    [
        (0.0, 0.0, "standing"),
        (15.0, 45.0, "sitting"),
        (45.0, 135.0, "supine"),
        (90.0, 180.0, "standing"),
    ],
)
def test_solarcal_table_boundaries_and_postures_match_reference(
    altitude: float, sharp: float, posture: str
) -> None:
    ours = solar_gain(
        altitude, sharp, 800.0, 1.0, 0.4, 1.0, posture=posture
    )
    reference = reference_solar_gain(
        altitude,
        sharp,
        800.0,
        1.0,
        0.4,
        1.0,
        posture=posture,
        round_output=False,
    )
    assert ours.erf == pytest.approx(
        float(reference.erf), rel=REL_TOL, abs=ABS_TOL
    )
    assert ours.delta_mrt == pytest.approx(
        float(reference.delta_mrt), rel=REL_TOL, abs=ABS_TOL
    )
