# Remote state in S3 (versioned bucket), the same bucket and settings as
# infra/artifacts/backend.tf. This module's state holds the GitHub token, the
# Stripe restricted key, and the webhook signing secret (they are Lambda
# environment variables), so it must not sit in a local terraform.tfstate on
# one laptop. No DynamoDB lock table, for the same single-operator reason as
# artifacts; add one (or upgrade to use_lockfile) if more than one person
# ever runs apply.
terraform {
  backend "s3" {
    bucket  = "gtfs-scorecard-tfstate-ckr"
    key     = "program-bundle/terraform.tfstate"
    region  = "us-west-2"
    encrypt = true
  }
}
