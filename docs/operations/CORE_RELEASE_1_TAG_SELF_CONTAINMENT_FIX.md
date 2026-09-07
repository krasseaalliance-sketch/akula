# Core Release 1 tag self-containment fix

Status: `BUNDLE READY FOR SERVER UPLOAD`

## Release identity

The old immutable tag `core-r1-staging-rc1-2026-09-07` pointed to
`e497f5152b204df74a065789aeb46542089bcb99`. It was incomplete: a clean
checkout collected 108 tests but stopped during collection with seven
`FileNotFoundError` import errors for untracked historical helpers.

The replacement immutable candidate is:

| Item | Value |
|---|---|
| Tag | `core-r1-staging-rc2-2026-09-07` |
| Commit | `57fd512f604ebb77d24e02d221a8a69cadc54925` |
| Repository | `https://github.com/krasseaalliance-sketch/akula.git` |
| Alembic head | `0025_core_day4_production_evidence` |
| GitHub Actions | [run 34107281442](https://github.com/krasseaalliance-sketch/akula/actions/runs/34107281442) |

The old tag was not moved. The new tag contains the product code, delivery
kit, CI, test-contract repairs, and PostgreSQL migration repairs.

## Root-cause inventory

| № | Test | Missing file/module | Why the test imported it | Must be in Release 1? | Decision |
|---:|---|---|---|---|---|
| 1 | `backend/tests/test_avito_opportunity_qa.py` | `tools/qa_avito_opportunity_2026_08_11.py` | `runpy.run_path()` loaded a one-off Avito/Vitrina QA helper. | No | B — rewrote the test against current tracked Hunter contracts. |
| 2 | `backend/tests/test_avito_site_verifier_regression.py` | `tools/avito_site_verifier_qa2.py` | `runpy.run_path()` loaded a local verifier with hard-coded `E:\Codex\Vitrina` paths. | No | B — kept deterministic coverage through current public modules. |
| 3 | `backend/tests/test_hunter_stage1r2.py` | `tools/run_lead_hunter_stage1r2.py` | `runpy.run_path()` loaded a historical stage runner and scoring helpers. | No | B — tests current adapter/pipeline contracts. |
| 4 | `backend/tests/test_hunter_stage1r4.py` | `tools/run_lead_hunter_stage1r4.py` | `runpy.run_path()` loaded a historical alert-loop runner. | No | B — tests the current fail-closed Hunter safety API. |
| 5 | `backend/tests/test_hunter_stage2.py` | `tools/run_lead_hunter_stage2.py` | `runpy.run_path()` loaded a runner and local generated reports. | No | B — tests current source ingestion with fixtures. |
| 6 | `backend/tests/test_hunter_stage21.py` | `tools/run_lead_hunter_stage21.py` | `runpy.run_path()` loaded a temporary measurement runner and external files. | No | B — tests deterministic current pipeline behavior. |
| 7 | `backend/tests/test_scout_quality.py` | `scout-vps-stage-20260814/scout.py` | A dynamic import targeted an old standalone SQLite/HTTP Scout snapshot. | No | B — tests the current tracked Scout/Hunter qualification contract. |

For every row, `git log --all -- <path>` and the Git object/path scan found no
tracked history. `rg` found the stale test as the only repository consumer;
there is no runtime import. The local copies are untracked deployment or QA
artifacts and were not copied into the release.

After those seven collection errors were repaired, the full run exposed one
additional stale contract in `backend/tests/test_hunter_stage1r1.py`: it read
an absent historical top-level `docker-compose.yml` and asserted a removed
`hunter-readonly` runner. It was replaced by the tracked
`app.hunter.safety.hunter_runtime_capabilities()` contract. This was a
separate post-collection dependency, not one of the original seven imports.

## Repairs included in rc2

Only the following tracked files changed between the old tag and rc2:

- the seven tests above, `test_hunter_stage1r1.py`, and
  `test_migrations_clean_upgrade.py`;
- `backend/migrations/versions/0001_initial.py` — dependency ordering for
  human-writing tables and PostgreSQL-safe `alembic_version` width;
- `backend/migrations/versions/0016_support_campaign_topics.py` — PostgreSQL
  in-place alteration instead of dropping a referenced primary key;
- `backend/migrations/versions/0024_core_day4_artifacts_qa.py` — PostgreSQL
  in-place alterations for tables referenced by Core child foreign keys;
- `.github/workflows/core-release1-staging.yml` — exact staging RC tag
  identity and tag-derived artifact naming;
- `deploy/platform-kit/**`, `scripts/build_platform_bundle.ps1`, and the
  operations documentation.

No Core API, model, UI, Scout runtime, Constructive runtime, authorization,
or production configuration logic was changed as part of the self-containment
repair. No skips, xfails, compatibility copies, or local helper files were
added.

The migration repairs were driven by clean fresh PostgreSQL failures:

1. `0001` referenced human-writing tables before creating them.
2. `0016` used SQLite batch recreation against a referenced PostgreSQL key.
3. `0024` had the same PostgreSQL batch-recreation problem for `core_agents`.
4. `0025` could not fit in Alembic's default `VARCHAR(32)` version column.

The migration-order assertion failed before the first repair and passed after
it. The focused rewritten contracts passed `18` tests after the changes.

## Clean-checkout verification

Clean clone used for final verification:

`C:\Users\Alexey\AppData\Local\Temp\akula-rc2-final-clean-c53e771864dd4fc8b87f9e7d254058ce\source`

Before installing dependencies, it had zero working-tree changes, resolved to
the exact rc2 commit/tag, and contained all tracked Core, Scout, Constructive,
migration, delivery-kit, CI, and runbook sources. No files from
`E:\Codex\Akula` were used by the clone.

The unified bundle was separately extracted to:

`C:\Users\Alexey\AppData\Local\Temp\akula-rc2-audit-77d1b798e1124723b58c89aaea3dc074\akula-platform-staging`

It contains `343` files: Core `242`, Scout `54`, Constructive `8`, and
migrations `26`. The required manifest, checksums, env templates, Compose,
Caddyfile, install/verify/rollback scripts, and README files are present.

## Verification results

All commands below were run against the exact rc2 checkout or the extracted
bundle, as noted.

| Check | Result |
|---|---|
| `git diff --check` | exit `0` |
| Clean-checkout full `python -m pytest -q` | `127 passed, 2330 warnings` in `102.14s` |
| Extracted-bundle full `python -m pytest -q` | `127 passed, 2330 warnings` in `135.11s` |
| `npm.cmd run test` | `6 passed, 0 failed` |
| `npx.cmd tsc --noEmit` | exit `0` |
| `npm.cmd run lint` | exit `0`; `0` errors, `4` warnings |
| `npm.cmd run build` | exit `0`; `11` routes generated |
| `python -m compileall -q backend` | exit `0` |
| Fresh PostgreSQL `alembic upgrade head` | exit `0` |
| Fresh PostgreSQL `alembic current` | `0025_core_day4_production_evidence (head)`, exit `0` |
| Extracted bundle `docker compose -f deploy/docker-compose.platform.yml config --quiet` | exit `0` |
| GitHub Actions exact rc2 run | [successful run 34107281442](https://github.com/krasseaalliance-sketch/akula/actions/runs/34107281442); candidate, backend, frontend, artifact all successful |

The four lint/build warnings are existing frontend warnings (`<img>` usage
and React hook dependencies). They are not import errors and were not hidden.
The `npm ci --ignore-scripts` setup reported three dependency-audit findings;
no secret values were printed or committed.

## Secret scan

High-confidence scan patterns covered private keys, AWS/GitHub tokens, Slack
tokens, and JWT-shaped credentials.

- exact rc2 candidate tree: `0` hits;
- full Git history: `0` hits across `28` commits;
- extracted bundle: `0` hits;
- `RELEASE_MANIFEST.json`: `0` hits;
- sensitive file classes in the bundle (`.env`, keys, DB files, dumps,
  uploads, logs): `0` files.

The bundle contains only safe environment templates. A broader lexical scan
found only source identifiers and placeholder/template references; none were
credential-bearing values.

## Bundle

The invalid pre-rc2 archive was replaced by a fresh build from the exact rc2
tag:

- path: `E:\Codex\Akula\artifacts\akula-platform-staging-2026-09-07.tar.gz`;
- size: `9,595,141` bytes;
- SHA-256:
  `42F87098A10E057B852FAA326DF054853EF6DC1624C2888CCE170A79751EA738`.

The manifest records tag `core-r1-staging-rc2-2026-09-07`, commit
`57fd512f604ebb77d24e02d221a8a69cadc54925`, Alembic head
`0025_core_day4_production_evidence`, environment `staging`, and
`production_deployment: false`. Checksums recomputed after extraction had
`0` mismatches. Compose config also passed from the extracted package.

The install script requires `AKULA_ENV=staging` and only has a
`--print-plan` mode. Verify requires a non-placeholder staging host. Rollback
is manual and does not execute destructive commands; data restore requires an
explicit confirmation flag and still performs no deletion.

## Production boundary

No production deployment, server, database, storage, DNS, service, or
production secret was accessed or changed. The old immutable tag was not
moved. The archive is now valid only as the rc2 staging bundle above; the
previous pre-rc2 archive checksum is superseded.

## Final status

`BUNDLE READY FOR SERVER UPLOAD`

The rc2 tag is self-contained for the tested Core/Scout/Constructive release
surface, the full pytest passes both from a clean clone and inside the clean
bundle extraction, and the bundle checksums and staging Compose validation
match the recorded manifest.
