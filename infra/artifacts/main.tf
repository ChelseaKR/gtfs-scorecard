# Artifact hosting: S3 bucket of published JSON behind CloudFront.
#
# Year 1 of docs/roadmap.md. The web app reads pre-computed JSON and nothing
# else, so serving the same files from CloudFront instead of GitHub Pages is a
# host swap with no change to the data contract. Private bucket, reached only
# through CloudFront via Origin Access Control.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

resource "aws_s3_bucket" "artifacts" {
  bucket = var.bucket_name
  tags   = { project = var.project }
}

# Artifacts are public data, but they are reached through the CDN, not the
# bucket directly. Block all public bucket access; CloudFront uses OAC.
resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Encrypt at rest. The artifacts are public data, so this is a default-good
# baseline control rather than a confidentiality need, but it costs nothing.
resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Keep the bucket bounded now that the collect job syncs every dated
# artifact and nothing prunes them client-side (docs/follow-ups.md, S3 as
# the artifact source of truth, step 4). Only objects tagged
# artifact-class=dated are eligible for expiration: the collect job's "Tag
# today's dated artifacts" step applies that tag to each day's
# `<agency>/<date>.json` file. latest.json, badge.json, directory.json, and
# the validator cache are never tagged, so current-state reads (what the
# site actually serves) never expire out from under it even if an agency's
# feed goes a long time without changing.
resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expire-dated-artifacts"
    status = "Enabled"

    filter {
      tag {
        key   = "artifact-class"
        value = "dated"
      }
    }

    # ~13 months: a bit more than a year of trend history survives, and the
    # oldest dated files (synced before this rule existed, and so never
    # tagged) are unaffected until a future re-tag.
    expiration {
      days = 400
    }
  }

  # Bucket versioning is on (above); without this, every overwritten or
  # deleted object version accumulates forever and the bucket never actually
  # shrinks regardless of the rule above.
  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {
      prefix = ""
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

resource "aws_cloudfront_origin_access_control" "artifacts" {
  name                              = "${var.project}-artifacts-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Artifacts are public JSON read cross-origin by the web app (served from a
# different origin: GitHub Pages or a custom domain) and embedded as badges on
# agency sites. Allow any origin to read them.
resource "aws_cloudfront_response_headers_policy" "cors" {
  name = "${var.project}-artifacts-cors"
  cors_config {
    access_control_allow_credentials = false
    access_control_allow_headers {
      items = ["*"]
    }
    access_control_allow_methods {
      items = ["GET", "HEAD"]
    }
    access_control_allow_origins {
      items = ["*"]
    }
    origin_override = true
  }
}

# The bucket also holds private pipeline inputs: content-addressed source feed
# archives under feeds/, validator cache entries under cache/, and the raw run
# ledger under data/artifacts/run/. A viewer-request allowlist runs before the
# cache lookup, so even an object cached before this policy existed cannot be
# served. The bucket policy below repeats the boundary at the origin.
resource "aws_cloudfront_function" "public_artifacts_only" {
  name    = "${var.project}-public-artifacts-only"
  runtime = "cloudfront-js-1.0"
  comment = "Allow only published scorecard artifacts; hide private pipeline inputs"
  publish = true
  code    = file("${path.module}/public-artifacts-only.js")
}

resource "aws_cloudfront_distribution" "artifacts" {
  enabled         = true
  comment         = "${var.project} artifacts"
  is_ipv6_enabled = true
  price_class     = "PriceClass_100" # North America + Europe; cheapest tier

  origin {
    domain_name              = aws_s3_bucket.artifacts.bucket_regional_domain_name
    origin_id                = "artifacts-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.artifacts.id
  }

  default_cache_behavior {
    target_origin_id           = "artifacts-s3"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    response_headers_policy_id = aws_cloudfront_response_headers_policy.cors.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.public_artifacts_only.arn
    }

    # Artifacts refresh daily; a short TTL keeps the site current without a
    # per-deploy invalidation. CORS-friendly so an agency page can embed a
    # badge cross-origin.
    min_ttl     = 0
    default_ttl = 300
    max_ttl     = 3600

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = { project = var.project }
}

# Allow only this distribution to read the bucket.
data "aws_iam_policy_document" "artifacts" {
  statement {
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*",
      "${aws_s3_bucket.artifacts.arn}/data/liveness.json",
    ]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.artifacts.arn]
    }
  }

  # data/artifacts/run/ is nested under the otherwise-public artifact prefix,
  # so deny it explicitly at the origin. feeds/ and cache/ are omitted from the
  # allow statement above; include them here as defense in depth and to keep
  # the intended boundary visible in a policy review.
  statement {
    effect  = "Deny"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/run/*",
      "${aws_s3_bucket.artifacts.arn}/feeds/*",
      "${aws_s3_bucket.artifacts.arn}/cache/*",
    ]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.artifacts.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  policy = data.aws_iam_policy_document.artifacts.json
}
