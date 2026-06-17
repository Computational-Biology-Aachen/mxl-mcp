"""Shared helpers for building StaticMCP servers.

Implements the StaticMCP standard (https://staticmcp.com/docs/standard):

    <root>/
      mcp.json                  # manifest
      resources/<encoded>.json  # one file per resource (read response)

We only emit resources (no tools), one StaticMCP root per package version,
plus a ``latest`` alias that mirrors the newest version.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import unicodedata
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


def encode_uri(uri: str) -> str:
    """Encode a resource URI into a static filename stem per the StaticMCP rules.

    Strips everything up to and including ``://``, normalises unicode, lowercases,
    keeps only ``[a-z0-9_-]`` (other chars -> ``_``), and caps the length at 200
    chars (long values become ``first-183`` + ``_`` + 16-char hex hash).
    """
    path = uri.split("://", 1)[1] if "://" in uri else uri
    normalised = unicodedata.normalize("NFKD", path)
    normalised = normalised.encode("ascii", "ignore").decode("ascii")
    out = []
    for ch in normalised.lower():
        out.append(ch if (ch.isalnum() or ch in "-_") else "_")
    encoded = "".join(out)
    if len(encoded) > 200:
        digest = hashlib.sha256(encoded.encode()).hexdigest()[:16]
        encoded = f"{encoded[:183]}_{digest}"
    return encoded


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
            stem = encode_uri(resource.uri)
            _write_json(version_dir / "resources" / f"{stem}.json", resource.read_response())

        latest_dir = root / self.name / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(version_dir, latest_dir)

        print(f"  wrote {len(self.resources)} resources -> {version_dir}")
        print(f"  refreshed alias       -> {latest_dir}")
        return version_dir


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
