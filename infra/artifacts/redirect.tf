# gtfsscorecard.com -> https://gtfsscorecard.org (defensive domain redirect).
#
# An S3 website bucket that 301-redirects every request to the canonical .org
# site; Route 53 aliases the .com apex and www at it. S3 website endpoints are
# HTTP-only, so a browser that reaches http://gtfsscorecard.com is redirected to
# the https .org site. (A CloudFront + ACM distribution would add TLS on the
# .com itself; not worth it for a parked redirect.)

data "aws_route53_zone" "com" {
  name = "gtfsscorecard.com."
}

resource "aws_s3_bucket" "redirect_com" {
  bucket = "gtfsscorecard.com"
}

# A redirect-all website bucket serves no objects, so it needs no public read.
# Keep all public access blocked explicitly rather than relying on S3 defaults.
resource "aws_s3_bucket_public_access_block" "redirect_com" {
  bucket                  = aws_s3_bucket.redirect_com.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_website_configuration" "redirect_com" {
  bucket = aws_s3_bucket.redirect_com.id
  redirect_all_requests_to {
    host_name = "gtfsscorecard.org"
    protocol  = "https"
  }
}

resource "aws_route53_record" "com_apex" {
  zone_id = data.aws_route53_zone.com.zone_id
  name    = "gtfsscorecard.com"
  type    = "A"
  alias {
    name                   = aws_s3_bucket_website_configuration.redirect_com.website_endpoint
    zone_id                = aws_s3_bucket.redirect_com.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "com_www" {
  zone_id = data.aws_route53_zone.com.zone_id
  name    = "www.gtfsscorecard.com"
  type    = "A"
  alias {
    name                   = aws_s3_bucket_website_configuration.redirect_com.website_endpoint
    zone_id                = aws_s3_bucket.redirect_com.hosted_zone_id
    evaluate_target_health = false
  }
}
