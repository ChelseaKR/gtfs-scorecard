# scorecard-pipeline

The scoring pipeline, command-line tool, and read-only MCP server behind
[GTFS Scorecard](https://gtfsscorecard.org/), which grades public GTFS Schedule
feeds and turns validator notices into plain-language fixes.

<!-- mcp-name: io.github.ChelseaKR/gtfs-scorecard -->

## What it does

- `scorecard try <feed-url>` scores one GTFS Schedule zip with the MobilityData
  validator (Java 17 or newer must be on `PATH`) and prints the grade, the
  category scores, and the top fixes.
- `scorecard-mcp` is a read-only Model Context Protocol server over stdio. Its
  tools read the published scorecards on gtfsscorecard.org: search tracked
  agencies, get a scorecard and its fixes, read a feed's grade history, and
  explain a validator finding. It needs no key and has no write surface.
- `scorecard-pipeline` is the same MCP server under the distribution's name, so
  `uvx scorecard-pipeline` starts it.

## Install

Once scorecard-pipeline is on PyPI, these work:

    uvx scorecard-pipeline
    pip install scorecard-pipeline

Check https://pypi.org/project/scorecard-pipeline/ for the versions that exist.
Before then, or to run code that is not released yet, install from the
repository:

    uvx --from "git+https://github.com/ChelseaKR/gtfs-scorecard#subdirectory=pipeline" scorecard-mcp

## Connect an assistant

An MCP client config that starts the server from PyPI (once it is there; use
the repository form above until then):

    {
      "mcpServers": {
        "gtfs-scorecard": {
          "command": "uvx",
          "args": ["scorecard-pipeline"]
        }
      }
    }

Set `SCORECARD_BASE_URL` to point it at a fork or a local preview.

## More

- Site and scorecards: https://gtfsscorecard.org/
- Report bundle for programs that support many agencies: https://gtfsscorecard.org/bundle/
- MCP tools and what they refuse to say: https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/mcp.md
- GitHub Action that gates a build on a feed's grade: https://github.com/marketplace/actions/gtfs-scorecard-gate
- Source, issues, and changelog: https://github.com/ChelseaKR/gtfs-scorecard

Apache-2.0.
