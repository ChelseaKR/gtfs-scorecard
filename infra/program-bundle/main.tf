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
#
# Status: written, not yet applied (same posture as infra/compute and
# infra/instant-score; see infra/README.md). Everything that can charge
# anyone sits behind `payments_enabled`, which defaults to "0" and cannot be
# turned on while the Stripe configuration is blank: the preconditions on
# terraform_data.commercial_gate_guard fail the *plan*, not a warning a CI
# `plan -out && apply` would never show anyone (the family-greenhouse
# pattern this copies).
#
# API Gateway, not Lambda function URLs, for the same account-level reason
# as infra/alerts and infra/submit.
#
# Build the deployment package before applying:
#   pip install ../../pipeline -t build && cp *.py build/
#   terraform init && terraform apply

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
  description = "Fine-scoped token with actions: write on the repo (workflow_dispatch only)."
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
  description = "Restricted Stripe key: read Checkout Sessions only. Test-mode until the live decision is recorded."
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_webhook_secret" {
  description = "Signing secret of the one webhook endpoint pointed at this API."
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_price_ids" {
  description = "Stripe price ids for the four knobs in docs/program-plan.md. All four must be set before payments_enabled can be \"1\"."
  type        = map(string)
  default = {
    bundle_25  = ""
    bundle_100 = ""
    refresh_mo = ""
    refresh_yr = ""
  }
}

variable "stripe_price_ids_are_live" {
  description = "Set true only after confirming the price ids above were created in live mode. A live key paired with test-mode prices sells nothing and looks like it does."
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
    precondition {
      condition     = var.payments_enabled == "0" || !startswith(var.stripe_secret_key, "rk_live_") || var.stripe_price_ids_are_live
      error_message = "A live Stripe key is paired with price ids not confirmed live (stripe_price_ids_are_live = false)."
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
# expires each row 30 days after creation, in step with the S3 lifecycle rule
# on program-bundles/ (infra/artifacts) and bundle.DOWNLOAD_DAYS.
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

# ---------------------------------------------------------------------------
# Lambdas (one package, three entrypoints)
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
        ]
      },
      {
        # Read only, and only the bundle prefix: the download route presigns
        # exactly one object per capability and nothing else in the bucket.
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
    GITHUB_REPO           = var.github_repo
    GITHUB_TOKEN          = var.github_token
    WORKFLOW_FILE         = "report-bundle.yml"
    WORKFLOW_REF          = "main"
    SUBSCRIPTIONS_TABLE   = aws_dynamodb_table.subscriptions.name
    BUNDLES_TABLE         = aws_dynamodb_table.bundles.name
    ARTIFACTS_BUCKET      = var.artifacts_bucket
    ALLOW_ORIGIN          = var.allow_origin
    PAYMENTS_ENABLED      = var.payments_enabled
    STRIPE_SECRET_KEY     = var.stripe_secret_key
    STRIPE_WEBHOOK_SECRET = var.stripe_webhook_secret
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

# ---------------------------------------------------------------------------
# Front door
# ---------------------------------------------------------------------------

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

output "api_base" {
  description = "Set this as the BUNDLE_API_BASE Actions variable and window.SCORECARD_BUNDLE_URL in web/src/config.js."
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "webhook_url" {
  description = "Point the one Stripe webhook endpoint here (events: checkout.session.completed, customer.subscription.*)."
  value       = "${aws_apigatewayv2_api.api.api_endpoint}/webhook"
}
