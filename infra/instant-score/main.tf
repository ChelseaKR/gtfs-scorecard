# Instant scoring (growth-plans 03-A4 / 06 Tier 1): paste any GTFS Schedule
# URL on web/try.html and get a graded scorecard back in about a minute, no
# PR and no wait for the daily run. A container-image Lambda (needs the JVM
# validator, so a zip package like infra/alerts or infra/submit will not fit)
# behind API Gateway, the same workaround infra/alerts and infra/submit use
# for the account-level block on public Lambda function URLs.
#
# Status: written, not yet applied (see infra/README.md). Deliberately
# relaxes CLAUDE.md's single-digit-dollars-a-month guardrail: the cost is a
# funnel, not steady-state infrastructure (docs/decisions/0029-instant-score-funnel.md).
#
# Build and push the image before applying:
#   docker build -f infra/instant-score/Dockerfile -t <ecr-repo>:latest .
#   docker push <ecr-repo>:latest
#   terraform init
#   terraform apply -var="image_uri=<ecr-repo>:latest" -var="artifacts_bucket=gtfs-scorecard-artifacts"

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}

variable "project" {
  type    = string
  default = "gtfs-scorecard"
}

variable "region" {
  type    = string
  default = "us-west-2"
}

variable "image_uri" {
  description = "ECR image URI built from infra/instant-score/Dockerfile."
  type        = string
}

variable "artifacts_bucket" {
  description = "Bucket from infra/artifacts; scored results are written under scratch/."
  type        = string
}

variable "ratelimit_table" {
  description = "Shared per-IP rate-limit table (predates this module, like infra/alerts)."
  type        = string
  default     = "gtfs-scorecard-ratelimit"
}

variable "allow_origin" {
  description = "CORS origin of web/try.html. Never '*' for an endpoint that costs real compute per request."
  type        = string
  default     = "https://gtfsscorecard.org"
}

variable "result_base_url" {
  description = "Public base URL scored results are served from (the artifacts CDN)."
  type        = string
  default     = "https://gtfsscorecard.org"
}

variable "max_concurrent_jobs" {
  description = "Reserved concurrency: the queue-depth analog for this queueless, self-invoking design. Bounds how many scoring runs (each a JVM invocation) execute at once, independent of the per-IP and gateway-throttle limits above."
  type        = number
  default     = 5
}

data "aws_dynamodb_table" "ratelimit" {
  name = var.ratelimit_table
}

# This module's own table (unlike infra/alerts' subscriptions table, which
# predates it): a scoring job is ephemeral by design, so Terraform owns its
# full lifecycle. TTL auto-expires a row 30 days after creation, matching
# JOB_TTL_SECONDS in handler.py and the "shareable link expires unless
# claimed" funnel design (gtfs-scorecard-plans/06-beyond-static-unlocks.md).
resource "aws_dynamodb_table" "jobs" {
  name         = "${var.project}-instant-score-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

resource "aws_iam_role" "instant_score" {
  name = "${var.project}-instant-score"
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
  role       = aws_iam_role.instant_score.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "instant_score" {
  name = "${var.project}-instant-score"
  role = aws_iam_role.instant_score.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Jobs"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.jobs.arn
      },
      {
        Sid      = "RateLimit"
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = data.aws_dynamodb_table.ratelimit.arn
      },
      {
        Sid      = "PublishResult"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "arn:aws:s3:::${var.artifacts_bucket}/scratch/*"
      },
      {
        # Self-invoke: the sync route returns in well under a second and fires
        # a second, async invocation of this same function to do the actual
        # scoring (handler.py's _start_scoring), since a real feed can run
        # past API Gateway's 30s proxy limit.
        Sid      = "SelfInvokeAsync"
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:${var.project}-instant-score"
      }
    ]
  })
}

resource "aws_lambda_function" "instant_score" {
  function_name = "${var.project}-instant-score"
  role          = aws_iam_role.instant_score.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  timeout       = 300  # the async scoring half needs headroom for fetch + the JVM validator
  memory_size   = 2048 # headroom for the JVM validator, matching infra/compute's worker

  # Caps concurrent executions across both invocation shapes (the sync HTTP
  # route and the async self-invoke that does the actual scoring), so a burst
  # of requests cannot run an unbounded number of JVMs at once.
  reserved_concurrent_executions = var.max_concurrent_jobs

  environment {
    variables = {
      JOBS_TABLE       = aws_dynamodb_table.jobs.name
      RATELIMIT_TABLE  = var.ratelimit_table
      ARTIFACTS_BUCKET = var.artifacts_bucket
      RESULT_BASE_URL  = var.result_base_url
      ALLOW_ORIGIN     = var.allow_origin
      FUNCTION_NAME    = "${var.project}-instant-score"
    }
  }
}

# Public front door via API Gateway. A single $default route, same as
# infra/alerts and infra/submit: the handler dispatches by HTTP method alone
# (POST -> start a job, GET -> poll one, OPTIONS -> preflight), so it needs no
# path-specific routing, and CORS/OPTIONS are handled by the handler itself.
resource "aws_apigatewayv2_api" "instant_score" {
  name          = "${var.project}-instant-score"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "instant_score" {
  api_id                 = aws_apigatewayv2_api.instant_score.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.instant_score.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.instant_score.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.instant_score.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.instant_score.id
  name        = "$default"
  auto_deploy = true

  # Gateway-level throttling on top of the handler's own per-IP limit (5/hour):
  # a hard ceiling so a flood cannot reach a Lambda that runs a JVM and costs
  # real compute per invocation, unlike the alerts/submit endpoints.
  default_route_settings {
    throttling_rate_limit  = 5
    throttling_burst_limit = 10
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.instant_score.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.instant_score.execution_arn}/*/*"
}

output "instant_score_url" {
  description = "Set this as SCORECARD_TRY_URL in web/src/config.js."
  value       = aws_apigatewayv2_stage.default.invoke_url
}
