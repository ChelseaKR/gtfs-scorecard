# gtfsscorecard.com -> https://gtfsscorecard.org (defensive domain redirect).
#
# One S3 website bucket per hostname, each 301-redirecting every request to the
# canonical .org site; Route 53 aliases the matching .com record at it. S3
# website endpoints are HTTP-only, so a browser that reaches
# http://gtfsscorecard.com is redirected to the https .org site. (A CloudFront +
# ACM distribution would add TLS on the .com itself; not worth it for a parked
# redirect -- see the note above `redirect_com_www` for why that verdict still
# holds now that www is served properly.)

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

# An S3 website endpoint picks the bucket from the request's Host header, not
# from the IP the client resolved. So a second hostname needs a second bucket
# named exactly after it -- there is no way to make one bucket answer for two
# names. `www.gtfsscorecard.com` had no bucket, and every request for it
# returned `404 NoSuchBucket` naming the bucket S3 looked for.
resource "aws_s3_bucket" "redirect_com_www" {
  bucket = "www.gtfsscorecard.com"
}

resource "aws_s3_bucket_public_access_block" "redirect_com_www" {
  bucket                  = aws_s3_bucket.redirect_com_www.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Redirect straight to the canonical .org rather than hopping through the .com
# apex: one 301 instead of two, and it keeps the two hostnames independent.
resource "aws_s3_bucket_website_configuration" "redirect_com_www" {
  bucket = aws_s3_bucket.redirect_com_www.id
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

# Aliasing www at the apex *record* (the previous attempt) cannot work: a
# Route 53 alias to a record in the same zone copies that record's answer, which
# here is a set of S3 website IPs. The request still leaves the browser with
# `Host: www.gtfsscorecard.com`, S3 still looks for a bucket of that name, and
# the answer is still `NoSuchBucket`. Only a real bucket named for the hostname
# fixes it, aliased at the *regional* website endpoint for the same reason the
# apex is (see the note on `com_apex`).
#
# A CloudFront + ACM distribution in front of both names would also work and
# would add TLS on the .com, which S3 website endpoints cannot do. Still not
# worth it: it is a certificate, a distribution, and a cache policy to own
# forever so that a defensive domain nobody is asked to type can answer https
# instead of http. Both .com hostnames now behave identically, and both hand the
# visitor to the https .org site on the first hop. Revisit only if the .com is
# ever printed somewhere people type it, or if browsers stop attempting http at
# all.
resource "aws_route53_record" "com_www" {
  zone_id = data.aws_route53_zone.com.zone_id
  name    = "www.gtfsscorecard.com"
  type    = "A"
  alias {
    name                   = aws_s3_bucket_website_configuration.redirect_com_www.website_domain
    zone_id                = aws_s3_bucket.redirect_com_www.hosted_zone_id
    evaluate_target_health = false
  }
}
