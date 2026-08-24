# Sweat for Home Assistant

Sweat is a HACS-installable Home Assistant custom integration that estimates
skin wettedness: the fraction of skin covered in liquid sweat, reported as a raw
ratio from 0 to 1. It also reports UTCI so that hot conditions remain distinguishable
when wettedness approaches the Gagge model's dynamic upper limit.

The integration is source-agnostic. Every weather input is an entity selected in
the UI; there are no station, location, or source-specific entity IDs in the code.
It does not fetch weather.

## Compatibility and installation

Sweat targets Home Assistant 2026.8.2 or newer. Its manifest intentionally contains
`"requirements": []`: the runtime uses only Python's standard-library `math` module
for the thermal models and does not import NumPy, SciPy, Numba, or a network client.

In HACS, add `https://github.com/mckalexee/sweat-assistant` as a custom integration
repository, install **Sweat**, restart Home Assistant, then choose **Settings →
Devices & services → Add integration → Sweat**.

## Current inputs

The setup flow requires:

- air temperature in °C, °F, or K;
- exactly one of relative humidity or dew point;
- wind speed in m/s, mph, km/h, or kn.

The selected wind is treated as observed 10 m meteorological wind for UTCI. The
walking-air-movement option is added only to Gagge's local air speed. Calm observed
wind is modeled as 0.5 m/s for UTCI, its lower applicability bound; both observed and
modeled speeds are exposed as attributes.

### Optional solar inputs

Supported configurations are:

- DNI by itself;
- DNI plus measured GHI and/or diffuse horizontal irradiance; or
- measured GHI and diffuse irradiance together, from which DNI is derived while the
  sun is above the horizon.

Solar altitude is also required when irradiance is configured. The flow suggests the
sole entity in the `sun` domain when one exists without embedding an entity ID. For a
Sun entity, Sweat reads its `elevation` attribute; a numeric entity can report degrees
in its state.

With DNI alone, the exact pythermalcomfort SolarCal assumptions are used: diffuse is
`0.2 × DNI`, and reflected horizontal radiation is derived from DNI, altitude, and
diffuse. Configured measured components replace only those assumptions. A selected
component becoming unavailable makes sun outputs unavailable but does not affect
shade. Missing or malformed component data makes sun outputs unknown.

With no irradiance entities, only shade sensors are created. Their `solar_data`
attribute is `false`. This is a fully supported path, not an error.

## Entities

On a fresh English installation the usual entity IDs are:

| Entity | State |
|---|---|
| `sensor.sweat_shade` | Skin wettedness, 0–1 |
| `sensor.sweat_utci_shade` | UTCI, native °C and converted by Home Assistant |
| `sensor.sweat_sun` | Sun skin wettedness, when solar is configured |
| `sensor.sweat_utci_sun` | Sun UTCI, when solar is configured |

Home Assistant owns entity IDs, so collisions, localization, and user renames can
change them. Sweat uses stable registry unique IDs rather than forcing these names.

Each current sensor exposes metabolic rate, clothing, posture, sky-view factor,
observed wind, Gagge air speed, UTCI wind, SHARP, body exposure, transmittance,
`delta_mrt`, and `solar_data` as audit attributes.

## Advanced options

These assumptions can be changed later from the integration's **Configure** menu:

| Option | Default |
|---|---:|
| Metabolic rate | 2.6 met |
| Clothing | 0.36 clo |
| Walking air movement added to Gagge wind | 1.1 m/s |
| Posture | standing |
| Sky-view factor | 0.4 |
| Body fraction exposed to direct sun (`f_bes`) | 1.0 |
| Solar transmittance | 1.0 |
| Sun-to-body horizontal angle (SHARP) | 90° |

The commissioned example table was generated with a total Gagge air speed of
1.0 m/s. It is not an acceptance table for the shipped 1.1 m/s walking-air-movement
default: with calm ambient wind, that default produces a total of 1.1 m/s. Set the
option to 1.0 m/s when reproducing those example values.

The sky-view factor is a street-canyon estimate, not a measurement. Under SolarCal it
scales diffuse and ground-reflected radiation; it does not directly scale the beam
falling on the body. SHARP is also an orientation assumption: 0° is front, 90° is
side-on, and 180° is back.

## Optional 48-hour forecast

Forecasts are deliberately separate from the core current-condition path. Select all
six `input_text` entities—temperature, dew point, wind, DNI, GHI, and diffuse—or leave
all six empty. Sweat never writes or alters those helpers.

Every helper uses this format:

```text
epoch,v1,v2,…,v48
```

`epoch` is the Unix UTC timestamp of `v1` and must be aligned to the start of a UTC
hour; each following value is one hour later.
Configure each `input_text` helper with a maximum length of 255 characters; the
default helper limit may be too short for a complete series.
Use canonical units because `input_text` has no unit metadata:

- temperature and dew point: °C;
- wind: m/s;
- DNI, GHI, and diffuse: W/m².

All six series must contain 48 finite integer values and the same epoch. This prevents a new
temperature generation from being combined with old wind or radiation data while an
automation updates helpers sequentially. Solar altitude is inferred from the coherent
DNI/GHI/diffuse components. At night the solar delta is zero.

The integration indexes the forecast by elapsed UTC seconds, then converts timestamps
to Home Assistant's time zone for the `forecast` attribute. This remains correct across
DST changes. The forecast sensors expose:

- their current-hour forecast as the numeric state;
- a structured `forecast` attribute with local timestamp, raw `w`, and UTCI in °C;
- a compact `series` attribute in `epoch,w1,…,w48` form, with wettedness multiplied by
  100 and stored as integers. The compact output is checked against the 255-character
  budget.

## Interpretation and calibration

Sweat reports raw model outputs and intentionally does not label values “sticky,”
“sweaty,” or “gross.” Thresholds differ by person and should be calibrated against
real ratings. The often-cited whole-body discomfort value near `w = 0.36` came from a
controlled treadmill protocol and is only indicative for an outdoor sidewalk.

Reference equality proves that the scalar equations were transcribed correctly. It
does **not** prove that the assumptions are correct for a person's metabolism,
clothing, wind exposure, orientation, surrounding surfaces, or street geometry. Shade
assumes mean radiant temperature equals air temperature. Treat the output as a model,
not a medical or safety measurement.

Sweat does not enforce source freshness because legitimate update cadences vary. A
numeric source state is treated as current; source integrations and automations remain
responsible for marking stale data unavailable.

## Development and validation

The two test environments are intentionally separate:

```bash
# Exact Home Assistant 2026.8.2 runtime tests on Python 3.14
uv run --no-project --python 3.14 \
  --with-requirements requirements-ha-test.txt \
  pytest -q tests --ignore=tests/test_against_reference.py

# pythermalcomfort 4.4.2 differential oracle on Python 3.13
uv run --no-project --python 3.13 \
  --with-requirements requirements-reference-test.txt \
  pytest -q tests/test_against_reference.py

uv run --extra quality ruff check .
```

The differential suite uses unrounded results and checks 768 grid combinations at
`rel_tol=1e-6` with a documented `abs_tol=1e-9` floor for exact-zero comparisons.

## License and attribution

This project is MIT licensed. The scalar Gagge two-node, SolarCal, and UTCI models are
adapted from [pythermalcomfort 4.4.2](https://github.com/pythermalcomfort/pythermalcomfort/tree/v4.4.2),
also MIT licensed. The complete upstream notice is retained in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
