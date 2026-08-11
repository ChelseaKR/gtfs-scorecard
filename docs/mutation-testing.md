# Mutation testing (advisory)

Line and branch coverage prove a line ran. They do not prove a test would notice
if that line were wrong. Mutation testing checks the second thing: it changes the
code in small ways (a `>` becomes `>=`, a returned value becomes `None`, a string
literal is altered) and reruns the tests. A mutant that the tests still pass is
said to have "survived", and it marks an assertion the suite is missing.

This repo applies mutation testing to the scoring math in
`pipeline/src/scorecard_pipeline/`: `score.py` (the grade ladder and the
fix-priority tiers), `metrics.py` (the correctness deduction arithmetic and the
freshness slope), and `rt.py` (the realtime component weighting). A silent bug
in any of them mis-grades an agency or reorders the "top 3 things to fix".
Coverage of these modules is already high, which makes mutation score the
useful next signal. The invariant properties in `tests/test_properties.py` and
the frozen corpus in `tests/test_score_corpus.py` are part of the kill signal,
so a mutant has to get past the invariants as well as the examples.

Per [CODE-QUALITY-STANDARD.md](standards/CODE-QUALITY-STANDARD.md) §10 this is a
**REVIEW-GATE, not a merge gate**: run time makes it a poor per-PR blocker, and a
surviving mutant is often an equivalent one that needs a human to judge. It runs
weekly and on demand, never on a pull request, and it never blocks a merge.

## How to run it

```
make mutation            # run mutmut on the scoring modules, then print the results
make mutation-results    # reprint the last run without rerunning
```

Both run inside `pipeline/`. The scope and test command live in
`pipeline/pyproject.toml` under `[tool.mutmut]`: it mutates `score.py`,
`metrics.py`, and `rt.py`, and uses the unit tests for those modules plus the
property and corpus tests as the kill signal. A full run over the current scope
is a few minutes at roughly 20-30 mutants a second.

For a clean-cache baseline, delete the working copy first:

```
cd pipeline && rm -rf mutants && uv run mutmut run
```

`mutmut show <mutant-id>` prints the diff for one mutant, for example
`uv run mutmut show scorecard_pipeline.score.x__fix_tier__mutmut_7`.

The `mutants/` working copy, the caches, and the per-run report files are all
gitignored. The committed artifact is this document.

## Baseline

| Run | Mutants | Killed | Survived | Score |
|-----|---------|--------|----------|-------|
| 2026-06-30, `score.py` only, pre-existing suite | 106 | 62 | 44 | 58.5% |
| 2026-06-30, after four assertion tests | 106 | 70 | 36 | 66.0% |
| 2026-07-02, scope widened to `metrics.py` and `rt.py` | 1484 | 824 | 660 | 55.5% |
| 2026-08-10, first weekly run that finished | 1965 | 1191 | 745 | 60.6% |
| 2026-08-10, after triaging those 745 | 1965 | 1504 | 432 | 76.5% |

A further 29 mutants are reported as skipped in every run of the current scope
and are not counted in either column.

The weekly workflow aborted during baseline collection until a path bug was
fixed on 2026-08-09, so the 60.6% row is the first complete survivor list this
repository has had. All 745 of those survivors were read individually and sorted
into the three buckets below. CODE-QUALITY-STANDARD §10 asks for 70% on a core
safety module; the run now clears it.

## Triage of the 2026-08-10 survivors

| Bucket | Mutants | Meaning |
|--------|---------|---------|
| Real gap, now closed | 313 | Changed grading behaviour a reader would notice, and nothing failed. New assertions kill them. |
| Equivalent | 32 | Cannot change observable behaviour: unreachable inputs, or arithmetic that lands on the same number. |
| Out of contract | 400 | Changes something the rubric does not specify: wording, log lines, internal diagnostics, fetch plumbing. |

No scoring code changed. Only `tests/test_score.py`, `tests/test_metrics.py`,
and `tests/test_rt.py` gained assertions.

### Real gaps closed

Each entry names the requirement the new test states, not the mutant.

**`score.py`**

1. **Grade-band margins had no test below the F floor and none at a precision
   that could tell one decimal from two.** A score under every band still
   reports its distance to the D floor above and to F's own floor, the way
   `letter_grade` degrades to F, and both margins are published to one decimal
   like the score itself. `test_grade_margins_below_every_band_degrade_to_the_f_band`,
   `test_grade_margins_are_published_to_one_decimal`.

**`metrics.py`**

2. **Every freshness threshold sat unexercised on its own boundary.** Expiry day
   is already expired. A day of runway is never described as ended. A feed
   expired a full year is never softened, whatever its service type. Thirty days
   of runway still meets the Caltrans floor and raises nothing.
   `test_expiry_day_itself_counts_as_already_expired` and the four tests beside it.
   Worth knowing when reading those: `freshness()` warns below 30 days while
   `expiry_status()` puts exactly 30 into `expiring_soon`, so a feed with exactly
   30 days of runway is bucketed one way in the directory and warned about
   differently on its own page. Both readings satisfy the Caltrans "at least 30
   days" wording, so the tests pin the behaviour as it stands. Changing either
   line moves published grades and belongs in a governed rubric change.

3. **On-demand service was never scored.** `demand_response` is the second
   declared intermittent type; a recently lapsed on-demand calendar gets the
   same floor as a seasonal one and is named "on-demand" in its summary.
   `test_on_demand_service_is_softened_and_named_like_seasonal`.

4. **A finding's advertised points were never checked against what the category
   lost.** Every freshness finding except the expiring-soon card is worth the
   whole gap between its score and 100, and the score bottoms out at 0 when
   deductions stack. `test_finding_points_match_the_points_the_category_lost`,
   `test_the_score_floor_is_zero_when_deductions_stack`.

5. **The expiring-soon card's softened estimate was unpinned**, though the code
   comment calls changing it a governed methodology change. It falls one point
   per day of runway lost and stays below the raw category loss.
   `test_expiring_soon_card_advertises_a_softened_point_estimate`.

6. **A `feed_info` with only one of its two validity dates was still counted as
   complete** by every existing example. One date cannot bound a window.
   `test_feed_info_needs_both_validity_dates`.

7. **No test asserted that a finding is publishable at all.** Every finding the
   category can emit carries a severity from the published set, the four
   plain-language fields, and one instance, because the site prints the instance
   count on the card. One case per finding code.
   `test_every_finding_the_category_can_emit_is_publishable`.

8. **The correctness summary and details were unasserted.** The summary states
   how many kinds of issue, how many instances, and the split by severity, and
   only says "no problems" when there are none. The details carry the validator
   version that produced the grade. `test_summary_reports_how_much_the_validator_found`,
   `test_details_carry_validator_provenance_and_counts`.

9. **A feed with no readable end date published its countdown untested.** It is
   null, which is what two dozen downstream modules read it as.
   `test_an_unknown_expiry_publishes_a_null_countdown`.

10. **Legacy horizon records.** All three published status values are
    authoritative when a record states one, and a day count written as a whole
    float still resolves. `test_every_published_status_value_is_taken_as_written`,
    `test_a_whole_number_written_as_a_float_still_resolves`.

**`rt.py`**

11. **The realtime thresholds were only ever sampled well away from the line.**
    A 60-second lag is fresh. An hour-old header is already lapsed, and the
    lapsed and stale findings never both fire. Ninety percent of vehicles on
    route clears the flag. Drift is called implausible past thirty minutes, not
    at thirty. `test_a_sixty_second_lag_still_reads_as_fresh` and the three
    tests beside it.

12. **The drift finding could have started costing points silently.** It informs
    and cannot become a top fix; weighting it is a governed change.
    `test_drift_is_flagged_only_past_thirty_minutes_and_never_scored`.

13. **The lapsed card's points were unpinned** where its gentler sibling's were
    tested. It is worth the whole freshness component it replaces.
    `test_lapsed_feed_reads_as_freshness_failure_not_zero`.

14. **The legacy fallback that infers feed kinds from the window was untested.**
    An agency that publishes TripUpdates alone is not marked down for two feeds
    it never had. `test_a_legacy_window_assesses_only_the_kinds_it_sampled`.

15. **Realtime findings had the same publishability gap as freshness**, plus
    per-kind severities. Same shape of test, one case per code.
    `test_every_finding_the_category_can_emit_is_publishable`.

16. **The numbers the category summary quotes were never read back.** Scheduled
    trips in the window, covered trips, vehicles checked, and the percentages
    beside them are published at one decimal.
    `test_details_publish_the_numbers_the_summary_quotes`.

17. **The schedule lookup that produces the coverage denominator had unpinned
    edges.** A trip is in service from its exact departure second through its
    last arrival, including after midnight. Calendar ranges include their own
    start and end dates. All seven weekday columns drive their own day. The
    seconds field counts. Departure is preferred and arrival is the fallback. A
    row with no usable time is skipped without ending the scan. A table missing
    columns reads as no service rather than raising, and a feed with no agency
    timezone is read as UTC. Nine tests across the schedule-lookup classes in
    `tests/test_rt.py`.

18. **`fetch_sample` kept observations it should drop and dropped some it should
    keep.** A TripUpdate naming no trip cannot cover a scheduled trip and does
    not stop the scan. Alerts are parsed for the alerts feed and no other. Both
    vehicle coordinates are kept, since plausibility needs both.
    `test_trip_update_without_a_trip_id_is_not_counted`,
    `test_service_alerts_sample_carries_its_alert_observations`.

### Accepted survivors

432 mutants survive on purpose. Grouped, with the reason each group is left
alone:

**Equivalent (32).** Not killable, and a test written to chase one would assert
nothing.

- Rounding digits on `round(100.0 - score, 1)` in the two intermittent-lapse
  findings (6): that branch pins the score at exactly 50.0, so every rounding
  precision yields the same number.
- Rounding digits on the expiring-soon deduction (3): the expression is always
  the integer `80 - days_left`.
- The unknown-severity fallback in `correctness()` (2): `validate.py` normalizes
  every notice severity into the three-value set before a report reaches scoring.
- The year-9989 overflow guard in `_years_after` (2): the argument is a snapshot
  date.
- The `translation` fallback in `_has_text` (2): a protobuf `TranslatedString`
  always has the field.
- Tolerant-reader defaults for `service_id` and `trip_id` (10): the mutated
  default is falsy or unmatchable in exactly the same way as the original.
- The freshness interpolation endpoints in `realtime` (2): the linear formula
  returns the same fraction as the two shortcuts it replaces.
- `(1 + fresh_fraction)` in the lapsed deduction (1): the branch only fires when
  `fresh_fraction` is 0.
- `>= 0` in the finding rescale filter (1): zero times any scale is zero.
- The upper score clamp in `realtime` (1): no component fraction can exceed 1.
- `score + GRADE_BANDS[-1][0]` in `grade_margins` (1): the F floor is 0.0.
- The lowest tier value in `_fix_tier` (1): nothing compares a tier to a
  literal, and it is already the least urgent bucket.

**Out of contract (400).** The rubric does not specify these.

- Wording and copy (313): the case and content of `what`, `why`, `fix`,
  `effort`, and summary sentences. The suite asserts the numbers inside those
  sentences, the finding codes, and the severities, and deliberately does not
  pin the prose word for word.
- Fetch and capture plumbing (49): `fetch_sample` request arguments, archive
  paths, log call arguments, and `capture_window` defaults. No unit test drives
  the network path end to end, and polling etiquette is documented in
  `docs/feeds.md` rather than scored.
- `methodology()` metadata (28): dict keys and prose in the published
  `scoring.json` description. Its load-bearing values (weights, grade bands,
  severity deductions, count-multiplier tiers) are pinned by
  `test_methodology_exposes_weights_bands_and_deductions`.
- Coarse duration switch points in `_human_duration` (6): where a stale header's
  age flips from seconds to minutes to hours. The function promises a coarse
  reading, not a specific switch point.
- `ValueError` message wording (3): internal diagnostics. The tests assert the
  error is raised under the right condition.
- `label = None` in the unreachable-feed sentence (1): one word of copy.

Re-triage when any of the three modules changes. A new survivor outside these
groups is a missing assertion, not noise.

## Notable survivors the coverage tests missed (2026-06, `score.py`)

These mutants survived the original 100%-coverage suite. Each was a real gap:
the line ran in a test, but no assertion pinned its behaviour. Tests in
`tests/test_score.py` kill them.

1. **The letter grade was never asserted end to end.** Mutating
   `grade=letter_grade(overall)` to `grade=None` in `build_scorecard` survived.
   `letter_grade()` was tested in isolation and `overall_score` was checked, but
   nothing asserted that a built `Scorecard` carries the grade for its own score.
   Killed by `test_build_scorecard_sets_the_letter_grade`.

2. **A zero-point note could have been offered as a fix.** Mutating the top-fix
   filter `f.deduction > 0` to `f.deduction >= 0` survived. The code comment
   promises a zero-deduction note is never surfaced as something to fix first, but
   no test mixed one in to confirm it. Killed by
   `test_zero_deduction_finding_is_never_a_top_fix`.

3. **The severity tiers rode on point ordering, not the severity check.**
   Mutating the `"ERROR"` literal in `_fix_tier`, and mutating the WARNING branch
   (`==` to `!=`, and its tier value), all survived. The existing tier tests used
   findings whose point deductions already matched the intended order, so a
   severity that was not recognized still sorted correctly by points. Killed by
   `test_error_severity_outranks_a_heavier_lower_tier_fix` and
   `test_warning_outranks_a_heavier_informational_fix`, which give the
   higher-tier finding a smaller deduction so only the tier can explain the order.
