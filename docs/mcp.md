# MCP server: ask the scorecard from an AI assistant

The pipeline ships a read-only [Model Context Protocol](https://modelcontextprotocol.io)
server, so an MCP-capable assistant (Claude Desktop, Claude Code, and most
agent frameworks) can answer questions like "why did my grade drop and what do
I tell my vendor" grounded in the same published JSON the site serves.

There is no write surface and no key. Every tool is a read of
`gtfsscorecard.org`; the server is a thin, stdlib-only translation between
MCP's stdio framing and the public data contract in [`api.md`](api.md).

## Install and connect

The server runs today from the source tree, with nothing to clone:

```sh
uvx --from "git+https://github.com/ChelseaKR/gtfs-scorecard#subdirectory=pipeline" scorecard-mcp
```

Or from a checkout:

```sh
cd pipeline && uv sync
```

Claude Desktop / Claude Code config for a checkout:

```json
{
  "mcpServers": {
    "gtfs-scorecard": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/gtfs-scorecard/pipeline", "scorecard-mcp"]
    }
  }
}
```

Once gtfs-scorecard is on PyPI, `uvx gtfs-scorecard` starts the same
server, and the config shrinks to `"command": "uvx", "args":
["gtfs-scorecard"]`. Nothing has been uploaded yet;
[pypi.org/project/gtfs-scorecard](https://pypi.org/project/gtfs-scorecard/)
lists the versions that exist. The `gtfs-scorecard` executable is an alias
for `scorecard-mcp`, because MCP clients reading the registry entry launch
`uvx <package name>`. The command-line tool keeps its own name, so it runs as
`uvx --from gtfs-scorecard scorecard`. The Python import package is
`scorecard_pipeline` either way.

Point a fork or a local preview at itself with `SCORECARD_BASE_URL`.

## Tools

| Tool | What it answers |
| --- | --- |
| `search_agencies` | "Which agencies in Ontario do you track?" Name, id, ISO country, ISO subdivision code or name, legacy state/province, and grade filters over the covered catalog. Results carry `country`, `subdivision_code`, and `subdivision_name`; an omitted historical country is returned as `US`. |
| `get_scorecard` | "How is Unitrans doing and what should they fix first?" Overall grade, category summaries, every finding with its plain-language fix, effort hint, and fix-guide link, plus NTD readiness. |
| `coverage_stats` | "What countries and subdivisions do you cover?" Covered-set quality totals plus portable country and subdivision rollups. Counts describe tracked public feeds, not every operator in a country. |
| `national_stats` | Legacy United States policy view retained for existing clients. Its `ntd_readiness` member is US-only; its historical `stats` member still describes the complete covered corpus. New clients should use `coverage_stats` for geography-neutral totals. |
| `get_history` | "Why did my grade drop?" One feed's dated grades and scores, with every measurement-contract boundary marked, plus the findings that appeared or cleared between the two most recent snapshots — reported only when those two are the same measurement. |
| `explain_finding` | "What is `expired_calendar` and what do I tell my vendor?" The written fix recipe, the authoritative rule link, and, when a producing tool is named, that tool's fix path. A code with no written recipe returns the rule link alone and says so. |
| `get_rollup` | "What does my program's cohort share?" One rollup's shared fixes, grade distribution, and the members needing attention. |
| `get_evidence_packet` | "Give me something I can send my vendor." The deterministic remediation packet: the producer contract, the work items with their acceptance tests, and the feed identity they were measured against. |
| `coverage_for` | "Do you cover Ontario?" Covered-set totals for one ISO country or one subdivision inside it. |

`search_agencies` accepts `country` as an ISO 3166-1 alpha-2 code and
`subdivision` as either an ISO 3166-2 code or its practitioner-facing name.
The older `state` input remains available and also matches a portable
subdivision name, so existing prompts and clients keep working.

Results carry the same framing rules as the site: an unmeasured realtime
category reads as not yet published, findings are framed as fixes, and every
scorecard result names that it is a data-quality lens, not a compliance
determination. NTD is never presented as a global standard: it remains an
explicit United States policy overlay.

### What these tools refuse to say

An assistant paraphrases what it is handed, so a caveat that is not in the
payload does not survive the paraphrase. Three refusals are therefore carried in
the data rather than in the prose here:

- **`get_history` never describes a change across a measurement boundary.** Each
  point carries `comparable_with_previous`, and where that is `false` the two
  snapshots were scored under a different rubric, scoring profile, validator,
  reader archive profile, or measured-category set. A rubric release moving a
  score is not the feed moving. `latest_change` is likewise `comparable: false`
  with a stated reason rather than an empty list of changes, so "nothing moved"
  and "we will not claim anything here" cannot be confused.
- **`explain_finding` invents nothing for a code with no written recipe.** The
  project has a generated fallback wording used on scorecard pages next to a real
  count; it is deliberately not served here, because as an answer to "what does
  this code mean" it would be a sentence the project made up handed to an
  assistant as knowledge. An unrecognized `tool` likewise returns no guidance and
  lists the keys that are recognized, rather than naming the nearest vendor.
- **`coverage_for` reports an untracked place as not covered, never as zero
  feeds.** "This scorecard tracks nothing here" and "there is nothing here" are
  different statements and only the first is one this project can make.

Every response is bounded: history is capped at 120 dated points and rollup
members at 100, each with `returned`, `available`, and a `truncated` flag, so a
caller can see that it is holding a page rather than the whole thing.

## Publishing: PyPI, then the MCP Registry

The repository carries a `server.json` manifest for the
[official MCP Registry](https://registry.modelcontextprotocol.io/), naming the
server `io.github.ChelseaKR/gtfs-scorecard`, with one `packages[]` entry:
`registryType: pypi`, identifier `gtfs-scorecard`, at the version
`pipeline/pyproject.toml` declares. Nothing is on PyPI and nothing is in the
registry. The order matters, because the registry only lists metadata and
checks the package on PyPI when the manifest is submitted:

1. **PyPI.** `.github/workflows/pypi-publish.yml` runs on a signed release
   tag (`vX.Y.Z`). Its build job verifies the tag signature, checks that the
   tag, `pyproject.toml` and `server.json` agree, refuses to go on unless the
   `pypi` environment has a required reviewer, builds and smoke-tests the
   sdist and wheel, and uploads nothing. The publish job runs in the `pypi`
   environment, so it waits for that reviewer, then uploads with
   [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (no stored
   token). A last job reads the release back from PyPI and compares digests.
   PyPI needs a matching pending publisher registered first: PyPI project
   `gtfs-scorecard`, owner `ChelseaKR`, repository `gtfs-scorecard`,
   workflow `pypi-publish.yml`, environment `pypi`.
2. **MCP Registry.** After the upload exists, submit the manifest with the
   registry's `mcp-publisher` CLI from a checkout of the released commit:
   `mcp-publisher login github` (a device-code login), then
   `mcp-publisher publish`. The registry proves the package is ours by finding
   `mcp-name: io.github.ChelseaKR/gtfs-scorecard` in the PyPI description,
   which is why `pipeline/README.md` carries it.
3. **Record it.** Set `pypi_first_upload` in `server.json`'s
   `_meta["dev.chelseakr/distribution"]` to the uploaded version and drop the
   "once it is on PyPI" wording. `tests/test_distribution_claims.py` holds the
   wording to that field in both states.

Two details the registry enforces that are easy to get wrong. The server
name's casing must match the GitHub login exactly (`ChelseaKR`, not
`chelseakr`), because the namespace check is case-sensitive
([modelcontextprotocol/registry#689](https://github.com/modelcontextprotocol/registry/issues/689)).
And `description` is capped at 100 characters. Both were checked against the
registry's validate endpoint on 2026-10-05 with `mcp-publisher` 1.8.1.

History: a revision before 2026-07-05 declared `registryType: pypi` when
nothing was on PyPI and there was no way to put it there, so the entry was
removed rather than left standing as a false registry claim (REL-05). It is
back now that the upload path exists, held to the order above. The
distribution was named `scorecard-pipeline` through v1.5.0. That tag's run of
the publish workflow built and reached the upload step on 2026-10-09, and PyPI
refused the name as too similar to the existing, unrelated project
`scorecardpipeline`, so a pending publisher for it could not be registered and
nothing was uploaded. The distribution is `gtfs-scorecard` from 1.5.1 on; the
import package `scorecard_pipeline`, the `scorecard` command and the server
name above did not change.

The Claude Connectors Directory is a separate, heavier bar (a remote server, a
privacy policy, and a Team/Enterprise submission); per the cost guardrail it
waits until remote hosting has a named user.

## Design notes

The protocol core (`handle_request`, `call_tool`) is pure over an injected
fetch function and covered by `tests/test_mcp_server.py`; the stdio loop in
`main()` is the only I/O. `call_tool` dispatches through a table keyed by tool
name, and a test asserts that table and `TOOLS` name the same set: a tool listed
in `tools/list` but not dispatchable is a promise the server cannot keep.
`explain_finding` performs no fetch at all — the recipes, rule links and tool
profiles are all in this package. No SDK dependency, for the same reason the
submission Lambda is stdlib-only: the deployable surface stays small and the
tested core carries the logic.
