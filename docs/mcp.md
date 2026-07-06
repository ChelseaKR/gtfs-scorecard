# MCP server: ask the scorecard from an AI assistant

The pipeline ships a read-only [Model Context Protocol](https://modelcontextprotocol.io)
server, so an MCP-capable assistant (Claude Desktop, Claude Code, and most
agent frameworks) can answer questions like "why did my grade drop and what do
I tell my vendor" grounded in the same published JSON the site serves.

There is no write surface and no key. Every tool is a read of
`gtfsscorecard.org`; the server is a thin, stdlib-only translation between
MCP's stdio framing and the public data contract in [`api.md`](api.md).

## Install and connect

From a checkout:

```sh
cd pipeline && uv sync
```

Claude Desktop / Claude Code config:

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

Point a fork or a local preview at itself with `SCORECARD_BASE_URL`.

## Tools

| Tool | What it answers |
| --- | --- |
| `search_agencies` | "Which agencies in Ontario do you track?" Name, id, state/province, and grade filters over the national catalog. |
| `get_scorecard` | "How is Unitrans doing and what should they fix first?" Overall grade, category summaries, every finding with its plain-language fix, effort hint, and fix-guide link, plus NTD readiness. |
| `national_stats` | "How is transit data doing nationally?" The stats rollup and NTD certification readiness, nationally and by state. |

Results carry the same framing rules as the site: an unmeasured realtime
category reads as not yet published, findings are framed as fixes, and every
scorecard result names that it is a data-quality lens, not a compliance
determination.

## Registry listing

The repository carries a `server.json` manifest for the
[official MCP Registry](https://registry.modelcontextprotocol.io/), naming the
server `io.github.chelseakr/gtfs-scorecard`. Publishing requires an interactive
GitHub login, so it is a one-time operator step:

```sh
brew install mcp-publisher   # or download from modelcontextprotocol/registry releases
mcp-publisher login github   # device-code flow, authorizes the io.github.chelseakr namespace
mcp-publisher publish        # reads server.json at the repo root
```

**As of 2026-07-05, `server.json` carries no `packages[]` entry** (see its
`_meta["dev.chelseakr/gap"]` note). An earlier revision declared
`registryType: pypi`, which was false: `scorecard-pipeline` has never been
published to PyPI, and the MCP registry schema's `registryType` enum (`npm`,
`pypi`, `oci`, `nuget`, `mcpb`) has no value for "installed from a git
subdirectory via `uvx --from`," which is what actually happens. Rather than
leave that false claim in a public registry listing, the packages entry was
removed; the registry listing is metadata-only until either `scorecard-pipeline`
is genuinely published to PyPI (tracked with the release-pipeline work) or the
schema adds a git-source registry type. Until then, use the "Install and
connect" recipe above (a local checkout), or the direct `uvx` invocation:

```sh
uvx --from git+https://github.com/ChelseaKR/gtfs-scorecard#subdirectory=pipeline scorecard-mcp
```

The Claude Connectors Directory is a separate, heavier bar (a remote server, a
privacy policy, and a Team/Enterprise submission); per the cost guardrail it
waits until remote hosting has a named user.

## Design notes

The protocol core (`handle_request`, `call_tool`) is pure over an injected
fetch function and covered by `tests/test_mcp_server.py`; the stdio loop in
`main()` is the only I/O. No SDK dependency, for the same reason the
submission Lambda is stdlib-only: the deployable surface stays small and the
tested core carries the logic.
