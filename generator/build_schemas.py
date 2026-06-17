# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build the StaticMCP server for mxl-schemas.

Usage:
    uv run generator/build_schemas.py <schemas-repo-dir> <version> <out-root>

Serves every JSON schema under each ``v<N>/`` directory verbatim
(mimeType application/json), plus the README.
"""

from __future__ import annotations

import sys
from pathlib import Path

from common import Resource, Server

PKG = "mxlschemas"


def main() -> None:
    repo_dir, version, out_root = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])

    server = Server(
        name=PKG,
        version=version,
        description=(
            "JSON Schema definitions for mxl models (kinetic and ODE models). "
            "Schemas are served verbatim as application/json."
        ),
    )

    readme = repo_dir / "README.md"
    if readme.exists():
        server.add(
            Resource(
                uri=f"{PKG}://readme",
                name="mxl-schemas README",
                description="Overview of the mxl JSON schemas.",
                text=readme.read_text("utf-8"),
            )
        )

    schema_files = sorted(repo_dir.glob("v*/*.schema.json"))
    if not schema_files:
        print(f"[{PKG}] WARNING: no schema files found under {repo_dir}")
    for schema in schema_files:
        vdir = schema.parent.name  # e.g. "v1"
        stem = schema.name.removesuffix(".schema.json")  # e.g. "kinetic-model"
        server.add(
            Resource(
                uri=f"{PKG}://schema/{vdir}/{stem}",
                name=f"{stem} schema ({vdir})",
                description=f"JSON Schema for {stem} ({vdir}).",
                text=schema.read_text("utf-8"),
                mime_type="application/json",
            )
        )

    print(f"[{PKG}] version {version}")
    server.write(out_root)


if __name__ == "__main__":
    main()
