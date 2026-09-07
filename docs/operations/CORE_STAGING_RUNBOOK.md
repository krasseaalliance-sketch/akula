# Core Release 1 — external staging runbook

This runbook is staging-only. It never targets `human-interface.ru`, its
database, Redis, storage, DNS, certificates, or secrets.

## Required host

- Dedicated VPS or container host with Docker Engine and Compose v2.
- Public DNS record for a staging-only hostname.
- Inbound TCP 80/443 for Caddy ACME issuance.
- At least 2 vCPU, 4 GB RAM, 20 GB free disk, and a backup destination.
- Separate staging PostgreSQL, Redis, artifact volume, JWT secret, and logs.
- GitHub read access to `krasseaalliance-sketch/akula`.

## DNS and HTTPS

1. Choose a hostname different from every production hostname.
2. Point only that hostname to the staging host.
3. Set `STAGING_HOST` and `STAGING_PUBLIC_URL` in the untracked
   `.env.staging` file.
4. Caddy obtains and renews the staging certificate. Do not copy a production
   certificate or DNS record.

## Staging configuration

Copy `.env.staging.example` to `.env.staging` on the host and replace every
`replace-in-secret-store` value through the approved secret channel. Do not put
the filled file in Git, GitHub Actions logs, or this report.

The Compose project uses named volumes prefixed by `akula-core-staging` and
binds backend/frontend only to loopback; Caddy is the sole public entry point.
Artifact files stay in the staging-only `staging_artifacts` volume.

## Deploy the exact candidate

```bash
git fetch --tags origin
git checkout --detach core-r1-rc1-2026-09-07
test "$(git rev-parse HEAD)" = "71b1d7869f10a44b895c04f5576d8ea55cde5bca"
docker compose --env-file .env.staging -f deploy/staging/docker-compose.staging.yml config
docker compose --env-file .env.staging -f deploy/staging/docker-compose.staging.yml up -d db redis
docker compose --env-file .env.staging -f deploy/staging/docker-compose.staging.yml exec -T db pg_dump -U "$STAGING_POSTGRES_USER" -d "$STAGING_POSTGRES_DB" --format=custom > backups/core-r1-staging-pre-migration.dump
docker compose --env-file .env.staging -f deploy/staging/docker-compose.staging.yml up -d backend frontend caddy
```

The backend command runs `alembic upgrade head` against staging PostgreSQL
only. Verify `0025_core_day4_production_evidence` before external E2E.

## Health and release identity checks

```bash
curl --fail --silent --show-error "https://${STAGING_HOST}/health"
curl --fail --silent --show-error --head "https://${STAGING_HOST}/scout/core"
test "$(curl --fail --silent --head "https://${STAGING_HOST}/health" | tr -d '\r' | grep -c 'X-Environment: STAGING')" -eq 1
test "$(curl --fail --silent --head "https://${STAGING_HOST}/health" | tr -d '\r' | grep -c 'X-Release-Tag: core-r1-rc1-2026-09-07')" -eq 1
```

Also verify `/core` is `404`, unauthenticated Core APIs do not return data,
artifact content is workspace-authorized, and Scout/Constructive routes remain
available. Keep response headers and logs free of bearer tokens and secrets.

## Backup and rollback

Keep the pre-migration dump, its SHA-256 checksum, image digests, and Caddy
logs in the staging backup location. To roll back the application, stop the
candidate, check out the previous approved tag, rebuild, and restart. Do not
run destructive Alembic downgrades. Restore the verified dump into an isolated
recovery database and cut over only through the approved staging procedure.

```bash
docker compose --env-file .env.staging -f deploy/staging/docker-compose.staging.yml down
git checkout --detach <previous-approved-tag>
docker compose --env-file .env.staging -f deploy/staging/docker-compose.staging.yml build backend frontend
docker compose --env-file .env.staging -f deploy/staging/docker-compose.staging.yml up -d backend frontend caddy
```

Production access is not part of this procedure.
