# Threat model

**Date:** 2026-07-10  
**Assets:** scoring integrity, public artifacts, subscription data, cloud roles, release
artifacts, and the availability of the scoring service.

| Threat | Boundary | Mitigation |
| --- | --- | --- |
| SSRF through a submitted feed URL | Internet to fetcher | Public HTTP(S) only, DNS/IP checks on every redirect, bounded download |
| Zip bomb or parser exhaustion | Feed bytes to validator | Download, entry-count, entry-size, expanded-size, and compression-ratio preflight; bounded workers |
| Malicious GTFS/RT protobuf or CSV | Feed bytes to parsers | Isolated scheduled/container execution, canonical validator, schema/normalization checks |
| Artifact or score tampering | CI to Pages/S3 | Protected `main`, required checks, OIDC roles, deterministic artifacts, hashes and provenance |
| Dependency/workflow compromise | External packages/actions | Locked Python graph, dependency review/audit, CodeQL/SAST, SHA-pinned Actions, container scan |
| Forged agency claim | Public issue to registry | Human evidence review; no automatic verification or registry mutation |
| Subscription abuse or address disclosure | Public form to alert store | Double opt-in, rate limits, generic responses, least-privilege delivery path |
| Secret leakage | Logs/workflows | Gitleaks, minimal permissions, OIDC rather than long-lived cloud keys, no private proof in issues |
| Denial of service | Public instant-score endpoint | Per-IP limits, reserved concurrency, timeouts, job TTL, safe generic errors |

Residual risks are upstream validator CVEs without a patched release, DNS rebinding between
resolution and connect, and provider outages. The time-bounded VEX, curated registry,
resource caps, mirrors, and graceful degradation reduce those risks; they do not erase them.
