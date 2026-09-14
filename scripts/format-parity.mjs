// Two things this pins down, run with: node scripts/format-parity.mjs
//
//  1. No rate that exists is ever printed as "0". A capped decimal count
//     rounds a small number away — 0.000000012 at eight places is 0.00000001,
//     anything smaller is 0.00000000 — and a reader cannot tell a rate printed
//     as nothing from a broken page.
//
//  2. The chart's copy of formatRate still behaves like lib/format.ts's. That
//     copy exists because its script carries `define:vars` and so cannot
//     import; the copies had already drifted once, which is what let a
//     conversion under 1e-8 print as "0" in the browser while the server-
//     rendered number beside it was right.
//
// The copy is read out of the .astro file and evaluated, so this fails if
// someone edits one side and not the other.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const { formatRate } = await import(path.join(root, "src/lib/format.ts"));

const source = readFileSync(path.join(root, "src/components/PairPage.astro"), "utf8");
const match = source.match(/\n(      function formatRate\(value\) \{[\s\S]*?\n      \})\n/);
if (!match) {
  console.error("FAIL could not find the inline formatRate in PairPage.astro");
  process.exit(1);
}
const inlineFormatRate = new Function(`${match[1]}; return formatRate;`)();

const failures = [];
const check = (name, ok, detail = "") => {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${name}${ok || !detail ? "" : ` — ${detail}`}`);
  if (!ok) failures.push(name);
};

// Every magnitude a rate or a converted amount can land on, plus the real
// rates on the site and the awkward values around each branch.
const values = [];
for (let exp = 6; exp >= -30; exp--) {
  for (const mantissa of [1, 1.2, 3.456789, 9.999999]) values.push(mantissa * 10 ** exp);
}
values.push(
  0.86594, 25987.53, 154.424667, 0.00003332, 1, 0.9999999, 999.9999999, 1000, 1000.004,
  0.000000012, 5e-9, 1e-8, Number.MIN_VALUE, Number.EPSILON,
);

const zeroed = [];
const mismatched = [];
const withE = [];
for (const value of values) {
  for (const v of [value, -value]) {
    const out = formatRate(v);
    if (v !== 0 && Number(out) === 0) zeroed.push([v, out]);
    if (out !== inlineFormatRate(v)) mismatched.push([v, out, inlineFormatRate(v)]);
    // Exponential is the last resort, not something an ordinary rate meets.
    if (/e/i.test(out) && Math.abs(v) > 1e-17) withE.push([v, out]);
  }
}

check("no non-zero value prints as zero", zeroed.length === 0, JSON.stringify(zeroed.slice(0, 5)));
check("the chart's copy matches lib/format.ts", mismatched.length === 0, JSON.stringify(mismatched.slice(0, 5)));
check("ordinary magnitudes avoid exponential notation", withE.length === 0, JSON.stringify(withE.slice(0, 5)));

// The formatting the site has always used, unchanged.
const same = [
  [0.865945, "0.865945"], [25987.53, "25,987.53"], [154.424667, "154.424667"],
  [0.00003332, "0.00003332"], [1, "1"], [0.5, "0.5"], [1000, "1,000.00"],
];
for (const [input, expected] of same) {
  check(`formatRate(${input}) is still ${expected}`, formatRate(input) === expected, formatRate(input));
}

// The values that used to collapse to "0".
check("0.000000012 keeps its digits", formatRate(0.000000012) === "0.000000012", formatRate(0.000000012));
check("5e-9 keeps its digits", formatRate(5e-9) === "0.000000005", formatRate(5e-9));
check("1.2e-12 keeps its digits", formatRate(1.2e-12) === "0.0000000000012", formatRate(1.2e-12));
check("a non-finite value is a dash, not NaN", formatRate(Number.NaN) === "—", formatRate(Number.NaN));

console.log(failures.length ? `\n${failures.length} check(s) FAILED` : "\nformat parity holds");
process.exit(failures.length ? 1 : 0);
