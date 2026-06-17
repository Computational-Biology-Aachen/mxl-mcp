// Build the StaticMCP server for mxlweb-core using the TypeScript compiler API.
//
// Usage:
//   node generator/build_webcore.mjs <pkg-dir> <version> <out-root>
//
// The public surface is taken from package.json "exports": each entry that maps
// to a src/*.ts module becomes one Markdown resource listing its exported
// symbols (functions, interfaces, classes, type aliases, enums) with JSDoc.

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import ts from "typescript";

const PKG = "mxlweb-core";
const PROTOCOL_VERSION = "2024-11-05";

const [pkgDir, version, outRoot] = process.argv.slice(2);
if (!pkgDir || !version || !outRoot) {
  console.error("usage: node build_webcore.mjs <pkg-dir> <version> <out-root>");
  process.exit(1);
}

// ---- StaticMCP filename encoding (mirrors generator/common.py) ----------------
function encodeUri(uri) {
  let p = uri.includes("://") ? uri.split("://").slice(1).join("://") : uri;
  p = p.normalize("NFKD").replace(/[\u0300-\u036f]/g, ""); // strip accents
  let out = "";
  for (const ch of p.toLowerCase()) {
    out += /[a-z0-9\-_]/.test(ch) ? ch : "_";
  }
  if (out.length > 200) {
    const hash = crypto.createHash("sha256").update(out).digest("hex").slice(0, 16);
    out = out.slice(0, 183) + "_" + hash;
  }
  return out;
}

// ---- Resolve public modules from package.json "exports" -----------------------
const pkgJson = JSON.parse(fs.readFileSync(path.join(pkgDir, "package.json"), "utf8"));
const seen = new Set();
const modules = []; // { exportName, file }
for (const [key, value] of Object.entries(pkgJson.exports ?? {})) {
  const srcPath = typeof value === "string" ? value : value?.types ?? value?.svelte;
  if (!srcPath || !srcPath.endsWith(".ts") || !srcPath.startsWith("./src/")) continue;
  const file = path.resolve(pkgDir, srcPath);
  if (!fs.existsSync(file) || seen.has(file)) continue;
  seen.add(file);
  // "." -> "index"; "./mathml" -> "mathml"; "./backends/js" -> "backends/js"
  const exportName = key === "." ? "index" : key.replace(/^\.\//, "");
  modules.push({ exportName, file });
}

// ---- Build a single Program over all entry files ------------------------------
const program = ts.createProgram(
  modules.map((m) => m.file),
  {
    target: ts.ScriptTarget.ESNext,
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
    allowJs: true,
    noEmit: true,
    skipLibCheck: true,
  },
);
const checker = program.getTypeChecker();

function jsdoc(symbol) {
  return ts.displayPartsToString(symbol.getDocumentationComment(checker)).trim();
}

function firstLine(text) {
  return text.split("\n")[0].trim();
}

function truncate(text, n = 400) {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > n ? flat.slice(0, n) + " …" : flat;
}

function kindOf(decl) {
  if (ts.isInterfaceDeclaration(decl)) return "interface";
  if (ts.isClassDeclaration(decl)) return "class";
  if (ts.isFunctionDeclaration(decl)) return "function";
  if (ts.isTypeAliasDeclaration(decl)) return "type";
  if (ts.isEnumDeclaration(decl)) return "enum";
  return null;
}

function renderMembers(symbol, decl) {
  const type = checker.getDeclaredTypeOfSymbol(symbol);
  const props = checker.getPropertiesOfType(type);
  if (!props.length) return [];
  const lines = ["", "**Members**", ""];
  for (const prop of props) {
    const pdecl = prop.valueDeclaration ?? prop.declarations?.[0] ?? decl;
    let typeStr = "";
    try {
      typeStr = checker.typeToString(checker.getTypeOfSymbolAtLocation(prop, pdecl));
    } catch {
      typeStr = "";
    }
    const doc = firstLine(jsdoc(prop));
    const sig = typeStr ? `${prop.getName()}: ${truncate(typeStr, 120)}` : prop.getName();
    lines.push(`- \`${sig}\`` + (doc ? ` — ${doc}` : ""));
  }
  return lines;
}

function renderSymbol(symbol) {
  const decl = symbol.declarations?.[0];
  if (!decl) return null;
  const kind = kindOf(decl);
  if (!kind) return null;
  const name = symbol.getName();
  const doc = jsdoc(symbol);
  const lines = [];

  if (kind === "function") {
    let sig = name;
    try {
      const t = checker.getTypeOfSymbolAtLocation(symbol, decl);
      sig = name + truncate(checker.typeToString(t), 300);
    } catch {
      /* keep bare name */
    }
    lines.push(`### \`function ${sig}\``, "");
    if (doc) lines.push(doc, "");
  } else if (kind === "interface" || kind === "class") {
    lines.push(`### ${kind} \`${name}\``, "");
    if (doc) lines.push(doc, "");
    lines.push(...renderMembers(symbol, decl));
    lines.push("");
  } else {
    // type alias / enum
    let typeStr = "";
    try {
      typeStr = truncate(checker.typeToString(checker.getDeclaredTypeOfSymbol(symbol)), 300);
    } catch {
      /* ignore */
    }
    lines.push(`### ${kind} \`${name}\`` + (typeStr ? ` = \`${typeStr}\`` : ""), "");
    if (doc) lines.push(doc, "");
  }
  return { name, kind, text: lines.join("\n") };
}

function renderModule(file, exportName) {
  const sf = program.getSourceFile(file);
  if (!sf) return null;
  const moduleSymbol = checker.getSymbolAtLocation(sf);
  if (!moduleSymbol) return null;
  const exports = checker.getExportsOfModule(moduleSymbol);

  const sections = [];
  for (const sym of exports) {
    // Follow aliases (re-exports via `export * from`) to the real declaration.
    const resolved =
      sym.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(sym) : sym;
    const rendered = renderSymbol(resolved);
    if (rendered) sections.push(rendered);
  }
  if (!sections.length) return null;

  sections.sort((a, b) => a.name.localeCompare(b.name));
  const body = [`# \`${PKG}\` — \`${exportName}\``, ""];
  // Module-level JSDoc (the `@module` block comment), if any.
  const moduleDoc = jsdoc(moduleSymbol);
  if (moduleDoc) body.push(moduleDoc, "");
  for (const s of sections) body.push(s.text);
  return body.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd() + "\n";
}

// ---- Assemble resources -------------------------------------------------------
const resources = [];
function addResource(uri, name, description, text, mimeType = "text/markdown") {
  resources.push({ uri, name, description, text, mimeType });
}

const readme = path.join(pkgDir, "README.md");
if (fs.existsSync(readme)) {
  addResource(
    `${PKG}://readme`,
    "mxlweb-core README",
    "Project overview.",
    fs.readFileSync(readme, "utf8"),
  );
}

const moduleIndex = [];
for (const { exportName, file } of modules) {
  const text = renderModule(file, exportName);
  if (!text) continue;
  const uri = `${PKG}://api/${exportName}`;
  addResource(uri, `mxlweb-core ${exportName}`, `Public API of the ${exportName} entry point.`, text);
  moduleIndex.push(uri);
}

const indexLines = ["# mxlweb-core API reference", "", `Version \`${version}\`.`, ""];
for (const uri of moduleIndex.sort()) indexLines.push(`- \`${uri}\``);
addResource(
  `${PKG}://index`,
  "mxlweb-core API index",
  "List of all documented mxlweb-core entry points.",
  indexLines.join("\n") + "\n",
);

// ---- Write StaticMCP root -----------------------------------------------------
const manifest = {
  protocolVersion: PROTOCOL_VERSION,
  serverInfo: { name: PKG, version },
  capabilities: {
    resources: resources.map((r) => ({
      uri: r.uri,
      name: r.name,
      description: r.description,
      mimeType: r.mimeType,
    })),
    tools: [],
  },
  instructions:
    "API reference for @computational-biology-aachen/mxlweb-core, a TypeScript " +
    "library for building and simulating metabolic models in the browser. " +
    "Read resource mxlweb-core://index for the list of entry points.",
};

const versionDir = path.join(outRoot, PKG, version);
fs.rmSync(versionDir, { recursive: true, force: true });
fs.mkdirSync(path.join(versionDir, "resources"), { recursive: true });
fs.writeFileSync(path.join(versionDir, "mcp.json"), JSON.stringify(manifest, null, 2) + "\n");
for (const r of resources) {
  const stem = encodeUri(r.uri);
  const payload = { uri: r.uri, mimeType: r.mimeType, text: r.text };
  fs.writeFileSync(
    path.join(versionDir, "resources", `${stem}.json`),
    JSON.stringify(payload, null, 2) + "\n",
  );
}

const latestDir = path.join(outRoot, PKG, "latest");
fs.rmSync(latestDir, { recursive: true, force: true });
fs.cpSync(versionDir, latestDir, { recursive: true });

console.log(`[${PKG}] version ${version}`);
console.log(`  wrote ${resources.length} resources -> ${versionDir}`);
console.log(`  refreshed alias       -> ${latestDir}`);
