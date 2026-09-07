# Core Release 1 — Day 7 staging evidence

**Status:** `BLOCKED`

**Evidence captured:** 2026-09-07T10:40:03+07:00

## Blocking condition

The workspace does not provide a public, isolated staging environment, a public
HTTPS URL, or credentials for an independently operated QA account. The only
available Core runtime is local (`http://127.0.0.1:3000/scout/core`) and is not
external staging. No production domain was used.

Required to unblock: provide one public staging URL with isolated frontend,
backend, database, artifact storage, configuration, and access for separate
Creator and QA accounts. The QA account must be created through the normal auth
flow and must not be an `OWNER` or a manually altered database identity.

## Candidate identity

- Base commit: `e646b902829ac20542a45e796d2f2353fc61fb08`.
- Release candidate label: `core-r1-day6-2026-09-07`.
- Immutable Day 7 commit/tag: not created. The worktree is on `main` and has
  450 lines of unrelated or pre-existing uncommitted changes; freezing a
  candidate without an explicit file boundary would be unsafe.
- Alembic head: `0025_core_day4_production_evidence`.
- Production deployment: not performed.

## Staging deployment record

| Field | Result |
|---|---|
| Public staging URL | Not available |
| Deployment time | Not applicable |
| Commit/tag deployed | None |
| Frontend/backend version | Not deployed externally |
| Alembic revision before/after | Not measured on external staging; repository head is `0025_core_day4_production_evidence` |
| File storage | External staging storage not provisioned |
| Configuration profile | External staging profile not provided |
| Rollback | Prepared, not executed; see [release candidate packet](CORE_RELEASE_1_DAY6_RELEASE_CANDIDATE.md) |
| Production isolation | No deployment or migration request was sent to production |

## Browser scenarios

External browser E2E was not run because there is no qualifying public staging
target. Local browser results are retained only as supporting development
evidence and do not satisfy Day 7 acceptance.

| Scenario | External result | Actor/audit evidence | Evidence |
|---|---|---|---|
| A — successful acceptance | `BLOCKED` | Not collected on external staging | No qualifying screenshot, log, or public URL |
| B — FAIL and remediation | `BLOCKED` | Not collected on external staging | No qualifying screenshot, log, or public URL |
| C — isolation and permissions | `BLOCKED` | Independent external QA identity unavailable | No qualifying cross-workspace evidence |

Local-only supporting checks previously completed on
`http://127.0.0.1:3000/scout/core`:

- the success path reached `SUCCEEDED`, independent QA request `PASS`, and
  `ACCEPTED` in the local test runtime;
- a real file and image were uploaded and viewed through authorized local
  content endpoints;
- the FAIL path returned the original task and created one remediation task;
- the local run does not prove an independent external QA account because the
  browser verifier was not a separate staging user.

These local results must not be presented as external staging evidence or
production approval.

## Technical checks

Local checks completed for the candidate worktree:

- `python -m pytest -q`: `132 passed, 2330 warnings`;
- frontend production build: passed, `11/11` static pages;
- TypeScript: passed, exit code `0`;
- ESLint: passed, `0 errors, 4 warnings`;
- Python `compileall`: passed, exit code `0`;
- clean Alembic upgrade test: `1 passed, 1 warning`;
- `alembic heads`: `0025_core_day4_production_evidence (head)`;
- frontend Node tests: `6 passed`;
- local smoke: Core `200`, health `200`, `/core` `404`, canonical route
  `/scout/core`;
- warning debt remains open: `2330` legacy warnings, `0` approved, `2330`
  requiring staged remediation.

The checks above are local verification only. They do not replace the required
external staging E2E, external identity checks, or staging evidence package.

## Production safety

- No production deployment, migration, DNS change, or production file change
  was performed.
- `human-interface.ru` was not used as a staging target.
- No secrets, credentials, or tokens are included in this document.
- Deployment and rollback procedures remain prepared in
  [CORE_RELEASE_1_DAY6_RELEASE_CANDIDATE.md](CORE_RELEASE_1_DAY6_RELEASE_CANDIDATE.md).

## Final decision

`BLOCKED`

The single blocker is the absence of a public isolated staging URL and access
to a separate QA identity. No `READY FOR PRODUCTION APPROVAL` decision is
permitted until that staging environment is provisioned and scenarios A, B,
and C are rerun there with verifiable evidence.
