# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the landing page (site/index.html) for the StaticMCP hub.

Usage:
    uv run generator/build_index.py <out-root> <base-url>

Scans <out-root> for <package>/<version>/mcp.json roots and renders an HTML
page listing every package and version with ready-to-paste client config.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path


def discover(out_root: Path) -> dict[str, dict]:
    """Return {package: {"versions": [...], "info": {...}}} found under out_root."""
    packages: dict[str, dict] = {}
    for manifest in sorted(out_root.glob("*/*/mcp.json")):
        version = manifest.parent.name
        package = manifest.parent.parent.name
        data = json.loads(manifest.read_text("utf-8"))
        entry = packages.setdefault(
            package,
            {"versions": [], "info": data.get("serverInfo", {}), "n_resources": 0},
        )
        if version != "latest":
            entry["versions"].append(version)
        if version == "latest":
            entry["n_resources"] = len(data.get("capabilities", {}).get("resources", []))
            entry["instructions"] = data.get("instructions", "")
    return packages


def client_config(package: str, base_url: str) -> str:
    url = f"{base_url.rstrip('/')}/{package}/latest"
    cfg = {
        "mcpServers": {
            package: {"command": "npx", "args": ["-y", "staticmcp-bridge", url]}
        }
    }
    return json.dumps(cfg, indent=2)


def render(packages: dict[str, dict], base_url: str) -> str:
    rows = []
    for package, entry in sorted(packages.items()):
        info = entry["info"]
        versions = sorted(entry["versions"], reverse=True)
        latest_url = f"{base_url.rstrip('/')}/{package}/latest/mcp.json"
        version_links = " · ".join(
            f'<a href="{html.escape(base_url.rstrip("/"))}/{package}/{html.escape(v)}/mcp.json">{html.escape(v)}</a>'
            for v in versions
        )
        rows.append(f"""
    <section class="pkg">
      <h2>{html.escape(package)} <span class="ver">latest: {html.escape(info.get('version', '?'))}</span></h2>
      <p class="desc">{html.escape(entry.get('instructions', ''))}</p>
      <p><strong>{entry['n_resources']}</strong> resources ·
         <a href="{html.escape(latest_url)}">manifest</a></p>
      <p class="versions">All versions: {version_links}</p>
      <details>
        <summary>Client config (Claude Desktop / Claude Code)</summary>
        <pre><code>{html.escape(client_config(package, base_url))}</code></pre>
      </details>
    </section>""")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mxl StaticMCP hub</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 16px/1.6 system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ margin-bottom: .2rem; }}
  .lede {{ color: #888; margin-top: 0; }}
  .pkg {{ border: 1px solid #8884; border-radius: 10px; padding: 1rem 1.25rem; margin: 1rem 0; }}
  .ver {{ font-size: .7em; font-weight: normal; color: #888; }}
  .desc {{ color: #aaa; }}
  pre {{ background: #8881; padding: .75rem; border-radius: 8px; overflow-x: auto; }}
  code {{ font-family: ui-monospace, monospace; }}
  a {{ color: #4493f8; }}
  footer {{ color: #888; font-size: .85em; margin-top: 2rem; }}
</style>
</head>
<body>
<h1>mxl StaticMCP hub</h1>
<p class="lede">Pre-generated <a href="https://staticmcp.com">StaticMCP</a> servers for the mxl packages.
   Point an MCP client at any <code>/&lt;package&gt;/latest</code> root via
   <a href="https://staticmcp.com/docs/bridge">staticmcp-bridge</a>.</p>
{''.join(rows)}
<footer>Rebuilt automatically on each upstream release · base URL <code>{html.escape(base_url)}</code></footer>
</body>
</html>
"""


def main() -> None:
    out_root = Path(sys.argv[1])
    base_url = sys.argv[2] if len(sys.argv) > 2 else "https://computational-biology-aachen.github.io/mxl-mcp"
    packages = discover(out_root)
    (out_root / "index.html").write_text(render(packages, base_url), encoding="utf-8")
    # Disable Jekyll so GitHub Pages serves files/dirs starting with underscores etc.
    (out_root / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote {out_root / 'index.html'} ({len(packages)} packages)")


if __name__ == "__main__":
    main()
