"""Regression checks for the public CDN/private bucket boundary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_viewer_request_function_is_an_allowlist() -> None:
    code = (ROOT / "infra" / "artifacts" / "public-artifacts-only.js").read_text()

    assert 'uri.indexOf("/data/artifacts/") === 0' in code
    assert 'uri.indexOf("/data/artifacts/run/") !== 0' in code
    assert 'uri === "/data/liveness.json"' in code
    assert "statusCode: 404" in code


def test_origin_policy_cannot_read_private_prefixes() -> None:
    terraform = (ROOT / "infra" / "artifacts" / "main.tf").read_text()

    assert "${aws_s3_bucket.artifacts.arn}/data/artifacts/*" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/data/liveness.json" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/*" not in terraform
    assert "${aws_s3_bucket.artifacts.arn}/feeds/*" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/cache/*" in terraform
    assert "${aws_s3_bucket.artifacts.arn}/data/artifacts/run/*" in terraform
    assert 'aws_cloudfront_function" "public_artifacts_only' in terraform
