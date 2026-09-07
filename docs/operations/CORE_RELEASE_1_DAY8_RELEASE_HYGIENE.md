# Core Release 1 — Day 8 release hygiene

**Status:** `BLOCKED`

## Snapshot

The source snapshot was taken on 2026-09-07 at 10:40 +07:00 before the Day 8
documents were added. `git status --short` contained exactly 450 entries. Each
entry was assigned to one mutually exclusive category below; no user files
were deleted, reset, cleaned, or silently moved.

| Category | Entries | Treatment | Explanation |
|---|---:|---|---|
| Release 1 Core candidate | 23 | Candidate scope; reviewed separately | Core API/models/services, Core migrations/tests, Core UI, proxy/path/build config, and Release 1 planning files. |
| App or infrastructure | 68 | Keep outside candidate until individually reviewed | Existing backend/frontend, deployment, scripts, tools, and other application changes not proven necessary for Core. |
| Documentation or text | 126 | Keep outside candidate unless explicitly Release 1 documentation | Historical reports, specifications, journals, and text exports with mixed provenance. |
| Data or build outputs | 107 | Exclude | Archives, exports, databases, logs, generated output, and other non-source artifacts. |
| Temporary work products | 105 | Exclude | `.tmp*`, screenshots, transfer material, staging experiments, and other transient files. |
| Other / unresolved | 21 | Do not touch; review before any release use | Paths that do not have a verified Release 1 ownership or safe inclusion rule. |
| **Total** | **450** |  | Every status entry is represented exactly once. |

## Candidate boundary

The 23 Release 1 entries in the snapshot were:

- `frontend/app/api/[...path]/route.ts`
- `frontend/app/paths.ts`
- `frontend/package.json`
- `frontend/tsconfig.json`
- `backend/app/core_api.py`
- `backend/app/core_models.py`
- `backend/app/core_schemas.py`
- `backend/app/core_services.py`
- `backend/migrations/versions/0020_core_release1_foundation.py`
- `backend/migrations/versions/0021_core_day2_workflow.py`
- `backend/migrations/versions/0022_core_day3_agents.py`
- `backend/migrations/versions/0023_core_day3_runs.py`
- `backend/migrations/versions/0024_core_day4_artifacts_qa.py`
- `backend/migrations/versions/0025_core_day4_production_evidence.py`
- `backend/tests/test_core_day2.py`
- `backend/tests/test_core_day3_agents.py`
- `backend/tests/test_core_day3_runs.py`
- `backend/tests/test_core_day4_artifacts.py`
- `backend/tests/test_core_day4_qa.py`
- `backend/tests/test_core_day5_uploads.py`
- `backend/tests/test_core_release1.py`
- `backend/tests/test_migrations_clean_upgrade.py`
- `frontend/app/core/`

The following additional files were explicitly reviewed and included in the
candidate because they are required to wire, seed, migrate, build, test, or
document Core: `.dockerignore`, `frontend/Dockerfile`,
`backend/app/main.py`, `backend/app/seed.py`, `backend/app/services.py`, the
legacy migration fixes `0001`, `0009`–`0013`, `0016`–`0018`,
`frontend/app/layout.tsx`, `frontend/eslint.config.mjs`, the three Core route
tests, and the four Release 1 operations documents. They were not included
merely because they were nearby; each is part of the reviewed candidate
boundary.

## Immutable candidate decision

The reviewed candidate was created from
`e646b902829ac20542a45e796d2f2353fc61fb08` on the separate branch
`codex/core-r1-rc1-2026-09-07`. The candidate commit is
`ceb2228` and the annotated tag is `core-r1-rc1-2026-09-07`.

The branch worktree still contains unrelated user changes after the candidate
commit. Deployment must therefore use a clean checkout of the exact tag, not
the current dirty worktree. No unrelated path was included in the candidate
commit.

The remaining release blocker is external staging access. See
[CORE_RELEASE_1_STAGING_ACCESS_REQUIREMENTS.md](CORE_RELEASE_1_STAGING_ACCESS_REQUIREMENTS.md).

## Verification baseline

The latest local baseline remains:

- `pytest`: `132 passed, 2330 warnings`;
- frontend build: passed, `11/11` pages;
- TypeScript: exit `0`;
- ESLint: `0 errors, 4 warnings`;
- Python `compileall`: exit `0`;
- clean Alembic upgrade test: `1 passed, 1 warning`;
- Alembic head: `0025_core_day4_production_evidence`;
- frontend Node tests: `6 passed`;
- local Core smoke: `200`; legacy `/core`: `404`.

These are local checks and do not constitute external staging approval.

## One next step

Provide the isolated public staging URL and the approved staging deployment
access described in the access requirements document. Then freeze the reviewed
candidate tag and run the external A/B/C browser evidence suite against that
exact tag.
