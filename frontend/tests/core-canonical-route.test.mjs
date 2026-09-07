import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const frontendRoot = join(import.meta.dirname, "..");

test("Core has one canonical route under the shared Scout base path", () => {
  const config = readFileSync(join(frontendRoot, "next.config.ts"), "utf8");
  const page = readFileSync(join(frontendRoot, "app", "core", "page.tsx"), "utf8");
  const paths = readFileSync(join(frontendRoot, "app", "paths.ts"), "utf8");
  assert.match(config, /basePath: appBasePath/);
  assert.match(config, /process\.env\.APP_BASE_PATH \?\? "\/scout"/);
  assert.match(page, /export default function CorePage/);
  assert.match(paths, /APP_BASE_PATH/);
  assert.match(paths, /CORE_ROUTE = "\/core"/);
  assert.match(paths, /corePath = \(\) => appPath\(CORE_ROUTE\)/);
  assert.doesNotMatch(page, /href=["']\/core/);
});
