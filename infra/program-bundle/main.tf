# Program report bundle (docs/program-plan.md, ADR 0049): the program tier's
# only always-on surface. Three small zip-package Lambdas behind one HTTP API
# Gateway plus a weekly EventBridge rule:
#
#   POST /setup                 the post-checkout form; confirms the Stripe
#                               session is paid, then dispatches
#                               .github/workflows/report-bundle.yml
#   GET  /download/{bundle_id}  the capability link in the delivery email;
#                               302 to a fifteen-minute presigned S3 URL
#   POST /webhook               Stripe events -> subscription state
#   (weekly)                    re-dispatch for active subscriptions
#   (daily)                     reconcile paid orders that bought nothing and
#                               report the counts in one GitHub issue
#
# Status: applied and live since 2026-09-12 (docs/program-plan.md's runbook
# records the sequence; `payments_enabled = "1"`, `stripe_price_ids_are_live =
# true`). Everything that can charge anyone sits behind `payments_enabled`,
# which defaults to "0" and cannot be turned on while the Stripe configuration
# is blank: the preconditions on terraform_data.commercial_gate_guard fail the
# *plan*, not a warning a CI `plan -out && apply` would never show anyone (the
# family-greenhouse pattern this copies). A fresh checkout or a from-scratch
# apply still starts at that same "written, not applied" posture as
# infra/compute and infra/instant-score (see infra/README.md) until the same
# runbook is followed again.
#
# API Gateway, not Lambda function URLs, for the same account-level reason
# as infra/alerts and infra/submit.
#
# Build the deployment package before applying, from the repository root:
#   scripts/build-lambda-package.sh infra/program-bundle
# It vendors the pipeline as Linux x86_64 / CPython 3.12 wheels and refuses a
# package holding any other platform's binaries. A plain
# `pip install ../../pipeline -t build` on a Mac vendors macOS binaries, and
# the setup and refresh handlers then fail to import in the Lambda runtime
# (rpds, under jsonschema). State lives in S3 (backend.tf), because it holds
# the GitHub token and both Stripe secrets; `terraform init` wires it up:
#   cd infra/program-bundle && terraform init && terraform apply

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
}

# Cost allocation: see the note in infra/artifacts/main.tf.
locals {
  default_tags = {
    project    = var.project
    component  = "program-bundle"
    managed-by = "terraform"
  }
  price_ids_missing = [for k, v in var.stripe_price_ids : k if v == ""]
  # Either live prefix counts, so the consistency check below still holds if
  # the restricted-key validation on stripe_secret_key is ever loosened.
  stripe_key_is_live = startswith(var.stripe_secret_key, "rk_live_") || startswith(var.stripe_secret_key, "sk_live_")
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.default_tags
  }
}

variable "project" {
  type    = string
  default = "gtfs-scorecard"
}

variable "region" {
  type    = string
  default = "us-west-2"
}

variable "github_repo" {
  description = "owner/name of the repo whose report-bundle.yml is dispatched."
  type        = string
  default     = "ChelseaKR/gtfs-scorecard"
}

variable "github_token" {
  description = "Fine-scoped token on this repository. Needs Actions: Read and write to dispatch the fulfilment workflow, and Issues: Read and write for the daily reconciler's standing report. Widening it is an owner action; github_token_can_write_issues is where that is attested."
  type        = string
  sensitive   = true
}

variable "artifacts_bucket" {
  description = "The infra/artifacts bucket; bundles land under program-bundles/<id>/."
  type        = string
}

variable "allow_origin" {
  description = "CORS origin of the setup form. Never '*' for a token-backed endpoint."
  type        = string
  default     = "https://gtfsscorecard.org"
}

variable "payments_enabled" {
  description = "\"1\" opens the purchase surface; \"0\" (default) keeps every route that could charge anyone closed. A string, validated exactly, so a tfvars typo fails the plan instead of silently disabling a launch that looks enabled."
  type        = string
  default     = "0"

  validation {
    condition     = contains(["0", "1"], var.payments_enabled)
    error_message = "payments_enabled must be exactly \"0\" or \"1\"."
  }
}

variable "stripe_secret_key" {
  description = "Restricted Stripe key (rk_test_... or rk_live_...) with Checkout Sessions: Read and nothing else. Test-mode until the live decision is recorded."
  type        = string
  default     = ""
  sensitive   = true

  # Only a restricted key is ever deployed. A full secret key (sk_...) can
  # charge, refund, and read every customer on the account; it stays with
  # scripts/stripe-setup.sh on the operator's machine.
  validation {
    condition     = var.stripe_secret_key == "" || startswith(var.stripe_secret_key, "rk_test_") || startswith(var.stripe_secret_key, "rk_live_")
    error_message = "stripe_secret_key must be a restricted key (rk_test_... or rk_live_...). A full secret key (sk_...) is never deployed."
  }
}

variable "stripe_webhook_secret" {
  description = "Signing secret of the one webhook endpoint pointed at this API."
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_price_ids" {
  description = "Stripe price ids for the four knobs in docs/program-plan.md. All four must be set before payments_enabled can be \"1\". The Lambdas read them (STRIPE_PRICE_IDS) to refuse any checkout for another price and to hold each purchase to its plan's agency cap."
  type        = map(string)
  default = {
    bundle_25  = ""
    bundle_100 = ""
    refresh_mo = ""
    refresh_yr = ""
  }

  # A tfvars map replaces the default outright, so a missing or misspelled
  # key would otherwise pass the gate and refuse every purchase of that plan.
  validation {
    condition     = toset(keys(var.stripe_price_ids)) == toset(["bundle_25", "bundle_100", "refresh_mo", "refresh_yr"])
    error_message = "stripe_price_ids must have exactly the keys bundle_25, bundle_100, refresh_mo, refresh_yr."
  }

  # One price id on two plans would let the Lambdas guess which cap applies.
  validation {
    condition     = length(distinct(compact(values(var.stripe_price_ids)))) == length(compact(values(var.stripe_price_ids)))
    error_message = "stripe_price_ids has the same price id on more than one plan."
  }
}

variable "reconciler_reporting_ready" {
  description = <<-EOT
    Turns the daily reconciler's schedule on. False keeps it DISABLED, because a job that
    finds paid orders and cannot tell anyone is the defect it exists to close, and Terraform
    cannot check a reporting channel for itself. Before setting it true, confirm both halves:

      1. github_token still carries the fine-grained repository permission
         "Issues: Read and write" on this repository.
         Verified present on 2026-09-12 by a differential probe:
         POST /repos/ChelseaKR/gtfs-scorecard/issues with an empty body answered 422 ("title"
         wasn't supplied), while the identical request against two other repositories answered
         403 ("Resource not accessible by personal access token"). The permission gate is
         checked before the payload on that endpoint, so the 422 is a pass and not merely a
         malformed request. A bare 422 on its own would have proved nothing.
      2. The label "program-bundle-reconciler" exists, or the first report fails on it.

    Named for readiness rather than for the token, so the default does not read as a claim
    that the permission is missing. It is not.
  EOT
  type        = bool
  default     = false
}

variable "stripe_price_ids_are_live" {
  description = "Set true only after confirming the price ids above were created in live mode. A live key paired with test-mode prices sells nothing and looks like it does."
  type        = bool
  default     = false
}

variable "google_ads_conversion_action" {
  description = "Google Ads conversion action resource name (\"customers/<id>/conversionActions/<id>\"). Blank keeps conversion_tracking.py's seam a no-op. Set to the real one created 2026-09-15 (\"Enhanced conversions for leads\", Purchases, primary, data-driven attribution, 90-day click-through) -- see docs/paid-search-readiness.md."
  type        = string
  default     = "customers/2688527650/conversionActions/7769927171"
}

# Google Ads credentials for ads_conversion_upload_handler.py, the same
# sensitive-variable-with-a-blank-default shape as stripe_secret_key and
# github_token above: never a value this repo commits, supplied at apply
# time from whichever tfvars or secret store already holds the rest of
# this module's configuration. See docs/google-ads-upload-setup.md for
# where each value comes from.
variable "google_ads_developer_token" {
  description = "Google Ads API developer token. Sunset as the access-control mechanism 2026-09-09 (access levels now attach to the Google Cloud project behind the OAuth client below), but the google-ads client library's config still accepts the field, so it is still generated and set for forward compatibility. Blank keeps the upload Lambda a no-op."
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_ads_client_id" {
  description = "OAuth 2.0 client id of the \"Desktop app\" credential created in Google Cloud Console for scripts/generate-google-ads-refresh-token.py. Blank keeps the upload Lambda a no-op."
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_ads_client_secret" {
  description = "OAuth 2.0 client secret paired with google_ads_client_id. Blank keeps the upload Lambda a no-op."
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_ads_refresh_token" {
  description = "OAuth 2.0 refresh token from scripts/generate-google-ads-refresh-token.py's one-time interactive run. Blank keeps the upload Lambda a no-op."
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_ads_login_customer_id" {
  description = "The Google Ads account performing the upload, ten digits, no dashes (the same numeric id embedded in google_ads_conversion_action above -- not a secret, just an account number). Validated the same way the google-ads client library validates it, so a typo fails the plan instead of failing at upload time."
  type        = string
  default     = "2688527650"

  validation {
    condition     = var.google_ads_login_customer_id == "" || can(regex("^[0-9]{10}$", var.google_ads_login_customer_id))
    error_message = "google_ads_login_customer_id must be exactly ten digits, no dashes, e.g. \"2688527650\"."
  }
}

variable "google_ads_upload_ready" {
  description = <<-EOT
    Turns the daily ads_conversion_upload_handler.py schedule on. False keeps it DISABLED,
    the same "Terraform cannot check this for itself" posture as reconciler_reporting_ready:
    the five google_ads_* credential variables above being non-blank proves they were typed
    in, not that they are valid, and the only real check is a call ads_conversion_upload_handler
    itself makes against a live Google Ads account. Before setting this true, run the Lambda
    by hand with {"dry_run": true} and confirm it logs the pending row(s) it would upload with
    no error, then run it for real once and check the row(s) it claims land as
    status: "uploaded" in the ad-conversions table, not "failed".
  EOT
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# The gate. Preconditions, not check blocks: a check block only warns.
# ---------------------------------------------------------------------------

resource "terraform_data" "commercial_gate_guard" {
  input = {
    payments_enabled = var.payments_enabled
  }

  lifecycle {
    precondition {
      condition     = var.payments_enabled == "0" || (var.stripe_secret_key != "" && var.stripe_webhook_secret != "")
      error_message = "payments_enabled is \"1\" but the Stripe secret key or webhook secret is blank."
    }
    precondition {
      condition     = var.payments_enabled == "0" || length(local.price_ids_missing) == 0
      error_message = "payments_enabled is \"1\" but these price ids are blank: ${join(", ", local.price_ids_missing)}."
    }
    # Both directions: a live key with test prices sells nothing, and a test
    # key cannot read a live checkout, so every live purchase would fail.
    precondition {
      condition     = var.payments_enabled == "0" || local.stripe_key_is_live == var.stripe_price_ids_are_live
      error_message = local.stripe_key_is_live ? "A live Stripe key is paired with price ids not confirmed live (stripe_price_ids_are_live = false)." : "stripe_price_ids_are_live is true but the Stripe key is not a live key."
    }
  }
}

# A flipped-on schedule with a blank credential would run daily, find
# pending conversions, and refuse every one of them with ConfigurationError
# -- loud, but a full day late each time, and an easy typo to make when the
# five variables above are set one at a time. Caught at plan time instead.
resource "terraform_data" "google_ads_upload_guard" {
  input = {
    google_ads_upload_ready = var.google_ads_upload_ready
  }

  lifecycle {
    # google_ads_developer_token is deliberately not required here: Google
    # sunset it as the access-control mechanism 2026-09-09 (access levels
    # now attach to the Cloud project behind the OAuth client), and its own
    # client library lists it as optional. Requiring it anyway would be a
    # gate this code cannot justify against what Google's current docs say
    # -- see docs/google-ads-upload-setup.md and that variable's own
    # description.
    precondition {
      condition = !var.google_ads_upload_ready || alltrue([
        var.google_ads_conversion_action != "",
        var.google_ads_client_id != "",
        var.google_ads_client_secret != "",
        var.google_ads_refresh_token != "",
        var.google_ads_login_customer_id != "",
      ])
      error_message = "google_ads_upload_ready is true but google_ads_conversion_action or one of the four required google_ads_* credential variables is blank."
    }
  }
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

# Subscriptions: one row per Stripe subscription. Kept on cancellation with
# a status and a date, never deleted; a cancellation is a fact, not an absence.
resource "aws_dynamodb_table" "subscriptions" {
  name         = "${var.project}-program-subscriptions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# Bundle capabilities: one row per download link, plus `session#` and
# `checkout#` rows the setup and webhook handlers use for idempotency. TTL
# expires a *capability* row 30 days after creation, in step with the S3
# lifecycle rule on program-bundles/ (infra/artifacts) and
# bundle.DOWNLOAD_DAYS. It expires neither of the other two, because neither
# carries `expires_at`, and the earlier wording here said it expired all
# three. For `session#` that is deliberate and load-bearing: the claim has to
# outlive the capability or a replay after 30 days would build a second
# bundle from one payment (setup_handler._session_row). For `checkout#` it is
# not deliberate. Those rows hold a buyer's email address and are kept so a
# checkout with no setup form can be found and helped by hand, which is a
# support decision with a retention consequence, not an oversight to paper
# over with a TTL nobody chose; see the note in webhook_handler.
resource "aws_dynamodb_table" "bundles" {
  name         = "${var.project}-program-bundles"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "bundle_id"

  attribute {
    name = "bundle_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

# One row per Stripe checkout session that produced a conversion event
# (conversion_tracking.store_pending_upload writes these; see that module's
# docstring for why a table and not a Logs Insights query over the printed
# CloudWatch lines). No TTL: a "failed" row is the record a human follows up
# on, and an "uploaded" row is the only durable proof this purchase was ever
# reported to Google Ads -- neither should expire out from under an owner
# who has not looked yet, the same reasoning as the `checkout#` rows in
# `bundles` above.
resource "aws_dynamodb_table" "ad_conversions" {
  name         = "${var.project}-program-ad-conversions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "conversion_id"

  attribute {
    name = "conversion_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ---------------------------------------------------------------------------
# Lambdas (one package, five entrypoints)
# ---------------------------------------------------------------------------

data "archive_file" "package" {
  type        = "zip"
  source_dir  = "${path.module}/build"
  output_path = "${path.module}/program-bundle.zip"
}

data "aws_s3_bucket" "artifacts" {
  bucket = var.artifacts_bucket
}

resource "aws_iam_role" "lambda" {
  name = "${var.project}-program-bundle"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.project}-program-bundle"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Tables"
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Scan"]
        Resource = [
          aws_dynamodb_table.subscriptions.arn,
          aws_dynamodb_table.bundles.arn,
          aws_dynamodb_table.ad_conversions.arn,
        ]
      },
      {
        # Read only, and only the bundle prefix: the download route presigns
        # exactly one object per capability and nothing else in the bucket,
        # and the reconciler heads one object per capability row.
        Sid      = "Bundles"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${data.aws_s3_bucket.artifacts.arn}/program-bundles/*"
      }
    ]
  })
}

locals {
  common_env = {
    GITHUB_REPO                  = var.github_repo
    GITHUB_TOKEN                 = var.github_token
    WORKFLOW_FILE                = "report-bundle.yml"
    WORKFLOW_REF                 = "main"
    SUBSCRIPTIONS_TABLE          = aws_dynamodb_table.subscriptions.name
    BUNDLES_TABLE                = aws_dynamodb_table.bundles.name
    ARTIFACTS_BUCKET             = var.artifacts_bucket
    ALLOW_ORIGIN                 = var.allow_origin
    PAYMENTS_ENABLED             = var.payments_enabled
    STRIPE_SECRET_KEY            = var.stripe_secret_key
    STRIPE_WEBHOOK_SECRET        = var.stripe_webhook_secret
    STRIPE_PRICE_IDS             = jsonencode(var.stripe_price_ids)
    GOOGLE_ADS_CONVERSION_ACTION = var.google_ads_conversion_action
    # Read by ads_conversion_upload_handler.py only, wired through this
    # shared env block like every other variable here (the same convention
    # GOOGLE_ADS_CONVERSION_ACTION above already follows for the webhook).
    AD_CONVERSIONS_TABLE         = aws_dynamodb_table.ad_conversions.name
    GOOGLE_ADS_DEVELOPER_TOKEN   = var.google_ads_developer_token
    GOOGLE_ADS_CLIENT_ID         = var.google_ads_client_id
    GOOGLE_ADS_CLIENT_SECRET     = var.google_ads_client_secret
    GOOGLE_ADS_REFRESH_TOKEN     = var.google_ads_refresh_token
    GOOGLE_ADS_LOGIN_CUSTOMER_ID = var.google_ads_login_customer_id
  }
}

resource "aws_lambda_function" "setup" {
  function_name    = "${var.project}-program-bundle-setup"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "setup_handler.handler"
  filename         = data.archive_file.package.output_path
  source_code_hash = data.archive_file.package.output_base64sha256
  timeout          = 20
  memory_size      = 256

  environment {
    variables = local.common_env
  }
}

resource "aws_lambda_function" "webhook" {
  function_name    = "${var.project}-program-bundle-webhook"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "webhook_handler.handler"
  filename         = data.archive_file.package.output_path
  source_code_hash = data.archive_file.package.output_base64sha256
  timeout          = 10
  memory_size      = 128

  environment {
    variables = local.common_env
  }
}

resource "aws_lambda_function" "refresh" {
  function_name    = "${var.project}-program-bundle-refresh"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "refresh_handler.handler"
  filename         = data.archive_file.package.output_path
  source_code_hash = data.archive_file.package.output_base64sha256
  timeout          = 60
  memory_size      = 128

  environment {
    variables = local.common_env
  }
}

resource "aws_lambda_function" "ads_conversion_upload" {
  function_name    = "${var.project}-program-bundle-ads-upload"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "ads_conversion_upload_handler.handler"
  filename         = data.archive_file.package.output_path
  source_code_hash = data.archive_file.package.output_base64sha256
  # One gRPC call to Google Ads carrying at most a handful of rows (this
  # product's weekly purchase volume); 60s matches refresh's own timeout for
  # a comparably small, comparably occasional upstream call.
  timeout     = 60
  memory_size = 128

  environment {
    variables = local.common_env
  }
}

# ---------------------------------------------------------------------------
# Front door
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "reconcile" {
  function_name    = "${var.project}-program-bundle-reconcile"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "reconcile_handler.handler"
  filename         = data.archive_file.package.output_path
  source_code_hash = data.archive_file.package.output_base64sha256
  # It heads one S3 object per capability row. A scan of a table this size
  # plus a few hundred HEADs fits inside a minute; the timeout is there to
  # stop a wedged call, not to bound the work.
  timeout     = 120
  memory_size = 128

  environment {
    variables = local.common_env
  }
}

resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project}-program-bundle"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "setup" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.setup.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "webhook" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.webhook.invoke_arn
  payload_format_version = "2.0"
}

# The purchase routes exist only while payments are enabled. With the gate
# closed the API has a webhook and nothing else, so the setup form on the
# site (which reads /bundle/plan.json) degrades to its paused notice and no
# request can reach a Lambda that could dispatch a build.
resource "aws_apigatewayv2_route" "setup" {
  count     = var.payments_enabled == "1" ? 1 : 0
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /setup"
  target    = "integrations/${aws_apigatewayv2_integration.setup.id}"
}

resource "aws_apigatewayv2_route" "setup_options" {
  count     = var.payments_enabled == "1" ? 1 : 0
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "OPTIONS /setup"
  target    = "integrations/${aws_apigatewayv2_integration.setup.id}"
}

resource "aws_apigatewayv2_route" "download" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /download/{bundle_id}"
  target    = "integrations/${aws_apigatewayv2_integration.setup.id}"
}

resource "aws_apigatewayv2_route" "webhook" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.webhook.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = 5
    throttling_burst_limit = 10
  }
}

resource "aws_lambda_permission" "setup" {
  statement_id  = "AllowApiGatewayInvokeSetup"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.setup.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "webhook" {
  statement_id  = "AllowApiGatewayInvokeWebhook"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

# ---------------------------------------------------------------------------
# Weekly refresh
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "weekly" {
  name                = "${var.project}-program-bundle-refresh"
  description         = "Re-dispatch report-bundle.yml for subscriptions due a refresh."
  schedule_expression = "cron(30 14 ? * TUE *)"
  state               = var.payments_enabled == "1" ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "weekly" {
  rule = aws_cloudwatch_event_rule.weekly.name
  arn  = aws_lambda_function.refresh.arn
}

resource "aws_lambda_permission" "events" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.refresh.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly.arn
}

# ---------------------------------------------------------------------------
# Daily reconciliation
# ---------------------------------------------------------------------------

# The only thing in this stack that looks for orders nobody is handling: a
# capability row with no archive, a claim that never dispatched, a checkout
# that never reached the setup form. It reports by opening one GitHub issue
# carrying counts and a CloudWatch pointer, and nothing identifying, because
# this repository is public.
#
# Disabled BY DEFAULT until the reporting path is confirmed ready. Terraform
# cannot check a channel for itself, so the switch is the gate; without it the
# job would run daily, find paid orders, fail to file them and be exactly the
# unreachable alerting it was built to replace. The variable's own description
# carries the two things to confirm before flipping it (default stays `false`
# so a plan from a clean checkout never turns this on as a side effect).
#
# Both were confirmed 2026-09-12 and `reconciler_reporting_ready` was set
# `true` in the local, gitignored `terraform.tfvars` and applied the same day
# -- see docs/program-plan.md's reconciler status note for the live evidence
# (the rule reads ENABLED in the account; three clean daily runs so far, zero
# findings). That fact lives only in the applied state and this comment,
# because the tfvars value itself is never committed.
resource "aws_cloudwatch_event_rule" "daily_reconcile" {
  name                = "${var.project}-program-bundle-reconcile"
  description         = "Report paid program orders with no delivered bundle."
  schedule_expression = "cron(10 15 * * ? *)"
  state               = var.payments_enabled == "1" && var.reconciler_reporting_ready ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "daily_reconcile" {
  rule = aws_cloudwatch_event_rule.daily_reconcile.name
  arn  = aws_lambda_function.reconcile.arn
}

resource "aws_lambda_permission" "events_reconcile" {
  statement_id  = "AllowEventBridgeInvokeReconcile"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.reconcile.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_reconcile.arn
}

# ---------------------------------------------------------------------------
# Daily Google Ads conversion upload
# ---------------------------------------------------------------------------

# Disabled until google_ads_upload_ready is true -- see that variable's own
# description and terraform_data.google_ads_upload_guard above. 15:50 UTC is
# after both the weekly refresh (14:30 Tuesdays) and the daily reconciler
# (15:10), so this never contends with either for the shared IAM role's
# throughput on the same clock tick.
resource "aws_cloudwatch_event_rule" "daily_ads_upload" {
  name                = "${var.project}-program-bundle-ads-upload"
  description         = "Upload pending Google Ads conversion events."
  schedule_expression = "cron(50 15 * * ? *)"
  state               = var.google_ads_upload_ready ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "daily_ads_upload" {
  rule = aws_cloudwatch_event_rule.daily_ads_upload.name
  arn  = aws_lambda_function.ads_conversion_upload.arn
}

resource "aws_lambda_permission" "events_ads_upload" {
  statement_id  = "AllowEventBridgeInvokeAdsUpload"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ads_conversion_upload.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_ads_upload.arn
}

output "reconcile_function" {
  description = "Invoke by hand with {\"dry_run\": true} to see what the daily reconciler would report."
  value       = aws_lambda_function.reconcile.function_name
}

output "ads_conversion_upload_function" {
  description = "Invoke by hand with {\"dry_run\": true} to see what the upload job would send to Google Ads."
  value       = aws_lambda_function.ads_conversion_upload.function_name
}

output "api_base" {
  description = "Set this as the BUNDLE_API_BASE Actions variable and window.SCORECARD_BUNDLE_URL in web/src/config.js."
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "webhook_url" {
  description = "Point the one Stripe webhook endpoint here (events: checkout.session.completed, customer.subscription.*)."
  value       = "${aws_apigatewayv2_api.api.api_endpoint}/webhook"
}
