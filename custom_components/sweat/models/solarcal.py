"""Scalar SolarCal model.

Adapted from pythermalcomfort 4.4.2
(`pythermalcomfort/models/solar_gain.py`), copyright Federico Tartarini,
under the MIT License. See THIRD_PARTY_NOTICES.md for the full license text.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_ALTITUDES = (0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0)
_DEGREES_TO_RADIANS = 0.0174532925
_SHARPS = (
    0.0,
    15.0,
    30.0,
    45.0,
    60.0,
    75.0,
    90.0,
    105.0,
    120.0,
    135.0,
    150.0,
    165.0,
    180.0,
)
_FP_STANDING = (
    (0.35, 0.35, 0.314, 0.258, 0.206, 0.144, 0.082),
    (0.342, 0.342, 0.31, 0.252, 0.2, 0.14, 0.082),
    (0.33, 0.33, 0.3, 0.244, 0.19, 0.132, 0.082),
    (0.31, 0.31, 0.275, 0.228, 0.175, 0.124, 0.082),
    (0.283, 0.283, 0.251, 0.208, 0.16, 0.114, 0.082),
    (0.252, 0.252, 0.228, 0.188, 0.15, 0.108, 0.082),
    (0.23, 0.23, 0.214, 0.18, 0.148, 0.108, 0.082),
    (0.242, 0.242, 0.222, 0.18, 0.153, 0.112, 0.082),
    (0.274, 0.274, 0.245, 0.203, 0.165, 0.116, 0.082),
    (0.304, 0.304, 0.27, 0.22, 0.174, 0.121, 0.082),
    (0.328, 0.328, 0.29, 0.234, 0.183, 0.125, 0.082),
    (0.344, 0.344, 0.304, 0.244, 0.19, 0.128, 0.082),
    (0.347, 0.347, 0.308, 0.246, 0.191, 0.128, 0.082),
)
_FP_SITTING = (
    (0.29, 0.324, 0.305, 0.303, 0.262, 0.224, 0.177),
    (0.292, 0.328, 0.294, 0.288, 0.268, 0.227, 0.177),
    (0.288, 0.332, 0.298, 0.29, 0.264, 0.222, 0.177),
    (0.274, 0.326, 0.294, 0.289, 0.252, 0.214, 0.177),
    (0.254, 0.308, 0.28, 0.276, 0.241, 0.202, 0.177),
    (0.23, 0.282, 0.262, 0.26, 0.233, 0.193, 0.177),
    (0.216, 0.26, 0.248, 0.244, 0.22, 0.186, 0.177),
    (0.234, 0.258, 0.236, 0.227, 0.208, 0.18, 0.177),
    (0.262, 0.26, 0.224, 0.208, 0.196, 0.176, 0.177),
    (0.28, 0.26, 0.21, 0.192, 0.184, 0.17, 0.177),
    (0.298, 0.256, 0.194, 0.174, 0.168, 0.168, 0.177),
    (0.306, 0.25, 0.18, 0.156, 0.156, 0.166, 0.177),
    (0.3, 0.24, 0.168, 0.152, 0.152, 0.164, 0.177),
)


@dataclass(frozen=True, slots=True)
class SolarGainResult:
    """Solar effective radiant field and mean-radiant-temperature delta."""

    erf: float
    delta_mrt: float


def _span(points: tuple[float, ...], value: float) -> int:
    for index in range(len(points) - 1):
        if points[index] <= value <= points[index + 1]:
            return index
    raise ValueError("Solar angle is outside the SolarCal table")


def _transpose_supine(sharp: float, altitude: float) -> tuple[float, float]:
    altitude_new = math.degrees(
        math.asin(
            math.sin(math.radians(abs(sharp - 90.0)))
            * math.cos(math.radians(altitude))
        )
    )
    sharp_new = math.degrees(
        math.atan(
            math.sin(math.radians(sharp))
            * math.tan(math.radians(90.0 - altitude))
        )
    )
    return round(sharp_new, 3), round(altitude_new, 3)


def _projected_area_factor(altitude: float, sharp: float, posture: str) -> float:
    table = _FP_SITTING if posture == "sitting" else _FP_STANDING
    altitude_index = _span(_ALTITUDES, altitude)
    sharp_index = _span(_SHARPS, sharp)
    altitude_low = _ALTITUDES[altitude_index]
    altitude_high = _ALTITUDES[altitude_index + 1]
    sharp_low = _SHARPS[sharp_index]
    sharp_high = _SHARPS[sharp_index + 1]
    fp11 = table[sharp_index][altitude_index]
    fp12 = table[sharp_index][altitude_index + 1]
    fp21 = table[sharp_index + 1][altitude_index]
    fp22 = table[sharp_index + 1][altitude_index + 1]
    projected = fp11 * (sharp_high - sharp) * (altitude_high - altitude)
    projected += fp21 * (sharp - sharp_low) * (altitude_high - altitude)
    projected += fp12 * (sharp_high - sharp) * (altitude - altitude_low)
    projected += fp22 * (sharp - sharp_low) * (altitude - altitude_low)
    return projected / (
        (sharp_high - sharp_low) * (altitude_high - altitude_low)
    )


def solar_gain(
    sol_altitude: float,
    sharp: float,
    sol_radiation_dir: float,
    sol_transmittance: float,
    f_svv: float,
    f_bes: float,
    *,
    asw: float = 0.7,
    posture: str = "sitting",
    floor_reflectance: float = 0.6,
    diffuse_radiation: float | None = None,
    global_horizontal_radiation: float | None = None,
    round_output: bool = False,
) -> SolarGainResult:
    """Calculate SolarCal for scalar inputs.

    Omitting measured diffuse and global horizontal irradiance exactly preserves
    pythermalcomfort's assumptions. Providing them replaces only those two radiation
    components; the remaining SolarCal equations are unchanged.
    """
    values = (
        sol_altitude,
        sharp,
        sol_radiation_dir,
        sol_transmittance,
        f_svv,
        f_bes,
        asw,
        floor_reflectance,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("SolarCal inputs must be finite")
    if posture not in {"standing", "sitting", "supine"}:
        raise ValueError("posture must be standing, sitting, or supine")
    if not 0.0 <= sol_altitude <= 90.0 or not 0.0 <= sharp <= 180.0:
        raise ValueError("Solar angles are outside the SolarCal domain")
    if sol_radiation_dir < 0:
        raise ValueError("DNI cannot be negative")
    if not all(0.0 <= value <= 1.0 for value in (sol_transmittance, f_svv, f_bes)):
        raise ValueError("Solar fractions must be between zero and one")

    geometry_altitude = sol_altitude
    geometry_sharp = sharp
    if posture == "supine":
        geometry_sharp, geometry_altitude = _transpose_supine(sharp, sol_altitude)

    if diffuse_radiation is None:
        diffuse_radiation = 0.2 * sol_radiation_dir
    if global_horizontal_radiation is None:
        # Upstream transposes supine geometry before calculating its assumed
        # reflected-horizontal component as well as the projected area.
        global_horizontal_radiation = (
            sol_radiation_dir
            * math.sin(geometry_altitude * _DEGREES_TO_RADIANS)
            + diffuse_radiation
        )
    if (
        not math.isfinite(diffuse_radiation)
        or not math.isfinite(global_horizontal_radiation)
        or diffuse_radiation < 0
        or global_horizontal_radiation < 0
    ):
        raise ValueError("Measured irradiance must be finite and nonnegative")

    projected_area = _projected_area_factor(
        geometry_altitude, geometry_sharp, posture
    )
    effective_area = 0.696 if posture == "sitting" else 0.725
    diffuse = (
        effective_area
        * f_svv
        * 0.5
        * sol_transmittance
        * diffuse_radiation
    )
    direct = (
        effective_area
        * projected_area
        * sol_transmittance
        * f_bes
        * sol_radiation_dir
    )
    reflected = (
        effective_area
        * f_svv
        * 0.5
        * sol_transmittance
        * global_horizontal_radiation
        * floor_reflectance
    )
    erf = (diffuse + direct + reflected) * (asw / 0.95)
    delta_mrt = erf / (6.0 * effective_area)
    if round_output:
        return SolarGainResult(erf=round(erf, 1), delta_mrt=round(delta_mrt, 1))
    return SolarGainResult(erf=erf, delta_mrt=delta_mrt)
