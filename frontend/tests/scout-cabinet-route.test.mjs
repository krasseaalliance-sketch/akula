import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const routePath = join(frontendRoot, "app", "cabinet", "page.tsx");

assert.equal(existsSync(routePath), true, "Scout cabinet route file must exist");
assert.match(readFileSync(routePath, "utf8"), /customer\/page/);
console.log("Scout cabinet route test passed");
