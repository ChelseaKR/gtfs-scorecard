"""Unit tests for scripts/bundle-testmode.sh's own logic.

The script drives Stripe, Terraform, AWS and a browser, so almost none of it
can be tested here. What can be, and is, is the part that decides *whether* to
do any of that: the phase sequence, `--only`/`--from`, the masking function,
the guard that stops a second set of Stripe objects being created, and the
guard that refuses a Terraform plan containing a destroy. Those five are where
a bug costs the owner real cleanup: duplicate Payment Links to archive by hand,
a destroyed artifacts bucket, or a credential in a log.

Nothing here needs a credential, a network, or an AWS account. The script is
sourced rather than run, which defines its functions and executes nothing (the
`BASH_SOURCE[0] = $0` guard at the bottom of the file), so each function is
called in isolation.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "bundle-testmode.sh"
DRIVER = REPO / "scripts" / "bundle-testmode-checkout.mjs"

# The runbook's order (gtfs-bundle-launch HUMAN-STEPS.md, Phase A). A phase
# moving earlier than the one whose output it reads is the failure this pins.
EXPECTED_PHASES = [
    "preflight",
    "stripe-objects",
    "build",
    "apply-closed",
    "artifacts-lifecycle",
    "webhook",
    "actions-var",
    "config-js",
    "open-gate",
    "purchase",
    "verify-fulfilment",
    "verify-cap",
    "teardown-notes",
]


def _bash(snippet: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Source the script and run one snippet against its functions."""
    return subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
        ["/usr/bin/env", "bash", "-c", f'source "{SCRIPT}"\n{snippet}'],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - repository-owned script, fixed arguments
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )


# ---------------------------------------------------------------------------
# Phase sequencing
# ---------------------------------------------------------------------------


def test_phases_are_the_runbook_order() -> None:
    listed = _run_script("--list-phases")
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.split() == EXPECTED_PHASES


def test_resolve_phases_with_no_flags_runs_everything_in_order() -> None:
    result = _bash('resolve_phases "" ""')
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == EXPECTED_PHASES


def test_only_runs_exactly_one_phase() -> None:
    result = _bash('resolve_phases "webhook" ""')
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["webhook"]


def test_from_resumes_at_that_phase_and_runs_the_rest() -> None:
    result = _bash('resolve_phases "" "open-gate"')
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == EXPECTED_PHASES[EXPECTED_PHASES.index("open-gate") :]


def test_from_the_first_phase_is_the_whole_run() -> None:
    result = _bash('resolve_phases "" "preflight"')
    assert result.stdout.split() == EXPECTED_PHASES


def test_only_wins_over_from() -> None:
    result = _bash('resolve_phases "build" "purchase"')
    assert result.stdout.split() == ["build"]


@pytest.mark.parametrize(
    ("only", "frm"),
    [("nope", ""), ("", "nope"), ("Build", ""), ("", "verify_cap")],
)
def test_an_unknown_phase_is_an_error_not_an_empty_run(only: str, frm: str) -> None:
    """A typo must stop the script, never silently run nothing (or everything)."""
    result = _bash(f'resolve_phases "{only}" "{frm}"')
    assert result.returncode == 2
    assert result.stdout.strip() == ""
    assert "unknown phase" in result.stderr


def test_an_unknown_phase_on_the_command_line_exits_non_zero() -> None:
    result = _run_script("--only", "nope", "--dry-run")
    assert result.returncode != 0
    assert "unknown phase" in result.stderr


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------


def _shaped(prefix: str, body: str) -> str:
    """A string shaped like a credential, joined at runtime rather than written
    out whole.

    The halves are separate on purpose. `.gitleaks.toml` allowlists no path
    under `pipeline/tests` outside `fixtures/`, and that is the right policy:
    hand-written source is exactly where a real credential must not hide. A
    fixture written out whole trips `stripe-access-token` and would either fail
    the secret scan or force a waiver that weakens it for every other file. The
    assembled value is what the assertions below use, so nothing is lost.
    """
    return prefix + body


LIVE_KEY = _shaped("sk_", "live_NotARealKey00000000")

# Shaped like the credentials the script handles, and deliberately not valid.
FAKE_SECRETS = [
    _shaped("sk_", "test_51NotARealKeyJustShapedLikeOne00000000"),
    _shaped("rk_", "test_51NotARealKeyJustShapedLikeOne00000000"),
    _shaped("github_", "pat_11NOTAREALTOKENjustShapedLikeOne00000"),
    _shaped("whsec_", "NotARealSigningSecretJustShapedLikeOne00"),
]


@pytest.mark.parametrize("secret", FAKE_SECRETS)
def test_mask_never_emits_the_value(secret: str) -> None:
    result = _bash(f'mask "{secret}"')
    assert result.returncode == 0, result.stderr
    assert secret not in result.stdout
    # At most four characters of the value survive, and they are the first four.
    assert result.stdout.startswith(secret[:4])
    assert secret[4:8] not in result.stdout
    assert str(len(secret)) in result.stdout


def test_mask_says_unset_rather_than_printing_an_empty_string() -> None:
    assert _bash('mask ""').stdout == "(unset)"


@pytest.mark.parametrize("secret", FAKE_SECRETS)
def test_preflight_output_never_contains_a_key_shaped_string(secret: str) -> None:
    """The end-to-end version of the check above: run the phase that reads
    every credential and assert none of them reaches stdout or stderr."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/nonexistent-home-for-this-test",
        "STRIPE_SECRET_KEY": secret,
        "STRIPE_RESTRICTED_KEY": secret,
        "BUNDLE_GITHUB_PAT": secret,
        "STRIPE_WEBHOOK_SECRET": secret,
        "BUNDLE_DELIVER_TO": "nobody@example.invalid",
    }
    result = subprocess.run(  # noqa: S603 - repository-owned script, fixed arguments
        [str(SCRIPT), "--only", "preflight", "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
        env=env,
    )
    combined = result.stdout + result.stderr
    assert secret not in combined
    assert secret[4:] not in combined
    # It still said something about each one.
    for name in ("STRIPE_SECRET_KEY", "STRIPE_RESTRICTED_KEY", "BUNDLE_GITHUB_PAT"):
        assert name in combined


def test_a_live_stripe_key_is_refused_loudly() -> None:
    result = _bash(
        f'ENV_PROBLEMS=0; STRIPE_SECRET_KEY="{LIVE_KEY}" '
        'check_env_var STRIPE_SECRET_KEY sk_test_ required; echo "problems=$ENV_PROBLEMS"'
    )
    assert "LIVE Stripe key" in result.stdout
    assert "Refusing" in result.stdout
    assert "problems=1" in result.stdout
    assert LIVE_KEY not in result.stdout


def test_the_script_carries_no_key_shaped_literal() -> None:
    """Nothing that looks like a credential may be committed in either file."""
    pattern = re.compile(r"\b(sk|rk)_(test|live)_[A-Za-z0-9]{12,}|\bwhsec_[A-Za-z0-9]{16,}")
    for path in (SCRIPT, DRIVER):
        assert not pattern.search(path.read_text(encoding="utf-8")), path


# ---------------------------------------------------------------------------
# The Stripe idempotency guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state_complete", "bundle_n", "refresh_n", "expected"),
    [
        (1, 0, 0, "reuse-state"),  # state says everything exists: create nothing
        (1, 1, 1, "reuse-state"),
        (0, 0, 0, "create"),  # the account is empty: run stripe-setup.sh once
        (0, 1, 1, "reuse"),  # one of each already there: skip creation
        (0, 2, 1, "duplicates"),  # stripe-setup.sh already ran twice
        (0, 1, 2, "duplicates"),
        (0, 1, 0, "partial"),  # half a run: re-running would duplicate the half
        (0, 0, 1, "partial"),
    ],
)
def test_stripe_objects_action(
    state_complete: int, bundle_n: int, refresh_n: int, expected: str
) -> None:
    result = _bash(f"stripe_objects_action {state_complete} {bundle_n} {refresh_n}")
    assert result.stdout == expected, result.stderr


# A stub for the one network call the discovery path makes. Redefining a
# function after sourcing is how a phase gets tested with no Stripe account.
_STRIPE_401 = (
    "stripe_api() { STRIPE_HTTP=401;"
    ' STRIPE_BODY=\'{"error":{"message":"Invalid API Key provided"}}\'; return 1; }'
)


def test_a_stripe_read_that_fails_is_not_an_empty_account() -> None:
    result = _bash(
        f"{_STRIPE_401}\nif stripe_products_named k n; then echo listed; else echo refused; fi"
    )
    assert result.stdout.strip() == "refused", result.stderr


def test_stripe_objects_refuses_rather_than_creating_when_the_account_cannot_be_read(
    tmp_path: Path,
) -> None:
    """A 401 returns no products. Reading that as "the account is empty" would
    run stripe-setup.sh against an account nobody could check first, which is
    the one mistake this phase exists to prevent."""
    path = _write_state(tmp_path, complete=False)
    result = _bash(
        f'STATE_FILE="{path}"; STRIPE_SECRET_KEY=unused; DRY_RUN=0; REPO_ROOT="{REPO}"\n'
        f"{_STRIPE_401}\n"
        'if phase_stripe_objects; then echo "rc=0"; else echo "rc=nonzero"; fi'
    )
    assert "rc=nonzero" in result.stdout
    assert "could not list Stripe products" in result.stdout
    assert "cannot be read is not an empty" in result.stdout
    assert "Running scripts/stripe-setup.sh" not in result.stdout


def _write_state(tmp_path: Path, *, complete: bool) -> Path:
    links = {
        "bundle_25": "https://buy.stripe.com/test_25",
        "bundle_100": "https://buy.stripe.com/test_100",
        "refresh_mo": "https://buy.stripe.com/test_mo",
        "refresh_yr": "https://buy.stripe.com/test_yr",
    }
    if not complete:
        del links["refresh_yr"]
    state: dict[str, object] = {
        "schema": "1",
        "mode": "test",
        "products": {"bundle": "prod_bundle", "refresh": "prod_refresh"},
        "prices": {
            "bundle_25": "price_25",
            "bundle_100": "price_100",
            "refresh_mo": "price_mo",
            "refresh_yr": "price_yr",
        },
        "links": links,
    }
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def _complete(path: Path) -> str:
    return _bash(
        f'STATE_FILE="{path}"; if state_is_complete; then echo yes; else echo no; fi'
    ).stdout.strip()


def test_a_complete_state_file_means_create_nothing(tmp_path: Path) -> None:
    assert _complete(_write_state(tmp_path, complete=True)) == "yes"


def test_a_state_file_missing_one_link_is_not_complete(tmp_path: Path) -> None:
    assert _complete(_write_state(tmp_path, complete=False)) == "no"


def test_a_missing_state_file_is_not_complete(tmp_path: Path) -> None:
    assert _complete(tmp_path / "absent.json") == "no"


def test_stripe_objects_phase_skips_creation_when_the_state_is_complete(tmp_path: Path) -> None:
    """The whole point: with a complete state file the phase returns without
    reaching Stripe at all. `stripe` is removed from PATH here, so if it tried,
    this test would fail rather than pass quietly."""
    path = _write_state(tmp_path, complete=True)
    result = _bash(
        f'STATE_FILE="{path}"; STRIPE_SECRET_KEY="unused"; DRY_RUN=0;'
        ' phase_stripe_objects; echo "rc=$?"',
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    assert "rc=0" in result.stdout
    assert "already records 2 products, 4 prices and 4 Payment Links" in result.stdout
    assert "Nothing will be created" in result.stdout
    assert "stripe-setup.sh" not in result.stdout.split("Nothing will be created")[1]


# ---------------------------------------------------------------------------
# The Terraform destroy guard
# ---------------------------------------------------------------------------


def _destroys(path: Path) -> str:
    return _bash(f'if plan_has_destroy "{path}"; then echo yes; else echo no; fi').stdout.strip()


def _plan(tmp_path: Path, *changes: list[str]) -> Path:
    plan = {
        "resource_changes": [
            {"address": f"aws_thing.n{i}", "change": {"actions": actions}}
            for i, actions in enumerate(changes)
        ]
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "changes",
    [
        ([["delete"]]),
        ([["delete", "create"]]),  # a replacement, which Terraform spells this way
        ([["create", "delete"]]),  # create_before_destroy spells it the other way
        ([["create"], ["update"], ["delete"]]),  # one destroy among many changes
        ([["no-op"], ["delete", "create"]]),
    ],
)
def test_plan_has_destroy_catches_every_shape_of_delete(
    tmp_path: Path, changes: list[list[str]]
) -> None:
    assert _destroys(_plan(tmp_path, *changes)) == "yes"


@pytest.mark.parametrize(
    "changes",
    [([["create"]]), ([["update"]]), ([["no-op"]]), ([["create"], ["update"], ["no-op"]])],
)
def test_plan_has_destroy_is_quiet_when_nothing_is_deleted(
    tmp_path: Path, changes: list[list[str]]
) -> None:
    assert _destroys(_plan(tmp_path, *changes)) == "no"


def test_an_empty_plan_has_no_destroys(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text("{}", encoding="utf-8")
    assert _destroys(path) == "no"


def test_plan_destroy_list_names_what_would_go(tmp_path: Path) -> None:
    path = _plan(tmp_path, ["create"], ["delete", "create"])
    result = _bash(f'plan_destroy_list "{path}"')
    assert "aws_thing.n1" in result.stdout
    assert "aws_thing.n0" not in result.stdout


def test_terraform_plan_apply_refuses_a_destroying_plan() -> None:
    """The guard is wired into the apply path, not just available beside it."""
    body = SCRIPT.read_text(encoding="utf-8")
    guard = body.index("if plan_has_destroy")
    apply = body.index('run_checked "${label}: terraform apply"')
    assert guard < apply, "the destroy check must run before the apply, not after"
    assert 'bad "${label}: the plan destroys something. Stopping without applying."' in body


def test_artifacts_lifecycle_never_passes_a_var_flag() -> None:
    """infra/README.md: a wrong bucket name from -var plans six destroys of
    the live artifacts bucket. The value comes from a tfvars file or not at
    all."""
    code = [
        line
        for line in SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    for line in code:
        assert " -var " not in line and " -var=" not in line, line
    assert any("-input=false" in line for line in code), (
        "terraform must never be able to prompt for bucket_name"
    )


# ---------------------------------------------------------------------------
# Housekeeping the script promises
# ---------------------------------------------------------------------------


def test_the_script_is_executable_and_sets_strict_mode() -> None:
    assert SCRIPT.stat().st_mode & 0o111, "scripts/bundle-testmode.sh must be executable"
    body = SCRIPT.read_text(encoding="utf-8")
    assert body.startswith("#!/usr/bin/env bash")
    assert "\nset -euo pipefail\n" in body


def test_credentials_are_written_only_to_a_0600_tfvars() -> None:
    body = SCRIPT.read_text(encoding="utf-8")
    assert 'chmod 600 "$TFVARS"' in body
    assert "umask 077" in body


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_shellcheck_is_clean() -> None:
    result = subprocess.run(  # noqa: S603 - resolved shellcheck binary over this checkout
        [shutil.which("shellcheck") or "shellcheck", "--shell=bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# The browser driver's selectors
#
# Half of them are Stripe's, on a page this repo does not own and cannot test
# against without a key, so the driver tries a list of candidates and dumps the
# page when none match. The other half are this repo's own setup form, and
# those can be pinned: if a field id changes, the driver would otherwise fail
# only during a paid checkout.
# ---------------------------------------------------------------------------

SETUP_FORM = REPO / "web" / "bundle" / "setup" / "index.html"


@pytest.mark.parametrize(
    "element_id",
    ["setup-form", "program_name", "accent", "agency_ids", "deliver_to", "form-status"],
)
def test_the_driver_targets_ids_the_setup_form_actually_has(element_id: str) -> None:
    driver = DRIVER.read_text(encoding="utf-8")
    form = SETUP_FORM.read_text(encoding="utf-8")
    assert f'#{element_id}"' in driver or f"#{element_id} " in driver, (
        f"the driver does not use #{element_id}"
    )
    assert f'id="{element_id}"' in form, f"the setup form has no #{element_id}"


def test_the_setup_form_submit_button_matches_the_driver() -> None:
    form = SETUP_FORM.read_text(encoding="utf-8")
    assert '<button type="submit"' in form
    assert "#setup-form button[type='submit']" in DRIVER.read_text(encoding="utf-8")


def test_the_driver_prints_exactly_one_json_object_on_stdout() -> None:
    """The shell parses stdout with jq, so every log line must go to stderr."""
    driver = DRIVER.read_text(encoding="utf-8")
    assert "console.log(" not in driver
    assert driver.count("process.stdout.write(") == 2  # the success and failure paths


def test_the_driver_uses_only_stripes_documented_test_card() -> None:
    body = SCRIPT.read_text(encoding="utf-8")
    assert 'TEST_CARD="4242424242424242"' in body


# ---------------------------------------------------------------------------
# Upstream messages, and where the key is allowed to travel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        # Stripe's real 401 body: it quotes the key back with only its middle
        # starred out, which is far more than four characters.
        "Invalid API Key provided: " + _shaped("sk_", "test_51AbCdEf***WxYz"),
        "Invalid API Key provided: " + _shaped("rk_", "live_51AbCdEf***WxYz"),
        "bad token github" + "_pat_11ABCDEFG0abcdefghij",
        "secret whsec" + "_abc123DEF456ghi789",
    ],
)
def test_redact_hides_a_credential_an_upstream_service_quoted_back(message: str) -> None:
    result = _bash(f'printf "%s" {message!r} | redact')
    assert "[redacted]" in result.stdout
    tail = message.split(" ")[-1]
    assert tail not in result.stdout
    # The sentence around it survives, so the diagnostic is still useful.
    assert result.stdout.split()[0] == message.split()[0]


def test_stripe_error_redacts_before_printing() -> None:
    body = json.dumps(
        {"error": {"message": "Invalid API Key provided: " + _shaped("sk_", "test_51AbCd***WxYz")}}
    )
    result = _bash(f"STRIPE_BODY={body!r}; stripe_error")
    assert "[redacted]" in result.stdout
    assert "51AbCd" not in result.stdout


def test_stripe_error_says_something_when_the_body_is_not_json() -> None:
    result = _bash("STRIPE_BODY='<html>502</html>'; stripe_error")
    assert "no readable error body" in result.stdout


def test_the_key_never_reaches_curls_argv(tmp_path: Path) -> None:
    """The key goes to curl through a config file on a pipe, not on the command
    line, so it is not readable in `ps` while the request is in flight. This
    replaces curl with a shim that records exactly what argv it was handed."""
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    argv_out = tmp_path / "argv.txt"
    shim = shim_dir / "curl"
    shim.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'printf "%s\\n" "$@" > "$CURL_ARGV_OUT"',
                "printf '{\"data\":[]}\\n200\\n'",
                "",
            ]
        ),
        encoding="utf-8",
    )
    shim.chmod(0o755)
    key = _shaped("sk_", "test_51ArgvProbeNotARealKey000000000000")
    result = _bash(
        f'set +e; export CURL_ARGV_OUT="{argv_out}"; PATH="{shim_dir}:$PATH";'
        f" stripe_api '{key}' GET /v1/products >/dev/null 2>&1"
    )
    assert argv_out.exists(), result.stderr
    argv = argv_out.read_text(encoding="utf-8")
    assert key not in argv
    assert "--config" in argv
    # The config arrives on a file descriptor, which is the whole point.
    assert "/dev/fd/" in argv


def test_no_failure_handler_hangs_off_a_pipeline_it_cannot_see() -> None:
    """`cmd | jq | sed || handler` never runs the handler: a pipeline's exit
    status is its last command's, and sed succeeds at printing nothing however
    badly cmd failed. That is this repo's own recurring bug class, so the shape
    is banned rather than reviewed."""
    # `|| true` is not a handler; it deliberately discards a status nobody
    # reads. What is banned is a real recovery hanging off a pipeline's tail.
    handlers = ("|| {", "|| return", "|| bad", "|| die", "|| printf")
    for number, line in enumerate(SCRIPT.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or "| sed" not in stripped:
            continue
        for handler in handlers:
            assert handler not in stripped, f"{number}: {stripped}"


def test_show_json_falls_back_to_raw_text() -> None:
    assert "not json at all" in _bash("show_json 'not json at all'").stdout
    assert '"ok"' in _bash("""show_json '{"ok":true}'""").stdout


def test_show_json_redacts() -> None:
    body = json.dumps({"error": _shaped("sk_", "test_51AbCdEfGhIjKlMnOp")})
    out = _bash(f"show_json {body!r}").stdout
    assert "[redacted]" in out
    assert "51AbCdEf" not in out
