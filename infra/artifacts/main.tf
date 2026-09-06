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

# Cost allocation. `project` is an activated cost-allocation tag key in Cost
# Explorer, so anything carrying it can be attributed to this project's budget
# and anything without it lands in the account-wide untagged pile. Setting the
# tags here rather than per resource means every taggable resource in this
# module gets them, including ones added later. `component` names the module so
# spend can be split within the project; `managed-by` marks what Terraform owns,
# which is the fast way to spot resources created out of band.
locals {
  default_tags = {
    project    = var.project
    component  = "artifacts"
    managed-by = "terraform"
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.default_tags
  }
}

resource "aws_s3_bucket" "artifacts" {
  bucket = var.bucket_name
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
      noncurrent_days = 1
    }
  }

  # Daily score shards hand private export fingerprints to the serialized
  # collect job through a run-scoped prefix. A failed run can strand that
  # staging data, so expire it independently of successful cleanup.
  # Program report bundles (infra/program-bundle, docs/program-plan.md):
  # each archive lives behind a 128-bit capability link that expires with
  # the object. 30 days, in step with bundle.DOWNLOAD_DAYS and the DynamoDB
  # TTL on the capability row. The prefix is outside the CloudFront
  # allow-list, so the only way to an archive is the download route.
  rule {
    id     = "expire-program-bundles"
    status = "Enabled"
    filter {
      prefix = "program-bundles/"
    }
    expiration {
      days = 30
    }
  }
  rule {
    id     = "expire-structure-staging"
    status = "Enabled"

    filter {
      prefix = "cache/structure-staging/"
    }

    expiration {
      days = 7
    }
  }

  # feeds/ must never expire: it is the reproducibility record (archive.py), and
  # `scorecard reproduce <agency> <date>` fetches the exact scored zip back by
  # content hash however long after the fact. What it can do is get cheaper. The
  # objects are written once and read almost never, only when a grade is
  # disputed, a validator-upgrade study runs, or a backfill needs the original
  # bytes, so Standard is the wrong class for anything but the recent tail.
  # Glacier Instant Retrieval keeps millisecond GETs, so reproduce.py is
  # unchanged, at roughly a sixth of the storage price. 30 days holds the window
  # where a fresh grade is most likely to be questioned in Standard, and the
  # bucket-level TransitionDefaultMinimumObjectSize of 128 KB already skips the
  # small feeds where a transition costs more than it saves.
  #
  # This matters because the prefix is unbounded by design: content addressing
  # means a new publication from any agency adds a zip and never replaces one.
  # It was 59.5 GB across 9,272 objects on 2026-08-07 and grows about 2.3 GB a
  # day, so it is the one storage line here that compounds rather than plateaus.
  rule {
    id     = "archive-feeds-to-glacier-ir"
    status = "Enabled"

    filter {
      prefix = "feeds/"
    }

    transition {
      days          = 30
      storage_class = "GLACIER_IR"
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
# ledger under data/artifacts/run/. Legacy internal state objects also exist
# under agency artifact directories. A viewer-request allowlist runs
# before the cache lookup, so even an object cached before this policy existed
# cannot be served. The bucket policy below repeats the boundary at the origin.
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
}

# Allow only this distribution to read the bucket.
data "aws_iam_policy_document" "artifacts" {
  statement {
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/directory.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/index.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/scoring.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/sensitivity.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/canada-equity.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/changes/*.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/rollups/*.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/rollups/*.csv",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/latest.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/????-??-??.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/badge.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/badge.svg",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/conformance.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/mark.svg",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/geometry.geojson",
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

  # The allow statement above is the public contract. Repeat every private
  # prefix and legacy pipeline-state shape as an explicit deny for defense in
  # depth and to keep the intended boundary visible in a policy review.
  statement {
    effect  = "Deny"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/run/*",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/validator-cache.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/structure.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/fixlog.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/corrected.zip",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/rollups/*.state.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/rollups/digest.md",
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
