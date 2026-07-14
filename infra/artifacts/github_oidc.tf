# GitHub Actions OIDC deploy role.
#
# The daily workflow's "Mirror artifacts to CDN bucket" step assumes a role via
# OIDC (no long-lived AWS keys in GitHub). The S3 + CloudFront module publishes
# the data; this provisions the least-privilege role that the CI step assumes to
# write into the bucket. Output `deploy_role_arn` becomes the AWS_ROLE_ARN
# GitHub secret.

variable "github_repo" {
  description = "owner/repo allowed to assume the deploy role via OIDC."
  type        = string
  default     = "ChelseaKR/gtfs-scorecard"
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set false if this AWS account already has one."
  type        = bool
  default     = true
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.create_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # GitHub's OIDC root CA thumbprints (both rotations).
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  github_oidc_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

data "aws_iam_policy_document" "deploy_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Only workflows running on the default branch may assume the role, so a
    # pushed branch / tag / PR ref can't mint credentials to write the bucket.
    # The daily mirror runs on a schedule (ref = main); widen this if a release
    # branch or environment ever needs to publish.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "${var.project}-artifacts-deploy"
  assume_role_policy = data.aws_iam_policy_document.deploy_assume.json
  tags               = { project = var.project }
}

# Least privilege: write/list only the artifacts bucket, plus SES send for the
# opt-in feed-health digest (inert until a sender is verified and SES_FROM is set).
data "aws_iam_policy_document" "deploy_s3" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]
  }
  # GetObject lets the score job read the S3 validator cache (cache/validator/*)
  # and lets the deploy assemble published data from the bucket; Put/Delete
  # publish artifacts and the cache. PutObjectTagging lets the collect job mark
  # each day's dated artifact for the bucket's expire-dated-artifacts lifecycle
  # rule (docs/follow-ups.md, S3 as the artifact source of truth, step 4).
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:PutObjectTagging"]
    resources = ["${aws_s3_bucket.artifacts.arn}/*"]
  }
  statement {
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = ["*"]
  }
  # Read the opt-in subscriber store so the daily notify step can build digests
  # for confirmed subscribers (the table is created out-of-band; ARN by name).
  statement {
    actions   = ["dynamodb:Scan", "dynamodb:GetItem"]
    resources = ["arn:aws:dynamodb:us-west-2:014248889144:table/gtfs-scorecard-subscriptions"]
  }
}

resource "aws_iam_role_policy" "deploy_s3" {
  name   = "artifacts-write"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy_s3.json
}

output "deploy_role_arn" {
  description = "Set as the AWS_ROLE_ARN GitHub Actions secret for the CDN mirror step."
  value       = aws_iam_role.deploy.arn
}

# Read-only role for the Pages deploy job (docs/follow-ups.md, S3 as the
# artifact source of truth, step 1). The `deploy` role above is write-scoped
# for the collect job's mirror step; the Pages job only ever reads, so it gets
# its own least-privilege role rather than reusing that one.
#
# The Pages workflow (pages.yml) assumes this role from two contexts with
# different OIDC `sub` claims: the `lighthouse` job (and any direct push /
# workflow_dispatch run) presents `ref:refs/heads/main`, while the `deploy`
# job sets `environment: github-pages`, which changes its `sub` to the
# environment form. Both must be trusted or the deploy job's sync would fail.
data "aws_iam_policy_document" "pages_read_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repo}:ref:refs/heads/main",
        "repo:${var.github_repo}:environment:github-pages",
      ]
    }
  }
}

resource "aws_iam_role" "pages_read" {
  name               = "${var.project}-artifacts-pages-read"
  assume_role_policy = data.aws_iam_policy_document.pages_read_assume.json
  tags               = { project = var.project }
}

# Least privilege: GetObject + ListBucket only, scoped to the artifacts
# bucket. This role must never gain write access -- a compromised Pages
# deploy job could otherwise tamper with published scores.
data "aws_iam_policy_document" "pages_read_s3" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "data/artifacts",
        "data/artifacts/*",
        "cache/fixlog",
        "cache/fixlog/*",
      ]
    }
  }
  statement {
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/directory.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/index.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/scoring.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/sensitivity.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/canada-equity.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/changes/*",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/rollups/*",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/run/*",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/latest.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/badge.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/badge.svg",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/conformance.json",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/mark.svg",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/geometry.geojson",
      "${aws_s3_bucket.artifacts.arn}/data/artifacts/*/????-??-??.json",
      "${aws_s3_bucket.artifacts.arn}/data/liveness.json",
      "${aws_s3_bucket.artifacts.arn}/cache/fixlog/*",
    ]
  }
}

resource "aws_iam_role_policy" "pages_read_s3" {
  name   = "artifacts-read"
  role   = aws_iam_role.pages_read.id
  policy = data.aws_iam_policy_document.pages_read_s3.json
}

output "pages_read_role_arn" {
  description = "Set as the PAGES_AWS_ROLE_ARN GitHub Actions secret for the Pages deploy job's read-only S3 sync."
  value       = aws_iam_role.pages_read.arn
}
