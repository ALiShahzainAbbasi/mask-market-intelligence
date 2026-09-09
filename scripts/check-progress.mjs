import { readFile } from "node:fs/promises";
const content = await readFile(new URL("../progress.txt", import.meta.url), "utf8");
const items = [...content.matchAll(/^\[([x ~?!])\] (P\d{2}-\d{2}|A\d{2}) /gm)];
const done = items.filter(item => item[1] === "x").length;
const ids = new Set(items.map(item => item[2]));
if (ids.size !== items.length) throw new Error("Duplicate checkpoint IDs");
const summary = content.match(/^Completed checkpoints: (\d+)\/(\d+)/m);
const remaining = content.match(/^Remaining checkpoints: (\d+)\/(\d+)/m);
if (!summary || +summary[1] !== done || +summary[2] !== items.length ||
    !remaining || +remaining[1] !== items.length - done || +remaining[2] !== items.length) {
  throw new Error("Tracker totals do not match checkboxes");
}
const rows = [...content.matchAll(/^(P\d{2}) \| [A-Z_ ]+ \|\s*(\d+)\/\s*(\d+) \|/gm)];
if (rows.length !== 25) throw new Error("Expected 25 phase rollups");
for (const row of rows) {
  const phase = items.filter(item => item[2].startsWith(row[1] + "-"));
  if (phase.length !== +row[3] || phase.filter(item => item[1] === "x").length !== +row[2]) {
    throw new Error("Phase rollup mismatch: " + row[1]);
  }
}
const autonomousRow = content.match(/^A\s+\| [A-Z_ ]+ \|\s*(\d+)\/\s*(\d+) \|/m);
const autonomous = items.filter(item => /^A\d{2}$/.test(item[2]));
if (!autonomousRow || autonomous.length !== +autonomousRow[2] ||
    autonomous.filter(item => item[1] === "x").length !== +autonomousRow[1]) {
  throw new Error("Autonomous build rollup mismatch");
}
console.log(`Tracker PASS: ${done}/${items.length} completed; ${items.length - done} remaining.`);
