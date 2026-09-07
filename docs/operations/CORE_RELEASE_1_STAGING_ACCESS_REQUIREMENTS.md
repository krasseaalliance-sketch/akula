# Core Release 1 — staging access requirements

**State:** `BLOCKED`

This document records the exact access required to perform Day 8 external
staging verification. Localhost, a local SQLite database, an HTTP 200 response,
or a running local process is not a substitute.

## Required access

| Item | Required value | Current state |
|---|---|---|
| Public staging URL | Dedicated HTTPS URL different from `human-interface.ru` | Missing |
| Hosting/server/CI | Operator access or approved deployment mechanism for the staging host | Missing |
| Frontend/backend | Separate staging services built from an immutable release tag | Missing |
| Database | Separate staging database, not production and not the local SQLite file | Missing |
| Artifact storage | Separate staging bucket/volume with a documented retention and rollback path | Missing |
| Credentials/configuration | Staging-only secrets and tokens delivered through the approved secret channel | Missing |
| Test workspace | Isolated workspace for the staging run | Missing |
| Creator account | Separate non-production test account with Creator permissions | Missing |
| QA account | Separate email/account, QA permissions without `OWNER`, created through normal auth | Missing |
| Deployment authority | Named operator allowed to deploy the exact release tag to staging | Missing |
| Minimum seed data | Test project/mission/sprint/task and permitted agent set | To be created after access |
| Rollback | Staging-specific previous tag/image and database recovery procedure | Procedure prepared; target unavailable |

## Explicitly not required

- Production credentials, production database, production artifact storage, or
  production tokens.
- Manual role changes in the database.
- API identity spoofing, test bypasses, or shared Creator/QA credentials.

## Acceptance after access is supplied

The operator must provide the staging URL, deployed immutable tag/commit,
deployment timestamp, frontend/backend versions, Alembic revision, storage
profile, and the secure delivery channel for the two test accounts. The
external browser scenarios A/B/C and the production-isolation checks can then
be executed and recorded in the Day 7 evidence package.

Production `human-interface.ru` must remain untouched throughout this work.
