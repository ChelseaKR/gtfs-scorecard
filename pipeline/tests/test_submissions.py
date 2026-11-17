"""Tests for the self-serve submission core."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from scorecard_pipeline import submissions
from scorecard_pipeline.agencies import (
    AgencyConfigError,
    parse_agencies,
    registry_paths,
)
from scorecard_pipeline.config import Agency
from scorecard_pipeline.mobilitydb import RegistryRenderError
from scorecard_pipeline.submissions import (
    _FIELD_CHECKS,
    _FIELD_LABELS,
    FIELD_MAX_LENGTH,
    build_submission,
    form_to_entry,
    validate_form,
)

# The real checkout, not the isolated per-test repo root the suite patches in.
REPO_ROOT = Path(__file__).resolve().parents[2]
INTAKE_PATH = REPO_ROOT / "registry/intake.yaml"
INTAKE_YAML = INTAKE_PATH.read_text()


def parse_intake_in_registry_context(intake_yaml: str) -> list[Agency]:
    """Validate an intake shard the way the registry actually loads it.

    The manifest validates every shard together, and intake entries reference
    records in the located shards: a retired feed record here can be an
    ``alias_of`` its successor in a state shard. Parsing intake on its own would
    reject that reference for being outside one file, which is not how the
    registry is read (and not how a submission is merged either).
    """
    entries: list[object] = []
    for path in registry_paths(REPO_ROOT):
        source = intake_yaml if path == INTAKE_PATH else path.read_text()
        entries.extend((yaml.safe_load(source) or {}).get("agencies") or [])
    return parse_agencies({"agencies": entries})


FORM = {
    "name": "Fairfield and Suisun Transit",
    "static_gtfs_url": "https://example.org/fast.zip",
    "vehicle_positions": "https://example.org/fast/vp.pb",
    "license_note": "CC-BY 4.0",
    "submitter_email": "ops@fasttransit.example",
}


def test_form_to_entry_derives_slug_and_rt() -> None:
    entry = form_to_entry(FORM)
    assert entry["id"] == "fairfield-and-suisun-transit"
    assert entry["rt_urls"] == {"vehicle_positions": "https://example.org/fast/vp.pb"}
    assert "country" not in entry  # legacy API payload keeps the registry's US default


def test_submission_yaml_parses_and_includes_new_agency() -> None:
    sub = build_submission(FORM, INTAKE_YAML)
    agencies = parse_intake_in_registry_context(sub.file_content)
    ids = {a.id for a in agencies}
    assert "fairfield-and-suisun-transit" in ids
    existing = {a.id for a in parse_intake_in_registry_context(INTAKE_YAML)}
    assert existing <= ids
    assert sub.branch == "submit-fairfield-and-suisun-transit"
    assert "fasttransit.example" in sub.pr_body
    assert "- Location: `US`" in sub.pr_body


def test_international_submission_preserves_explicit_portable_location() -> None:
    form = {
        **FORM,
        "name": "Barrie Transit Test",
        "country": "ca",
        "subdivision_code": "ca-on",
        "subdivision_name": "Ontario",
    }
    entry = form_to_entry(form)
    assert entry["country"] == "CA"
    assert entry["subdivision_code"] == "CA-ON"
    assert entry["subdivision_name"] == "Ontario"
    sub = build_submission(form, INTAKE_YAML)
    agencies = parse_intake_in_registry_context(sub.file_content)
    added = next(a for a in agencies if a.id == "barrie-transit-test")
    assert (added.country, added.subdivision_code, added.subdivision_name) == (
        "CA",
        "CA-ON",
        "Ontario",
    )
    assert "- Location: `CA / CA-ON (Ontario)`" in sub.pr_body


def test_country_only_international_submission_is_valid() -> None:
    form = {**FORM, "name": "National Feed Test", "country": "CA"}
    entry = form_to_entry(form)
    assert entry["country"] == "CA"
    assert "subdivision_code" not in entry
    sub = build_submission(form, INTAKE_YAML)
    agencies = parse_intake_in_registry_context(sub.file_content)
    added = next(a for a in agencies if a.id == "national-feed-test")
    assert (added.country, added.subdivision_code, added.subdivision_name) == ("CA", "", "")


@pytest.mark.parametrize(
    "updates, message",
    [
        (
            {"country": "CA", "subdivision_code": "CA-ON"},
            "both an ISO subdivision code and subdivision name",
        ),
        (
            {"country": "CA", "subdivision_name": "Ontario"},
            "both an ISO subdivision code and subdivision name",
        ),
        ({"subdivision_code": "US-CA", "subdivision_name": "California"}, "Country is required"),
    ],
)
def test_ambiguous_international_location_is_rejected(
    updates: dict[str, str], message: str
) -> None:
    with pytest.raises(AgencyConfigError, match=message):
        form_to_entry({**FORM, **updates})


def test_duplicate_intake_agency_is_rejected() -> None:
    # An agency still awaiting a verified location, so this exercises the
    # intake half of the duplicate check rather than the sharded half below.
    dup = dict(FORM, name="Megabus")
    with pytest.raises(AgencyConfigError, match="already tracked"):
        build_submission(dup, INTAKE_YAML)


def test_duplicate_sharded_agency_is_rejected_via_known_ids() -> None:
    dup = dict(FORM, name="Unitrans")
    with pytest.raises(AgencyConfigError, match="already tracked"):
        build_submission(dup, INTAKE_YAML, known_ids={"unitrans"})


def test_missing_name_is_rejected() -> None:
    with pytest.raises(AgencyConfigError):
        build_submission(dict(FORM, name=""), INTAKE_YAML)


def test_bad_url_is_rejected_by_registry_rules() -> None:
    with pytest.raises(AgencyConfigError):
        build_submission(dict(FORM, static_gtfs_url="ftp://nope"), INTAKE_YAML)


# The line breaks YAML recognizes besides LF. A submitted value holding one must
# never reach the intake shard as anything but the single value it was.
_YAML_LINE_BREAKS = ["\r", "\x85", "\u2028", "\u2029"]


@pytest.mark.parametrize("sep", _YAML_LINE_BREAKS)
@pytest.mark.parametrize("field", ["name", "static_gtfs_url", "vehicle_positions"])
def test_a_line_break_in_a_name_or_url_is_rejected_at_the_form(sep: str, field: str) -> None:
    form = FORM | {field: f"{FORM[field]}{sep}    large_feed:{sep}      true"}
    with pytest.raises(AgencyConfigError):
        build_submission(form, INTAKE_YAML)


@pytest.mark.parametrize("sep", _YAML_LINE_BREAKS)
def test_a_line_break_in_a_note_never_adds_a_registry_field(sep: str) -> None:
    """Whether a note like this is refused or kept, it must stay one value."""
    form = FORM | {"license_note": f"CC-BY 4.0{sep}    large_feed:{sep}      true"}
    try:
        sub = build_submission(form, INTAKE_YAML)
    except AgencyConfigError:
        return
    entries = yaml.safe_load(sub.file_content)["agencies"]
    (added,) = [e for e in entries if e["id"] == "fairfield-and-suisun-transit"]
    assert set(added) == {"id", "name", "static_gtfs_url", "feed_status", "rt_urls", "license_note"}
    assert added["license_note"] == form["license_note"]


# --- strict validation of every submitted field ------------------------------

LINE_SEPARATOR = chr(0x2028)
PARAGRAPH_SEPARATOR = chr(0x2029)
RIGHT_TO_LEFT_OVERRIDE = chr(0x202E)
ZERO_WIDTH_SPACE = chr(0x200B)


def test_validate_form_returns_trimmed_non_empty_fields_only() -> None:
    cleaned = validate_form(
        {
            "name": "  Fairfield and Suisun Transit  ",
            "static_gtfs_url": " https://example.org/fast.zip ",
            "country": "us",
            "subdivision_code": "",
            "license_note": "   ",
        }
    )
    assert cleaned == {
        "name": "Fairfield and Suisun Transit",
        "static_gtfs_url": "https://example.org/fast.zip",
        "country": "us",
    }


@pytest.mark.parametrize(
    "payload",
    [None, [], "name=Demo", 7, [["name", "Demo"]], {1: "Demo"}],
)
def test_a_payload_that_is_not_a_mapping_of_fields_is_refused(payload: object) -> None:
    with pytest.raises(AgencyConfigError, match="set of named form fields"):
        validate_form(payload)


@pytest.mark.parametrize("field", ["id", "large_feed", "is_official", "alias_of", "fetch_auth"])
def test_a_field_the_form_does_not_have_is_refused(field: str) -> None:
    with pytest.raises(AgencyConfigError, match="does not accept"):
        validate_form(FORM | {field: "x"})


@pytest.mark.parametrize("value", [None, 7, True, ["Demo"], {"a": "b"}])
@pytest.mark.parametrize("field", sorted(FIELD_MAX_LENGTH))
def test_every_field_must_be_text(field: str, value: object) -> None:
    with pytest.raises(AgencyConfigError, match="must be text"):
        validate_form(FORM | {field: value})


@pytest.mark.parametrize("field", sorted(FIELD_MAX_LENGTH))
def test_every_field_has_a_length_limit(field: str) -> None:
    too_long = "a" * (FIELD_MAX_LENGTH[field] + 1)
    with pytest.raises(AgencyConfigError, match="too long"):
        validate_form(FORM | {field: too_long})


@pytest.mark.parametrize(
    "name",
    [
        "Société de transport de Montréal",
        "東京都交通局",
        "Ishikari City Transit (石狩市AIデマンド交通「いつモ」)",
        "AC Transit (Alameda-Contra Costa)",
        "Brighton & Hove Buses",
        "exo La Presqu'Île / Vaudreuil",
        "CRTM — Red de Metro Ligero",
        "SNgo! (Seine Normandie Agglomération)",
        "A:Shiwi Transit",
        "Lignes+ No. 5, Fort St. John",
    ],
)
def test_ordinary_agency_names_in_any_script_are_accepted(name: str) -> None:
    assert validate_form(FORM | {"name": name})["name"] == name


@pytest.mark.parametrize(
    "name",
    [
        "Demo <b>Transit</b>",
        "Demo > Transit",
        "Demo `Transit`",
        "Demo @maintainer Transit",
        "Demo #123",
        "Demo [link](https://example.org)",
        "Demo ![x](https://example.org/x.png)",
        "Demo {{ secrets.TOKEN }}",
        "Demo ${HOME}",
        "Demo $(id)",
        "Demo; id",
        "Demo | id",
        "Demo \\ Transit",
        'Demo "Transit"',
        "Demo * Transit",
        "Demo = Transit",
        "Demo ~ Transit",
        "Demo ^ Transit",
        "Demo % Transit",
        "Demo ? Transit",
        "Demo_Transit",
        "Demo\tTransit",
        "Demo\nTransit",
        "Demo\rTransit",
        "Demo\x85Transit",
        "Demo\x00Transit",
        "Demo\x1bTransit",
        "Demo\x7fTransit",
        f"Demo{LINE_SEPARATOR}Transit",
        f"Demo{PARAGRAPH_SEPARATOR}Transit",
        f"Demo{RIGHT_TO_LEFT_OVERRIDE}Transit",
        f"Demo{ZERO_WIDTH_SPACE}Transit",
        "Demo \U0001f68c Transit",
        "Demo \ue000 Transit",
    ],
)
def test_names_with_markup_control_or_symbol_characters_are_refused(name: str) -> None:
    with pytest.raises(AgencyConfigError, match="Agency name can use"):
        validate_form(FORM | {"name": name})


@pytest.mark.parametrize("name", ["---", "...", "()", "'"])
def test_a_name_needs_a_letter_or_number(name: str) -> None:
    with pytest.raises(AgencyConfigError, match="at least one letter or number"):
        validate_form(FORM | {"name": name})


@pytest.mark.parametrize(
    "note",
    [
        "CC-BY 4.0",
        "License: https://example.org/terms?lang=en#reuse",
        "Open data; attribution required (see agency site).",
        "ODbL_1.0 + attribution, 100% open",
    ],
)
def test_ordinary_notes_are_accepted(note: str) -> None:
    assert validate_form(FORM | {"license_note": note, "rt_note": note})["rt_note"] == note


@pytest.mark.parametrize(
    "note",
    [
        "see <a href=x>terms</a>",
        "ping @maintainer",
        "`code`",
        "[terms](https://example.org)",
        "{{ x }}",
        "a\\b",
        'say "hi"',
        "two\nlines",
        f"two{LINE_SEPARATOR}lines",
        "cost $5",
        "a | b",
    ],
)
@pytest.mark.parametrize("field", ["license_note", "rt_note"])
def test_notes_with_markup_or_control_characters_are_refused(field: str, note: str) -> None:
    with pytest.raises(AgencyConfigError, match="can use letters"):
        validate_form(FORM | {field: note})


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/gtfs.zip",
        "http://example.org/gtfs.zip",
        "HTTPS://Example.ORG/gtfs.zip",
        "https://data.example.co.uk:8443/feeds/gtfs.zip?key=abc-123&v=2#latest",
        "https://rapid.example.org/UserUploadFiles/11834/ats_albany_ga_us(2).zip",
        "https://foothill_3rdparty.example.com/myStop/GTFS-Realtime.ashx?&Type=Alert",
        "https://xn--bcher-kva.example.xn--p1ai/gtfs.zip",
        "https://example.org/path%20with%20space/gtfs.zip",
    ],
)
@pytest.mark.parametrize("field", ["static_gtfs_url", "trip_updates"])
def test_ordinary_feed_urls_are_accepted(field: str, url: str) -> None:
    assert validate_form(FORM | {field: url})[field] == url


@pytest.mark.parametrize(
    "url, message",
    [
        ("ftp://example.org/gtfs.zip", "must start with https:// or http://"),
        ("file:///etc/passwd", "must start with https:// or http://"),
        ("javascript:alert(1)", "must start with https:// or http://"),
        ("data:text/html,x", "must start with https:// or http://"),
        ("//example.org/gtfs.zip", "must start with https:// or http://"),
        ("example.org/gtfs.zip", "must start with https:// or http://"),
        ("https:/example.org/gtfs.zip", "not a complete web address"),
        ("https:///gtfs.zip", "not a complete web address"),
        ("https://example.org:99999/gtfs.zip", "not a complete web address"),
        ("https://example.org:port/gtfs.zip", "not a complete web address"),
        ("https://user:pass@example.org/gtfs.zip", "plain web address"),
        ("https://example.org/gtfs zip", "plain web address"),
        ("https://example.org/gtfs.zip\nx", "plain web address"),
        (f"https://example.org/gtfs.zip{LINE_SEPARATOR}x", "plain web address"),
        ("https://example.org/<script>", "plain web address"),
        ("https://example.org/`id`", "plain web address"),
        ("https://example.org/$(id)", "plain web address"),
        ("https://example.org/${{x}}", "plain web address"),
        ("https://example.org/a|b", "plain web address"),
        ("https://example.org/a\\b", "plain web address"),
        ("https://example.org/'a'", "plain web address"),
        ('https://example.org/"a"', "plain web address"),
        ("https://exämple.org/gtfs.zip", "plain web address"),
        ("https://[::1]/gtfs.zip", "plain web address"),
        ("https://127.0.0.1/gtfs.zip", "public host name"),
        ("https://10.0.0.5:8080/gtfs.zip", "public host name"),
        ("https://169.254.169.254/latest/meta-data", "public host name"),
        ("https://2130706433/gtfs.zip", "public host name"),
        ("https://0x7f.0.0.1/gtfs.zip", "public host name"),
        ("https://localhost/gtfs.zip", "public host name"),
        ("https://intranet/gtfs.zip", "public host name"),
        ("https://feeds.agency.local/gtfs.zip", "public host name"),
        ("https://feeds.agency.internal/gtfs.zip", "public host name"),
        ("https://something.localhost/gtfs.zip", "public host name"),
        ("https://abc.onion/gtfs.zip", "public host name"),
        ("https://-bad-.example.org/gtfs.zip", "public host name"),
        ("https://example..org/gtfs.zip", "public host name"),
        ("https://example.org./gtfs.zip", "public host name"),
    ],
)
@pytest.mark.parametrize("field", ["static_gtfs_url", "service_alerts"])
def test_urls_outside_the_scheme_and_host_rules_are_refused(
    field: str, url: str, message: str
) -> None:
    with pytest.raises(AgencyConfigError, match=message):
        validate_form(FORM | {field: url})


@pytest.mark.parametrize(
    "email",
    [
        "not-an-email",
        "@maintainer",
        "a@b",
        "a b@example.org",
        "a@example.org\nBcc: x@example.org",
        "<a@example.org>",
        "a@example.org, b@example.org",
        "`a`@example.org",
    ],
)
def test_contact_email_must_be_one_plain_address(email: str) -> None:
    with pytest.raises(AgencyConfigError, match="Contact email"):
        validate_form(FORM | {"submitter_email": email})


@pytest.mark.parametrize("country", ["USA", "U", "U1", "U-"])
def test_country_must_be_two_letters(country: str) -> None:
    with pytest.raises(AgencyConfigError, match="Country"):
        validate_form(FORM | {"country": country})


@pytest.mark.parametrize("code", ["ON", "CA_ON", "CA-", "C-ON", "CA-O!"])
def test_subdivision_code_must_look_like_iso_3166_2(code: str) -> None:
    with pytest.raises(AgencyConfigError, match="Subdivision code"):
        validate_form(FORM | {"country": "CA", "subdivision_code": code})


def test_build_submission_runs_the_strict_checks_itself() -> None:
    with pytest.raises(AgencyConfigError, match="does not accept"):
        build_submission(FORM | {"large_feed": "true"}, INTAKE_YAML)
    with pytest.raises(AgencyConfigError, match="set of named form fields"):
        build_submission(["name", "Demo"], INTAKE_YAML)


def test_a_name_too_long_to_make_an_id_is_refused() -> None:
    name = " ".join(["Transit"] * 18)  # 143 characters, inside the name limit
    assert len(name) <= FIELD_MAX_LENGTH["name"]
    with pytest.raises(AgencyConfigError, match="could not build a short id"):
        build_submission(FORM | {"name": name}, INTAKE_YAML)


def test_pull_request_text_carries_submitted_values_only_as_code_spans() -> None:
    form = FORM | {
        "name": "Brighton & Hove Buses (Test)",
        "static_gtfs_url": "https://example.org/feeds/gtfs.zip?key=a&v=2",
        "country": "GB",
        "subdivision_code": "GB-ENG",
        "subdivision_name": "England",
    }
    sub = build_submission(form, INTAKE_YAML)

    assert sub.branch == "submit-brighton-hove-buses-test"
    assert re.fullmatch(r"submit-[a-z0-9][a-z0-9-]{0,119}", sub.branch)
    assert sub.commit_message == ("feat(agency): add brighton-hove-buses-test via self-serve form")
    assert sub.pr_title == "Add Brighton & Hove Buses (Test) to the scorecard"
    for text in (sub.branch, sub.commit_message, sub.pr_title):
        assert "\n" not in text
        assert "`" not in text
    assert "Adds `Brighton & Hove Buses (Test)` (`brighton-hove-buses-test`)" in sub.pr_body
    assert "- Static GTFS: `https://example.org/feeds/gtfs.zip?key=a&v=2`\n" in sub.pr_body
    assert "- Location: `GB / GB-ENG (England)`\n" in sub.pr_body
    assert "by `ops@fasttransit.example`." in sub.pr_body
    # Outside the code spans the body is the fixed template: no mention, link or image.
    outside = re.sub(r"`[^`\n]*`", "", sub.pr_body)
    assert "@" not in outside
    assert "http" not in outside
    assert "[" not in outside
    assert sub.pr_body.count("`") % 2 == 0


def test_every_accepted_field_has_a_limit_a_label_and_a_checker() -> None:
    assert set(_FIELD_CHECKS) == set(FIELD_MAX_LENGTH) == set(_FIELD_LABELS)


def test_a_block_the_writer_refuses_is_answered_as_a_rejected_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(_proposals: object) -> str:
        raise RegistryRenderError("does not read back")

    monkeypatch.setattr(submissions, "render_yaml", refuse)
    with pytest.raises(AgencyConfigError, match="could not be written as a registry entry"):
        build_submission(FORM, INTAKE_YAML)
