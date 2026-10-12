# The history tables on AWS Data Exchange (ADR 0065, docs/data-marketplace.md).
#
# Off by default. With `marketplace_enabled = false` (the default) this file
# creates nothing and the plan is unchanged. The owner turns it on only after
# the account is a registered AWS Marketplace seller qualified for AWS Data
# Exchange; registration, the product, the offer, and the data subscription
# agreement are console steps no automation takes.
#
# What it creates when on:
#
# - One owned data set of S3 files. Every monthly build becomes one revision of
#   it; the product the owner creates in the AWS Marketplace Management Portal
#   includes this data set, and a finalized revision reaches subscribers.
# - The role history-export.yml's `marketplace` job assumes. It may create a
#   revision of this one data set, import the month's five files from
#   history/<YYYY-MM>/tables/ into it, rename those assets, finalize it, and
#   delete an unfinalized revision an interrupted run left. It cannot touch any
#   other data set, publish or change a product or an offer (those are AWS
#   Marketplace Catalog actions it is not given), or read anything else in the
#   bucket. Trusts runs on main only, like the other two roles in this module.

variable "marketplace_enabled" {
  description = "Create the AWS Data Exchange data set and the publishing role. Leave false until the account is a qualified Data Exchange provider (docs/data-marketplace.md)."
  type        = bool
  default     = false
}

locals {
  marketplace_count = var.marketplace_enabled ? 1 : 0
}

data "aws_caller_identity" "current" {
  count = local.marketplace_count
}

resource "aws_dataexchange_data_set" "history" {
  count      = local.marketplace_count
  asset_type = "S3_SNAPSHOT"
  name       = "GTFS Scorecard history tables"
  # Visible to subscribers only. The product's own long description is the
  # listing; this is the short note a subscriber sees beside the files.
  description = "Monthly build of the GTFS Scorecard check-level and finding-level history: checks.parquet (one row per feed record per dated check), findings.parquet (one row per finding per check), DATA-DICTIONARY.md, PROVENANCE.json, and LICENSE.md. Each revision is the whole history to that month, not an increment."
}

resource "aws_iam_role" "marketplace_publish" {
  count              = local.marketplace_count
  name               = "${var.project}-marketplace-publish"
  assume_role_policy = data.aws_iam_policy_document.deploy_assume.json
}

data "aws_iam_policy_document" "marketplace_publish" {
  count = local.marketplace_count

  # The data set itself: read it, list its revisions, and create a revision
  # in it. Nothing else of the account's data sets.
  statement {
    sid       = "TheOneDataSet"
    actions   = ["dataexchange:GetDataSet", "dataexchange:ListDataSetRevisions", "dataexchange:CreateRevision"]
    resources = [aws_dataexchange_data_set.history[0].arn]
  }

  # Its revisions and their assets: check, rename, finalize, and delete an
  # unfinalized leftover. A finalized revision in a published product cannot
  # be deleted by the API at all; revoking one is a console step.
  statement {
    sid = "ItsRevisionsAndAssets"
    actions = [
      "dataexchange:GetRevision",
      "dataexchange:UpdateRevision",
      "dataexchange:DeleteRevision",
      "dataexchange:ListRevisionAssets",
      "dataexchange:GetAsset",
      "dataexchange:UpdateAsset",
    ]
    resources = [
      "${aws_dataexchange_data_set.history[0].arn}/revisions/*",
      "${aws_dataexchange_data_set.history[0].arn}/revisions/*/assets/*",
    ]
  }

  # Import jobs only. A job's id does not exist until it is created, so the
  # resource is the account's jobs; the job type condition keeps it to
  # imports from S3 (no export, no signed-URL job).
  statement {
    sid       = "ImportJobsOnly"
    actions   = ["dataexchange:CreateJob", "dataexchange:StartJob", "dataexchange:GetJob", "dataexchange:CancelJob"]
    resources = ["arn:aws:dataexchange:${var.region}:${data.aws_caller_identity.current[0].account_id}:jobs/*"]
    condition {
      test     = "StringEquals"
      variable = "dataexchange:JobType"
      values   = ["IMPORT_ASSETS_FROM_S3"]
    }
  }

  # The import reads the month's unzipped files with the caller's permissions.
  # Only the tables/ folder of a month: never the zip a Stripe buyer's link
  # names, never the dated artifacts, never stored orders.
  statement {
    sid       = "ReadTheMonthsTables"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/history/*/tables/*"]
  }
  statement {
    sid       = "LocateTheBucket"
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.artifacts.arn]
  }

  # The import writes into Data Exchange's own service buckets. Scoped the way
  # the Data Exchange guide scopes it: buckets named *aws-data-exchange*, and
  # only when the request comes through Data Exchange.
  statement {
    sid       = "WriteIntoDataExchangeOnly"
    actions   = ["s3:PutObject", "s3:PutObjectAcl"]
    resources = ["arn:aws:s3:::*aws-data-exchange*"]
    condition {
      test     = "ForAnyValue:StringEquals"
      variable = "aws:CalledVia"
      values   = ["dataexchange.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "marketplace_publish" {
  count  = local.marketplace_count
  name   = "marketplace-publish"
  role   = aws_iam_role.marketplace_publish[0].id
  policy = data.aws_iam_policy_document.marketplace_publish[0].json
}

output "marketplace_data_set_id" {
  description = "Set as the ADX_DATA_SET_ID repository variable once the product exists (docs/data-marketplace.md). Null while marketplace_enabled is false."
  value       = var.marketplace_enabled ? aws_dataexchange_data_set.history[0].id : null
}

output "marketplace_publish_role_arn" {
  description = "Set as the MARKETPLACE_AWS_ROLE_ARN repository secret. Null while marketplace_enabled is false."
  value       = var.marketplace_enabled ? aws_iam_role.marketplace_publish[0].arn : null
}
