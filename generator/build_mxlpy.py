# /// script
# requires-python = ">=3.11"
# dependencies = ["griffe>=1.0"]
# ///
"""Build the StaticMCP server for mxlpy from its source tree.

Usage:
    uv run generator/build_mxlpy.py <pkg-src-dir> <version> <out-root>

Emits one Markdown resource per public module (recursively), plus the README,
changelog, and a generated API index. Docstrings are parsed statically with
griffe (no import of mxlpy or its heavy deps required).
"""

from __future__ import annotations

import sys
from pathlib import Path

import griffe
from griffe import Class, Function, Module, ParameterKind

from common import Resource, Server

PKG = "mxlpy"


def fmt(value: object) -> str:
    """Render a griffe annotation/default expression as a string."""
    return "" if value is None else str(value)


def signature(func: Function) -> str:
    parts: list[str] = []
    for p in func.parameters:
        if p.kind is ParameterKind.var_positional:
            token = f"*{p.name}"
        elif p.kind is ParameterKind.var_keyword:
            token = f"**{p.name}"
        else:
            token = p.name
        if p.annotation is not None:
            token += f": {fmt(p.annotation)}"
        if p.default is not None:
            token += f" = {fmt(p.default)}"
        parts.append(token)
    ret = f" -> {fmt(func.returns)}" if func.returns is not None else ""
    return f"{func.name}({', '.join(parts)}){ret}"


def docstring(obj: object) -> str:
    doc = getattr(obj, "docstring", None)
    return doc.value.strip() if doc and doc.value else ""


def is_public(name: str) -> bool:
    return not name.startswith("_")


def render_function(func: Function) -> str:
    lines = [f"### `{signature(func)}`", ""]
    doc = docstring(func)
    if doc:
        lines += [doc, ""]
    return "\n".join(lines)


def render_class(cls: Class) -> str:
    lines = [f"### class `{cls.name}`", ""]
    doc = docstring(cls)
    if doc:
        lines += [doc, ""]
    methods = [
        m
        for name, m in cls.members.items()
        if is_public(name) and isinstance(m, Function) and not m.is_alias
    ]
    if methods:
        lines.append("**Methods**")
        lines.append("")
        for m in methods:
            summary = docstring(m).splitlines()[0] if docstring(m) else ""
            lines.append(f"- `{signature(m)}`" + (f" — {summary}" if summary else ""))
        lines.append("")
    return "\n".join(lines)


def render_module(module: Module) -> str:
    rel = module.path[len(PKG) + 1 :] if module.path != PKG else PKG
    lines = [f"# `{module.path}`", ""]
    doc = docstring(module)
    if doc:
        lines += [doc, ""]

    classes, functions = [], []
    for name, member in module.members.items():
        if not is_public(name) or member.is_alias:
            continue
        if isinstance(member, Class):
            classes.append(member)
        elif isinstance(member, Function):
            functions.append(member)

    if classes:
        lines += ["## Classes", ""]
        for cls in sorted(classes, key=lambda c: c.name):
            lines.append(render_class(cls))
    if functions:
        lines += ["## Functions", ""]
        for func in sorted(functions, key=lambda f: f.name):
            lines.append(render_function(func))
    if not classes and not functions and not doc:
        return ""  # nothing worth a resource
    return "\n".join(lines).rstrip() + "\n", rel  # type: ignore[return-value]


def iter_modules(module: Module):
    for name, member in module.members.items():
        if isinstance(member, Module) and is_public(name) and not member.is_alias:
            yield member
            yield from iter_modules(member)


def main() -> None:
    src_dir, version, out_root = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    pkg = griffe.load(
        PKG,
        search_paths=[src_dir],
        allow_inspection=False,
        store_source=False,
    )

    server = Server(
        name=PKG,
        version=version,
        description=(
            "API reference and documentation for mxlpy, a Python package for "
            "metabolic modeling and analysis. Read resource mxlpy://index "
            "for the list of modules."
        ),
    )

    # README + changelog, served verbatim.
    src_root = Path(src_dir).parent  # src/ -> repo root has README/changelog
    for fname, uri, name, desc in [
        ("README.md", f"{PKG}://readme", "mxlpy README", "Project overview and quickstart."),
        ("changelog.rst", f"{PKG}://changelog", "mxlpy changelog", "Release history."),
    ]:
        path = src_root / fname
        if path.exists():
            server.add(
                Resource(uri=uri, name=name, description=desc, text=path.read_text("utf-8"))
            )

    # One resource per public module.
    module_index: list[tuple[str, str]] = []
    for module in iter_modules(pkg):
        result = render_module(module)
        if not result:
            continue
        text, rel = result
        uri = f"{PKG}://api/{rel}"
        summary = docstring(module).splitlines()[0] if docstring(module) else rel
        server.add(
            Resource(uri=uri, name=f"mxlpy.{rel}", description=summary, text=text)
        )
        module_index.append((uri, summary))

    # Generated API index.
    index_lines = ["# mxlpy API reference", "", f"Version `{version}`.", ""]
    for uri, summary in sorted(module_index):
        index_lines.append(f"- `{uri}` — {summary}")
    server.add(
        Resource(
            uri=f"{PKG}://index",
            name="mxlpy API index",
            description="List of all documented mxlpy modules.",
            text="\n".join(index_lines) + "\n",
        )
    )

    print(f"[{PKG}] version {version}")
    server.write(out_root)


if __name__ == "__main__":
    main()
