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

# Route 53 resolves an S3-website alias by matching the RECORD NAME to the
# bucket name, so the alias target must be the *regional* website endpoint
# (`s3-website-us-west-2.amazonaws.com`), not the bucket-prefixed
# `website_endpoint`. With the bucket-prefixed form Route 53 accepts the record
# but cannot evaluate it, and every query returns NOERROR with zero answers --
# which is exactly how this redirect was silently dead. `website_domain` is the
# regional form; `website_endpoint` is not.
resource "aws_route53_record" "com_apex" {
  zone_id = data.aws_route53_zone.com.zone_id
  name    = "gtfsscorecard.com"
  type    = "A"
  alias {
    name                   = aws_s3_bucket_website_configuration.redirect_com.website_domain
    zone_id                = aws_s3_bucket.redirect_com.hosted_zone_id
    evaluate_target_health = false
  }
}

# There is no `www.gtfsscorecard.com` bucket, and Route 53 matches an
# S3-website alias by record name -- so pointing www at the S3 endpoint can
# never resolve. Alias it to the apex record in this zone instead; the apex
# already 301s to https://gtfsscorecard.org/.
resource "aws_route53_record" "com_www" {
  zone_id = data.aws_route53_zone.com.zone_id
  name    = "www.gtfsscorecard.com"
  type    = "A"
  alias {
    name                   = aws_route53_record.com_apex.name
    zone_id                = data.aws_route53_zone.com.zone_id
    evaluate_target_health = false
  }
}
