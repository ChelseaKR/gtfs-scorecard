# 0039: A bounded large-feed tier for oversized official feeds

Status: accepted (2026-07)

## Context

Ingestion caps how large a feed may be before the Java validator ever opens it.
The archive-shape preflight in `fetch._validate_gtfs_archive` rejects a download
over 256 MiB, any single entry that expands past 512 MiB, an archive that expands
past 2 GiB in total, more than 200,000 entries, and any entry with an implausible
compression ratio. Those checks read the zip central directory only, so they run
before Apache Commons Compress or the validator parse attacker-controlled bytes;
they are the zip-bomb mitigation named in `vex.json` and in
`docs/audits/threat-model.md`.

The caps are deliberately tighter than a generic download ceiling because GTFS is
text and normally compresses well, so a multi-gigabyte expansion is far more
likely to be a bomb than a real schedule. That assumption holds for the roughly
1,300 feeds in the registry. It does not hold for a small set of legitimate
official feeds that carry an entire country's rail plus bus, or a whole
metropolitan network, in one export: Israel's national feed, Melbourne (PTV), HSL
Helsinki, Wiener Linien, and Carris Metropolitana. Their compressed download runs
past 256 MiB, or one table such as `stop_times.txt` expands past the single-entry
cap. Two of them, HSL and Wiener Linien, had been tracked in the registry and
silently failing the daily run as over-cap since they were added.

Raising the global caps to fit these feeds would weaken the guard for all 1,300
ordinary feeds, which is the wrong trade: a bomb submitted as an ordinary feed
would then be handed gigabytes of expansion room it has no reason to need. How
large a feed is allowed to be should follow from a curator's judgement about that
specific feed, not from the largest feed anyone ever wants to score.

## Decision

Add a per-record opt-in, `large_feed: true` in the registry, that moves one feed
onto a bounded larger tier. A curator sets it only after confirming the feed is a
real published export, not a bomb. The tier does three things and nothing else:

1. **Streams the download to disk with bounded memory.** A standard feed keeps
   the existing buffer-then-write path (`net.safe_get` into memory), so the 1,300
   ordinary feeds see byte-for-byte the same behaviour. A large feed routes
   through `net.safe_download`, which writes each response chunk straight to a
   `.netpart` file and renames on success. `safe_download` shares `_stream_guarded`
   with `safe_get`, so the SSRF check, the per-redirect public-address validation,
   and the declared and streamed size caps are identical; only the sink differs (a
   file writer instead of an in-memory accumulator). Memory use is one chunk
   regardless of feed size, so a hundreds-of-megabyte feed never has to fit in RAM
   before it touches disk.

2. **Raises only the raw size ceilings**, to a still-bounded larger level:
   512 MiB download, 2 GiB single entry, 4 GiB total (`fetch.LARGE_LIMITS`, an
   `ArchiveLimits` instance). `limits_for(large_feed)` returns that instance for
   an opted-in feed and `None` for a standard feed, where `None` means "read the
   module-level constants" and keeps those constants the single monkeypatchable
   source of truth for the standard tier. `_validate_gtfs_archive` and the
   fetch/reader path are parameterized on the limits, so the two tiers share one
   code path with different numbers.

3. **Gives the validator an explicit heap ceiling.** `run_validator(...,
   large_feed=True)` passes `-Xmx` (default 6g, read from
   `SCORECARD_LARGE_FEED_HEAP` so it is env-tunable without a code change) so a
   large feed validates against a known bound instead of the runner's implicit JVM
   default; ordinary feeds keep the default heap.

Every zip-bomb *shape* guard stays exactly as strict for a large feed as for an
ordinary one. The entry-count cap, the compression-ratio check, and the
central-directory-only inspection before Java opens the bytes are unchanged. Only
the raw size ceilings move, and only for a feed a curator opted in.

## Why this over the alternatives

**Not raising the global caps.** Covered above: it would widen the guard for every
feed to fit a handful, and the generic download ceiling (`net.MAX_DOWNLOAD_BYTES`,
512 MiB) is deliberately left where it is even for a large feed, so that guard is
never widened.

**Not splitting one oversized feed into per-mode or per-region records.** A
national feed could in principle be cut into rail, bus, and so on, each under the
standard caps. Rejected for now: it is real GTFS surgery (referential integrity
across `trips`, `stop_times`, `calendar`, and shared stops and shapes), it
redefines what "one feed record" means for identity, deduplication, and scoring,
and it is unnecessary, since the bounded tier already unblocks every feed we
currently want to score. Splitting is kept on the shelf as a possible future
extension if a feed ever exceeds even the large tier, or if a per-mode grade turns
out to be what agencies actually want.

## Consequences

- The tier is verified end to end on HSL Helsinki, whose `stop_times.txt` expands
  to about 1 GiB. Under the 6g heap the validator peaked around 3.5 GB RSS on a
  standard runner, which confirms the explicit heap is both necessary (the run
  would be at the mercy of the runner's default ceiling without it) and sufficient
  (it completes with headroom). First feeds on the tier: Israel's national feed,
  Melbourne (PTV), HSL, Wiener Linien, and Carris Metropolitana.
- Per-agency scoring stays isolated, so a large feed that ever OOMs or otherwise
  fails is recorded as that agency's failure, not a broken shard: the validator
  produces no `report.json`, `run_validator` raises, and only that feed's
  scorecard is affected while the rest of the run proceeds.
- The security argument is unchanged, and that is the point. The archive-shape
  preflight is the zip-bomb mitigation described in `vex.json` and
  `docs/audits/threat-model.md`; this change touches none of those guard rows. It
  moves raw size numbers for curator-opted-in feeds and adds a streaming download
  path that carries the same SSRF and size guards as the buffered one. The
  threat-model row ("Download, entry-count, entry-size, expanded-size, and
  compression-ratio preflight; bounded workers") still describes the mitigation
  accurately and needs no edit.

---

**References:**
- `pipeline/src/scorecard_pipeline/fetch.py`: `ArchiveLimits`, `LARGE_LIMITS`,
  `limits_for`, the parameterized `_validate_gtfs_archive`, `_fetch_to`, and
  `_download_with_mirror_fallback`.
- `pipeline/src/scorecard_pipeline/net.py`: `safe_download` sharing
  `_stream_guarded` with `safe_get`.
- `pipeline/src/scorecard_pipeline/validate.py`: `SCORECARD_LARGE_FEED_HEAP` and
  the `-Xmx` heap flag for large feeds.
- `pipeline/src/scorecard_pipeline/config.py` and `agencies.py`: the `large_feed`
  record field and its registry validation.
- `vex.json` and `docs/audits/threat-model.md`: the archive-shape zip-bomb
  mitigation this change leaves intact.
- `docs/global-coverage-roadmap.md`: large-feed sharding as a cross-cutting
  enabler.
