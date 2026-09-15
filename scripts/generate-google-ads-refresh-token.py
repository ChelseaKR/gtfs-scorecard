#!/usr/bin/env python3
"""One-time interactive script: exchange a Google Cloud OAuth client for a
Google Ads API refresh token (docs/google-ads-upload-setup.md, step 4).

Run this once, by hand, on your own machine -- never in CI, never on the
Lambda. It opens a browser tab, asks you to sign in and grant access, and
prints a refresh token to the terminal. That token is
``google_ads_refresh_token`` in whichever tfvars or secret store holds the
rest of infra/program-bundle's configuration (never committed, never
printed anywhere but this terminal).

Before running this you need:
  1. A Google Cloud project with the Google Ads API enabled.
  2. An OAuth 2.0 client of type "Desktop app" created in that project
     (Google Cloud Console -> APIs & Services -> Credentials -> Create
     Credentials -> OAuth client ID -> Desktop app), downloaded as JSON.
     A Desktop app client needs no redirect URI configured in the
     console -- ``google-auth-oauthlib`` handles that locally.

Usage:
    pip install google-ads   # pulls in google-auth-oauthlib
    python3 scripts/generate-google-ads-refresh-token.py \\
        --client-secrets /path/to/client_secret.json

Mirrors the shape of Google's own published sample
(developers.google.com/google-ads/api/samples/generate-user-credentials):
same scope, same localhost-callback approach. Written out here rather than
pointed at only because a script an owner can read end to end before
running it -- on a machine that is about to grant it access to a real
Google account -- is worth the ~40 lines.
"""

from __future__ import annotations

import argparse
import sys

# The one scope the Google Ads API needs; granting anything narrower or
# broader is not meaningful here.
SCOPE = "https://www.googleapis.com/auth/adwords"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--client-secrets",
        required=True,
        help="Path to the Desktop app OAuth client JSON downloaded from Google Cloud Console.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Local port for the OAuth callback (default: 8080; change if that port is busy).",
    )
    args = parser.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "google-auth-oauthlib is not installed. Run `pip install google-ads` first "
            "(it pulls this in), or `pip install google-auth-oauthlib` on its own.",
            file=sys.stderr,
        )
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secrets, scopes=[SCOPE])
    # A browser tab opens for you to sign in and consent; this call blocks
    # until that finishes.
    credentials = flow.run_local_server(port=args.port)

    if not credentials.refresh_token:
        # Happens when this exact client has already been authorized once
        # before and Google does not re-issue a refresh token on a repeat
        # consent. Revoke the earlier grant (myaccount.google.com/permissions)
        # and run this again, or create a fresh OAuth client.
        print(
            "No refresh token was returned. This usually means this OAuth client was already "
            "authorized once before -- revoke access at "
            "https://myaccount.google.com/permissions and run this again.",
            file=sys.stderr,
        )
        return 1

    print("\nAuthorization complete. Refresh token:\n")
    print(credentials.refresh_token)
    print(
        "\nSet this as google_ads_refresh_token in whichever tfvars or secret store already "
        "holds infra/program-bundle's other sensitive values. Do not commit it, and do not "
        "paste it anywhere but that one place."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
