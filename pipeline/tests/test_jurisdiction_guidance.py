from scorecard_pipeline.jurisdiction_guidance import guidance_for, resolve_subdivision_code


def test_global_core_has_no_us_requirement() -> None:
    canada = guidance_for("CA", "CA-ON")
    assert canada["universal"]["scope"] == "all"
    assert canada["national"] is None
    assert canada["jurisdiction"] is None


def test_us_overlays_are_additive() -> None:
    california = guidance_for("US", "US-CA")
    assert california["national"]["scope"] == "US"
    assert california["jurisdiction"]["kind"] == "guideline"
    assert california["support"] is None


def test_support_resource_is_not_a_guideline() -> None:
    minnesota = guidance_for("US", "US-MN")
    assert minnesota["jurisdiction"] is None
    assert minnesota["support"]["kind"] == "support"


def test_legacy_state_name_resolves_only_for_us() -> None:
    assert resolve_subdivision_code("US", state="California") == "US-CA"
    assert resolve_subdivision_code("CA", state="California") == ""
