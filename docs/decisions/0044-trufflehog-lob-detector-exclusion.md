# ADR 0044: The scheduled TruffleHog sweep excludes the Lob detector

**Status:** Accepted (2026-08-10)

## Context

Gate 3 of the secret-scanning setup ([SEC-19], `.github/workflows/trufflehog.yml`)
runs a weekly full-history TruffleHog scan with `--results=verified`, so it only
fails on credentials TruffleHog could confirm are live. That gate has been
failing.

Run 31359367918 on 2026-08-10 scanned 898,352 chunks and reported
`"verified_secrets": 94, "unverified_secrets": 0`, exiting 183. Every warning
line named the same detector: `Found verified Lob result`. Lob is a direct-mail
API. Nothing in this project sends mail.

The cause is the detector's key pattern:

```
\b((live|test)_[a-zA-Z0-9_]{35})\b
```

Underscores are word characters and are inside the character class, so the
pattern matches any identifier beginning `test_` and followed by exactly 35 more
word characters. A pytest function name of the right length is an exact match.
This repo has dozens of them, all in `pipeline/tests/`:

```
test_distinct_grades_get_distinct_colors
test_a_missing_publish_root_fails_closed
test_reindex_assembles_history_from_disk
test_alert_content_never_moves_the_score
test_repo_registry_includes_canada_pilot
```

Those are function names in tracked, readable Python source. They carry no
credential material.

The second half of the failure is the verifier. TruffleHog POSTs the candidate
to `https://api.lob.com/v1/us_verifications` with HTTP basic auth and treats a
403 response as proof of an active key with no billing method attached. From CI
and from a local run the endpoint answers in a way the detector reads as 403, so
every match is promoted to verified. It is not a burst or rate-limit artifact:
scanning a single file at `--concurrency=1` still returns `Verified: true`, with
a null `VerificationError`.

Confirmed before changing anything, using `trufflesecurity/trufflehog:3.96.0`
against a read-only mount of `pipeline/tests`:

```
docker run --rm -v "$PWD/pipeline/tests:/scan:ro" \
  trufflesecurity/trufflehog:3.96.0 filesystem /scan \
  --results=verified --include-detectors=Lob --json --no-update
```

339 verified Lob results, every `.Raw` a pytest identifier. The larger local
count includes `__pycache__` bytecode, which CI does not see; the git-history
scan reproduces the CI number from committed sources, including test names that
have since been renamed away.

## Decision

Pass `--exclude-detectors=Lob` alongside `--results=verified` in
`.github/workflows/trufflehog.yml`. The workflow carries a comment stating why.

The gate stays blocking. `--fail` is still supplied by the action's own
entrypoint, `--results` is unchanged, and no path exclusion, allowlist, or
`|| true` was added.

Path exclusions were considered and rejected. The matches sit in
`pipeline/tests/`, which is hand-written source that must keep getting scanned
by every other detector. Excluding the directory would blind the sweep to a real
credential pasted into a test.

Checks run before accepting this:

- `--exclude-detectors=Lob` suppresses the Lob findings and the job exits 0.
- Other detectors keep running under the same flag. A scratch file containing a
  GitHub token shape still produced a `Github` result, so the exclusion is
  scoped to the one detector named.

## Consequences

- The weekly sweep passes again and still fails on a verified secret from any
  other detector.
- A genuine Lob API key committed to this repo would not be caught by Gate 3.
  Residual coverage is gitleaks at Gate 1 (pre-commit) and Gate 2 (CI diff),
  which scan hand-written source with the default ruleset. Those are
  pattern-based and do not verify, so this is a real, accepted narrowing rather
  than an equivalent control. The project has no Lob account and no direct-mail
  integration, which is why the narrowing is acceptable.
- The exclusion should be revisited if the upstream detector tightens its
  pattern or stops reading 403 as verification. Removing the flag and getting a
  clean run is the test.
- This is a divergence from the SEC-19 row in the vendored security standard,
  which describes the gate as running without detector exclusions. It is
  recorded in [`docs/standards-conformance-gaps.md`](../standards-conformance-gaps.md).

## Alternatives rejected

- **Drop `--results=verified` or add `|| true`.** That turns a security control
  into decoration.
- **Exclude `pipeline/tests/` by path.** Wrong axis. The problem is one
  detector, not one directory, and the directory holds source worth scanning.
- **Rename the test functions.** Roughly 70 renames at HEAD, more in history,
  and the history cannot be edited. It would also encode a third-party regex
  quirk into this project's naming.
- **Pin an older TruffleHog.** The detector behaviour is not new, and pinning
  backwards would forfeit newer detectors.

[SEC-19]: ../standards/SECURITY-AND-SUPPLY-CHAIN-STANDARD.md
