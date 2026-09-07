# Core Release 1 — Day 6 release candidate packet

Статус пакета: `BLOCKED` для решения о production approval.

Причина: в текущем workspace нет отдельного публичного staging URL и предоставленного доступа к изолированному staging-окружению. `127.0.0.1` используется только для локальной проверки и не считается external staging.

## Candidate identity

- Base git commit: `e646b902829ac20542a45e796d2f2353fc61fb08`.
- Candidate label: `core-r1-day6-2026-09-07`.
- Candidate state: рабочее дерево содержит незакоммиченные изменения; перед любым deployment нужен отдельный immutable commit/tag.
- Alembic head: `0025_core_day4_production_evidence`.
- Production deployment: не выполнялся.

## Runtime file set

Backend application:

- `backend/app/core_models.py`
- `backend/app/core_schemas.py`
- `backend/app/core_services.py`
- `backend/app/core_api.py`
- `backend/migrations/versions/0001_initial.py`
- `backend/migrations/versions/0009_lead_message_links.py`
- `backend/migrations/versions/0010_community_ranking_join_state.py`
- `backend/migrations/versions/0011_widen_lead_recommendation.py`
- `backend/migrations/versions/0012_lead_recommendation_text.py`
- `backend/migrations/versions/0013_lead_analysis_recommendation_text.py`
- `backend/migrations/versions/0016_support_campaign_topics.py`
- `backend/migrations/versions/0017_constructive_domain.py`
- `backend/migrations/versions/0018_asmet_message_processing.py`
- `backend/migrations/versions/0020_core_release1_foundation.py`
- `backend/migrations/versions/0021_core_day2_workflow.py`
- `backend/migrations/versions/0022_core_day3_agents.py`
- `backend/migrations/versions/0023_core_day3_runs.py`
- `backend/migrations/versions/0024_core_day4_artifacts_qa.py`
- `backend/migrations/versions/0025_core_day4_production_evidence.py`

Frontend application:

- `frontend/app/api/[...path]/route.ts`
- `frontend/app/paths.ts`
- `frontend/app/core/page.tsx`
- `frontend/app/core/artifact-qa-panel.tsx`
- `frontend/app/core/run-monitor.tsx`
- `frontend/app/core/core.css`
- `frontend/package.json`
- `frontend/tsconfig.json`

## Backup before deployment

Run from the deployment host after verifying the target and environment file. Do not continue if the output file is missing or empty:

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
New-Item -ItemType Directory -Path "backups\core-r1-$stamp" -Force
docker compose exec -T db pg_dump -U $env:POSTGRES_USER -d $env:POSTGRES_DB --format=custom --file=- > "backups\core-r1-$stamp\lead_hunter.dump"
Get-Item "backups\core-r1-$stamp\lead_hunter.dump" | Where-Object Length -gt 0
```

Record the active image digests and backup checksum before migration.

## Deployment procedure — prepared, not executed

1. Freeze the candidate as an immutable git commit/tag and verify the public QA checklist against that exact commit.
2. Confirm the staging and production environment files are different and that the target host is the intended environment.
3. Complete and verify the database backup above.
4. Build only the candidate images: `docker compose build backend frontend`.
5. Run `docker compose run --rm backend alembic -c alembic.ini upgrade head` and verify `0025_core_day4_production_evidence`.
6. Restart only the intended backend/frontend services with `docker compose up -d backend frontend`.
7. Run health, canonical route, authorization, workspace-isolation, artifact-content, Scout, and Constructive smoke checks.
8. Stop and roll back if any check fails; do not infer readiness from process status or HTTP 200 alone.

## Rollback procedure — prepared, not executed

1. Stop the candidate services and retain their logs and image digests.
2. Restore the previous application image/tag.
3. Do not downgrade Alembic destructively. Restore the verified database backup into an isolated recovery database, validate it, then perform the approved database cutover procedure.
4. Restart the previous services and run the smoke checklist.
5. Record the incident, restored image, backup checksum, operator, and verification time.

## Public QA checklist

- Public staging URL is reachable and shows the candidate commit/build.
- `/scout/core` loads; `/core` returns `404`.
- Creator and QA are separate accounts with separate workspaces and non-creator QA permissions.
- Creator-created task receives an agent result, file/image evidence, independent QA `PASS`, and becomes `ACCEPTED`.
- QA `FAIL` creates exactly one remediation task and cannot accept the original result.
- Artifact content, versions, audit events, and workspace isolation are verified with direct and unauthenticated requests.
- Logs contain no bearer tokens, passwords, or secret configuration values.
- Production evidence contains URL, build/commit, screenshot, logs, checklist, result, timestamp, and executor.

This packet is preparation only. No production deployment, production migration, or production file change was performed.
