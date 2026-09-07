# Akula Platform staging deployment

This package is for `environment: staging` only. It contains one shared runtime for Core, Scout and Constructive. It has no production deployment step.

## Future upload

After the staging host and SSH access are approved, upload the archive to a staging-only directory:

```text
scp artifacts/akula-platform-staging-2026-09-07.tar.gz deploy@<STAGING_HOST>:/opt/akula-platform-staging/
```

Do not replace `<STAGING_HOST>` with `human-interface.ru`.

## Install order

1. Verify the archive SHA-256 and `RELEASE_MANIFEST.json`.
2. Extract it into a new staging release directory.
3. Copy `env/shared.env.example` to `env/shared.env` and fill staging-only values on the host.
4. Create the staging PostgreSQL backup target before migrations.
5. Run `AKULA_ENV=staging ./deploy/install.sh --print-plan`.
6. Review the printed Compose command and execute it manually.
7. Run `AKULA_ENV=staging STAGING_HOST=<real-host> ./deploy/verify.sh`.

The Compose project keeps PostgreSQL, Redis, artifacts and Caddy state in staging-only volumes. Outbound Scout/Telegram activity is disabled by the staging profile.
