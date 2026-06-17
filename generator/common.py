"""Shared helpers for building StaticMCP servers.

Implements the StaticMCP standard (https://staticmcp.com/docs/standard):

    <root>/
      mcp.json                # manifest
      resources/<path>.json   # one file per resource, path mirrors the URI

We only emit resources (no tools), one StaticMCP root per package version,
plus a ``latest`` alias that mirrors the newest version.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# MCP protocol revision advertised in every manifest.
PROTOCOL_VERSION = "2024-11-05"


@dataclass
class Resource:
    """A single MCP resource and its pre-rendered read response."""

    uri: str
    name: str
    description: str
    text: str
    mime_type: str = "text/markdown"

    def manifest_entry(self) -> dict:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }

    def read_response(self) -> dict:
        return {"uri": self.uri, "mimeType": self.mime_type, "text": self.text}


def uri_to_relpath(uri: str) -> str:
    """Map a resource URI to its relative file path (sans ``.json`` suffix).

    This must match how ``staticmcp-bridge`` resolves a read request: it strips
    everything up to and including ``://`` and uses the remainder *verbatim* as a
    path under ``resources/`` (``resources/<remainder>.json``). Slashes therefore
    become real subdirectories and dots stay literal -- e.g.
    ``mxlpy://api/meta.codegen_latex`` -> ``api/meta.codegen_latex``.

    We do not re-encode the remainder: any mangling here would no longer match the
    path the bridge requests. We only guard against path traversal so a malformed
    URI cannot escape the ``resources/`` directory.
    """
    path = uri.split("://", 1)[1] if "://" in uri else uri
    if path.startswith("/") or ".." in path.split("/"):
        raise ValueError(f"unsafe resource URI: {uri!r}")
    return path


@dataclass
class Server:
    """Accumulates resources for one package and writes a StaticMCP root."""

    name: str
    version: str
    description: str
    resources: list[Resource] = field(default_factory=list)

    def add(self, resource: Resource) -> None:
        self.resources.append(resource)

    def manifest(self) -> dict:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": {"name": self.name, "version": self.version},
            "capabilities": {
                "resources": [r.manifest_entry() for r in self.resources],
                "tools": [],
            },
            "instructions": self.description,
        }

    def write(self, root: Path) -> Path:
        """Write the manifest + resource files into ``root/<name>/<version>``.

        Also (re)creates the ``latest`` alias as a copy of this version.
        Returns the version directory.
        """
        version_dir = root / self.name / self.version
        if version_dir.exists():
            shutil.rmtree(version_dir)
        (version_dir / "resources").mkdir(parents=True)

        _write_json(version_dir / "mcp.json", self.manifest())
        for resource in self.resources:
            out_path = version_dir / "resources" / f"{uri_to_relpath(resource.uri)}.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(out_path, resource.read_response())

        latest_dir = root / self.name / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(version_dir, latest_dir)

        print(f"  wrote {len(self.resources)} resources -> {version_dir}")
        print(f"  refreshed alias       -> {latest_dir}")
        return version_dir


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
