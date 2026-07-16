"""Mode-aware copy stays descriptive, ungraded, and technically exact."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.mode_language import (
    adapt_artifact_language,
    adapt_text,
    language_kind,
    mode_label,
)


def _artifact(*, ferry_only: bool, multimodal: bool = False) -> dict[str, Any]:
    modes = [{"key": "ferry", "label": "Ferry"}]
    if multimodal:
        modes.insert(0, {"key": "bus", "label": "Bus"})
    return {
        "overall": {"grade": "B", "score": 84.0},
        "mode_profile": {
            "measured": True,
            "graded": False,
            "primary_mode": "ferry",
            "ferry_only": ferry_only,
            "is_multimodal": multimodal,
            "modes": modes,
        },
        "categories": {
            "correctness": {
                "summary": "The bus data was checked.",
                "findings": [
                    {
                        "code": "stop_too_far_from_shape",
                        "what": "Some stops sit far from the route line they belong to.",
                        "why": (
                            "The bus may use the wrong streets or send riders to the wrong corner."
                        ),
                        "fix": "Check 3 of 4 stops in stops.txt and keep stop_id exact.",
                        "effort": "A few minutes per flagged stop.",
                    }
                ],
            }
        },
        "top_fixes": [
            {
                "code": "scorecard_wheelchair_accessible_unknown",
                "what": "19 of 19 stops don't say whether a wheelchair user can board there.",
                "why": (
                    "Even with accessible stops, riders need to know the bus itself can take them."
                ),
                "fix": "Set wheelchair_boarding for every stop in stops.txt.",
            }
        ],
        "conformance": {
            "summary": "States wheelchair access on 0% of stops.",
            "criteria": [{"key": "accessible", "detail": "Nearly every stop is described."}],
        },
    }


def test_ferry_copy_uses_vessels_and_terminals_without_touching_scores_or_codes() -> None:
    artifact = _artifact(ferry_only=True)
    result = adapt_artifact_language(artifact)
    finding = result["categories"]["correctness"]["findings"][0]
    fix = result["top_fixes"][0]

    assert language_kind(result) == "ferry"
    assert mode_label(result) == "Ferry"
    assert result["overall"] == {"grade": "B", "score": 84.0}
    assert finding["code"] == "stop_too_far_from_shape"
    assert "vessel" in finding["why"] and "wrong terminal" in finding["why"]
    assert "Some terminals sit" in finding["what"]
    assert "3 of 4 terminals" in finding["fix"]
    assert "stops.txt" in finding["fix"] and "stop_id" in finding["fix"]
    assert "19 of 19 terminals" in fix["what"]
    assert "accessible terminals" in fix["why"] and "vessel" in fix["why"]
    assert "every terminal" in fix["fix"] and "stops.txt" in fix["fix"]
    assert "0% of terminals" in result["conformance"]["summary"]
    assert "Nearly every terminal" in result["conformance"]["criteria"][0]["detail"]
    assert artifact["categories"]["correctness"]["summary"] == "The bus data was checked."


def test_mixed_mode_copy_is_neutral_and_label_names_both_modes() -> None:
    artifact = _artifact(ferry_only=False, multimodal=True)
    result = adapt_artifact_language(artifact)

    assert language_kind(result) == "generic"
    assert mode_label(result) == "Bus + Ferry"
    assert "transit vehicle" in result["categories"]["correctness"]["summary"]
    assert "boarding location" in result["categories"]["correctness"]["findings"][0]["why"]
    assert "19 of 19 stops" in result["top_fixes"][0]["what"]


def test_bus_copy_is_unchanged() -> None:
    artifact = _artifact(ferry_only=False)
    artifact["mode_profile"].update(primary_mode="bus", modes=[{"key": "bus"}])

    assert language_kind(artifact) == "bus"
    assert adapt_text("The bus uses these stops.", "bus") == "The bus uses these stops."
    assert adapt_artifact_language(artifact)["categories"] == artifact["categories"]
