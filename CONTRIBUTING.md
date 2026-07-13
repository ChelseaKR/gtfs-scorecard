# Contributing

Thanks for helping improve the GTFS Scorecard.

## Add or fix an agency's feed

The most common contribution is adding an agency or correcting a feed URL. That
path is documented end to end in [docs/add-your-agency.md](docs/add-your-agency.md):
add an entry to `registry/intake.yaml` and open a pull request. You can also use the
self-serve form at [gtfsscorecard.org](https://gtfsscorecard.org/submit.html).

## Develop on the pipeline

The scorer lives in `pipeline/` (Python 3.12+, [uv](https://docs.astral.sh/uv/),
and Java 17 for the validator). Before opening a pull request, run the same
merge-blocking gate CI runs:

```sh
make verify
```

This runs lint, format-check, `mypy --strict`, tests with the 92% branch-coverage
floor, the AAA design-token contrast check, the plain-language readability
check, and the no-bare-TODO/FIXME/HACK grep, in that order — see the root
`Makefile` and `.github/workflows/ci.yml`, which invoke the same steps. This
repo's applicable standards live in [docs/standards/](docs/standards/); see
`docs/standards/README.md` for how a repo here declares and gates conformance.

The frontend is in `web/` (vanilla JS, no build step) and reads the published
JSON artifacts. Keep scoring and other logic in the pipeline so the frontend
stays a thin renderer of precomputed JSON.

## Conventions

- Conventional commits, small and focused.
- Findings are framed as fixes, never as failures; plain practitioner language.
- Accessibility is non-negotiable: the site targets WCAG 2.2 AAA and meets Section 508.
  The `Accessibility` axe gate and the contrast gate are merge-blocking; see the
  [conformance report](docs/accessibility.md), the [VPAT](docs/vpat.md), and the manual
  [test script](docs/accessibility-testing.md).

The full project guide is in [CLAUDE.md](CLAUDE.md), and design decisions are
recorded as ADRs under [docs/decisions/](docs/decisions/).
