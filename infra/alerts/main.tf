# Opt-in alerts: a Lambda behind a function URL that takes a subscribe request,
# stores a pending (unverified) row, and emails a double opt-in confirm link;
# the confirm route marks the row verified. The web form (web/subscribe.html)
# POSTs here. See docs/decisions/0004-opt-in-alerts.md.
#
# The DynamoDB table is created out-of-band (it predates this module) and read
# by the pipeline; here it is a data source, so Terraform never owns or recreates
# it. State for this small stack is local (single operator), matching infra/submit.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
}

# Cost allocation: see the note in infra/artifacts/main.tf. `project` is the
# activated cost-allocation tag key, so untagged resources are invisible to the
# per-project budget; declaring it here covers every taggable resource in this
# module.
locals {
  default_tags = {
    project    = var.project
    component  = "alerts"
    managed-by = "terraform"
  }
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

variable "table_name" {
  type    = string
  default = "gtfs-scorecard-subscriptions"
}

variable "ratelimit_table" {
  type    = string
  default = "gtfs-scorecard-ratelimit"
}

variable "ses_from" {
  type    = string
  default = "alerts@gtfsscorecard.org"
}

variable "allow_origin" {
  description = "CORS origin of the web form. Never '*' for a state-changing endpoint."
  type        = string
  default     = "https://gtfsscorecard.org"
}

variable "subscribe_shared_secret" {
  description = "Optional X-Subscribe-Token. Empty by design: the public form cannot hold a real secret, so abuse is bounded by server-side rate limiting (per-IP window + per-address cooldown) plus double opt-in and CORS."
  type        = string
  default     = ""
  sensitive   = true
}

data "aws_dynamodb_table" "subscriptions" {
  name = var.table_name
}

data "aws_dynamodb_table" "ratelimit" {
  name = var.ratelimit_table
}

data "aws_ses_email_identity" "sender_domain" {
  email = "gtfsscorecard.org"
}

data "archive_file" "alerts" {
  type        = "zip"
  source_file = "${path.module}/handler.py"
  output_path = "${path.module}/alerts.zip"
}

resource "aws_iam_role" "alerts" {
  name = "${var.project}-alerts"
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
  role       = aws_iam_role.alerts.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "alerts" {
  name = "${var.project}-alerts"
  role = aws_iam_role.alerts.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Store"
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
        Resource = [
          data.aws_dynamodb_table.subscriptions.arn,
          data.aws_dynamodb_table.ratelimit.arn,
        ]
      },
      {
        Sid      = "Send"
        Effect   = "Allow"
        Action   = ["ses:SendEmail"]
        Resource = data.aws_ses_email_identity.sender_domain.arn
      }
    ]
  })
}

resource "aws_lambda_function" "alerts" {
  function_name    = "${var.project}-alerts"
  role             = aws_iam_role.alerts.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.alerts.output_path
  source_code_hash = data.archive_file.alerts.output_base64sha256
  timeout          = 15
  memory_size      = 128

  environment {
    variables = {
      SUBSCRIPTIONS_TABLE     = var.table_name
      RATELIMIT_TABLE         = var.ratelimit_table
      SES_FROM                = var.ses_from
      ALLOW_ORIGIN            = var.allow_origin
      SUBSCRIBE_SHARED_SECRET = var.subscribe_shared_secret
    }
  }
}

# Public front door. A Lambda function URL would be simpler, but this account
# blocks public (auth NONE) function URLs (AccessDeniedException despite a correct
# resource policy and no org SCP), so an HTTP API Gateway fronts the Lambda
# instead — a different invoke path (lambda:InvokeFunction) the block does not
# cover. The handler reads the same v2 event shape, so its code is unchanged. CORS
# and OPTIONS are handled by the handler, so the API needs no CORS config.
resource "aws_apigatewayv2_api" "alerts" {
  name          = "${var.project}-alerts"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "alerts" {
  api_id                 = aws_apigatewayv2_api.alerts.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.alerts.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.alerts.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.alerts.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.alerts.id
  name        = "$default"
  auto_deploy = true

  # Gateway-level throttling on top of the handler's per-IP / per-address limits:
  # a hard ceiling on requests/second so a flood cannot reach the Lambda at all.
  default_route_settings {
    throttling_rate_limit  = 10
    throttling_burst_limit = 20
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.alerts.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.alerts.execution_arn}/*/*"
}

output "subscribe_url" {
  description = "Set this as SCORECARD_SUBSCRIBE_URL in web/src/config.js."
  value       = aws_apigatewayv2_stage.default.invoke_url
}
