"""The history tables' pages, plan file, workflow, and Terraform (ADR 0063, phase 2).

The same shape as the bundle's contract tests: the price lives in one plan
file, the served page carries only what the generator writes from it, the
post-checkout page is noindex and out of the sitemap, every gate that opens a
purchase surface knows about the new pages, the monthly workflow carries no
buyer data and touches only its prefix, and the Terraform grants the Lambda and
the workflow exactly the access the doc describes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from scorecard_pipeline.site_shell import (
    BUNDLE_GENERATED_REGION_RES,
    HISTORY_PAGE_PATH,
    HISTORY_PLAN_PATH,
    HISTORY_SERVICE_ID,
    STATIC_NAV_PAGES,
    history_noscript_region,
    history_offers_jsonld,
    history_offers_region,
    sync_history_offers,
)

_REPO = Path(__file__).resolve().parents[2]
_WEB = _REPO / "web"
_PAGE = _WEB / HISTORY_PAGE_PATH
_SETUP = _WEB / "data" / "history" / "setup" / "index.html"
_PLAN = _WEB / HISTORY_PLAN_PATH
_WORKFLOW = _REPO / ".github" / "workflows" / "history-export.yml"
_BUNDLE_TF = _REPO / "infra" / "program-bundle" / "main.tf"
_ARTIFACTS_TF = _REPO / "infra" / "artifacts" / "main.tf"
_OIDC_TF = _REPO / "infra" / "artifacts" / "github_oidc.tf"
_FOOTER_TAG = '<footer class="site-footer">'


def _plan() -> dict[str, Any]:
    plan: dict[str, Any] = json.loads(_PLAN.read_text())
    return plan


# --- the plan file ----------------------------------------------------------------------


def test_the_plan_file_sells_one_one_time_product_and_names_its_state() -> None:
    plan = _plan()
    assert set(plan) == {"schema_version", "paymentsAvailable", "currency", "products"}
    assert plan["schema_version"] == "1"
    assert isinstance(plan["paymentsAvailable"], bool)
    assert plan["currency"] == "USD"
    assert list(plan["products"]) == ["history_once"]
    product = plan["products"]["history_once"]
    assert set(product) == {"label", "price", "interval", "checkout_url"}
    assert isinstance(product["price"], int) and product["price"] > 0
    assert product["interval"] is None, "the history tables are a one-time purchase"
    url = product["checkout_url"]
    assert url is None or (isinstance(url, str) and url.startswith("https://buy.stripe.com/"))
    if plan["paymentsAvailable"]:
        assert url, "payments on with no checkout link would announce a sale nobody can make"


# --- the served page --------------------------------------------------------------------


def test_the_page_regions_are_what_the_generator_writes_from_the_plan(tmp_path: Path) -> None:
    text = _PAGE.read_text()
    regions = [pattern.search(text) for pattern in BUNDLE_GENERATED_REGION_RES]
    assert all(regions), "the page must carry both marker pairs"
    plan = _plan()
    assert regions[0].group(0) == history_offers_region(plan)  # type: ignore[union-attr]
    assert regions[1].group(0) == history_noscript_region(plan)  # type: ignore[union-attr]
    # And the sync is a no-op against the committed tree.
    assert sync_history_offers(root=_REPO) == []


def test_a_selling_plan_renders_an_offer_on_the_history_service_node() -> None:
    plan = {
        "paymentsAvailable": True,
        "currency": "USD",
        "products": {
            "history_once": {
                "label": "History tables, one-time",
                "price": 99,
                "interval": None,
                "checkout_url": "https://buy.stripe.com/test_example",
            }
        },
    }
    node = history_offers_jsonld(plan)
    assert node is not None
    assert node["@id"] == HISTORY_SERVICE_ID and node["url"].endswith("/data/history/")
    assert node["@type"] == ["Service", "Product"]
    offer = node["offers"]
    assert offer["@type"] == "Offer" and offer["price"] == "99" and offer["category"] == "one-time"
    assert "priceSpecification" not in offer
    region = history_offers_region(plan)
    assert region.startswith("<!-- offers:begin -->") and '"price":"99"' in region
    noscript = history_noscript_region(plan)
    assert "$99" in noscript and "Buy" not in noscript, (
        "the no-scripting list states the price and offers no checkout"
    )
    off = {**plan, "paymentsAvailable": False}
    assert history_offers_jsonld(off) is None
    assert "not for sale from this page right now" in history_noscript_region(off)
    assert "$99" not in history_noscript_region(off)


def test_the_landing_page_is_indexable_and_the_setup_page_is_not() -> None:
    page = _PAGE.read_text()
    setup = _SETUP.read_text()
    assert 'name="robots"' not in page
    assert '<meta name="robots" content="noindex,follow">' in setup
    assert '<link rel="canonical" href="https://gtfsscorecard.org/data/history/">' in page
    assert '<link rel="canonical" href="https://gtfsscorecard.org/data/history/setup/">' in setup
    seo = json.loads((_REPO / "site-seo.json").read_text())
    assert "/data/history/setup/" in seo["noindex_path_patterns"]
    # The Product node is the offers block, which exists only while the plan
    # says payments are available, so the SEO contract may require it only
    # then. The PR that turns the plan on must add "Product" here too, or the
    # deploy gate's structural SEO check fails the page.
    plan = json.loads(_PLAN.read_text())
    expected_types = ["Service", "Product"] if plan["paymentsAvailable"] else ["Service"]
    assert seo["required_json_ld_types"]["/data/history/"] == expected_types, (
        "site-seo.json requires a Product node on /data/history/ only while plan.json "
        "says payments are available"
    )
    render_site = (_REPO / "pipeline" / "src" / "scorecard_pipeline" / "render_site.py").read_text()
    assert 'f"{BASE_URL}/data/history/",' in render_site, "the landing page is in the sitemap list"
    assert "/data/history/setup/" not in render_site, "the setup page stays out of the sitemap"


def test_the_landing_page_states_what_the_contract_states() -> None:
    page = _PAGE.read_text()
    head, separator, _footer = page.partition(_FOOTER_TAG)
    assert separator
    for phrase in (
        "checks.parquet",
        "findings.parquet",
        "DATA-DICTIONARY.md",
        "PROVENANCE.json",
        "LICENSE.md",
        "never for sale",
        "stays free",
        "30 days",
        'id="license"',
        "One organization.",
        "No redistribution of the package.",
        "The facts stay free.",
        "Share-alike rows.",
        "Publisher terms travel with the rows.",
        "Attribution.",
        "No warranty.",
        "scored on top of the MobilityData gtfs-validator",
    ):
        assert phrase in head, phrase
    assert 'href="/bundle/"' not in head, (
        "the history page sells one thing; the bundle is reached through the shared footer"
    )
    assert '@type":"Service"' in head and HISTORY_SERVICE_ID in head
    assert page.count('id="plan-offers-jsonld"') <= 1


def test_the_setup_page_has_no_form_and_says_the_right_thing_without_scripting() -> None:
    setup = _SETUP.read_text()
    assert "<form" not in setup, "a history purchase names everything; there is nothing to ask"
    assert 'id="download-link"' in setup and 'id="setup-status"' in setup
    assert "the payment is recorded" in setup, "a reader without scripting has already paid"
    assert (
        "Do not pay again"
        in _SETUP.parent.parent.parent.parent.joinpath("src", "history-setup.js").read_text()
    )
    assert "/src/config.js" in setup and "/src/history-setup.js" in setup


def test_the_scripts_read_the_plan_file_and_post_only_the_session_id() -> None:
    page_script = (_WEB / "src" / "history.js").read_text()
    setup_script = (_WEB / "src" / "history-setup.js").read_text()
    assert 'const PLAN_URL = "/data/history/plan.json";' in page_script
    assert "SCORECARD_BUNDLE_URL" in setup_script
    assert "JSON.stringify({ session_id: sessionId })" in setup_script
    assert "program_name" not in setup_script and "agency_ids" not in setup_script
    for script in (page_script, setup_script):
        assert "$99" not in script and '"99"' not in script and " 99" not in script, (
            "no amount is typed into a script; the plan file owns it"
        )


def test_every_gate_that_opens_a_purchase_surface_knows_the_new_pages() -> None:
    assert STATIC_NAV_PAGES["data/history/index.html"] is None
    assert STATIC_NAV_PAGES["data/history/setup/index.html"] is None
    config = json.loads((_REPO / ".pa11yci.json").read_text())
    scanned = {
        (entry["url"] if isinstance(entry, dict) else entry).replace("http://127.0.0.1:8080", ""): (
            entry.get("wait", 0) if isinstance(entry, dict) else 0
        )
        for entry in config["urls"]
    }
    assert scanned.get("/data/history/", 0) >= 1000, (
        "the plan renders after a fetch; the scan must wait"
    )
    assert "/data/history/setup/" in scanned


# --- the workflow -----------------------------------------------------------------------


def test_the_export_workflow_carries_no_buyer_data_and_touches_only_its_prefix() -> None:
    text = _WORKFLOW.read_text()
    workflow = yaml.safe_load(text)
    on = workflow.get("on") or workflow.get(True)
    assert list(on["workflow_dispatch"]["inputs"]) == ["month"]
    assert on["schedule"] == [{"cron": "17 18 4 * *"}], (
        "day 4, after the free dataset release's window"
    )
    assert workflow["concurrency"] == {"group": "history-export", "cancel-in-progress": False}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["export"]
    assert job["permissions"] == {"contents": "read", "id-token": "write"}
    assert "secrets.HISTORY_AWS_ROLE_ARN" in text and "secrets.AWS_ROLE_ARN" not in text
    assert "uv sync --locked --extra query" in text, "DuckDB writes the Parquet"
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))
    assert "upload-artifact" not in code, "a run artifact of a public repository is published"
    assert "--size-only" not in text
    for line in text.splitlines():
        if "aws s3 cp" in line and "s3://" in line:
            assert "/history/${month}/" in line, line
    assert text.count("aws s3 cp") == 2
    assert "unzip -Z1" in text and "checks.parquet" in text and "findings.parquet" in text
    assert "deliver_to" not in text and "program_name" not in text and "session" not in text.lower()


# --- the Terraform ----------------------------------------------------------------------


def test_the_lambda_gains_exactly_the_history_access_the_doc_describes() -> None:
    tf = _BUNDLE_TF.read_text()
    assert re.search(r"HISTORY_ENABLED\s+= var.history_sales_enabled", tf)
    assert re.search(r"SES_FROM\s+= var.ses_from", tf)
    assert "merge(var.stripe_price_ids, { history_once = var.history_price_id })" in tf
    assert 'Resource = "${data.aws_s3_bucket.artifacts.arn}/history/*"' in tf
    assert 'StringLike = { "s3:prefix" = ["history/*"] }' in tf
    assert 'Action   = ["ses:SendEmail"]' in tf and "Resource = var.ses_identity_arn" in tf
    assert 'count = var.ses_identity_arn == "" ? 0 : 1' in tf, (
        "no SES grant until an identity is named"
    )
    assert 'var.history_sales_enabled == "0" || (var.payments_enabled == "1"' in tf
    assert 'contains(["0", "1"], var.history_sales_enabled)' in tf
    assert "[^*]+$" in tf, "the SES identity ARN refuses a wildcard"
    # The bundle's own price map is untouched: still exactly four keys.
    assert 'toset(["bundle_25", "bundle_100", "refresh_mo", "refresh_yr"])' in tf


def test_the_bucket_retires_and_denies_the_history_prefix() -> None:
    tf = _ARTIFACTS_TF.read_text()
    rule = tf.split('id     = "expire-history-exports"', 1)[1].split("rule {", 1)[0]
    assert 'prefix = "history/"' in rule and "days = 400" in rule
    deny = tf.split("# The allow statement above is the public contract.", 1)[1].split(
        'resource "aws_s3_bucket_policy"', 1
    )[0]
    for private in ("history/*", "program-bundles/*", "program-requests/*", "feeds/*", "cache/*"):
        assert f'"${{aws_s3_bucket.artifacts.arn}}/{private}"' in deny, private
    allow = tf.split('data "aws_iam_policy_document" "artifacts"', 1)[1].split(
        "# The allow statement", 1
    )[0]
    assert "history" not in allow, "the history prefix is never on the public allow list"


def test_the_workflow_role_is_its_own_and_least_privilege() -> None:
    tf = _OIDC_TF.read_text()
    role = tf.split('resource "aws_iam_role" "history_export"', 1)[1]
    assert "data.aws_iam_policy_document.deploy_assume.json" in role, "trusts runs on main only"
    policy = tf.split('data "aws_iam_policy_document" "history_export_s3"', 1)[1].split(
        'resource "aws_iam_role_policy" "history_export_s3"', 1
    )[0]
    assert 'values   = ["data/artifacts/*", "history/*"]' in policy
    assert 'resources = ["${aws_s3_bucket.artifacts.arn}/data/artifacts/*"]' in policy
    assert 'resources = ["${aws_s3_bucket.artifacts.arn}/history/*"]' in policy
    assert "DeleteObject" not in policy and "PutObjectTagging" not in policy
    assert '"${aws_s3_bucket.artifacts.arn}/*"' not in policy, "no bucket-wide wildcard"
    assert "ses:" not in policy and "dynamodb:" not in policy
    assert 'output "history_export_role_arn"' in tf
