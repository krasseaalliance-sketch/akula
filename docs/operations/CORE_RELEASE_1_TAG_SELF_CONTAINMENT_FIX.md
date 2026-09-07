# Core Release 1 tag self-containment fix

Status: `IN PROGRESS`

## Baseline

The audit was performed from a clean checkout of `core-r1-staging-rc1-2026-09-07` at commit `e497f5152b204df74a065789aeb46542089bcb99`. No files from the dirty working copy were available to that checkout.

`pytest -q` collected 108 tests and stopped during collection with seven `FileNotFoundError` import errors. The missing paths are not present in the old tag.

## Root-cause inventory

| № | Test | Missing file/module | Why the test imports it | Must be in Release 1? | Decision |
|---:|---|---|---|---|---|
| 1 | `backend/tests/test_avito_opportunity_qa.py` | `tools/qa_avito_opportunity_2026_08_11.py` | `runpy.run_path()` loads local helper functions for an Avito/Vitrina QA snapshot. | No. It is a one-off QA script, not a Core, Scout, or Constructive runtime dependency. | B — rewrite against current Hunter contracts. |
| 2 | `backend/tests/test_avito_site_verifier_regression.py` | `tools/avito_site_verifier_qa2.py` | `runpy.run_path()` loads a local site-verification helper with hard-coded `E:\\Codex\\Vitrina` paths. | No. It is a local web-QA helper and is not imported by runtime code. | B — keep deterministic verification coverage through current public modules. |
| 3 | `backend/tests/test_hunter_stage1r2.py` | `tools/run_lead_hunter_stage1r2.py` | `runpy.run_path()` loads a historical stage runner to inspect constants and scoring helpers. | No. The current read-only Hunter pipeline and source adapters replace this runner. | B — test current adapter/pipeline contracts. |
| 4 | `backend/tests/test_hunter_stage1r4.py` | `tools/run_lead_hunter_stage1r4.py` | `runpy.run_path()` loads a historical alert-loop runner and its local file-alert adapter. | No. The helper is not a runtime module and has no tracked consumer outside this stale test. | B — preserve fail-closed outbound safety using the current Hunter safety API. |
| 5 | `backend/tests/test_hunter_stage2.py` | `tools/run_lead_hunter_stage2.py` | `runpy.run_path()` loads a historical stage runner and reads generated local reports. | No. Generated stage reports are deployment/measurement artifacts, not application dependencies. | B — test current source ingestion and pipeline behavior with fixtures. |
| 6 | `backend/tests/test_hunter_stage21.py` | `tools/run_lead_hunter_stage21.py` | `runpy.run_path()` loads a follow-up measurement runner and reads files generated outside Git. | No. It is a temporary observation script with no runtime consumer. | B — test current deterministic pipeline behavior without generated files. |
| 7 | `backend/tests/test_scout_quality.py` | `scout-vps-stage-20260814/scout.py` | A dynamic import calls a legacy standalone SQLite/HTTP Scout dashboard predicate. | No. Current Scout is the tracked FastAPI/Next application and this standalone snapshot is unrelated to `/scout`. | B — assert the current Hunter qualification contract. |

## Evidence used for classification

- `git log --all -- <path>` and an object/path scan found no tracked history for any of the seven paths.
- The descendant snapshot commit `667904aa4e5bbae6e364bf8e35634aa873806cb2` contains the current tracked backend/frontend Scout and Constructive sources, but none of these seven paths.
- `rg` found the seven test files as the only repository consumers of the missing paths; no application module imports them.
- The local copies are untracked artifacts. Two Avito helpers contain absolute `E:\\Codex\\Vitrina\\source-assets\\lead-research` paths. The four stage runners write local reports/state and chain to other untracked stage scripts. The standalone Scout snapshot uses SQLite, network polling, and `SCOUT_HOME`.

Therefore adding the local files would make the release depend on machine-specific and historical artifacts. The repair keeps the useful regression intent in tests and removes the stale path dependency.

## Baseline verification

- Old tag clean checkout: exact commit/tag verified.
- `git diff --check`: exit `0`.
- `pytest -q`: exit `1`, 7 collection/import errors listed above.
- Production and the old immutable tag have not been changed.

After the seven collection errors were removed, the first clean full run reached all tests and exposed one additional stale, non-import dependency: `backend/tests/test_hunter_stage1r1.py` read the absent historical top-level `docker-compose.yml` and asserted a removed `hunter-readonly` service/runner. This path is also not present in the old tag, has no current runtime consumer, and was replaced with the tracked `app.hunter.safety.hunter_runtime_capabilities()` contract. It is documented separately from the original seven import errors because it was only observable after collection succeeded.

The first real fresh PostgreSQL upgrade then exposed a schema-order problem in `0001_initial`: the current `message_drafts` model contains foreign keys to `human_writing_runs` and `human_writing_variants`, while those tables were not in `INITIAL_TABLES`. The repair adds the required `community_style_profiles → human_writing_runs → human_writing_variants` order before `message_drafts`. The PostgreSQL-safe path in `0016_support_campaign_topics` was also corrected after the same fresh upgrade reached it: batch recreation attempted to drop a primary-key constraint still referenced by `support_messages`; PostgreSQL now uses in-place ALTER operations while SQLite keeps the existing batch path.

A subsequent fresh PostgreSQL run reached `0024_core_day4_artifacts_qa` and found the same unsafe batch-recreation pattern for `core_agents`, whose primary key is referenced by Core child tables. `0024` now uses PostgreSQL in-place ALTER operations for all four affected tables and retains its existing SQLite batch path.

The next fresh PostgreSQL run completed schema DDL but failed while updating `alembic_version`: Alembic's default `VARCHAR(32)` could not store the 33-character `0025_core_day4_production_evidence` revision. `0001_initial` now widens that version column to `VARCHAR(128)` on PostgreSQL before applying the rest of the initial schema.

## Planned repair

Rewrite only the seven stale test contracts to use tracked current APIs and deterministic fixtures. No skips, xfails, compatibility copies, or production deployment are permitted. The final sections of this document will record the red/green runs, new rc2 commit/tag, clean-clone verification, bundle checksum, and final status.
