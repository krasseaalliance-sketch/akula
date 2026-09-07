# Akula Platform staging bundle — 2026-09-07

**Статус: `FAILED`**

Пакет собран локально, без deployment. Он не может быть объявлен готовым к загрузке из-за провала обязательного полного `pytest` на чистом exact tag.

## Immutable source

- Repository: `https://github.com/krasseaalliance-sketch/akula.git`
- Tag: `core-r1-staging-rc1-2026-09-07`
- Commit: `e497f5152b204df74a065789aeb46542089bcb99`
- Alembic head: `0025_core_day4_production_evidence`
- Source was cloned into a temporary directory and checked out detached at the exact tag.

## Bundle

- Archive: `artifacts/akula-platform-staging-2026-09-07.tar.gz`
- Size: `9,594,225` bytes
- SHA-256: `014E4815E506CAF17D23924D87AD467C1D9FC657C54B00CA73F634AE4245B782`
- Extracted package root: `akula-platform-staging/`
- Files after extraction: `343`
- `CHECKSUMS.sha256` entries: `342`
- Checksum mismatches after extraction: `0`
- Manifest missing files: `0`
- Manifest extra files: `0`

The manifest records `environment: staging` and `production_deployment: false`.

## Components

| Component | Source included | Files | Component SHA-256 |
| --- | --- | ---: | --- |
| Core | Full runnable backend/frontend monorepo snapshot, including Core API/UI and migrations | 242 | `24b0a9be07275b09aee0bb6fe357549e16dffcf323dda2191ec588dedac0ce6b` |
| Scout | Real Hunter modules, lead monitor and Scout routes/components from the same monorepo | 54 | `328f5030273aeed7810a97843217062886fe9ebf2da910481a192a2e569d62c7` |
| Constructive | Real Constructive backend modules and frontend route/components | 8 | `35752604aef2bb87bf368ddfa7d10cdedf9de0d9adc5cfd460d0cab65d077c83` |

The bundle also contains `migrations/`, staging-only Compose/Caddy/scripts, four safe env templates, deployment README and rollback README. No empty component directory was used.

## Security and exclusions

Excluded from the package:

- `.env` and real secrets;
- SSH/private keys and certificates;
- SQLite/PostgreSQL files and dumps;
- user uploads and logs;
- `.next`, `node_modules`, Python virtual environments;
- temporary directories, old archives and Docker volumes;
- production deployment configuration.

Secret scan results:

- bundle tree: `HUNTER_SECRET_SCAN_PASS`, exit `0`;
- extracted tree: `HUNTER_SECRET_SCAN_PASS`, exit `0`;
- `RELEASE_MANIFEST.json`: `HUNTER_SECRET_SCAN_PASS`, exit `0`;
- forbidden sensitive file patterns: `0`.

## Verification results on clean exact tag

| Check | Result |
| --- | --- |
| `git diff --check` | exit `0` |
| `pytest` | **exit `1`** — 108 collected, 7 collection errors; tests reference files absent from the tag: `tools/qa_avito_opportunity_2026_08_11.py`, `tools/avito_site_verifier_qa2.py`, `tools/run_lead_hunter_stage1r2.py`, `tools/run_lead_hunter_stage1r4.py`, `tools/run_lead_hunter_stage2.py`, `tools/run_lead_hunter_stage21.py`, `scout-vps-stage-20260814/scout.py` |
| `npm ci` | exit `0`; npm reported 3 high-severity audit findings |
| `npm run test` | exit `0`; 6 passed |
| `npx tsc --noEmit` | exit `0` |
| `npm run lint` | exit `0`; 0 errors, 4 warnings |
| `npm run build` | exit `0` on repeat; 11 pages generated, legacy build warnings present |
| `python -m compileall -q backend` | exit `0` |
| `alembic upgrade head` | exit `0` against a new temporary SQLite database; head reached `0025_core_day4_production_evidence` |
| `docker compose --env-file .env.staging.example -f deploy/staging/docker-compose.staging.yml config --quiet` | exit `0` |

The first build attempt reached final page generation but timed out at the process wrapper (`124`); the repeated command completed with exit `0`. This is recorded rather than hidden.

## Clean extraction and Compose verification

The archive was extracted into a new temporary directory. Required paths for all three components, manifest, checksums, env templates, Compose, Caddy, scripts and migration head were present. Compose configuration from the extracted package completed with exit `0` using `env/shared.env.example`.

The deployment scripts were checked with Ubuntu WSL:

- `install.sh`, `verify.sh`, `rollback.sh` syntax: exit `0`;
- install/verify without `AKULA_ENV=staging`: exit `2` and refuse;
- rollback plan with `AKULA_ENV=staging`: exit `0`, no data restore/deletion;
- scripts contain no production hostname;
- no deployment command executes automatically; install prints the manual command only.

## Future server upload and install

After the pytest blocker is fixed in the immutable source, the exact future upload command is:

```text
scp artifacts/akula-platform-staging-2026-09-07.tar.gz deploy@<STAGING_HOST>:/opt/akula-platform-staging/
```

The operator must replace `<STAGING_HOST>` with a separate staging hostname, verify the archive SHA-256, create `env/shared.env` from the example with staging-only values, create the staging DB backup target, and review `AKULA_ENV=staging ./deploy/install.sh --print-plan` before any manual Compose start.

## Rollback

Rollback target is the previous approved staging tag/image plus a staging PostgreSQL backup. `README-ROLLBACK.md` and `deploy/rollback.sh` describe the process. No production DB, storage, DNS, secrets, files or services are part of the procedure.

## Blocker

The exact release tag is not self-contained for the mandatory full `pytest`: seven test dependencies are absent from the tag and exist only as local untracked files outside the clean checkout. Including them would violate the requirement to build strictly from the immutable tag.

Required resolution: add the missing helper files to a new reviewed immutable release tag, or remove/update the tests in the source tag so the full test suite is self-contained; then rebuild and rerun the complete verification matrix.

Production was not touched. No server upload or deployment was performed.
