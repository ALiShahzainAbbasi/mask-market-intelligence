import { readFile, writeFile } from "node:fs/promises";
import { randomBytes } from "node:crypto";

const root = new URL("../", import.meta.url);
const template = await readFile(new URL(".env.example", root), "utf8");
const values = new Map();
const content = template.replace(/__GENERATE_[A-Z_]+__/g, key => {
  if (!values.has(key)) values.set(key, randomBytes(32).toString("hex"));
  return values.get(key);
});
try {
  await writeFile(new URL(".env", root), content, { flag: "wx", mode: 0o600 });
  console.log("Created ignored .env with fresh local-only secrets. Values are not printed.");
} catch (error) {
  if (error.code !== "EEXIST") throw error;
  console.log(".env already exists; left unchanged.");
}
console.log("Next: configure PostgreSQL URLs; run pnpm dev:worker, pnpm dev:api, and pnpm dev in separate terminals.");
console.log("Setup does not install/start PostgreSQL or application processes. See docs/DEVELOPMENT.md.");
