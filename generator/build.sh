#!/usr/bin/env bash
# Build one or all StaticMCP servers from upstream source.
#
# Usage: generator/build.sh <package|all> [ref] [version]
#
#   package : mxlpy | mxlschemas | mxlweb-core | all
#   ref     : git ref/tag to check out (default: each repo's default branch)
#   version : version label for the StaticMCP root (default: derived from source)
#
# Clones each upstream repo into a temp dir and runs the matching generator,
# writing into ./site. Existing versions in ./site are preserved.
set -euo pipefail

PKG="${1:-all}"
REF="${2:-}"
VERSION="${3:-}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE="$ROOT/site"
GEN="$ROOT/generator"
ORG="https://github.com/Computational-Biology-Aachen"

# package -> upstream repo name
repo_for() {
  case "$1" in
    mxlpy)       echo "MxlPy" ;;
    mxlschemas)  echo "mxl-schemas" ;;
    mxlweb-core) echo "mxlweb-core" ;;
    *) echo "unknown package: $1" >&2; return 1 ;;
  esac
}

clone() {
  local repo="$1" dest="$2" ref="$3"
  if [ -n "$ref" ]; then
    git clone --quiet --depth 1 --branch "$ref" "$ORG/$repo" "$dest"
  else
    git clone --quiet --depth 1 "$ORG/$repo" "$dest"
  fi
}

build_one() {
  local pkg="$1" ref="$2" version="$3"
  local repo dest
  repo="$(repo_for "$pkg")"
  dest="$(mktemp -d)"
  trap 'rm -rf "$dest"' RETURN

  echo "::group::build $pkg (ref='${ref:-default}')"
  clone "$repo" "$dest" "$ref"

  case "$pkg" in
    mxlpy)
      [ -n "$version" ] || version="$(grep -m1 -oP 'version = "\K[^"]+' "$dest/pyproject.toml")"
      uv run "$GEN/build_mxlpy.py" "$dest/src" "$version" "$SITE"
      ;;
    mxlschemas)
      if [ -z "$version" ]; then
        version="$(git -C "$dest" describe --tags --abbrev=0 2>/dev/null || git -C "$dest" rev-parse --short HEAD)"
      fi
      uv run "$GEN/build_schemas.py" "$dest" "$version" "$SITE"
      ;;
    mxlweb-core)
      [ -n "$version" ] || version="$(node -p "require('$dest/package.json').version")"
      node "$GEN/build_webcore.mjs" "$dest" "$version" "$SITE"
      ;;
  esac
  echo "::endgroup::"
}

if [ "$PKG" = "all" ]; then
  for p in mxlpy mxlschemas mxlweb-core; do
    build_one "$p" "" ""
  done
else
  build_one "$PKG" "$REF" "$VERSION"
fi
