#!/usr/bin/env bash
# Create the program report bundle's Stripe products, prices, and payment
# links (docs/program-plan.md, ADR 0049), and print the Terraform variables
# and the web/bundle/plan.json values they map to.
#
# Runs against whichever mode the key in STRIPE_SECRET_KEY belongs to. Use a
# TEST key first; the runbook says when a live one is allowed. The key is
# read from the environment and never written anywhere by this script.
#
# Needs: the Stripe CLI (https://stripe.com/docs/stripe-cli), jq.
#
# Usage:
#   STRIPE_SECRET_KEY=sk_test_... scripts/stripe-setup.sh
#   STRIPE_SECRET_KEY=sk_test_... scripts/stripe-setup.sh --site https://staging.example
#
# Idempotence: Stripe products and prices have no natural key, so re-running
# creates duplicates. Run it once per mode, record the ids, and archive
# anything created by mistake in the dashboard.

set -euo pipefail

SITE="https://gtfsscorecard.org"
if [ "${1:-}" = "--site" ] && [ -n "${2:-}" ]; then SITE="$2"; fi

if [ -z "${STRIPE_SECRET_KEY:-}" ]; then
  echo "STRIPE_SECRET_KEY is not set. Export a test-mode key first." >&2
  exit 2
fi
command -v stripe >/dev/null || { echo "stripe CLI not found" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 2; }

case "$STRIPE_SECRET_KEY" in
  sk_test_*|rk_test_*) MODE="test" ;;
  sk_live_*|rk_live_*) MODE="live" ;;
  *) echo "Unrecognised key prefix; refusing to guess the mode." >&2; exit 2 ;;
esac
echo "Mode: $MODE  Site: $SITE" >&2

# Amounts are the hypotheses in docs/program-plan.md, in cents. Change them
# there first, then here; the page never carries a price of its own.
BUNDLE_25_CENTS=14900
BUNDLE_100_CENTS=34900
REFRESH_MO_CENTS=4900
REFRESH_YR_CENTS=49000

api() { stripe "$@" --api-key "$STRIPE_SECRET_KEY"; }

bundle_product=$(api products create \
  --name "GTFS Scorecard board reports, program bundle" \
  --description "Branded board reports for every agency a program supports, as one archive. Agency-facing scoring stays free." \
  | jq -r .id)
refresh_product=$(api products create \
  --name "GTFS Scorecard board reports, monthly refresh" \
  --description "A fresh branded archive every month for a program's agencies. Cancel any time." \
  | jq -r .id)

price_bundle_25=$(api prices create --product "$bundle_product" --currency usd --unit-amount "$BUNDLE_25_CENTS" --nickname "bundle_25" | jq -r .id)
price_bundle_100=$(api prices create --product "$bundle_product" --currency usd --unit-amount "$BUNDLE_100_CENTS" --nickname "bundle_100" | jq -r .id)
price_refresh_mo=$(api prices create --product "$refresh_product" --currency usd --unit-amount "$REFRESH_MO_CENTS" -d "recurring[interval]=month" --nickname "refresh_mo" | jq -r .id)
price_refresh_yr=$(api prices create --product "$refresh_product" --currency usd --unit-amount "$REFRESH_YR_CENTS" -d "recurring[interval]=year" --nickname "refresh_yr" | jq -r .id)

# Payment Links send the buyer to the setup form with the session reference.
success="${SITE}/bundle/setup/?session_id={CHECKOUT_SESSION_ID}"
link() {
  api payment_links create \
    -d "line_items[0][price]=$1" -d "line_items[0][quantity]=1" \
    -d "after_completion[type]=redirect" \
    -d "after_completion[redirect][url]=$success" \
    | jq -r .url
}
link_bundle_25=$(link "$price_bundle_25")
link_bundle_100=$(link "$price_bundle_100")
link_refresh_mo=$(link "$price_refresh_mo")
link_refresh_yr=$(link "$price_refresh_yr")

cat <<EOF

# --- infra/program-bundle terraform.tfvars ($MODE mode) ---------------------
stripe_price_ids = {
  bundle_25  = "$price_bundle_25"
  bundle_100 = "$price_bundle_100"
  refresh_mo = "$price_refresh_mo"
  refresh_yr = "$price_refresh_yr"
}
stripe_price_ids_are_live = $([ "$MODE" = "live" ] && echo true || echo false)

# --- web/bundle/plan.json products (set paymentsAvailable only after the e2e check) ---
$(jq -n \
  --arg b25 "$link_bundle_25" --arg b100 "$link_bundle_100" \
  --arg mo "$link_refresh_mo" --arg yr "$link_refresh_yr" \
  --argjson p25 $((BUNDLE_25_CENTS / 100)) --argjson p100 $((BUNDLE_100_CENTS / 100)) \
  --argjson pmo $((REFRESH_MO_CENTS / 100)) --argjson pyr $((REFRESH_YR_CENTS / 100)) '{
  bundle_25:  {label: "One bundle, up to 25 agencies",     price: $p25,  interval: null,    checkout_url: $b25},
  bundle_100: {label: "One bundle, up to 100 agencies",    price: $p100, interval: null,    checkout_url: $b100},
  refresh_mo: {label: "Monthly refresh",                   price: $pmo,  interval: "month", checkout_url: $mo},
  refresh_yr: {label: "Monthly refresh, billed yearly",    price: $pyr,  interval: "year",  checkout_url: $yr}
}')
EOF
