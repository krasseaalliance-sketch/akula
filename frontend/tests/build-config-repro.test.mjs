import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const frontendRoot = join(import.meta.dirname, "..");

test("Next type-check config does not scan archived deployment trees", () => {
  const tsconfig = readFileSync(join(frontendRoot, "tsconfig.json"), "utf8");
  assert.doesNotMatch(tsconfig, /\.next-deploy/);
  assert.doesNotMatch(tsconfig, /\.next-production-/);
});
