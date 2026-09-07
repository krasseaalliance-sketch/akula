import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const coreRoute = readFileSync(join(frontendRoot, "app", "core", "page.tsx"), "utf8");
const artifactQaPanel = readFileSync(join(frontendRoot, "app", "core", "artifact-qa-panel.tsx"), "utf8");

test("Core route is a real authenticated workspace UI", () => {
  assert.match(coreRoute, /api\/auth\/login/);
  assert.match(coreRoute, /sessionStorage\.getItem\("lead-hunter-token"\)/);
  assert.match(coreRoute, /\/core\/context/);
  assert.match(coreRoute, /\/core\/projects/);
  assert.match(coreRoute, /\/core\/tasks/);
  assert.match(coreRoute, /\/dependencies/);
  assert.match(coreRoute, /onUpdate/);
  assert.match(coreRoute, /required_competencies/);
  assert.match(coreRoute, /Компетенции задачи/);
  assert.match(coreRoute, /Создать проект/);
  assert.match(coreRoute, /Журнал/);
  assert.match(coreRoute, /ArtifactQaPanel/);
  assert.match(coreRoute, /artifacts\/upload/);
  assert.match(coreRoute, /x-file-name/);
  assert.match(coreRoute, /body: file/);
  assert.match(artifactQaPanel, /artifact_key/);
  assert.match(artifactQaPanel, /type="file"/);
  assert.match(artifactQaPanel, /Загрузить и сохранить/);
  assert.match(artifactQaPanel, /Новая версия/);
  assert.match(artifactQaPanel, /PENDING|PASS|FAIL|BLOCKED/);
  assert.match(artifactQaPanel, /production-evidence|PRODUCTION EVIDENCE/);
  assert.match(artifactQaPanel, /remediation/);
  assert.doesNotMatch(coreRoute, /demo|mock|FAKE|фальш/i);
});
