"""Packaging invariants that protect dependency-free installation."""

import ast
import json
import re
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


def test_hacs_payload_contains_upstream_license_notice() -> None:
    notice = (INTEGRATION / "THIRD_PARTY_NOTICES.md").read_text()
    assert "Copyright (c) 2019 Federico Tartarini" in notice
    assert "Permission is hereby granted, free of charge" in notice


def test_hacs_manifest_uses_supported_keys() -> None:
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert set(hacs) <= {
        "name",
        "content_in_root",
        "zip_release",
        "filename",
        "hide_default_branch",
        "country",
        "homeassistant",
        "hacs",
        "persistent_directory",
    }


def test_github_actions_are_pinned_to_full_commit_shas() -> None:
    workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text()
    references = re.findall(r"uses:\s*[^@\s]+@([^\s#]+)", workflow)
    assert references
    assert all(
        re.fullmatch(r"[0-9a-f]{40}|sha256:[0-9a-f]{64}", reference)
        for reference in references
    )
