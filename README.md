# mxl-mcp

Pre-generated [StaticMCP](https://staticmcp.com) servers for the mxl packages,
hosted on GitHub Pages. MCP clients get API reference + docs for each package
over plain HTTP — **zero runtime, no server to operate**.

One StaticMCP root per package:

| Package | Source | Content |
|---|---|---|
| `mxlpy` | [MxlPy](https://github.com/Computational-Biology-Aachen/MxlPy) | README, changelog, one Markdown API-reference resource per module (extracted with [griffe](https://mkdocstrings.github.io/griffe/)) |
| `mxlschemas` | [mxl-schemas](https://github.com/Computational-Biology-Aachen/mxl-schemas) | README + each JSON Schema served verbatim |
| `mxlweb-core` | [mxlweb-core](https://github.com/Computational-Biology-Aachen/mxlweb-core) | README, one Markdown API-reference resource per public entry point (extracted via the TypeScript compiler API) |

Every release is kept under a version-prefixed path, and `latest/` always
mirrors the newest version.

## Layout

```
site/                              # the published GitHub Pages site
├── index.html                    # human landing page (generated)
├── <package>/
│   ├── <version>/
│   │   ├── mcp.json              # StaticMCP manifest (resources only, no tools)
│   │   └── resources/*.json      # one pre-rendered read response per resource
│   └── latest/                   # copy of the newest version
generator/                         # build tooling (see below)
.github/workflows/build.yml        # rebuild + deploy on upstream release
docs/source-repo-release.yml       # snippet to add to each upstream repo
```

## Using it from an MCP client

Point [`staticmcp-bridge`](https://staticmcp.com/docs/bridge) at any
`/<package>/latest` root. Example Claude Desktop / Claude Code config:

```json
{
  "mcpServers": {
    "mxlpy": {
      "command": "npx",
      "args": ["-y", "staticmcp-bridge", "https://computational-biology-aachen.github.io/mxl-mcp/mxlpy/latest"]
    }
  }
}
```

Pin a specific version by swapping `latest` for e.g. `0.52.0`.

## How updates flow

1. An upstream package publishes a GitHub Release.
2. Its `notify-staticmcp.yml` workflow (copied from
   [`docs/source-repo-release.yml`](docs/source-repo-release.yml)) sends a
   `repository_dispatch` to this repo with the released version/tag.
3. [`.github/workflows/build.yml`](.github/workflows/build.yml) clones that
   package at the tag, regenerates only its StaticMCP root, commits `site/`,
   and deploys to Pages.

One-time setup in each upstream repo: a fine-grained PAT with
`Contents: read & write` on this repo, stored as the `STATIC_MCP_TOKEN` secret.

## Building locally

```bash
# all packages (clones upstream from GitHub):
generator/build.sh all

# one package at a specific tag:
generator/build.sh mxlpy v0.52.0

# regenerate the landing page:
uv run generator/build_index.py site "https://computational-biology-aachen.github.io/mxl-mcp"
```

Generators run individually too (against an already-checked-out source tree):

```bash
uv run generator/build_mxlpy.py   pkg/mxlpy/src        0.52.0  site
uv run generator/build_schemas.py pkg/mxlschemas       v1      site
npm  --prefix generator install
node generator/build_webcore.mjs  pkg/mxlweb-core      1.0.0   site
```

Requirements: [uv](https://docs.astral.sh/uv/) (auto-installs Python deps like
griffe) and Node 22+ (the webcore generator needs `typescript`, installed via
`npm --prefix generator install`).
