from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_spa_ntd_and_guidance_are_country_aware() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()
    assert 'artifact.agency?.country || "US"' in app
    assert '!== "US") return ""' in app
    assert "standardsSection(artifact, dirRecord)" in app
    assert (
        'showUsPolicyToolsForCountry(dirRecord?.country || artifact.agency?.country || "US")' in app
    )
    assert "document.querySelector('.site-footer a[href=\"/ntd/\"]')" in app
    assert 'dirRecord?.country || artifact.agency?.country || "US"' in app
    assert (
        "artifact = { ...artifact, agency: { ...artifact.agency, country: effectiveCountry } };"
        in app
    )


def test_spa_has_no_hand_maintained_state_guidance_table() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()
    assert "const STATE_STANDARDS" not in app
    assert "JURISDICTION_GUIDANCE" in app
    assert "SUPPORT_RESOURCES" in app
    assert 'const CW = "/crosswalk/"' in app
    assert "blob/main/docs/crosswalk.md" not in app


def test_spa_fix_points_name_the_category_scale() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()
    assert "worth about +${Math.round(f.points)} points in its category</span>" in app


def test_spa_comparisons_disclose_the_full_producer_contract() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()
    assert "required_scoring_profile_id" in app
    assert "required_validator_version" in app
    assert "required_measured_categories" in app
    assert "come from distinct feed bytes" in app


def test_spa_ignores_legacy_corrected_feed_download_urls() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()

    assert "autofix.download_url" not in app
    assert "Download corrected feed" not in app
    assert "Safe fixes you can run locally" in app
    assert "The scorecard does not publish a modified feed" in app
