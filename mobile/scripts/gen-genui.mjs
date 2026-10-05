// Generates src/genui/types.gen.ts from the backend's GenUI contract (backend/contracts).
// The contract holds three schemas (envelope, event, action_request) that share definitions;
// they are merged into one schema so every model compiles once.
import { readFileSync, writeFileSync } from 'node:fs';
import { compile } from 'json-schema-to-typescript';

const CONTRACT = new URL('../../backend/contracts/genui.schema.json', import.meta.url);
const OUT = new URL('../src/genui/types.gen.ts', import.meta.url);

const contract = JSON.parse(readFileSync(CONTRACT, 'utf8'));
const defs = {};
const roots = {};
for (const [key, schema] of Object.entries(contract)) {
  if (typeof schema !== 'object' || schema === null) continue;
  const { $defs = {}, ...root } = schema;
  Object.assign(defs, $defs);
  const name = root.title ?? key;
  if (root.properties || root.oneOf) {
    defs[name] = root;
    roots[key] = { $ref: `#/$defs/${name}` };
  }
}

const merged = {
  title: 'GenUIContract',
  type: 'object',
  properties: roots,
  required: Object.keys(roots),
  additionalProperties: false,
  $defs: defs,
};

const banner = `/* Generated from backend/contracts/genui.schema.json by scripts/gen-genui.mjs.
 * Do not edit by hand: run \`npm run gen\` (or \`make contracts\`). */
export const GENUI_CATALOG_VERSION = ${Number(contract.catalog_version)};`;

const ts = await compile(merged, 'GenUIContract', {
  bannerComment: banner,
  unreachableDefinitions: true,
  ignoreMinAndMaxItems: true, // arrays, not 20-way tuple unions
  additionalProperties: false,
  strictIndexSignatures: true,
  style: { singleQuote: true, semi: true, printWidth: 100 },
});
writeFileSync(OUT, ts);
console.log(`wrote ${OUT.pathname} (catalog v${contract.catalog_version}, ${Object.keys(defs).length} models)`);
