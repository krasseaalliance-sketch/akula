import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const scoutHome = readFileSync(join(frontendRoot, "app", "page.tsx"), "utf8");
const constructiveHome = readFileSync(join(frontendRoot, "app", "constructive-landing.tsx"), "utf8");

test("Scout homepage has its own description and only the requested counters", () => {
  assert.match(scoutHome, /Scout — интеллектуальная система поиска новых возможностей для бизнеса/);
  assert.match(scoutHome, /Он помогает находить клиентов, заказы и точки роста — вовремя и по заданным критериям/);
  assert.match(scoutHome, /Кампании в работе/);
  assert.match(scoutHome, /Источники в работе/);
  assert.doesNotMatch(constructiveHome, /Кампании в работе|Источники в работе/);
});
