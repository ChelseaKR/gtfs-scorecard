# Year 2 fan-out compute (docs/roadmap.md): EventBridge -> SQS -> worker pool,
# plus a scheduled realtime sampler. Status: written, not yet applied. The
# pilot and Year 1 run on the GitHub Actions matrix (scorecard.yml); this is the
# path for when the daily run outgrows it.
#
# Decision record: docs/decisions/0003-fan-out-compute.md.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Cost allocation: see the note in infra/artifacts/main.tf. This module is not
# applied yet, so tagging it now means the fan-out compute is attributable from
# its first apply rather than after a spend surprise.
locals {
  default_tags = {
    project    = var.project
    component  = "compute"
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
variable "artifacts_bucket" {
  description = "Bucket from infra/artifacts; workers upload scored artifacts here."
  type        = string
}
variable "worker_image_uri" {
  description = "ECR image URI built from infra/compute/Dockerfile."
  type        = string
}

# ---------- work queue ----------

resource "aws_sqs_queue" "dlq" {
  name                    = "${var.project}-work-dlq"
  sqs_managed_sse_enabled = true # encrypt at rest with SQS-managed keys
}

resource "aws_sqs_queue" "work" {
  name                       = "${var.project}-work"
  visibility_timeout_seconds = 300  # >= worker timeout
  sqs_managed_sse_enabled    = true # encrypt at rest with SQS-managed keys
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

# ---------- producer: one message per agency, daily ----------

data "archive_file" "enqueue" {
  type        = "zip"
  source_dir  = "${path.module}/build-enqueue" # CI assembles: pipeline + enqueue.py
  output_path = "${path.module}/enqueue.zip"
}

resource "aws_iam_role" "enqueue" {
  name               = "${var.project}-enqueue"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "enqueue" {
  role = aws_iam_role.enqueue.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = aws_sqs_queue.work.arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "enqueue_logs" {
  role       = aws_iam_role.enqueue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "enqueue" {
  function_name    = "${var.project}-enqueue"
  role             = aws_iam_role.enqueue.arn
  runtime          = "python3.12"
  handler          = "enqueue.handler"
  filename         = data.archive_file.enqueue.output_path
  source_code_hash = data.archive_file.enqueue.output_base64sha256
  timeout          = 60
  environment {
    variables = { WORK_QUEUE_URL = aws_sqs_queue.work.url }
  }
}

resource "aws_cloudwatch_event_rule" "daily" {
  name                = "${var.project}-daily"
  schedule_expression = "cron(23 13 * * ? *)" # 13:23 UTC, matches the CI cron
}

resource "aws_cloudwatch_event_target" "daily_enqueue" {
  rule = aws_cloudwatch_event_rule.daily.name
  arn  = aws_lambda_function.enqueue.arn
}

resource "aws_lambda_permission" "daily_enqueue" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.enqueue.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily.arn
}

# ---------- worker: validator container draining the queue ----------

resource "aws_iam_role" "worker" {
  name               = "${var.project}-worker"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "worker" {
  role = aws_iam_role.worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.work.arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "arn:aws:s3:::${var.artifacts_bucket}/data/artifacts/*"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "worker_logs" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "worker" {
  function_name = "${var.project}-worker"
  role          = aws_iam_role.worker.arn
  package_type  = "Image"
  image_uri     = var.worker_image_uri
  timeout       = 300
  memory_size   = 2048 # headroom for the JVM validator
  environment {
    variables = { ARTIFACTS_BUCKET = var.artifacts_bucket }
  }
}

resource "aws_lambda_event_source_mapping" "worker" {
  event_source_arn        = aws_sqs_queue.work.arn
  function_name           = aws_lambda_function.worker.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
  scaling_config {
    maximum_concurrency = 20 # raise to scale; SQS caps the fan-out
  }
}

# ---------- realtime sampler: scheduled Fargate task, peak windows only ----------
#
# Realtime quality needs samples across a window (polled every 30-60s during
# representative service hours), which does not fit a once-a-day batch. This
# runs the sampler as a Fargate task on a schedule so cost tracks the sampling
# windows, not the clock. ECS cluster/task wiring is omitted here for brevity;
# the schedule below is the shape (three short windows a day).

resource "aws_cloudwatch_event_rule" "rt_windows" {
  for_each            = toset(["0 15 * * ? *", "0 20 * * ? *", "0 1 * * ? *"]) # AM/midday/PM UTC
  name                = "${var.project}-rt-${replace(each.key, " ", "-")}"
  schedule_expression = "cron(${each.key})"
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

output "work_queue_url" {
  value = aws_sqs_queue.work.url
}
