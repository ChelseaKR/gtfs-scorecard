"""Instance identity: the pieces a fork edits to stand up its own scorecard.

EXP-15 (`docs/ideation/03-expansions.md`) asks for the region-specific pieces
of the site to live behind config instead of hardcoded literals, so a third
party can deploy a branded instance without a code change. This module is the
first, load-bearing slice of that: the site's public identity (canonical
base URL, display name, organization name, contact address) reads from
``instance.yaml`` at the repo root when present, falling back to the
maintainer's production values so the upstream repo's behavior is unchanged.

A fork copies ``instance.example.yaml`` to ``instance.yaml`` and edits it;
no code change is required to rebrand the site's canonical URLs, feed titles,
JSON-LD publisher fields, and the like. See ``docs/fork-quickstart.md``.

**Scope note.** This covers identity, not the rubric. The scoring thresholds
in `rt.py` (Caltrans v4.0 realtime targets) and `metrics.py` (freshness lead
time) are California-guideline citations woven into the scoring math itself,
not swappable config yet -- making the *rubric* pluggable per region is a
larger, separate follow-up (tracked as a prerequisite in EXP-15's own
write-up, referencing RR:E11). Forking today gets you your own branded
instance scored on the same shared rubric, which the excellence bar in
EXP-15 treats as the honest default: version the shared rubric rather than
let each fork silently diverge on what "good GTFS" means.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import repo_root


@dataclass(frozen=True)
class InstanceConfig:
    """The identity fields a forked deployment customizes."""

    base_url: str
    site_name: str
    org_name: str
    contact_email: str
    tagline: str


# The maintainer's production values. A fork with no instance.yaml (or an
# instance.yaml missing a field) gets these, so the file is optional and
# every field can be overridden independently.
DEFAULTS = InstanceConfig(
    base_url="https://gtfsscorecard.org",
    site_name="GTFS Scorecard",
    org_name="GTFS Scorecard",
    contact_email="hello@gtfsscorecard.org",
    tagline="An open-source GTFS quality scorecard for small transit agencies.",
)


def _config_path() -> Path:
    """``instance.yaml`` at the repo root, overridable for tests."""
    env = os.environ.get("SCORECARD_INSTANCE_CONFIG")
    if env:
        return Path(env)
    return repo_root() / "instance.yaml"


def load_instance_config() -> InstanceConfig:
    """Load instance identity from ``instance.yaml``, defaulting field-by-field.

    Missing file, empty file, or a missing individual key all fall back to
    ``DEFAULTS`` rather than erroring, so a fork can override just the one
    field it cares about (e.g. only ``base_url``) and leave the rest.
    """
    path = _config_path()
    if not path.exists():
        return DEFAULTS
    raw = yaml.safe_load(path.read_text())
    data: dict[str, object] = raw if isinstance(raw, dict) else {}
    return InstanceConfig(
        base_url=str(data.get("base_url", DEFAULTS.base_url)).rstrip("/"),
        site_name=str(data.get("site_name", DEFAULTS.site_name)),
        org_name=str(data.get("org_name", DEFAULTS.org_name)),
        contact_email=str(data.get("contact_email", DEFAULTS.contact_email)),
        tagline=str(data.get("tagline", DEFAULTS.tagline)),
    )


# Module-level singleton, matching the config.py convention (AGENCIES, etc.):
# loaded once at import time from whatever SCORECARD_ROOT / instance.yaml is
# in effect. Call load_instance_config() directly in tests that need a fresh
# read after changing the file or env var mid-process.
INSTANCE = load_instance_config()
BASE_URL = INSTANCE.base_url
SITE_NAME = INSTANCE.site_name
ORG_NAME = INSTANCE.org_name
CONTACT_EMAIL = INSTANCE.contact_email
TAGLINE = INSTANCE.tagline
