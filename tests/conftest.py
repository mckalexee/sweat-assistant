"""Home Assistant fixtures for Sweat tests."""

from importlib.util import find_spec

if find_spec("pytest_homeassistant_custom_component") is not None:
    import pytest

    pytest_plugins = "pytest_homeassistant_custom_component"

    @pytest.fixture(autouse=True)
    def _enable_custom_integrations(enable_custom_integrations):
        """Allow loading the integration from custom_components."""
