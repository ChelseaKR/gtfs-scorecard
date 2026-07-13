# Self-serve submission: a Lambda behind an HTTP API Gateway that opens a PR
# adding an agency to registry/intake.yaml (docs/roadmap.md, Year 1). The web form
# POSTs here.
#
# Uses API Gateway (not a Lambda function URL) because this account blocks public
# (auth NONE) Lambda function URLs — the same reason infra/alerts uses API GW.
# The handler reads the standard v2 payload shape that both emit.
#
# Build the deployment package before applying:
#   pip install ../../pipeline -t build && cp handler.py build/
#   terraform init && terraform apply

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
}

provider "aws" {
  region = var.region
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
  description = "owner/name of the scorecard repo the PR is opened against."
  type        = string
}

variable "github_token" {
  description = "Fine-scoped token with contents + pull_requests write."
  type        = string
  sensitive   = true
}

variable "allow_origin" {
  description = "CORS origin of the deployed web form. Never '*' for a state-changing, token-backed endpoint."
  type        = string
  default     = "https://gtfsscorecard.org"
}

variable "submit_shared_secret" {
  description = "If set, the form must send a matching X-Submit-Token header. A weak (client-visible) guard against trivial abuse; pair with a captcha for real protection."
  type        = string
  default     = ""
  sensitive   = true
}

data "archive_file" "submit" {
  type        = "zip"
  source_dir  = "${path.module}/build"
  output_path = "${path.module}/submit.zip"
}

resource "aws_iam_role" "submit" {
  name = "${var.project}-submit"
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
  role       = aws_iam_role.submit.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "submit" {
  function_name    = "${var.project}-submit"
  role             = aws_iam_role.submit.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.submit.output_path
  source_code_hash = data.archive_file.submit.output_base64sha256
  timeout          = 20
  memory_size      = 256

  environment {
    variables = {
      GITHUB_REPO          = var.github_repo
      GITHUB_TOKEN         = var.github_token
      ALLOW_ORIGIN         = var.allow_origin
      BASE_BRANCH          = "main"
      SUBMIT_SHARED_SECRET = var.submit_shared_secret
    }
  }
}

# Public front door via API Gateway — the same workaround as infra/alerts for
# the account-level block on public Lambda function URLs.
resource "aws_apigatewayv2_api" "submit" {
  name          = "${var.project}-submit"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "submit" {
  api_id                 = aws_apigatewayv2_api.submit.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.submit.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.submit.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.submit.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.submit.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = 5
    throttling_burst_limit = 10
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.submit.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.submit.execution_arn}/*/*"
}

output "submit_url" {
  description = "Set this as SCORECARD_SUBMIT_URL in web/src/config.js."
  value       = aws_apigatewayv2_stage.default.invoke_url
}
