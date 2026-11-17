"""Turn a self-serve submission into a reviewable pull request.

The roadmap's Year 1 onboarding path (docs/roadmap.md): an agency or a liaison
submits a feed URL through a short web form, and instead of asking them to learn
YAML, a small serverless function opens a pull request that adds an entry to
``registry/intake.yaml``. A human still reviews and merges, so nothing reaches
the live scorecard unvetted.

This module is the pure core of that function: it checks every submitted field
against a strict shape (``validate_form``), validates the result with the same
rules the registry loader uses (so a bad submission is rejected with one
sentence, not a broken PR), renders the block in the registry's style, and
returns everything the GitHub side needs. Keeping it here means it is covered
by the pipeline test suite and shares one definition of "valid agency" with the
daily pipeline. The serverless handler in infra/submit just calls
build_submission and talks to the GitHub API.

The form is public and anonymous, so its rules are narrower than the
registry's. A maintainer can add by hand an entry the form would refuse (a
feed served from an IP address, a name with unusual punctuation); the form
only has to accept what an ordinary agency submits (ADR 0078).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

import yaml

from .agencies import AgencyConfigError, parse_agencies
from .mobilitydb import ProposedAgency, render_yaml, slugify

RT_FIELDS = ("trip_updates", "vehicle_positions", "service_alerts")
URL_FIELDS = ("static_gtfs_url", *RT_FIELDS)

#: Every field the form may send, with the longest value accepted for it
#: (characters, after trimming). Anything else in the payload is refused.
FIELD_MAX_LENGTH = {
    "name": 150,
    "static_gtfs_url": 500,
    "trip_updates": 500,
    "vehicle_positions": 500,
    "service_alerts": 500,
    "country": 2,
    "subdivision_code": 6,
    "subdivision_name": 80,
    "license_note": 300,
    "rt_note": 300,
    "submitter_email": 254,
}

_FIELD_LABELS = {
    "name": "Agency name",
    "static_gtfs_url": "GTFS Schedule URL",
    "trip_updates": "Trip updates URL",
    "vehicle_positions": "Vehicle positions URL",
    "service_alerts": "Service alerts URL",
    "country": "Country",
    "subdivision_code": "Subdivision code",
    "subdivision_name": "Subdivision name",
    "license_note": "License note",
    "rt_note": "Realtime note",
    "submitter_email": "Contact email",
}

# Text fields accept letters, combining marks and digits in any script, spaces,
# and ordinary punctuation: dashes, brackets, quotation marks and the "other
# punctuation" class that holds . , ' / : & and their full-width forms. Control
# characters, line and paragraph separators, format characters, symbols and
# private-use code points are in none of these classes, so they are refused
# without being listed.
_TEXT_CATEGORIES = frozenset(
    {"Lu", "Ll", "Lt", "Lm", "Lo", "Mn", "Mc", "Me", "Nd", "Nl", "No", "Zs"}
    | {"Pd", "Ps", "Pe", "Pi", "Pf", "Po"}
)
# Punctuation inside those classes that has a meaning to something downstream
# of the form: Markdown and mention syntax in the pull request text, and
# brackets and braces generally. A name needs none of it.
_NAME_REFUSED = frozenset('@#*\\"%;?[]{}')
_NAME_EXTRA = frozenset("+")
# A note may quote a URL or a license identifier, so it keeps # % ; ? and adds
# the few symbols those use.
_NOTE_REFUSED = frozenset('@*\\"[]{}')
_NOTE_EXTRA = frozenset("+=_~")

# The characters a feed URL is made of. Deliberately narrower than RFC 3986:
# no quotes, backticks, brackets, braces, backslash, "@" (so no credentials in
# the URL), and nothing outside ASCII (an internationalized name is submitted
# in its punycode form).
_URL_CHARS = re.compile(r"[A-Za-z0-9\-._~:/?#&=%+,;()]+")
_HOST_LABEL = r"[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?"
_TLD = r"(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})"
_HOSTNAME = re.compile(rf"(?=.{{4,253}}\Z)(?:{_HOST_LABEL}\.)+{_TLD}")
# Names that never resolve on the public internet, or only by local convention.
_REFUSED_TLDS = frozenset(
    {"local", "localhost", "localdomain", "internal", "intranet", "lan", "home", "corp"}
    | {"test", "invalid", "example", "onion", "arpa"}
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_COUNTRY = re.compile(r"[A-Za-z]{2}")
_SUBDIVISION_CODE = re.compile(r"[A-Za-z]{2}-[A-Za-z0-9]{1,3}")
# The branch name and the registry id are both built from this slug. The same
# shape the site's own pages accept for an agency id.
_SUBMISSION_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,119}")


@dataclass(frozen=True)
class Submission:
    """Everything the GitHub side needs to open the pull request."""

    agency_id: str
    branch: str
    file_content: str  # the full new registry/intake.yaml
    commit_message: str
    pr_title: str
    pr_body: str


def _clean(form: dict[str, str], key: str) -> str:
    value = form.get(key)
    return value.strip() if isinstance(value, str) else ""


def _refuse(message: str) -> AgencyConfigError:
    return AgencyConfigError(message)


def _check_text(label: str, value: str, *, refused: frozenset[str], extra: frozenset[str]) -> None:
    for char in value:
        allowed = char in extra or (
            unicodedata.category(char) in _TEXT_CATEGORIES and char not in refused
        )
        if not allowed:
            raise _refuse(
                f"{label} can use letters, numbers, spaces and ordinary punctuation only."
            )


def _check_url(label: str, value: str) -> None:
    if not _URL_CHARS.fullmatch(value):
        raise _refuse(f"{label} must be a plain web address with no spaces, quotes or brackets.")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise _refuse(f"{label} is not a complete web address.") from None
    if parts.scheme.lower() not in {"http", "https"}:
        raise _refuse(f"{label} must start with https:// or http://.")
    host = (parts.hostname or "").lower()
    expected_netloc = host if port is None else f"{host}:{port}"
    if not host or parts.netloc.lower() != expected_netloc:
        raise _refuse(f"{label} is not a complete web address.")
    if not _HOSTNAME.fullmatch(host) or host.rsplit(".", 1)[-1] in _REFUSED_TLDS:
        raise _refuse(
            f"{label} must use a public host name, like https://example.gov/gtfs.zip. "
            "A feed served from an IP address or a private name needs the manual walkthrough."
        )


def _check_name(label: str, value: str) -> None:
    _check_text(label, value, refused=_NAME_REFUSED, extra=_NAME_EXTRA)
    if not any(char.isalnum() for char in value):
        raise _refuse(f"{label} must include at least one letter or number.")


def _check_note(label: str, value: str) -> None:
    _check_text(label, value, refused=_NOTE_REFUSED, extra=_NOTE_EXTRA)


def _check_country(_label: str, value: str) -> None:
    if not _COUNTRY.fullmatch(value):
        raise _refuse("Country must be a two-letter ISO code, like US or CA.")


def _check_subdivision_code(_label: str, value: str) -> None:
    if not _SUBDIVISION_CODE.fullmatch(value):
        raise _refuse("Subdivision code must be an ISO 3166-2 code, like CA-ON.")


def _check_email(_label: str, value: str) -> None:
    if not _EMAIL.fullmatch(value):
        raise _refuse("Contact email must be a complete address, like name@agency.gov.")


# One checker per field. A field with no checker here cannot be submitted:
# test_submissions holds this table to the same keys as FIELD_MAX_LENGTH.
_FIELD_CHECKS = {
    "name": _check_name,
    "static_gtfs_url": _check_url,
    "trip_updates": _check_url,
    "vehicle_positions": _check_url,
    "service_alerts": _check_url,
    "country": _check_country,
    "subdivision_code": _check_subdivision_code,
    "subdivision_name": _check_name,
    "license_note": _check_note,
    "rt_note": _check_note,
    "submitter_email": _check_email,
}


def validate_form(form: object) -> dict[str, str]:
    """Check a submitted payload field by field; return the trimmed, non-empty fields.

    Raises AgencyConfigError with one plain sentence for the first problem:
    a payload that is not a mapping, a field the form does not have, a value
    that is not text, a value that is too long, or a value holding characters
    its field does not take. Nothing in the returned mapping holds a control
    character, a line break of any kind, or markup.
    """
    if not isinstance(form, dict) or not all(isinstance(key, str) for key in form):
        raise _refuse("The submission must be a set of named form fields.")
    if set(form) - set(FIELD_MAX_LENGTH):
        raise _refuse("The submission has a field this form does not accept.")

    cleaned: dict[str, str] = {}
    for field, max_length in FIELD_MAX_LENGTH.items():
        label = _FIELD_LABELS[field]
        raw = form.get(field, "")
        if not isinstance(raw, str):
            raise _refuse(f"{label} must be text.")
        value = unicodedata.normalize("NFC", raw).strip()
        if not value:
            continue
        if len(value) > max_length:
            raise _refuse(f"{label} is too long (the limit is {max_length} characters).")
        _FIELD_CHECKS[field](label, value)
        cleaned[field] = value
    return cleaned


def form_to_entry(form: object) -> dict[str, object]:
    """Build a registry entry mapping from submitted form fields.

    The form is checked by ``validate_form`` first. The id is derived from the
    agency name so submitters never supply a slug. Realtime URLs are optional
    and only included when given.
    """
    fields = validate_form(form)
    name = _clean(fields, "name")
    entry: dict[str, object] = {
        "id": slugify(name, ""),
        "name": name,
        "static_gtfs_url": _clean(fields, "static_gtfs_url"),
    }
    country = _clean(fields, "country").upper()
    subdivision_code = _clean(fields, "subdivision_code").upper()
    subdivision_name = _clean(fields, "subdivision_name")
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
    rt_urls = {field: _clean(fields, field) for field in RT_FIELDS if _clean(fields, field)}
    if rt_urls:
        entry["rt_urls"] = rt_urls
    if _clean(fields, "license_note"):
        entry["license_note"] = _clean(fields, "license_note")
    if _clean(fields, "rt_note"):
        entry["rt_note"] = _clean(fields, "rt_note")
    return entry


def checked_entry(form: object) -> tuple[dict[str, str], dict[str, object]]:
    """Run every check that needs nothing but the submission itself.

    Returns the validated form fields and the registry entry built from them.
    The handler calls this before it counts a request or uses its GitHub
    token, so a submission that could never become a pull request costs
    nothing; build_submission calls it again and adds the duplicate check,
    which needs the registry.
    """
    fields = validate_form(form)
    entry = form_to_entry(fields)
    if not entry["name"]:
        raise AgencyConfigError("Agency name is required.")
    if not entry["static_gtfs_url"]:
        raise AgencyConfigError("GTFS Schedule URL is required.")
    if not _SUBMISSION_ID.fullmatch(str(entry["id"])):
        raise AgencyConfigError(
            "The scorecard could not build a short id from that agency name. "
            "Shorten the name, or use the manual walkthrough."
        )
    # Reuse the registry's own validator so the form enforces the same rules.
    parse_agencies({"agencies": [entry]})
    return fields, entry


def build_submission(
    form: object, existing_yaml: str, known_ids: set[str] | None = None
) -> Submission:
    """Validate a submission and produce the new intake shard plus PR metadata.

    Raises AgencyConfigError (with a plain-language message) if the entry is
    invalid or duplicates an agency already in the registry. ``existing_yaml``
    is the intake shard the new entry is appended to; ``known_ids`` covers
    entries already curated into another manifest-listed shard.
    """
    fields, entry = checked_entry(form)

    existing = yaml.safe_load(existing_yaml) or {}
    existing_ids = {a.get("id") for a in existing.get("agencies", []) if isinstance(a, dict)}
    existing_ids |= known_ids or set()

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

    # Everything submitted is written into the pull request as a code span.
    # validate_form admits no backtick, so a span cannot be closed early, and
    # nothing in it is read as a mention, a link, an image or a heading.
    submitter = _clean(fields, "submitter_email")
    credit = f"\n\nSubmitted via the self-serve form by `{submitter}`." if submitter else ""
    location = str(entry.get("country") or "US")
    if entry.get("subdivision_code"):
        location += f" / {entry['subdivision_code']} ({entry.get('subdivision_name', '')})"
    return Submission(
        agency_id=agency_id,
        branch=f"submit-{agency_id}",
        file_content=file_content,
        commit_message=f"feat(agency): add {agency_id} via self-serve form",
        pr_title=f"Add {entry['name']} to the scorecard",
        pr_body=(
            f"Adds `{entry['name']}` (`{agency_id}`) to `registry/intake.yaml`.\n\n"
            f"- Static GTFS: `{entry['static_gtfs_url']}`\n"
            f"- Location: `{location}`\n"
            f"- Realtime: {'yes' if proposal.rt_urls else 'none submitted'}\n\n"
            "The daily pipeline will score it automatically once merged. Please "
            "verify the feed URL and license before merging." + credit
        ),
    )
