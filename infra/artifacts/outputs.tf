output "bucket_name" {
  description = "S3 bucket holding published artifacts."
  value       = aws_s3_bucket.artifacts.bucket
}

output "cdn_domain" {
  description = "CloudFront domain; set this as ARTIFACTS_CDN for the web app."
  value       = aws_cloudfront_distribution.artifacts.domain_name
}
