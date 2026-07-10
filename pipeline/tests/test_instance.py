"""Tests for the instance identity config (EXP-15 forkable template)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scorecard_pipeline.instance import DEFAULTS, load_instance_config


def test_defaults_when_no_instance_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No instance.yaml at all falls back to the maintainer's production values."""
    monkeypatch.setenv("SCORECARD_INSTANCE_CONFIG", str(tmp_path / "missing.yaml"))
    cfg = load_instance_config()
    assert cfg == DEFAULTS


def test_empty_instance_yaml_falls_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "instance.yaml"
    path.write_text("")
    monkeypatch.setenv("SCORECARD_INSTANCE_CONFIG", str(path))
    cfg = load_instance_config()
    assert cfg == DEFAULTS


def test_partial_override_leaves_other_fields_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fork can override just one field (e.g. base_url) and inherit the rest."""
    path = tmp_path / "instance.yaml"
    path.write_text("base_url: https://gtfs.example-state.gov/\n")
    monkeypatch.setenv("SCORECARD_INSTANCE_CONFIG", str(path))
    cfg = load_instance_config()
    # Trailing slash stripped for consistent URL-building elsewhere.
    assert cfg.base_url == "https://gtfs.example-state.gov"
    assert cfg.site_name == DEFAULTS.site_name
    assert cfg.org_name == DEFAULTS.org_name
    assert cfg.contact_email == DEFAULTS.contact_email
    assert cfg.tagline == DEFAULTS.tagline


def test_full_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "instance.yaml"
    path.write_text(
        "base_url: https://scorecard.example.org\n"
        "site_name: Example Scorecard\n"
        "org_name: Example State DOT\n"
        "contact_email: hello@example.org\n"
        "tagline: A forked instance for Example State.\n"
    )
    monkeypatch.setenv("SCORECARD_INSTANCE_CONFIG", str(path))
    cfg = load_instance_config()
    assert cfg.base_url == "https://scorecard.example.org"
    assert cfg.site_name == "Example Scorecard"
    assert cfg.org_name == "Example State DOT"
    assert cfg.contact_email == "hello@example.org"
    assert cfg.tagline == "A forked instance for Example State."


def test_non_mapping_yaml_falls_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed instance.yaml (e.g. a bare list) never crashes the pipeline."""
    path = tmp_path / "instance.yaml"
    path.write_text("- not\n- a\n- mapping\n")
    monkeypatch.setenv("SCORECARD_INSTANCE_CONFIG", str(path))
    cfg = load_instance_config()
    assert cfg == DEFAULTS


def test_module_level_singleton_matches_production_defaults() -> None:
    """Imported with no instance.yaml on this checkout, the module-level
    constants match the maintainer's production identity unchanged."""
    from scorecard_pipeline import instance

    assert instance.BASE_URL == "https://gtfsscorecard.org"
    assert instance.SITE_NAME == "GTFS Scorecard"
