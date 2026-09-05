import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const mainRoute = readFileSync(join(frontendRoot, "app", "page.tsx"), "utf8");
const cabinetRoute = readFileSync(join(frontendRoot, "app", "cabinet", "page.tsx"), "utf8");
const constructiveRoute = readFileSync(join(frontendRoot, "app", "constructive", "page.tsx"), "utf8");
const loginRoute = readFileSync(join(frontendRoot, "app", "constructive", "login", "page.tsx"), "utf8");
const registerRoute = readFileSync(join(frontendRoot, "app", "constructive", "register", "[token]", "page.tsx"), "utf8");

assert.match(mainRoute, /ConstructiveLanding/);
assert.doesNotMatch(mainRoute, /return <ConstructiveView \/>/);
assert.match(cabinetRoute, /customer\/page/);
assert.match(constructiveRoute, /ConstructiveLanding/);
assert.match(loginRoute, /appPath\("\/cabinet"\)/);
assert.match(registerRoute, /appPath\("\/cabinet"\)/);
console.log("Constructive main/cabinet route separation test passed");
