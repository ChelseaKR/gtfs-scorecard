#!/usr/bin/env bash
# Run the program report bundle's test-mode walkthrough as one command.
#
# This is Phase A of gtfs-bundle-launch/HUMAN-STEPS.md and steps 1 to 6 of the
# runbook in docs/program-plan.md, automated. Everything here is Stripe *test*
# mode: no money moves, and the script refuses a live key outright.
#
# Two things it deliberately will not do, because they are the owner's call:
# create the two dashboard-only credentials (the restricted key and the GitHub
# PAT), and push the one-line commit to `main` that points the public setup
# form at the deployed API. The `config-js` phase writes that edit and prints
# the commands; it never pushes.
#
# SECRETS. Nothing here asks for, stores, logs, or prints a key. The three
# credentials are read from the environment the owner exports in their own
# shell, passed to curl through a config file on a pipe (never argv, so they
# are not in `ps`), and the only place one lands on disk is
# infra/program-bundle/terraform.tfvars, which is gitignored and written 0600.
# Every diagnostic that names a credential prints at most four characters of
# it. If a phase seems to want a key you do not have, it is a phase you cannot
# run yet; that is the design, not a gap.
#
# Usage:
#   scripts/bundle-testmode.sh --dry-run        every read-only check, no writes
#   scripts/bundle-testmode.sh                  the whole walkthrough
#   scripts/bundle-testmode.sh --only webhook   one phase
#   scripts/bundle-testmode.sh --from open-gate resume after a failure
#   scripts/bundle-testmode.sh --list-phases
#
# Environment (export these yourself; see HUMAN-STEPS.md Phase A):
#   STRIPE_SECRET_KEY       sk_test_...  full test key, stays on this machine
#   STRIPE_RESTRICTED_KEY   rk_test_...  Checkout Sessions: Read; deployed
#   BUNDLE_GITHUB_PAT       github_pat_. Actions: Read and write; deployed
#   BUNDLE_DELIVER_TO       where the test archive's download link is emailed
#   STRIPE_WEBHOOK_SECRET   whsec_...    only when reusing an endpoint (below)
#   BUNDLE_ARTIFACTS_BUCKET default gtfs-scorecard-artifacts-ckr
#   BUNDLE_SITE             default https://gtfsscorecard.org
#
# State lives in ~/.gtfs-bundle-testmode/state.json (0600, outside the repo),
# so a re-run reuses the Stripe objects a previous run created rather than
# making a second set. scripts/stripe-setup.sh is not idempotent; this is what
# stands between one run and four duplicate Payment Links.
#
# Sourcing this file defines its functions and runs nothing, which is how
# pipeline/tests/test_bundle_testmode_script.py exercises the pure logic
# (phase selection, masking, the destroy guard) with no credentials.

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PHASES=(
  preflight
  stripe-objects
  build
  apply-closed
  artifacts-lifecycle
  webhook
  actions-var
  config-js
  open-gate
  purchase
  verify-fulfilment
  verify-cap
  teardown-notes
)

STRIPE_API="https://api.stripe.com"
BUNDLE_PRODUCT_NAME="GTFS Scorecard board reports, program bundle"
REFRESH_PRODUCT_NAME="GTFS Scorecard board reports, monthly refresh"
PLAN_KEYS=(bundle_25 bundle_100 refresh_mo refresh_yr)
WEBHOOK_EVENTS=(
  checkout.session.completed
  customer.subscription.created
  customer.subscription.updated
  customer.subscription.deleted
)
# The agency ids the walkthrough buys reports for. The third is deliberately
# not a tracked id: the manifest must name it with a reason rather than drop it.
TEST_AGENCY_IDS="unitrans, yolobus, not-a-real-agency"
TEST_PROGRAM_NAME="Test-mode walkthrough"
TEST_ACCENT="#2c5f70"
# Stripe's documented test card. Test mode only; it cannot move money.
TEST_CARD="4242424242424242"

STATE_DIR="${HOME}/.gtfs-bundle-testmode"
STATE_FILE="${STATE_DIR}/state.json"

DRY_RUN=0
ONLY_PHASE=""
FROM_PHASE=""
CURRENT_PHASE="(startup)"
ASSERT_PASS=0
ASSERT_FAIL=0
FAILURES=()
ENV_PROBLEMS=0
STRIPE_BODY=""
STRIPE_HTTP=""

REPO_ROOT=""
TFVARS=""
ARTIFACTS_BUCKET="${BUNDLE_ARTIFACTS_BUCKET:-gtfs-scorecard-artifacts-ckr}"
SITE="${BUNDLE_SITE:-https://gtfsscorecard.org}"
GH_REPO="ChelseaKR/gtfs-scorecard"

# ---------------------------------------------------------------------------
# Output, assertions, masking
# ---------------------------------------------------------------------------

say()  { printf '%s\n' "$*"; }
note() { printf '        %s\n' "$*"; }

banner() {
  printf '\n== %s %s\n' "$1" "$(printf '%.0s-' $(seq 1 $((66 - ${#1}))))"
}

ok() {
  ASSERT_PASS=$((ASSERT_PASS + 1))
  printf '  PASS  %s\n' "$*"
}

bad() {
  ASSERT_FAIL=$((ASSERT_FAIL + 1))
  FAILURES+=("${CURRENT_PHASE}: $*")
  printf '  FAIL  %s\n' "$*"
}

# Print at most four characters of a secret, then an ellipsis. Four is short
# enough that nothing key-shaped survives, and long enough to tell an
# accidentally-pasted wrong value from a blank one.
mask() {
  local value="${1:-}"
  if [ -z "$value" ]; then
    printf '(unset)'
  else
    printf '%.4s…(%d chars)' "$value" "${#value}"
  fi
}

# True when $1 starts with $2. Reported as a yes/no; the value is never shown.
has_prefix() {
  case "${1:-}" in
    "${2}"*) return 0 ;;
    *) return 1 ;;
  esac
}

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    ok "${label}: ${actual}"
  else
    bad "${label}: expected '${expected}', got '${actual}'"
  fi
}

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  case "$haystack" in
    *"$needle"*) ok "${label}: found '${needle}'" ;;
    *) bad "${label}: '${needle}' is not in the output" ;;
  esac
}

assert_not_contains() {
  local label="$1" needle="$2" haystack="$3"
  case "$haystack" in
    *"$needle"*) bad "${label}: '${needle}' should not be in the output" ;;
    *) ok "${label}: '${needle}' absent, as expected" ;;
  esac
}

# Run a command and judge it on BOTH its status and its output. This repo has
# been bitten by gates that exit 0 while printing a failure, so an exit code on
# its own is never the verdict when there is output to read.
run_checked() {
  local label="$1" expect="$2"
  shift 2
  local out status=0
  out="$("$@" 2>&1)" || status=$?
  if [ "$status" -ne 0 ]; then
    bad "${label}: exited ${status}"
    printf '%s\n' "$out" | redact | sed 's/^/        | /'
    return 1
  fi
  case "$out" in
    *"$expect"*) ok "${label}: exited 0 and printed '${expect}'" ;;
    *)
      bad "${label}: exited 0 but did not print '${expect}'"
      printf '%s\n' "$out" | redact | sed 's/^/        | /'
      return 1
      ;;
  esac
  printf '%s\n' "$out" | redact | sed 's/^/        | /'
}

would() { printf '  WOULD %s\n' "$*"; }

# Print a JSON blob indented, or the raw text when it is not JSON.
#
# Take it as a rule that a pipeline's exit status is its LAST command's. So
# `cmd | jq | sed || handler` never runs the handler, however badly cmd failed,
# because sed succeeded at printing nothing. Anything whose success matters is
# captured first and judged on its own, then printed.
show_json() {
  if printf '%s' "$1" | jq . >/dev/null 2>&1; then
    printf '%s' "$1" | jq . | redact | sed 's/^/        | /'
  else
    printf '%s\n' "$1" | redact | sed 's/^/        | /'
  fi
}

die() {
  printf 'bundle-testmode: %s\n' "$*" >&2
  exit 2
}

# ---------------------------------------------------------------------------
# Phase selection (pure; unit-tested)
# ---------------------------------------------------------------------------

phase_index() {
  local want="$1" i=0 phase
  for phase in "${PHASES[@]}"; do
    if [ "$phase" = "$want" ]; then
      printf '%s' "$i"
      return 0
    fi
    i=$((i + 1))
  done
  return 1
}

# resolve_phases <only> <from> -> one phase name per line.
# --only wins over --from; an unknown name is an error, never an empty run.
resolve_phases() {
  local only="${1:-}" from="${2:-}" start=0 i=0 phase
  if [ -n "$only" ]; then
    if ! phase_index "$only" >/dev/null; then
      printf 'unknown phase: %s\n' "$only" >&2
      return 2
    fi
    printf '%s\n' "$only"
    return 0
  fi
  if [ -n "$from" ]; then
    if ! start="$(phase_index "$from")"; then
      printf 'unknown phase: %s\n' "$from" >&2
      return 2
    fi
  fi
  for phase in "${PHASES[@]}"; do
    if [ "$i" -ge "$start" ]; then
      printf '%s\n' "$phase"
    fi
    i=$((i + 1))
  done
}

# ---------------------------------------------------------------------------
# Terraform plan guard (pure; unit-tested)
# ---------------------------------------------------------------------------

# plan_has_destroy <plan.json> -> 0 when the plan deletes anything.
# `terraform show -json` spells a replacement as ["delete","create"] (or
# ["create","delete"] for create_before_destroy), so this looks for the action
# anywhere in the list rather than comparing the list to ["delete"].
plan_has_destroy() {
  local plan_json="$1" count
  count="$(jq '[.resource_changes // [] | .[]
                | select(any(.change.actions[]?; . == "delete"))] | length' "$plan_json")"
  [ "$count" -gt 0 ]
}

plan_destroy_list() {
  jq -r '.resource_changes // [] | .[]
         | select(any(.change.actions[]?; . == "delete"))
         | "  - \(.address) [\(.change.actions | join(","))]"' "$1"
}

plan_counts() {
  jq -r '[.resource_changes // [] | .[] | .change.actions] as $a
         | "add=\($a | map(select(index("create")) | select(index("delete") | not)) | length)"
         + " change=\($a | map(select(index("update"))) | length)"
         + " destroy=\($a | map(select(index("delete"))) | length)"' "$1"
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

state_init() {
  mkdir -p "$STATE_DIR"
  chmod 700 "$STATE_DIR"
  if [ ! -f "$STATE_FILE" ]; then
    ( umask 077; printf '{"schema":"1","mode":"test"}\n' > "$STATE_FILE" )
  fi
  chmod 600 "$STATE_FILE"
}

state_get() {
  [ -f "$STATE_FILE" ] || return 0
  jq -r "${1} // empty" "$STATE_FILE"
}

state_set() {
  local path="$1" value="$2" tmp
  if [ "$DRY_RUN" -eq 1 ]; then
    would "record ${path} = ${value} in ${STATE_FILE}"
    return 0
  fi
  state_init
  tmp="$(mktemp "${STATE_DIR}/state.XXXXXX")"
  chmod 600 "$tmp"
  jq --arg v "$value" "${path} = \$v" "$STATE_FILE" > "$tmp"
  mv "$tmp" "$STATE_FILE"
  chmod 600 "$STATE_FILE"
}

# ---------------------------------------------------------------------------
# Stripe REST helper
#
# The key reaches curl through a config file on a pipe, so it is never in argv
# and never visible in `ps`. Body and status land in STRIPE_BODY/STRIPE_HTTP.
# ---------------------------------------------------------------------------

stripe_api() {
  local key="$1" method="$2" path="$3"
  shift 3
  local out status=0
  out="$(curl --silent --show-error --max-time 30 --write-out $'\n%{http_code}' \
    --config <(printf 'url = "%s%s"\nrequest = "%s"\nheader = "Authorization: Bearer %s"\n' \
      "$STRIPE_API" "$path" "$method" "$key") \
    "$@" 2>&1)" || status=$?
  if [ "$status" -ne 0 ]; then
    STRIPE_BODY="curl failed with status ${status}"
    STRIPE_HTTP="000"
    return 1
  fi
  STRIPE_HTTP="${out##*$'\n'}"
  STRIPE_BODY="${out%$'\n'*}"
  case "$STRIPE_HTTP" in
    2*) return 0 ;;
    *) return 1 ;;
  esac
}

# Upstream messages are not ours and may quote a credential back at us. Stripe's
# "Invalid API Key provided" body echoes the key with only its middle starred
# out, which shows far more of it than this script's four-character rule allows.
# Everything that came from a service goes through this before it is printed.
redact() {
  sed -E \
    -e 's/(sk|rk|pk)_(test|live)_[A-Za-z0-9*_-]+/\1_\2_[redacted]/g' \
    -e 's/whsec_[A-Za-z0-9*_-]+/whsec_[redacted]/g' \
    -e 's/github_pat_[A-Za-z0-9*_-]+/github_pat_[redacted]/g' \
    -e 's/\bgh[pousr]_[A-Za-z0-9]{16,}/gh_[redacted]/g'
}

# Stripe error bodies name the object and the missing permission. They can also
# name the key, so the message is redacted on the way out.
stripe_error() {
  local message
  message="$(printf '%s' "$STRIPE_BODY" | jq -r '.error.message // .error.type // empty' 2>/dev/null || true)"
  if [ -z "$message" ]; then
    message="(no readable error body)"
  fi
  printf '%s' "$message" | redact
}

http_code() {
  local url="$1"
  shift
  curl --silent --show-error --output /dev/null --max-time 30 \
    --write-out '%{http_code}' "$@" "$url" 2>/dev/null || printf '000'
}

# ---------------------------------------------------------------------------
# Repo helpers
# ---------------------------------------------------------------------------

repo_root() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  printf '%s' "$here"
}

git_repo() { git -C "$REPO_ROOT" "$@"; }

tf() { terraform -chdir="$1" "${@:2}"; }

# ---------------------------------------------------------------------------
# Phase: preflight
# ---------------------------------------------------------------------------

phase_preflight() {
  local missing=0 tool path

  say "Tools"
  for tool in stripe terraform jq gh aws docker node curl unzip python3; do
    if path="$(command -v "$tool" 2>/dev/null)"; then
      ok "$(printf '%-10s %s' "$tool" "$path")"
    else
      bad "$(printf '%-10s not on PATH' "$tool")"
      missing=$((missing + 1))
    fi
  done

  say ""
  say "Repository"
  local infra_diff infra_dirty other_dirty
  infra_diff="$(git_repo diff origin/main --stat -- infra/ || true)"
  if [ -z "$infra_diff" ]; then
    ok "infra/ matches origin/main"
  else
    bad "infra/ differs from origin/main; the Lambdas deploy from what is here"
    printf '%s\n' "$infra_diff" | sed 's/^/        | /'
    missing=$((missing + 1))
  fi
  infra_dirty="$(git_repo status --porcelain -- infra/ || true)"
  if [ -z "$infra_dirty" ]; then
    ok "infra/ has no uncommitted changes"
  else
    bad "infra/ has uncommitted changes"
    printf '%s\n' "$infra_dirty" | sed 's/^/        | /'
    missing=$((missing + 1))
  fi
  other_dirty="$(git_repo status --porcelain -- . ':(exclude)infra' || true)"
  if [ -n "$other_dirty" ]; then
    note "Other uncommitted files (not a failure; the config-js phase makes one):"
    printf '%s\n' "$other_dirty" | sed 's/^/        | /'
  fi

  say ""
  say "AWS"
  local caller
  if caller="$(aws sts get-caller-identity --output json 2>&1)"; then
    ok "aws sts get-caller-identity: account $(printf '%s' "$caller" | jq -r .Account), $(printf '%s' "$caller" | jq -r .Arn)"
  else
    bad "aws sts get-caller-identity failed"
    printf '%s\n' "$caller" | sed 's/^/        | /'
    missing=$((missing + 1))
  fi

  say ""
  say "GitHub CLI"
  local gh_status
  if gh_status="$(gh auth status 2>&1)"; then
    ok "gh is authenticated ($(printf '%s' "$gh_status" | sed -n 's/.*Logged in to github.com account \([^ ]*\).*/\1/p' | head -1))"
  else
    bad "gh is not authenticated; run: gh auth login"
    missing=$((missing + 1))
  fi

  say ""
  say "Credentials (values are never printed)"
  ENV_PROBLEMS=0
  check_env_var STRIPE_SECRET_KEY sk_test_ required
  check_env_var STRIPE_RESTRICTED_KEY rk_test_ required
  check_env_var BUNDLE_GITHUB_PAT github_pat_ required
  check_env_var STRIPE_WEBHOOK_SECRET whsec_ optional
  missing=$((missing + ENV_PROBLEMS))

  if [ -n "${BUNDLE_DELIVER_TO:-}" ]; then
    ok "BUNDLE_DELIVER_TO is set (${BUNDLE_DELIVER_TO})"
  else
    bad "BUNDLE_DELIVER_TO is not set; the test archive has nowhere to be emailed"
    missing=$((missing + 1))
  fi

  say ""
  say "Settings"
  note "artifacts bucket   ${ARTIFACTS_BUCKET}"
  note "site               ${SITE}"
  note "repo               ${GH_REPO}"
  note "state              ${STATE_FILE}"
  note "tfvars             ${TFVARS}"

  if [ "$missing" -ne 0 ]; then
    say ""
    say "  ${missing} preflight problem(s). Nothing after this will run cleanly."
    return 1
  fi
  return 0
}

# check_env_var <name> <expected prefix> <required|optional>
# Adds to ENV_PROBLEMS. Never run this in a command substitution: ok() and
# bad() keep counters, and a subshell would discard them.
check_env_var() {
  local name="$1" prefix="$2" need="$3"
  local value="${!name:-}"
  if [ -z "$value" ]; then
    if [ "$need" = "required" ]; then
      bad "${name} is not set (expected a ${prefix}… value)"
      ENV_PROBLEMS=$((ENV_PROBLEMS + 1))
    else
      ok "${name} is not set (optional; only needed to reuse an existing webhook endpoint)"
    fi
    return 0
  fi
  # A live key in test mode is the one mistake that can move real money.
  if has_prefix "$value" "sk_live_" || has_prefix "$value" "rk_live_"; then
    bad "${name} is a LIVE Stripe key ($(mask "$value")). This script is test mode only. Refusing."
    ENV_PROBLEMS=$((ENV_PROBLEMS + 1))
    return 0
  fi
  if has_prefix "$value" "$prefix"; then
    ok "${name} is set, starts with ${prefix} ($(mask "$value"))"
  else
    bad "${name} is set but does not start with ${prefix} ($(mask "$value"))"
    ENV_PROBLEMS=$((ENV_PROBLEMS + 1))
  fi
}

# ---------------------------------------------------------------------------
# Phase: stripe-objects
# ---------------------------------------------------------------------------

# state_is_complete: 0 when the state file already records both products, all
# four prices and all four Payment Links. A complete state is the strongest
# possible "do not create anything": stripe-setup.sh is not idempotent, so the
# cost of creating a second set is four Payment Links to archive by hand.
state_is_complete() {
  [ -f "$STATE_FILE" ] || return 1
  local plan
  [ -n "$(state_get '.products.bundle')" ] || return 1
  [ -n "$(state_get '.products.refresh')" ] || return 1
  for plan in "${PLAN_KEYS[@]}"; do
    [ -n "$(state_get ".prices.${plan}")" ] || return 1
    [ -n "$(state_get ".links.${plan}")" ] || return 1
  done
  return 0
}

# stripe_objects_action <state-complete 0|1> <bundle products> <refresh products>
# The whole idempotency decision, with no network in it, so it can be tested.
#   reuse-state  the state file already has everything; touch nothing
#   reuse        one of each product on the account; skip creation, re-read ids
#   create       the account is empty of them; run stripe-setup.sh once
#   duplicates   more than one of a product; a second run already happened
#   partial      exactly one of the two products; re-running would duplicate it
stripe_objects_action() {
  local state_complete="$1" bundle_n="$2" refresh_n="$3"
  if [ "$state_complete" = "1" ]; then printf 'reuse-state'; return 0; fi
  if [ "$bundle_n" -gt 1 ] || [ "$refresh_n" -gt 1 ]; then printf 'duplicates'; return 0; fi
  if [ "$bundle_n" -eq 0 ] && [ "$refresh_n" -eq 0 ]; then printf 'create'; return 0; fi
  if [ "$bundle_n" -eq 1 ] && [ "$refresh_n" -eq 1 ]; then printf 'reuse'; return 0; fi
  printf 'partial'
}

# Find every active product whose name matches exactly, into STRIPE_PRODUCT_IDS
# (one id a line). A global rather than stdout, because a command substitution
# is a subshell and STRIPE_HTTP set inside one would not survive: the caller has
# to be able to tell "no such product" from "the account could not be read".
STRIPE_PRODUCT_IDS=""
stripe_products_named() {
  local key="$1" name="$2"
  STRIPE_PRODUCT_IDS=""
  stripe_api "$key" GET "/v1/products?active=true&limit=100" >/dev/null || return 1
  STRIPE_PRODUCT_IDS="$(printf '%s' "$STRIPE_BODY" \
    | jq -r --arg n "$name" '.data[] | select(.name == $n) | .id')"
  return 0
}

STRIPE_PRICES_JSON=""
stripe_prices_for() {
  local key="$1" product="$2"
  STRIPE_PRICES_JSON=""
  stripe_api "$key" GET "/v1/prices?product=${product}&active=true&limit=100" >/dev/null || return 1
  STRIPE_PRICES_JSON="$STRIPE_BODY"
  return 0
}

# Read both product names, or refuse. An account that cannot be read is not an
# empty account, and the difference is four Payment Links.
read_products() {
  local key="$1"
  if ! stripe_products_named "$key" "$BUNDLE_PRODUCT_NAME"; then
    bad "could not list Stripe products (HTTP ${STRIPE_HTTP}): $(stripe_error)"
    note "Nothing was created. An account that cannot be read is not an empty"
    note "account, and this phase will not treat it as one."
    return 1
  fi
  READ_BUNDLE_IDS="$STRIPE_PRODUCT_IDS"
  if ! stripe_products_named "$key" "$REFRESH_PRODUCT_NAME"; then
    bad "could not list Stripe products (HTTP ${STRIPE_HTTP}): $(stripe_error)"
    return 1
  fi
  READ_REFRESH_IDS="$STRIPE_PRODUCT_IDS"
  return 0
}
READ_BUNDLE_IDS=""
READ_REFRESH_IDS=""

phase_stripe_objects() {
  local key="${STRIPE_SECRET_KEY:-}"
  [ -n "$key" ] || { bad "STRIPE_SECRET_KEY is not set"; return 1; }

  say "Looking for objects scripts/stripe-setup.sh already created."
  say "(That script is not idempotent: a second run makes a second set.)"
  say ""

  local state_complete=0
  if state_is_complete; then
    state_complete=1
    ok "${STATE_FILE} already records 2 products, 4 prices and 4 Payment Links"
    local plan
    for plan in "${PLAN_KEYS[@]}"; do
      note "$(printf '%-11s %s  %s' "$plan" "$(state_get ".prices.${plan}")" "$(state_get ".links.${plan}")")"
    done
    note "Nothing will be created. Delete ${STATE_FILE} only if you have also"
    note "archived those objects in the dashboard."
    return 0
  fi

  local bundle_ids refresh_ids bundle_id refresh_id action
  read_products "$key" || return 1
  bundle_ids="$READ_BUNDLE_IDS"
  refresh_ids="$READ_REFRESH_IDS"

  local bundle_n refresh_n
  bundle_n="$(printf '%s' "$bundle_ids" | grep -c . || true)"
  refresh_n="$(printf '%s' "$refresh_ids" | grep -c . || true)"

  action="$(stripe_objects_action "$state_complete" "$bundle_n" "$refresh_n")"
  note "decision: ${action}"

  if [ "$action" = "duplicates" ]; then
    bad "duplicate products on this account (bundle: ${bundle_n}, refresh: ${refresh_n})"
    note "stripe-setup.sh has run more than once. Archive the extras in the"
    note "dashboard (Product catalog) until one of each remains, then re-run."
    printf '%s\n%s\n' "$bundle_ids" "$refresh_ids" | sed '/^$/d;s/^/        | /'
    return 1
  fi

  if [ "$action" = "create" ]; then
    say "Nothing on the account yet."
    if [ "$DRY_RUN" -eq 1 ]; then
      would "run scripts/stripe-setup.sh once, creating 2 products, 4 prices, 4 Payment Links"
      would "save the price ids and link URLs to ${STATE_FILE}"
      return 0
    fi
    local log
    log="${STATE_DIR}/stripe-setup-test-$(date -u +%Y%m%dT%H%M%SZ).txt"
    say "Running scripts/stripe-setup.sh (once). Output: ${log}"
    ( umask 077
      STRIPE_SECRET_KEY="$key" "${REPO_ROOT}/scripts/stripe-setup.sh" --site "$SITE" > "$log" 2>&1 )
    ok "scripts/stripe-setup.sh completed; its output is saved 0600 outside the repo"
    note "Re-reading the account rather than parsing that output, so what the"
    note "state file records is what Stripe actually holds."
    read_products "$key" || return 1
    bundle_ids="$READ_BUNDLE_IDS"
    refresh_ids="$READ_REFRESH_IDS"
  elif [ "$action" = "reuse" ]; then
    ok "both products already exist; skipping creation"
  else
    bad "exactly one of the two products exists (bundle: ${bundle_n}, refresh: ${refresh_n})"
    note "A half-finished run. Re-running stripe-setup.sh would duplicate the"
    note "one that is already there. Archive it in the dashboard and re-run this"
    note "phase, or create the missing prices by hand."
    return 1
  fi

  bundle_id="$(printf '%s' "$bundle_ids" | head -1)"
  refresh_id="$(printf '%s' "$refresh_ids" | head -1)"
  if [ -z "$bundle_id" ] || [ -z "$refresh_id" ]; then
    bad "products still missing after setup"
    return 1
  fi
  ok "bundle product  ${bundle_id}"
  ok "refresh product ${refresh_id}"
  state_set '.products.bundle' "$bundle_id"
  state_set '.products.refresh' "$refresh_id"

  # Prices, matched on the nicknames stripe-setup.sh gives them.
  local prices_json plan price_id count
  stripe_prices_for "$key" "$bundle_id" || { bad "could not list prices: $(stripe_error)"; return 1; }
  prices_json="$STRIPE_PRICES_JSON"
  stripe_prices_for "$key" "$refresh_id" || { bad "could not list prices: $(stripe_error)"; return 1; }
  prices_json="${prices_json}"$'\n'"$STRIPE_PRICES_JSON"
  for plan in "${PLAN_KEYS[@]}"; do
    count="$(printf '%s' "$prices_json" | jq -r --arg n "$plan" '.data[] | select(.nickname == $n) | .id' | grep -c . || true)"
    price_id="$(printf '%s' "$prices_json" | jq -r --arg n "$plan" '.data[] | select(.nickname == $n) | .id' | head -1)"
    if [ "$count" -eq 1 ]; then
      ok "price ${plan} = ${price_id}"
      state_set ".prices.${plan}" "$price_id"
    elif [ "$count" -eq 0 ]; then
      bad "no active price nicknamed ${plan}"
    else
      bad "${count} active prices nicknamed ${plan}; archive the extras"
    fi
  done

  # Payment Links, matched by the price each one sells.
  stripe_api "$key" GET "/v1/payment_links?active=true&limit=100" >/dev/null || {
    bad "could not list Payment Links: $(stripe_error)"
    return 1
  }
  local links_json link_ids link_id items url
  links_json="$STRIPE_BODY"
  link_ids="$(printf '%s' "$links_json" | jq -r '.data[].id')"
  for plan in "${PLAN_KEYS[@]}"; do
    price_id="$(state_get ".prices.${plan}")"
    [ -n "$price_id" ] || continue
    url=""
    for link_id in $link_ids; do
      stripe_api "$key" GET "/v1/payment_links/${link_id}/line_items?limit=10" >/dev/null || continue
      items="$(printf '%s' "$STRIPE_BODY" | jq -r '.data[].price.id')"
      if [ "$items" = "$price_id" ]; then
        url="$(printf '%s' "$links_json" | jq -r --arg id "$link_id" '.data[] | select(.id == $id) | .url')"
        break
      fi
    done
    if [ -n "$url" ]; then
      ok "payment link ${plan} = ${url}"
      state_set ".links.${plan}" "$url"
    else
      bad "no active Payment Link sells price ${price_id} (${plan})"
    fi
  done

  # The redirect is what carries the session id to the setup form.
  local redirects
  redirects="$(printf '%s' "$links_json" | jq -r '.data[].after_completion.redirect.url // empty' | sort -u)"
  assert_contains "Payment Link redirect" "${SITE}/bundle/setup/?session_id={CHECKOUT_SESSION_ID}" "$redirects"
  return 0
}

# ---------------------------------------------------------------------------
# Phase: build
# ---------------------------------------------------------------------------

phase_build() {
  if [ "$DRY_RUN" -eq 1 ]; then
    would "run scripts/build-lambda-package.sh infra/program-bundle"
    would "assert every compiled file in the package is a Linux/ELF binary"
    return 0
  fi
  local out status=0
  out="$(cd "$REPO_ROOT" && ./scripts/build-lambda-package.sh infra/program-bundle 2>&1)" || status=$?
  printf '%s\n' "$out" | sed 's/^/        | /'
  if [ "$status" -ne 0 ]; then
    bad "build-lambda-package.sh exited ${status}"
    return 1
  fi
  assert_contains "ELF check" "all Linux/ELF" "$out"

  # The script's own message reads "ok — 0 compiled file(s), all Linux/ELF" if
  # pip vendored no extensions at all, which would pass a check that only
  # looks for that phrase. Count them.
  local so_count
  so_count="$(printf '%s' "$out" | sed -n 's/.*ok — \([0-9]*\) compiled file(s).*/\1/p' | head -1)"
  if [ -n "$so_count" ] && [ "$so_count" -ge 1 ]; then
    ok "package holds ${so_count} compiled file(s), so the ELF check had something to judge"
  else
    bad "package holds no compiled files; the ELF check passed on an empty set"
  fi

  local zipdir="${REPO_ROOT}/infra/program-bundle/build"
  for f in common.py setup_handler.py webhook_handler.py refresh_handler.py; do
    if [ -f "${zipdir}/${f}" ]; then
      ok "packaged ${f}"
    else
      bad "missing ${f} from the package"
    fi
  done
  if [ -d "${zipdir}/scorecard_pipeline" ]; then
    ok "packaged scorecard_pipeline (parse_request is the pipeline's own)"
  else
    bad "scorecard_pipeline is not in the package"
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Phase: apply-closed
# ---------------------------------------------------------------------------

write_tfvars() {
  local payments="$1" webhook_secret_line="${2:-}"
  local p25 p100 pmo pyr
  p25="$(state_get '.prices.bundle_25')"
  p100="$(state_get '.prices.bundle_100')"
  pmo="$(state_get '.prices.refresh_mo')"
  pyr="$(state_get '.prices.refresh_yr')"
  if [ -z "$p25" ] || [ -z "$p100" ] || [ -z "$pmo" ] || [ -z "$pyr" ]; then
    bad "price ids are not in ${STATE_FILE}; run the stripe-objects phase first"
    return 1
  fi
  ( umask 077
    {
      printf '# Written by scripts/bundle-testmode.sh. Gitignored (.gitignore: *.tfvars).\n'
      printf '# Mode 0600. This is the one place a credential lands on disk.\n'
      printf 'github_token      = "%s"\n' "${BUNDLE_GITHUB_PAT}"
      printf 'artifacts_bucket  = "%s"\n' "$ARTIFACTS_BUCKET"
      printf 'stripe_secret_key = "%s"\n' "${STRIPE_RESTRICTED_KEY}"
      printf 'payments_enabled  = "%s"\n' "$payments"
      if [ -n "$webhook_secret_line" ]; then
        printf '%s\n' "$webhook_secret_line"
      fi
      printf 'stripe_price_ids = {\n'
      printf '  bundle_25  = "%s"\n' "$p25"
      printf '  bundle_100 = "%s"\n' "$p100"
      printf '  refresh_mo = "%s"\n' "$pmo"
      printf '  refresh_yr = "%s"\n' "$pyr"
      printf '}\n'
      printf 'stripe_price_ids_are_live = false\n'
    } > "$TFVARS" )
  chmod 600 "$TFVARS"
  ok "wrote ${TFVARS} (mode $(stat -f '%Lp' "$TFVARS" 2>/dev/null || stat -c '%a' "$TFVARS")), payments_enabled = \"${payments}\""
  if [ -n "$webhook_secret_line" ]; then
    note "It holds the PAT, the restricted key and the webhook secret."
  else
    note "It holds the PAT and the restricted key."
  fi
  note "It is gitignored and never printed. Delete it when you are done."
}

# Keep the webhook secret line from an existing tfvars without reading its
# value into a shell variable.
existing_webhook_line() {
  [ -f "$TFVARS" ] || return 0
  grep -E '^[[:space:]]*stripe_webhook_secret[[:space:]]*=' "$TFVARS" 2>/dev/null | head -1 || true
}

terraform_plan_apply() {
  local dir="$1" label="$2" allow_destroy="$3"
  local plan_bin plan_json
  plan_bin="${STATE_DIR}/$(basename "$dir").tfplan"
  plan_json="${plan_bin}.json"

  run_checked "${label}: terraform init" "Terraform has been" \
    terraform -chdir="$dir" init -input=false -no-color || return 1

  ( umask 077
    terraform -chdir="$dir" plan -input=false -no-color -out="$plan_bin" >/dev/null ) || {
    bad "${label}: terraform plan failed"
    terraform -chdir="$dir" plan -input=false -no-color 2>&1 | tail -30 | sed 's/^/        | /'
    return 1
  }
  chmod 600 "$plan_bin"
  # A saved plan carries every variable value, secrets included; it lives 0600
  # outside the repo and is deleted as soon as it is applied.
  ( umask 077; terraform -chdir="$dir" show -json "$plan_bin" > "$plan_json" )
  chmod 600 "$plan_json"

  say "  plan: $(plan_counts "$plan_json")"
  jq -r '.resource_changes // [] | .[]
         | select(.change.actions != ["no-op"])
         | "        \(.change.actions | join("+"))  \(.address)"' "$plan_json"

  if plan_has_destroy "$plan_json"; then
    if [ "$allow_destroy" = "allow" ]; then
      ok "${label}: plan contains destroys, and this module allows them"
    else
      bad "${label}: the plan destroys something. Stopping without applying."
      plan_destroy_list "$plan_json"
      note "Read infra/README.md before going further. Nothing was applied."
      rm -f "$plan_bin" "$plan_json"
      return 1
    fi
  else
    ok "${label}: plan destroys nothing"
  fi

  run_checked "${label}: terraform apply" "Apply complete" \
    terraform -chdir="$dir" apply -input=false -no-color "$plan_bin" || {
    rm -f "$plan_bin" "$plan_json"
    return 1
  }
  rm -f "$plan_bin" "$plan_json"
  return 0
}

phase_apply_closed() {
  local dir="${REPO_ROOT}/infra/program-bundle"
  if [ "$DRY_RUN" -eq 1 ]; then
    would "write ${TFVARS} at mode 0600 with github_token, stripe_secret_key, the four price ids, payments_enabled = \"0\""
    would "terraform -chdir=infra/program-bundle init   (S3 backend, from backend.tf)"
    would "terraform plan -out, show the summary, and apply the saved plan"
    would "record api_base and webhook_url in ${STATE_FILE}"
    would "assert POST /webhook -> 400, GET /download/<32 zeroes> -> 404, POST /setup -> 404"
    # Offline: -backend=false means no S3, no state, no credentials, no plan.
    if terraform -chdir="$dir" init -backend=false -input=false -no-color >/dev/null 2>&1 \
      && terraform -chdir="$dir" validate -no-color >/dev/null 2>&1; then
      ok "terraform validate (offline: no backend, no state, no credentials)"
    else
      bad "terraform validate failed"
      terraform -chdir="$dir" validate -no-color 2>&1 | sed 's/^/        | /'
    fi
    return 0
  fi

  [ -d "${dir}/build" ] || { bad "infra/program-bundle/build is missing; run the build phase"; return 1; }
  write_tfvars "0" "$(existing_webhook_line)" || return 1
  terraform_plan_apply "$dir" "program-bundle (gate closed)" refuse || return 1

  local api webhook
  api="$(terraform -chdir="$dir" output -raw api_base)"
  webhook="$(terraform -chdir="$dir" output -raw webhook_url)"
  [ -n "$api" ] || { bad "api_base output is empty"; return 1; }
  ok "api_base    ${api}"
  ok "webhook_url ${webhook}"
  state_set '.api_base' "$api"
  state_set '.webhook_url' "$webhook"

  say ""
  say "The three closed-gate checks (HUMAN-STEPS step 4):"
  assert_eq "POST /webhook (reachable, refusing unsigned)" "400" \
    "$(http_code "${api}/webhook" -X POST -d '{}')"
  assert_eq "GET /download/<never issued>" "404" \
    "$(http_code "${api}/download/00000000000000000000000000000000")"
  assert_eq "POST /setup (route absent while the gate is closed)" "404" \
    "$(http_code "${api}/setup" -X POST -d '{}')"
  return 0
}

# ---------------------------------------------------------------------------
# Phase: artifacts-lifecycle
# ---------------------------------------------------------------------------

phase_artifacts_lifecycle() {
  local dir="${REPO_ROOT}/infra/artifacts"
  local vars="${dir}/terraform.tfvars"

  local drift
  drift="$(git_repo diff origin/main --stat -- infra/artifacts || true)"
  if [ -z "$drift" ]; then
    ok "infra/artifacts matches origin/main"
  else
    bad "infra/artifacts differs from origin/main; refusing to plan against it"
    printf '%s\n' "$drift" | sed 's/^/        | /'
    return 1
  fi

  # bucket_name has no default. Without a tfvars, `terraform plan` either
  # prompts or fails, and a wrong answer plans six destroys of the live
  # bucket. -var is never passed here, per infra/README.md; the value comes
  # from a tfvars file, written once, and checked before every plan.
  if [ -f "$vars" ]; then
    if grep -qF "\"${ARTIFACTS_BUCKET}\"" "$vars"; then
      ok "${vars} names ${ARTIFACTS_BUCKET}"
    else
      bad "${vars} exists but does not name ${ARTIFACTS_BUCKET}. Refusing."
      note "A wrong bucket name here plans six destroys of the live bucket."
      return 1
    fi
  elif [ "$DRY_RUN" -eq 1 ]; then
    would "create ${vars} from terraform.tfvars.example with bucket_name = \"${ARTIFACTS_BUCKET}\""
  else
    say "  ${vars} does not exist; writing it from terraform.tfvars.example."
    {
      printf '# Written by scripts/bundle-testmode.sh from terraform.tfvars.example.\n'
      printf 'bucket_name = "%s"\n' "$ARTIFACTS_BUCKET"
      printf 'project     = "gtfs-scorecard"\n'
      printf 'region      = "us-west-2"\n'
      printf 'github_repo = "%s"\n' "$GH_REPO"
    } > "$vars"
    ok "wrote ${vars} (no secrets; gitignored)"
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    would "terraform -chdir=infra/artifacts init && plan -out (never -var)"
    would "abort without applying if the plan deletes ANYTHING"
    would "apply, then assert the expire-program-bundles rule has Expiration.Days == 30"
    return 0
  fi

  terraform_plan_apply "$dir" "artifacts" refuse || return 1

  local rule
  rule="$(aws s3api get-bucket-lifecycle-configuration --bucket "$ARTIFACTS_BUCKET" 2>&1 \
    | jq -r '.Rules[]? | select(.ID == "expire-program-bundles")' || true)"
  if [ -z "$rule" ]; then
    bad "no expire-program-bundles rule on ${ARTIFACTS_BUCKET}"
    return 1
  fi
  assert_eq "lifecycle expire-program-bundles Expiration.Days" "30" \
    "$(printf '%s' "$rule" | jq -r '.Expiration.Days')"
  assert_eq "lifecycle expire-program-bundles Status" "Enabled" \
    "$(printf '%s' "$rule" | jq -r '.Status')"
  assert_eq "lifecycle expire-program-bundles prefix" "program-bundles/" \
    "$(printf '%s' "$rule" | jq -r '.Filter.Prefix // .Prefix')"
  return 0
}

# ---------------------------------------------------------------------------
# Phase: webhook
# ---------------------------------------------------------------------------

phase_webhook() {
  local key="${STRIPE_SECRET_KEY:-}" webhook_url
  webhook_url="$(state_get '.webhook_url')"
  [ -n "$webhook_url" ] || { bad "no webhook_url in state; run apply-closed first"; return 1; }
  [ -n "$key" ] || { bad "STRIPE_SECRET_KEY is not set"; return 1; }

  stripe_api "$key" GET "/v1/webhook_endpoints?limit=100" >/dev/null || {
    bad "could not list webhook endpoints: $(stripe_error)"
    return 1
  }
  local existing
  existing="$(printf '%s' "$STRIPE_BODY" | jq -r --arg u "$webhook_url" \
    '.data[] | select(.url == $u) | .id')"

  local have_secret=0
  if [ -n "$(existing_webhook_line)" ]; then have_secret=1; fi

  if [ -n "$existing" ]; then
    ok "a webhook endpoint for that URL already exists ($(printf '%s' "$existing" | head -1)); reusing it"
    note "Stripe returns an endpoint's signing secret only when it is created,"
    note "so it cannot be re-read. This phase therefore needs either a"
    note "terraform.tfvars that already carries it, or STRIPE_WEBHOOK_SECRET."
    if [ "$have_secret" -eq 0 ] && [ -z "${STRIPE_WEBHOOK_SECRET:-}" ]; then
      bad "the endpoint exists but no signing secret is available"
      note "Either reveal it in the dashboard and export STRIPE_WEBHOOK_SECRET,"
      note "or delete the endpoint and re-run this phase to create a fresh one."
      return 1
    fi
  elif [ "$DRY_RUN" -eq 1 ]; then
    would "create a test-mode webhook endpoint at ${webhook_url}"
    would "subscribe it to: ${WEBHOOK_EVENTS[*]}"
    would "write its signing secret straight into ${TFVARS} without printing it"
    would "re-apply infra/program-bundle, then POST a signed synthetic event and read the outcome"
    return 0
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    would "re-apply infra/program-bundle with the existing signing secret"
    return 0
  fi

  local secret_line=""
  if [ -n "$existing" ]; then
    if [ -n "${STRIPE_WEBHOOK_SECRET:-}" ]; then
      secret_line="$(printf 'stripe_webhook_secret = "%s"' "${STRIPE_WEBHOOK_SECRET}")"
      state_set '.webhook_endpoint' "$(printf '%s' "$existing" | head -1)"
    else
      secret_line="$(existing_webhook_line)"
    fi
  else
    local args=()
    local event
    for event in "${WEBHOOK_EVENTS[@]}"; do
      args+=(--data-urlencode "enabled_events[]=${event}")
    done
    args+=(--data-urlencode "url=${webhook_url}")
    args+=(--data-urlencode "description=gtfs-scorecard program bundle (test), created by scripts/bundle-testmode.sh")
    stripe_api "$key" POST "/v1/webhook_endpoints" "${args[@]}" >/dev/null || {
      bad "could not create the webhook endpoint: $(stripe_error)"
      return 1
    }
    local endpoint_id
    endpoint_id="$(printf '%s' "$STRIPE_BODY" | jq -r '.id')"
    ok "created webhook endpoint ${endpoint_id} with ${#WEBHOOK_EVENTS[@]} events"
    state_set '.webhook_endpoint' "$endpoint_id"
    # The secret goes from the response into the tfvars line without passing
    # through anything that prints.
    secret_line="$(printf '%s' "$STRIPE_BODY" \
      | jq -r 'if (.secret // "") == "" then "" else "stripe_webhook_secret = \"" + .secret + "\"" end')"
    if [ -z "$secret_line" ]; then
      bad "Stripe created the endpoint but returned no signing secret"
      return 1
    fi
    ok "captured the signing secret into the tfvars line (never printed)"
  fi

  write_tfvars "$(current_payments_enabled)" "$secret_line" || return 1
  terraform_plan_apply "${REPO_ROOT}/infra/program-bundle" "program-bundle (webhook secret)" refuse || return 1

  say ""
  say "Proving the deployed Lambda holds that secret, with a signed synthetic event."
  local result
  result="$(send_signed_test_event "$webhook_url")" || true
  printf '%s\n' "$result" | sed 's/^/        | /'
  local code body outcome
  code="$(printf '%s' "$result" | sed -n '1p')"
  body="$(printf '%s' "$result" | sed -n '2p')"
  outcome="$(printf '%s' "$body" | jq -r '.outcome // ""' 2>/dev/null || printf '')"
  assert_eq "signed checkout.session.completed" "200" "$code"
  assert_eq "body .ok" "true" "$(printf '%s' "$body" | jq -r '.ok // ""' 2>/dev/null || printf '')"

  # What the outcome means, which the runbook had backwards. The synthetic
  # session id does not exist in Stripe, so a working restricted key gets a
  # 404 on its line items and the handler answers "ignored". "noted" here
  # means the line-items read did NOT return 404, which on a fabricated id
  # means the key could not read it at all (403) -- exactly the failure the
  # runbook told you to look for a green light for.
  case "$outcome" in
    ignored)
      ok "outcome 'ignored': the restricted key read the line items and Stripe said 404"
      ;;
    noted)
      bad "outcome 'noted' on a fabricated session id: the line-items read did not 404"
      note "That is what a restricted key without Checkout Sessions: Read looks like."
      note "Check the key's permissions before any real purchase; every buyer would"
      note "otherwise see 'Could not confirm the payment yet.'"
      ;;
    *)
      bad "unexpected outcome '${outcome}'"
      ;;
  esac

  assert_eq "unsigned POST /webhook still refused" "400" \
    "$(http_code "$webhook_url" -X POST -d '{}')"
  return 0
}

current_payments_enabled() {
  if [ -f "$TFVARS" ]; then
    local value
    value="$(sed -n 's/^[[:space:]]*payments_enabled[[:space:]]*=[[:space:]]*"\([01]\)".*/\1/p' "$TFVARS" | head -1)"
    printf '%s' "${value:-0}"
  else
    printf '0'
  fi
}

# Sign a synthetic event with the secret read straight out of terraform.tfvars
# and POST it. The secret is read inside python, never into a shell variable,
# never into argv, never printed. Prints two lines: status, then body.
send_signed_test_event() {
  local url="$1"
  python3 - "$TFVARS" "$url" <<'PY'
import hashlib, hmac, json, re, sys, time, urllib.error, urllib.request

tfvars, url = sys.argv[1], sys.argv[2]
secret = ""
try:
    with open(tfvars, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r'\s*stripe_webhook_secret\s*=\s*"([^"]*)"', line)
            if m:
                secret = m.group(1)
except OSError as err:
    print("000"); print(json.dumps({"error": f"cannot read tfvars: {err.strerror}"})); raise SystemExit(0)
if not secret:
    print("000"); print(json.dumps({"error": "no stripe_webhook_secret in tfvars"})); raise SystemExit(0)

# Shaped like Stripe's own "Send test event": a session id that is not a real
# object on the account.
payload = json.dumps({
    "id": "evt_00000000000000",
    "object": "event",
    "type": "checkout.session.completed",
    "data": {"object": {
        "id": "cs_test_00000000000000",
        "object": "checkout.session",
        "mode": "payment",
        "payment_status": "paid",
        "customer_details": {"email": "nobody@example.invalid"},
    }},
}).encode()
stamp = int(time.time())
signature = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
request = urllib.request.Request(url, data=payload, method="POST")  # noqa: S310
request.add_header("Content-Type", "application/json")
request.add_header("Stripe-Signature", f"t={stamp},v1={signature}")
try:
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        print(response.status); print(response.read().decode().strip())
except urllib.error.HTTPError as err:
    print(err.code); print(err.read().decode().strip())
except OSError as err:
    print("000"); print(json.dumps({"error": str(err)}))
PY
}

# ---------------------------------------------------------------------------
# Phase: actions-var
# ---------------------------------------------------------------------------

phase_actions_var() {
  local api
  api="$(state_get '.api_base')"
  [ -n "$api" ] || { bad "no api_base in state; run apply-closed first"; return 1; }
  if [ "$DRY_RUN" -eq 1 ]; then
    would "gh variable set BUNDLE_API_BASE --repo ${GH_REPO} --body '${api}'"
    would "read it back and assert it matches"
    local current
    current="$(gh variable list --repo "$GH_REPO" --json name,value \
      --jq '.[] | select(.name == "BUNDLE_API_BASE") | .value' 2>/dev/null || true)"
    note "BUNDLE_API_BASE today: ${current:-(not set)}"
    return 0
  fi
  gh variable set BUNDLE_API_BASE --repo "$GH_REPO" --body "$api"
  local readback
  readback="$(gh variable list --repo "$GH_REPO" --json name,value \
    --jq '.[] | select(.name == "BUNDLE_API_BASE") | .value')"
  assert_eq "BUNDLE_API_BASE reads back" "$api" "$readback"

  # report-bundle.yml sends no email unless all three are set.
  local vars
  vars="$(gh variable list --repo "$GH_REPO" --json name --jq '[.[].name] | join(" ")')"
  for name in ARTIFACTS_BUCKET AWS_REGION SES_FROM; do
    assert_contains "delivery variable ${name}" "$name" "$vars"
  done
  local secrets
  secrets="$(gh secret list --repo "$GH_REPO" --json name --jq '[.[].name] | join(" ")' 2>/dev/null || printf '')"
  assert_contains "AWS_ROLE_ARN is a repository secret" "AWS_ROLE_ARN" "$secrets"
  return 0
}

# ---------------------------------------------------------------------------
# Phase: config-js
# ---------------------------------------------------------------------------

phase_config_js() {
  local api file tmp
  api="$(state_get '.api_base')"
  file="${REPO_ROOT}/web/src/config.js"
  [ -n "$api" ] || { bad "no api_base in state; run apply-closed first"; return 1; }

  say "This one is a commit to main, and main is the public site."
  say "The script writes the edit and stops. It does not commit and does not"
  say "push: /bundle/setup/ is unlinked and noindex, but pages.yml deploys"
  say "every push to main, so this is a change to a live site and the call is"
  say "the owner's, not a script's."
  say ""

  if grep -qF "window.SCORECARD_BUNDLE_URL = \"${api}\";" "$file"; then
    ok "web/src/config.js already points at ${api}"
  elif [ "$DRY_RUN" -eq 1 ]; then
    would "rewrite the one SCORECARD_BUNDLE_URL line in web/src/config.js to \"${api}\""
    note "current: $(grep -n 'SCORECARD_BUNDLE_URL' "$file" | tail -1)"
  else
    tmp="$(mktemp)"
    sed "s|^window.SCORECARD_BUNDLE_URL = null;|window.SCORECARD_BUNDLE_URL = \"${api}\";|" "$file" > "$tmp"
    mv "$tmp" "$file"
    local changed
    changed="$(git_repo diff --numstat -- web/src/config.js | awk '{print $1"/"$2}')"
    assert_eq "exactly one line changed in web/src/config.js" "1/1" "${changed:-0/0}"
    git_repo --no-pager diff -- web/src/config.js | sed 's/^/        | /'
  fi

  say ""
  say "  Run these yourself when you are ready:"
  say ""
  say "    git -C \"${REPO_ROOT}\" switch -c chore/bundle-api-base origin/main"
  say "    git -C \"${REPO_ROOT}\" add web/src/config.js"
  say "    git -C \"${REPO_ROOT}\" commit -m 'chore(bundle): point the setup form at the program-bundle API'"
  say "    git -C \"${REPO_ROOT}\" push -u origin chore/bundle-api-base"
  say "    gh pr create --repo ${GH_REPO} --fill"
  say ""
  say "  Merge it, wait for pages.yml, then check:"
  say "    curl -s ${SITE}/src/config.js | grep SCORECARD_BUNDLE_URL"
  say ""

  local live
  live="$(curl --silent --max-time 20 "${SITE}/src/config.js" 2>/dev/null \
    | sed -n 's/^window.SCORECARD_BUNDLE_URL = "\(.*\)";$/\1/p' | head -1 || true)"
  if [ "$live" = "$api" ]; then
    ok "the deployed site already serves ${api}; the rest of the run can go on"
    return 0
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    note "The deployed site serves: ${live:-null}. A real run would stop here."
    return 0
  fi
  # Stopping here rather than carrying on and failing two phases later. Every
  # phase after this one needs the deployed form to point at the API, and the
  # thing that makes that true is a person merging the commit above.
  bad "the deployed ${SITE}/src/config.js serves ${live:-null}, not ${api}"
  note "This is your turn, not a broken run. Merge that PR, wait for pages.yml,"
  note "then re-run the same command with --from config-js; this phase will"
  note "pass and the run will carry on into open-gate by itself."
  return 1
}

# ---------------------------------------------------------------------------
# Phase: open-gate
# ---------------------------------------------------------------------------

phase_open_gate() {
  local api dir="${REPO_ROOT}/infra/program-bundle"
  api="$(state_get '.api_base')"
  [ -n "$api" ] || { bad "no api_base in state; run apply-closed first"; return 1; }
  if [ "$DRY_RUN" -eq 1 ]; then
    would "set payments_enabled = \"1\" in ${TFVARS}"
    would "plan (expect: 2 /setup routes added, the weekly rule enabled, 3 Lambdas updated)"
    would "apply, then assert OPTIONS ${api}/setup returns 204"
    return 0
  fi
  [ -f "$TFVARS" ] || { bad "${TFVARS} is missing; run apply-closed first"; return 1; }
  if [ -z "$(existing_webhook_line)" ]; then
    bad "${TFVARS} has no stripe_webhook_secret; the plan's precondition will refuse"
    note "Run the webhook phase first."
    return 1
  fi
  write_tfvars "1" "$(existing_webhook_line)" || return 1
  terraform_plan_apply "$dir" "program-bundle (gate open)" refuse || return 1
  assert_eq "OPTIONS /setup" "204" "$(http_code "${api}/setup" -X OPTIONS)"
  assert_eq "POST /setup with no body (route present, form rejected)" "400" \
    "$(http_code "${api}/setup" -X POST -H 'Content-Type: application/json' -d '{}')"
  return 0
}

# ---------------------------------------------------------------------------
# Playwright
# ---------------------------------------------------------------------------

playwright_dir() { printf '%s' "${STATE_DIR}/playwright"; }

ensure_playwright() {
  local dir
  dir="$(playwright_dir)"
  if [ -d "${REPO_ROOT}/node_modules/playwright" ]; then
    printf '%s' "$REPO_ROOT"
    return 0
  fi
  mkdir -p "$dir"
  if [ ! -f "${dir}/package.json" ]; then
    printf '{"name":"gtfs-bundle-testmode","private":true,"type":"module"}\n' > "${dir}/package.json"
  fi
  if [ ! -d "${dir}/node_modules/playwright" ]; then
    say "  Installing playwright into ${dir} (once)." >&2
    ( cd "$dir" && npm install --silent --no-audit --no-fund playwright >&2 )
    ( cd "$dir" && npx --yes playwright install chromium >&2 )
  fi
  printf '%s' "$dir"
}

# pay_session <hosted checkout url> <what it is, for the message>
# Pays one Checkout Session and nothing else. The driver's status is checked
# before its output is printed, not after a pipeline has swallowed it.
pay_session() {
  local url="$1" label="$2" paid
  if ! paid="$(run_checkout --url "$url" --email "${BUNDLE_DELIVER_TO}" --card "$TEST_CARD" \
    --artifacts "${STATE_DIR}/playwright-artifacts" --pay-only)"; then
    bad "could not pay the ${label}"
    show_json "$paid"
    return 1
  fi
  show_json "$paid"
  return 0
}

# run_checkout <mode> <url> [extra args...] -> the driver's JSON on stdout
run_checkout() {
  local base
  base="$(ensure_playwright)"
  cp "${REPO_ROOT}/scripts/bundle-testmode-checkout.mjs" "${base}/bundle-testmode-checkout.mjs"
  ( cd "$base" && node bundle-testmode-checkout.mjs "$@" )
}

# ---------------------------------------------------------------------------
# Phase: purchase
# ---------------------------------------------------------------------------

site_form_is_wired() {
  local api live
  api="$(state_get '.api_base')"
  live="$(curl --silent --max-time 20 "${SITE}/src/config.js" 2>/dev/null \
    | sed -n 's/^window.SCORECARD_BUNDLE_URL = "\(.*\)";$/\1/p' | head -1 || true)"
  [ -n "$api" ] && [ "$live" = "$api" ]
}

phase_purchase() {
  local link api
  link="$(state_get '.links.bundle_25')"
  api="$(state_get '.api_base')"
  if [ "$DRY_RUN" -eq 1 ]; then
    would "open ${link:-<the bundle_25 Payment Link>} in headless chromium"
    would "pay with Stripe's test card ${TEST_CARD}, any future expiry, any CVC, any postal code"
    would "follow the redirect to ${SITE}/bundle/setup/?session_id=cs_test_…"
    would "fill program name '${TEST_PROGRAM_NAME}', accent ${TEST_ACCENT}, ids '${TEST_AGENCY_IDS}'"
    would "submit, and record session_id and bundle_id in ${STATE_FILE}"
    if site_form_is_wired; then
      ok "the deployed setup form is wired to ${api}"
    else
      note "The deployed setup form is NOT yet wired to the API, so this phase"
      note "would stop. Merge the config-js commit and wait for pages.yml."
    fi
    return 0
  fi

  [ -n "$link" ] || { bad "no bundle_25 Payment Link in state; run stripe-objects first"; return 1; }
  [ -n "${BUNDLE_DELIVER_TO:-}" ] || { bad "BUNDLE_DELIVER_TO is not set"; return 1; }
  if ! site_form_is_wired; then
    bad "the deployed ${SITE}/src/config.js does not point at ${api}"
    note "Merge the config-js commit first, or the setup form will refuse to submit."
    return 1
  fi

  local started
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  state_set '.purchase_started_at' "$started"

  local out
  out="$(run_checkout \
    --url "$link" \
    --email "${BUNDLE_DELIVER_TO}" \
    --card "$TEST_CARD" \
    --program "$TEST_PROGRAM_NAME" \
    --accent "$TEST_ACCENT" \
    --agency-ids "$TEST_AGENCY_IDS" \
    --deliver-to "${BUNDLE_DELIVER_TO}" \
    --artifacts "${STATE_DIR}/playwright-artifacts" \
    --submit-setup)" || {
    bad "the checkout driver failed"
    printf '%s\n' "$out" | sed 's/^/        | /'
    return 1
  }
  show_json "$out"

  local session_id bundle_id status
  session_id="$(printf '%s' "$out" | jq -r '.session_id // ""' 2>/dev/null || printf '')"
  bundle_id="$(printf '%s' "$out" | jq -r '.bundle_id // ""' 2>/dev/null || printf '')"
  status="$(printf '%s' "$out" | jq -r '.setup_status // ""' 2>/dev/null || printf '')"

  case "$session_id" in
    cs_test_*) ok "session_id ${session_id}" ;;
    *) bad "no cs_test_ session id came back from the redirect" ;;
  esac
  assert_eq "POST /setup status" "200" "$status"
  if [ ${#bundle_id} -eq 32 ]; then
    ok "bundle_id ${bundle_id}"
  else
    bad "bundle_id is not 32 characters: '${bundle_id}'"
  fi
  state_set '.session_id' "$session_id"
  state_set '.bundle_id' "$bundle_id"
  return 0
}

# ---------------------------------------------------------------------------
# Phase: verify-fulfilment
# ---------------------------------------------------------------------------

bundles_table() { printf 'gtfs-scorecard-program-bundles'; }
subscriptions_table() { printf 'gtfs-scorecard-program-subscriptions'; }

wait_for_run() {
  local since="$1" deadline=$((SECONDS + 1500)) run_id="" status conclusion
  while [ "$SECONDS" -lt "$deadline" ]; do
    run_id="$(gh run list --repo "$GH_REPO" --workflow=report-bundle.yml --limit 10 \
      --json databaseId,createdAt,status,conclusion \
      --jq "[.[] | select(.createdAt >= \"${since}\")] | sort_by(.createdAt) | .[0].databaseId // empty")"
    if [ -n "$run_id" ]; then break; fi
    sleep 10
  done
  if [ -z "$run_id" ]; then
    printf 'none\n'
    return 1
  fi
  while [ "$SECONDS" -lt "$deadline" ]; do
    status="$(gh run view "$run_id" --repo "$GH_REPO" --json status --jq .status)"
    if [ "$status" = "completed" ]; then break; fi
    sleep 15
  done
  conclusion="$(gh run view "$run_id" --repo "$GH_REPO" --json conclusion --jq .conclusion)"
  printf '%s %s\n' "$run_id" "$conclusion"
}

phase_verify_fulfilment() {
  local api bundle_id session_id since
  api="$(state_get '.api_base')"
  bundle_id="$(state_get '.bundle_id')"
  session_id="$(state_get '.session_id')"
  since="$(state_get '.purchase_started_at')"

  if [ "$DRY_RUN" -eq 1 ]; then
    would "poll gh run list --workflow=report-bundle.yml for the run the purchase dispatched"
    would "read the bundle row from DynamoDB table $(bundles_table)"
    would "GET ${api:-\$API}/download/<bundle_id>, follow the 302, and unzip the archive"
    would "assert manifest.json names unitrans, yolobus and not-a-real-agency, each with an outcome"
    would "assert not-a-real-agency carries a reason rather than being dropped"
    would "assert both HTML reports carry '${TEST_PROGRAM_NAME}' and ${TEST_ACCENT}"
    note "Tables are named by convention from infra/program-bundle/main.tf"
    note "(\${project}-program-bundles). The Lambda's env would also say, but"
    note "reading it returns every variable, secrets included, so this does not."
    return 0
  fi

  [ -n "$bundle_id" ] || { bad "no bundle_id in state; run the purchase phase first"; return 1; }

  say "Waiting for the workflow run the purchase dispatched."
  local run_line run_id conclusion
  run_line="$(wait_for_run "${since:-1970-01-01T00:00:00Z}")" || true
  run_id="$(printf '%s' "$run_line" | awk '{print $1}')"
  conclusion="$(printf '%s' "$run_line" | awk '{print $2}')"
  if [ "$run_id" = "none" ] || [ -z "$run_id" ]; then
    bad "no report-bundle.yml run appeared after ${since}"
    return 1
  fi
  ok "run ${run_id} (https://github.com/${GH_REPO}/actions/runs/${run_id})"
  assert_eq "run conclusion" "success" "$conclusion"

  # The webhook's own record of the same purchase: this is the proof that
  # Stripe reached API Gateway, which a self-signed event cannot show.
  local checkout_row
  checkout_row="$(aws dynamodb get-item --table-name "$(bundles_table)" --region us-west-2 \
    --key "{\"bundle_id\":{\"S\":\"checkout#${session_id}\"}}" --output json 2>/dev/null || printf '{}')"
  if [ "$(printf '%s' "$checkout_row" | jq -r '.Item.plan.S // ""')" = "bundle_25" ]; then
    ok "the webhook noted the same checkout as plan bundle_25 (Stripe reached the API)"
  else
    bad "no checkout#${session_id} row with plan bundle_25 in $(bundles_table)"
    note "The webhook endpoint may not be subscribed to checkout.session.completed."
  fi

  local row
  row="$(aws dynamodb get-item --table-name "$(bundles_table)" --region us-west-2 \
    --key "{\"bundle_id\":{\"S\":\"${bundle_id}\"}}" --output json 2>/dev/null || printf '{}')"
  if [ "$(printf '%s' "$row" | jq -r '.Item.bundle_id.S // ""')" = "$bundle_id" ]; then
    ok "capability row exists for ${bundle_id}"
    assert_eq "row deliver_to" "${BUNDLE_DELIVER_TO}" "$(printf '%s' "$row" | jq -r '.Item.deliver_to.S // ""')"
    assert_eq "row source" "checkout" "$(printf '%s' "$row" | jq -r '.Item.source.S // ""')"
  else
    bad "no capability row for ${bundle_id}"
    return 1
  fi

  local work zip
  work="$(mktemp -d)"
  zip="${work}/bundle.zip"
  local code
  code="$(curl --silent --show-error --location --max-time 120 \
    --write-out '%{http_code}' --output "$zip" "${api}/download/${bundle_id}")"
  assert_eq "GET /download/<bundle_id> (after the 302)" "200" "$code"
  if [ "$(head -c 2 "$zip" 2>/dev/null)" = "PK" ]; then
    ok "the download is a zip archive ($(wc -c < "$zip" | tr -d ' ') bytes)"
  else
    bad "the download is not a zip archive"
    rm -rf "$work"
    return 1
  fi
  unzip -q -o "$zip" -d "${work}/out"
  ok "archive contents: $(cd "${work}/out" && find . -type f | sed 's|^\./||' | sort | tr '\n' ' ')"

  local manifest="${work}/out/manifest.json"
  if [ ! -f "$manifest" ]; then
    bad "no manifest.json in the archive"
    rm -rf "$work"
    return 1
  fi

  local id
  for id in unitrans yolobus not-a-real-agency; do
    local status detail
    status="$(jq -r --arg i "$id" '.agencies[] | select(.id == $i) | .status' "$manifest")"
    detail="$(jq -r --arg i "$id" '.agencies[] | select(.id == $i) | .detail' "$manifest")"
    if [ -n "$status" ]; then
      ok "manifest names ${id} with outcome '${status}'"
    else
      bad "manifest does not name ${id}"
    fi
    if [ "$id" = "not-a-real-agency" ]; then
      if [ -n "$detail" ] && [ "$detail" != "null" ]; then
        ok "not-a-real-agency carries a reason: ${detail}"
      else
        bad "not-a-real-agency is listed without a reason (or was dropped)"
      fi
    fi
  done
  assert_eq "manifest program_name" "$TEST_PROGRAM_NAME" "$(jq -r .program_name "$manifest")"
  assert_eq "manifest bundle_id" "$bundle_id" "$(jq -r .bundle_id "$manifest")"

  local report
  for id in unitrans yolobus; do
    report="${work}/out/reports/${id}-board-report.html"
    if [ ! -f "$report" ]; then
      bad "no report for ${id} in the archive"
      continue
    fi
    if grep -qF "$TEST_PROGRAM_NAME" "$report"; then
      ok "${id} report carries the program name"
    else
      bad "${id} report does not carry the program name"
    fi
    if grep -qiF "$TEST_ACCENT" "$report"; then
      ok "${id} report carries the accent ${TEST_ACCENT}"
    else
      bad "${id} report does not carry the accent ${TEST_ACCENT}"
    fi
  done
  note "Archive unpacked at ${work}/out (delete it when you are done)."
  return 0
}

# ---------------------------------------------------------------------------
# Phase: verify-cap
# ---------------------------------------------------------------------------

# create_session <key> <price id> -> prints "<session id> <hosted url>"
create_session() {
  local key="$1" price="$2" mode="${3:-payment}"
  stripe_api "$key" POST "/v1/checkout/sessions" \
    --data-urlencode "mode=${mode}" \
    --data-urlencode "line_items[0][price]=${price}" \
    --data-urlencode "line_items[0][quantity]=1" \
    --data-urlencode "success_url=${SITE}/bundle/setup/?session_id={CHECKOUT_SESSION_ID}" \
    --data-urlencode "cancel_url=${SITE}/bundle/" >/dev/null || return 1
  printf '%s %s' \
    "$(printf '%s' "$STRIPE_BODY" | jq -r .id)" \
    "$(printf '%s' "$STRIPE_BODY" | jq -r .url)"
}

post_setup() {
  local api="$1" session="$2" ids="$3"
  local payload
  payload="$(jq -n --arg s "$session" --arg p "$TEST_PROGRAM_NAME" --arg a "$TEST_ACCENT" \
    --arg i "$ids" --arg d "${BUNDLE_DELIVER_TO:-}" \
    '{session_id: $s, program_name: $p, accent: $a, logo: "", agency_ids: $i, deliver_to: $d}')"
  curl --silent --show-error --max-time 40 --write-out $'\n%{http_code}' \
    -X POST -H 'Content-Type: application/json' --data "$payload" "${api}/setup"
}

runs_since() {
  gh run list --repo "$GH_REPO" --workflow=report-bundle.yml --limit 20 \
    --json createdAt --jq "[.[] | select(.createdAt >= \"$1\")] | length"
}

phase_verify_cap() {
  local key="${STRIPE_SECRET_KEY:-}" api price25
  api="$(state_get '.api_base')"
  price25="$(state_get '.prices.bundle_25')"

  if [ "$DRY_RUN" -eq 1 ]; then
    would "create a Checkout Session for the bundle_25 price and pay it with the test card"
    would "POST /setup with 26 agency ids and assert a 400 reading:"
    would "  'your plan covers at most 25 agencies; 26 were given'"
    would "assert no report-bundle.yml run was dispatched by that attempt"
    would "create a throwaway \$1 test product and price, buy it, and POST /setup with that session"
    would "assert a 4xx reading 'This checkout was not for a GTFS Scorecard report bundle'"
    would "assert no run and no bundle row came of it"
    note "This is the half of PR #400 that has never run against the deployed"
    note "Lambda: the cap comes off the price that was paid for, and a paid"
    note "session for any other price must build nothing."
    return 0
  fi

  [ -n "$key" ] || { bad "STRIPE_SECRET_KEY is not set"; return 1; }
  [ -n "$api" ] || { bad "no api_base in state"; return 1; }
  [ -n "$price25" ] || { bad "no bundle_25 price in state"; return 1; }

  # --- the cap -------------------------------------------------------------
  say "1. The bundle_25 cap, read off the price that was actually paid for."
  local pair session url
  pair="$(create_session "$key" "$price25")" || { bad "could not create a Checkout Session: $(stripe_error)"; return 1; }
  session="${pair%% *}"
  url="${pair##* }"
  ok "session ${session}"

  local before after
  before="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  pay_session "$url" "bundle_25 session" || return 1

  local ids="" i=1
  while [ "$i" -le 26 ]; do
    ids="${ids}${ids:+,}test-agency-${i}"
    i=$((i + 1))
  done
  local out code body
  out="$(post_setup "$api" "$session" "$ids")"
  code="${out##*$'\n'}"
  body="${out%$'\n'*}"
  printf '        | %s %s\n' "$code" "$body"
  assert_eq "26 ids on a bundle_25 purchase" "400" "$code"
  assert_contains "refusal sentence" "your plan covers at most 25 agencies; 26 were given" "$body"
  sleep 20
  after="$(runs_since "$before")"
  assert_eq "workflow runs dispatched by the refused submit" "0" "$after"

  # The refusal must not consume the session: the runbook tells the buyer to
  # trim the list and submit again on the same checkout.
  local out2 code2
  out2="$(post_setup "$api" "$session" "unitrans, yolobus")"
  code2="${out2##*$'\n'}"
  assert_eq "the same session still works after the refusal" "200" "$code2"
  state_set '.cap_session' "$session"
  state_set '.cap_bundle_id' \
    "$(printf '%s' "${out2%$'\n'*}" | jq -r '.bundle_id // ""' 2>/dev/null || printf '')"

  # --- a price that is not one of the four ---------------------------------
  say ""
  say "2. A paid session for a price this product does not sell."
  say "   This is PR #400's security fix, proved against the deployed Lambda."
  stripe_api "$key" POST "/v1/products" \
    --data-urlencode "name=bundle-testmode throwaway (safe to archive)" >/dev/null || {
    bad "could not create the throwaway product: $(stripe_error)"; return 1; }
  local throwaway_product throwaway_price
  throwaway_product="$(printf '%s' "$STRIPE_BODY" | jq -r .id)"
  stripe_api "$key" POST "/v1/prices" \
    --data-urlencode "product=${throwaway_product}" \
    --data-urlencode "currency=usd" \
    --data-urlencode "unit_amount=100" \
    --data-urlencode "nickname=bundle-testmode-throwaway" >/dev/null || {
    bad "could not create the throwaway price: $(stripe_error)"; return 1; }
  throwaway_price="$(printf '%s' "$STRIPE_BODY" | jq -r .id)"
  ok "throwaway product ${throwaway_product}, price ${throwaway_price} (\$1.00, test mode)"
  state_set '.throwaway.product' "$throwaway_product"
  state_set '.throwaway.price' "$throwaway_price"

  local pair2 session2 url2
  pair2="$(create_session "$key" "$throwaway_price")" || { bad "could not create the foreign session"; return 1; }
  session2="${pair2%% *}"
  url2="${pair2##* }"
  ok "foreign session ${session2}"

  before="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  pay_session "$url2" "foreign session" || return 1

  local out3 code3 body3
  out3="$(post_setup "$api" "$session2" "unitrans")"
  code3="${out3##*$'\n'}"
  body3="${out3%$'\n'*}"
  printf '        | %s %s\n' "$code3" "$body3"
  case "$code3" in
    4*) ok "a paid session for an unconfigured price is refused (${code3})" ;;
    *) bad "expected a 4xx for an unconfigured price, got ${code3}" ;;
  esac
  assert_contains "refusal sentence" "not for a GTFS Scorecard report bundle" "$body3"
  assert_not_contains "no bundle was minted" "bundle_id" "$body3"
  sleep 20
  assert_eq "workflow runs dispatched by the foreign purchase" "0" "$(runs_since "$before")"
  return 0
}

# ---------------------------------------------------------------------------
# Phase: teardown-notes
# ---------------------------------------------------------------------------

phase_teardown_notes() {
  local api webhook endpoint throwaway_product throwaway_price
  api="$(state_get '.api_base')"
  webhook="$(state_get '.webhook_url')"
  endpoint="$(state_get '.webhook_endpoint')"
  throwaway_product="$(state_get '.throwaway.product')"
  throwaway_price="$(state_get '.throwaway.price')"

  cat <<TEXT
Test-mode rows expire on their own after 30 days (the DynamoDB TTL and the S3
lifecycle rule). The Stripe objects and the AWS stack do not. Here is what now
exists and how to remove it.

In the Stripe TEST account
  2 products, 4 prices, 4 Payment Links, from scripts/stripe-setup.sh.
    Dashboard -> Product catalog -> each product -> Archive.
    Dashboard -> Payment Links -> each link -> Deactivate.
    Archived, not deleted: Stripe keeps price objects a purchase referred to.
  bundle product   $(state_get '.products.bundle')
  refresh product  $(state_get '.products.refresh')
$(for p in "${PLAN_KEYS[@]}"; do printf '  price %-11s %s\n' "$p" "$(state_get ".prices.${p}")"; done)
$(if [ -n "$throwaway_product" ]; then
    printf '  throwaway from verify-cap: product %s, price %s\n' "$throwaway_product" "$throwaway_price"
    printf '    Archive it the same way; it exists only to prove the refusal.\n'
  fi)
  1 webhook endpoint${endpoint:+ (${endpoint})} at ${webhook:-<webhook_url>}
    Dashboard -> Developers -> Webhooks -> the endpoint -> Delete.
    Leaving it costs nothing; it fails signature checks once the module is
    re-applied with a different secret.
  Test-mode Checkout Sessions, PaymentIntents and Customers from the purchase
  and verify-cap phases. These cannot be deleted and do not need to be; they
  are inert test-mode records.

In AWS (account $(aws sts get-caller-identity --query Account --output text 2>/dev/null || printf '?'), us-west-2)
  Everything infra/program-bundle creates: 3 Lambdas, 1 HTTP API (${api:-<api_base>}),
  2 DynamoDB tables, 1 IAM role and policy, 1 EventBridge rule.
    To close the purchase surface but keep issued links working:
      set payments_enabled = "0" in ${TFVARS} and apply.
    To remove it entirely:
      terraform -chdir=infra/program-bundle destroy
    That deletes the two tables, so any download link still in someone's inbox
    stops working. In test mode nobody has one.
  The expire-program-bundles lifecycle rule on ${ARTIFACTS_BUCKET}.
    Leave it. It is part of infra/artifacts and live mode needs it.
  Objects under s3://${ARTIFACTS_BUCKET}/program-bundles/
    They expire after 30 days on their own.

In GitHub
  Repository variable BUNDLE_API_BASE.
    gh variable delete BUNDLE_API_BASE --repo ${GH_REPO}
    Leave it set if live mode will use the same API, which it does.
  The fine-grained PAT from the dashboard step. Put its expiry in your
  calendar: when it lapses the setup Lambda answers 502 and every purchase
  needs a make-good by hand.

On this machine
  ${TFVARS}
    The one file holding credentials. rm it when you are done, or leave it
    0600 until live mode reuses the shape.
  ${STATE_DIR}/
    state.json, the saved stripe-setup output, the playwright install and its
    failure screenshots. rm -rf it to start clean; the next run will then
    re-discover the Stripe objects rather than re-create them.
  ${REPO_ROOT}/infra/program-bundle/build/ and program-bundle.zip
    Gitignored build output; rebuilt by the build phase.
TEXT
  return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

run_phase() {
  local name="$1" fn
  CURRENT_PHASE="$name"
  fn="phase_${name//-/_}"
  banner "$name"
  if ! "$fn"; then
    return 1
  fi
  return 0
}

usage() {
  sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//;$d'
}

main() {
  local phases_to_run=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --dry-run) DRY_RUN=1 ;;
      --only) ONLY_PHASE="${2:-}"; shift ;;
      --only=*) ONLY_PHASE="${1#*=}" ;;
      --from) FROM_PHASE="${2:-}"; shift ;;
      --from=*) FROM_PHASE="${1#*=}" ;;
      --list-phases) printf '%s\n' "${PHASES[@]}"; return 0 ;;
      -h|--help) usage; return 0 ;;
      *) die "unknown argument: $1 (try --help)" ;;
    esac
    shift
  done

  REPO_ROOT="$(repo_root)"
  TFVARS="${REPO_ROOT}/infra/program-bundle/terraform.tfvars"
  # A dry run reads state if it is there and creates none if it is not, so
  # "nothing was written" in the summary is a fact rather than a figure of
  # speech.
  if [ "$DRY_RUN" -eq 0 ]; then
    state_init
  fi

  local resolved line
  resolved="$(resolve_phases "$ONLY_PHASE" "$FROM_PHASE")" || die "see --list-phases"
  while IFS= read -r line; do
    if [ -n "$line" ]; then
      phases_to_run+=("$line")
    fi
  done <<< "$resolved"

  say "gtfs-scorecard program report bundle: test-mode walkthrough"
  say "repo     ${REPO_ROOT}"
  if [ "$DRY_RUN" -eq 1 ]; then
    say "mode     DRY RUN (read-only; creates and applies nothing)"
  else
    say "mode     LIVE test-mode run (creates Stripe test objects and AWS resources)"
  fi
  say "phases   ${phases_to_run[*]}"

  local phase stopped=""
  for phase in "${phases_to_run[@]}"; do
    if ! run_phase "$phase"; then
      if [ "$DRY_RUN" -eq 1 ]; then
        note "(dry run: carrying on so every phase can say what it would do)"
        continue
      fi
      stopped="$phase"
      break
    fi
  done

  banner "summary"
  say "  ${ASSERT_PASS} passed, ${ASSERT_FAIL} failed"
  if [ "${#FAILURES[@]}" -gt 0 ]; then
    say ""
    local failure
    for failure in "${FAILURES[@]}"; do
      say "  FAIL  ${failure}"
    done
  fi
  if [ -n "$stopped" ]; then
    say ""
    say "  Stopped in phase '${stopped}'. Fix it, then resume with:"
    say "    scripts/bundle-testmode.sh --from ${stopped}"
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    say ""
    say "  Dry run: no Stripe object, no AWS resource, no credential file, no"
    say "  state file, no commit. The one thing it does write is the gitignored"
    say "  .terraform/ provider cache, which terraform validate needs."
  fi
  if [ "$ASSERT_FAIL" -ne 0 ] || [ -n "$stopped" ]; then
    return 1
  fi
  return 0
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  main "$@"
fi
