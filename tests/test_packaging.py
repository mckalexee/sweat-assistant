"""Packaging invariants that protect dependency-free installation."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "sweat"


def test_manifest_has_no_runtime_requirements() -> None:
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    assert manifest["requirements"] == []
    assert manifest["config_flow"] is True


def test_integration_does_not_import_forbidden_dependencies() -> None:
    forbidden = {"numpy", "scipy", "numba", "requests", "aiohttp"}
    imported: set[str] = set()
    for path in INTEGRATION.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(forbidden)


def test_hacs_brand_and_translation_assets_exist() -> None:
    assert (INTEGRATION / "brand" / "icon.png").stat().st_size > 0
    json.loads((INTEGRATION / "translations" / "en.json").read_text())
