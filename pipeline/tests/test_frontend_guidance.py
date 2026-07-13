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
