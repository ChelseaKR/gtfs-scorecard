"""Turn a self-serve submission into a reviewable pull request.

The roadmap's Year 1 onboarding path (docs/roadmap.md): an agency or a liaison
submits a feed URL through a short web form, and instead of asking them to learn
YAML, a small serverless function opens a pull request that adds the
agencies.yaml block. A human still reviews and merges, so nothing reaches the
live scorecard unvetted.

This module is the pure core of that function: it validates the form with the
same rules the registry loader uses (so a bad submission is rejected with one
sentence, not a broken PR), renders the block in the registry's style, and
returns everything the GitHub side needs. Keeping it here means it is covered
by the pipeline test suite and shares one definition of "valid agency" with the
daily pipeline. The serverless handler in infra/submit just calls
build_submission and talks to the GitHub API.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from .agencies import AgencyConfigError, parse_agencies
from .mobilitydb import ProposedAgency, render_yaml, slugify

RT_FIELDS = ("trip_updates", "vehicle_positions", "service_alerts")


@dataclass(frozen=True)
class Submission:
    """Everything the GitHub side needs to open the pull request."""

    agency_id: str
    branch: str
    file_content: str  # the full new agencies.yaml
    commit_message: str
    pr_title: str
    pr_body: str


def _clean(form: dict[str, str], key: str) -> str:
    value = form.get(key)
    return value.strip() if isinstance(value, str) else ""


def form_to_entry(form: dict[str, str]) -> dict[str, object]:
    """Build an agencies.yaml entry mapping from submitted form fields.

    The id is derived from the agency name so submitters never supply a slug.
    Realtime URLs are optional and only included when given.
    """
    name = _clean(form, "name")
    entry: dict[str, object] = {
        "id": slugify(name, ""),
        "name": name,
        "static_gtfs_url": _clean(form, "static_gtfs_url"),
    }
    country = _clean(form, "country").upper()
    subdivision_code = _clean(form, "subdivision_code").upper()
    subdivision_name = _clean(form, "subdivision_name")
    if not country and (subdivision_code or subdivision_name):
        raise AgencyConfigError("Country is required when a subdivision code or name is submitted.")
    if bool(subdivision_code) != bool(subdivision_name):
        raise AgencyConfigError(
            "Submit both an ISO subdivision code and subdivision name, or leave both blank."
        )
    # An omitted country is the legacy API shape and intentionally keeps the
    # registry's US default. New browser submissions always send this field.
    if country:
        entry["country"] = country
    if subdivision_code:
        entry["subdivision_code"] = subdivision_code
    if subdivision_name:
        entry["subdivision_name"] = subdivision_name
    rt_urls = {field: _clean(form, field) for field in RT_FIELDS if _clean(form, field)}
    if rt_urls:
        entry["rt_urls"] = rt_urls
    if _clean(form, "license_note"):
        entry["license_note"] = _clean(form, "license_note")
    if _clean(form, "rt_note"):
        entry["rt_note"] = _clean(form, "rt_note")
    return entry


def build_submission(form: dict[str, str], existing_yaml: str) -> Submission:
    """Validate a submission and produce the new agencies.yaml plus PR metadata.

    Raises AgencyConfigError (with a plain-language message) if the entry is
    invalid or duplicates an agency already in the registry.
    """
    entry = form_to_entry(form)
    if not entry["name"]:
        raise AgencyConfigError("Agency name is required.")

    existing = yaml.safe_load(existing_yaml) or {}
    existing_ids = {a.get("id") for a in existing.get("agencies", []) if isinstance(a, dict)}

    # Reuse the registry's own validator so the form enforces the same rules.
    parse_agencies({"agencies": [entry]})
    agency_id = str(entry["id"])
    if agency_id in existing_ids:
        raise AgencyConfigError(
            f"'{agency_id}' is already tracked. If its feed URL changed, edit the "
            "existing entry instead of submitting a new one."
        )

    # Build from the entry that parse_agencies just validated, not from the raw
    # form, so the proposal can't diverge from what passed validation.
    rt_urls_entry = entry.get("rt_urls")
    proposal = ProposedAgency(
        id=agency_id,
        name=str(entry["name"]),
        static_gtfs_url=str(entry["static_gtfs_url"]),
        country=str(entry.get("country") or "US"),
        subdivision_code=str(entry.get("subdivision_code") or ""),
        subdivision_name=str(entry.get("subdivision_name") or ""),
        rt_urls=dict(rt_urls_entry) if isinstance(rt_urls_entry, dict) else {},
        rt_note=str(entry.get("rt_note") or ""),
        license_note=str(entry.get("license_note") or ""),
    )
    block = render_yaml([proposal])
    file_content = existing_yaml.rstrip("\n") + "\n" + block

    submitter = _clean(form, "submitter_email")
    credit = f"\n\nSubmitted via the self-serve form by {submitter}." if submitter else ""
    location = str(entry.get("country") or "US")
    if entry.get("subdivision_code"):
        location += f" / {entry['subdivision_code']} ({entry.get('subdivision_name', '')})"
    return Submission(
        agency_id=agency_id,
        branch=f"submit-{agency_id}",
        file_content=file_content,
        commit_message=f"feat(agency): add {entry['name']} via self-serve form",
        pr_title=f"Add {entry['name']} to the scorecard",
        pr_body=(
            f"Adds **{entry['name']}** (`{agency_id}`) to `agencies.yaml`.\n\n"
            f"- Static GTFS: {entry['static_gtfs_url']}\n"
            f"- Location: {location}\n"
            f"- Realtime: {'yes' if proposal.rt_urls else 'none submitted'}\n\n"
            "The daily pipeline will score it automatically once merged. Please "
            "verify the feed URL and license before merging." + credit
        ),
    )
