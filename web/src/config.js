// Optional site config, loaded before app.js. Keeping it separate means
// pointing the web app at a CDN (docs/roadmap.md, Year 1) is a one-line change
// here, not an edit to application code.
//
// Leave SCORECARD_DATA_BASE null to read artifacts from the repo/site layout
// (the default for the pilot on GitHub Pages). Set it to the CloudFront origin
// once infra/artifacts is applied, e.g.:
//
//   window.SCORECARD_DATA_BASE = "https://d1234abcd.cloudfront.net/data/artifacts";
//
// Reading from the same GitHub Pages origin the site deploys to: the CloudFront
// mirror only refreshes from the daily job's S3 sync, so a manual artifact fix
// (or any push) would not reach it and the app would serve stale data. Pages is
// updated by every deploy, so the app and the published data never drift. To
// re-enable the CDN, set this back to the CloudFront origin; the daily job keeps
// it in sync.
window.SCORECARD_DATA_BASE = null;

// Endpoint for the self-serve "add your agency" form (API Gateway → Lambda,
// from infra/submit). The form POSTs here and the Lambda opens a PR. Left null
// disables the live form and falls back to the manual walkthrough link.
window.SCORECARD_SUBMIT_URL = "https://oieyqljvl1.execute-api.us-west-2.amazonaws.com";

// Opt-in feed-health alerts (infra/alerts): an HTTP API Gateway fronting the
// Lambda (a function URL is blocked on this account). The subscribe form POSTs
// to <url>/subscribe; abuse is bounded by server-side rate limiting and double
// opt-in, so no client secret is needed. Null disables the form.
window.SCORECARD_SUBSCRIBE_URL = "https://5oemr66b9a.execute-api.us-west-2.amazonaws.com";

// Instant scoring (infra/instant-score): an HTTP API Gateway fronting a
// container-image Lambda that scores any GTFS URL on demand
// (docs/decisions/0029-instant-score-funnel.md). web/try.html POSTs
// <url>/score and polls <url>/score/<job_id>. Null falls back to the GitHub
// Issue Form on the same page, so try.html is never a dead end. Set this once
// the module is applied.
window.SCORECARD_TRY_URL = null;
