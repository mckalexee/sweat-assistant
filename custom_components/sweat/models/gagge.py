"""Scalar Gagge two-node model.

Adapted from pythermalcomfort 4.4.2
(`pythermalcomfort/models/two_nodes_gagge.py`), copyright Federico Tartarini,
under the MIT License. See THIRD_PARTY_NOTICES.md for the full license text.

Only the outputs used by this integration are retained. The thermoregulatory
simulation is otherwise kept numerically equivalent to the upstream scalar kernel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GaggeResult:
    """Outputs needed by the Sweat integration."""

    w: float
    m_rsw: float
    e_max: float


def saturation_vapor_pressure_torr(temperature_c: float) -> float:
    """Return saturation vapor pressure in torr."""
    return math.exp(18.6686 - 4030.183 / (temperature_c + 235.0))


def relative_humidity_from_dew_point(
    temperature_c: float, dew_point_c: float
) -> float:
    """Convert dew point to relative humidity using the model's vapor equation."""
    return 100.0 * saturation_vapor_pressure_torr(
        dew_point_c
    ) / saturation_vapor_pressure_torr(temperature_c)


def two_nodes_gagge(
    tdb: float,
    tr: float,
    v: float,
    rh: float,
    met: float,
    clo: float,
    *,
    wme: float = 0.0,
    body_surface_area: float = 1.8258,
    p_atm: float = 101325.0,
    position: str = "standing",
    max_skin_blood_flow: float = 90.0,
    max_sweating: float = 500.0,
    w_max: float | None = None,
    round_output: bool = False,
) -> GaggeResult:
    """Calculate skin wettedness and sweat evaporation for one environment."""
    values = (
        tdb,
        tr,
        v,
        rh,
        met,
        clo,
        wme,
        body_surface_area,
        p_atm,
        max_skin_blood_flow,
        max_sweating,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Gagge inputs must be finite")
    if position not in {"standing", "sitting", "supine"}:
        raise ValueError("position must be standing, sitting, or supine")
    if body_surface_area <= 0 or p_atm <= 0 or met <= 0 or v < 0:
        raise ValueError("Gagge inputs are outside their physical domain")

    vapor_pressure = rh * saturation_vapor_pressure_torr(tdb) / 100.0
    air_speed = max(v, 0.1)
    body_weight = 70.0
    met_factor = 58.2
    stefan_boltzmann = 0.000000056697
    sweating_coefficient = 170.0
    dilation_coefficient = 120.0
    constriction_coefficient = 0.5

    skin_neutral = 33.7
    core_neutral = 36.8
    alpha = 0.1
    body_neutral = alpha * skin_neutral + (1.0 - alpha) * core_neutral
    neutral_skin_blood_flow = 6.3

    t_skin = skin_neutral
    t_core = core_neutral
    skin_blood_flow = neutral_skin_blood_flow
    e_skin = 0.1 * met
    e_rsw = 0.0
    e_max = 0.0
    m_rsw = 0.0

    pressure_atm = p_atm / 101325.0
    r_clo = 0.155 * clo
    f_a_cl = 1.0 + 0.15 * clo
    lewis_ratio = 2.2 / pressure_atm
    rm = (met - wme) * met_factor
    metabolic_power = met * met_factor

    i_cl = 0.45 if clo > 0 else 1.0
    if not w_max:
        w_max = 0.38 * air_speed**-0.29
        if clo > 0:
            w_max = 0.59 * air_speed**-0.08

    h_cc = 3.0 * pressure_atm**0.53
    h_fc = 8.600001 * (air_speed * pressure_atm) ** 0.53
    h_cc = max(h_cc, h_fc)
    if met > 0.85:
        h_cc = max(h_cc, 5.66 * (met - 0.85) ** 0.39)

    h_r = 4.7
    h_t = h_r + h_cc
    r_a = 1.0 / (f_a_cl * h_t)
    t_op = (h_r * tr + h_cc * tdb) / h_t
    t_body = alpha * t_skin + (1.0 - alpha) * t_core

    q_res = 0.0023 * metabolic_power * (44.0 - vapor_pressure)
    c_res = 0.0014 * metabolic_power * (34.0 - tdb)

    simulation_minute = 1
    while simulation_minute < 60:
        simulation_minute += 1
        t_cl = (r_a * t_skin + r_clo * t_op) / (r_a + r_clo)

        for _iteration in range(151):
            area_ratio = 0.7 if position == "sitting" else 0.73
            h_r = (
                4.0
                * 0.95
                * stefan_boltzmann
                * ((t_cl + tr) / 2.0 + 273.15) ** 3.0
                * area_ratio
            )
            h_t = h_r + h_cc
            r_a = 1.0 / (f_a_cl * h_t)
            t_op = (h_r * tr + h_cc * tdb) / h_t
            t_cl_new = (r_a * t_skin + r_clo * t_op) / (r_a + r_clo)
            converged = abs(t_cl_new - t_cl) <= 0.01
            t_cl = t_cl_new
            if converged:
                break
        else:
            raise RuntimeError("Gagge clothing-temperature iteration did not converge")

        q_sensible = (t_skin - t_op) / (r_a + r_clo)
        heat_flow_core_skin = (t_core - t_skin) * (
            5.28 + 1.163 * skin_blood_flow
        )
        storage_core = (
            metabolic_power - heat_flow_core_skin - q_res - c_res - wme
        )
        storage_skin = heat_flow_core_skin - q_sensible - e_skin
        capacity_skin = 0.97 * alpha * body_weight
        capacity_core = 0.97 * (1.0 - alpha) * body_weight
        t_skin += storage_skin * body_surface_area / (capacity_skin * 60.0)
        t_core += storage_core * body_surface_area / (capacity_core * 60.0)
        t_body = alpha * t_skin + (1.0 - alpha) * t_core

        skin_signal = t_skin - skin_neutral
        warm_skin = max(skin_signal, 0.0)
        cold_skin = max(-skin_signal, 0.0)
        core_signal = t_core - core_neutral
        warm_core = max(core_signal, 0.0)
        cold_core = max(-core_signal, 0.0)
        body_signal = t_body - body_neutral
        warm_body = max(body_signal, 0.0)

        skin_blood_flow = (
            neutral_skin_blood_flow + dilation_coefficient * warm_core
        ) / (1.0 + constriction_coefficient * cold_skin)
        skin_blood_flow = min(skin_blood_flow, max_skin_blood_flow)
        skin_blood_flow = max(skin_blood_flow, 0.5)

        m_rsw = sweating_coefficient * warm_body * math.exp(warm_skin / 10.7)
        m_rsw = min(m_rsw, max_sweating)
        e_rsw = 0.68 * m_rsw
        r_ea = 1.0 / (lewis_ratio * f_a_cl * h_cc)
        r_ecl = r_clo / (lewis_ratio * i_cl)
        e_max = (
            saturation_vapor_pressure_torr(t_skin) - vapor_pressure
        ) / (r_ea + r_ecl)
        if e_max == 0:
            e_max = 0.001

        p_rsw = e_rsw / e_max
        wettedness = 0.06 + 0.94 * p_rsw
        e_diff = wettedness * e_max - e_rsw
        if wettedness > w_max:
            wettedness = w_max
            p_rsw = w_max / 0.94
            e_rsw = p_rsw * e_max
            e_diff = 0.06 * (1.0 - p_rsw) * e_max
        if e_max < 0:
            e_diff = 0.0
            e_rsw = 0.0
            wettedness = w_max

        e_skin = e_rsw + e_diff
        m_rsw = e_rsw / 0.68
        metabolic_power = rm + 19.4 * cold_skin * cold_core
        alpha = 0.0417737 + 0.7451833 / (skin_blood_flow + 0.585417)

    result = GaggeResult(w=wettedness, m_rsw=m_rsw, e_max=e_max)
    if round_output:
        return GaggeResult(
            w=round(result.w, 2),
            m_rsw=round(result.m_rsw, 2),
            e_max=round(result.e_max, 2),
        )
    return result
