"""Dependency-free scalar thermal models used by Sweat."""

from .gagge import GaggeResult, two_nodes_gagge
from .solarcal import SolarGainResult, solar_gain
from .utci import utci

__all__ = [
    "GaggeResult",
    "SolarGainResult",
    "solar_gain",
    "two_nodes_gagge",
    "utci",
]
