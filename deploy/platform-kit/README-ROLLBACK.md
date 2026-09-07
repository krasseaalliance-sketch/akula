# Akula Platform staging rollback

Rollback is limited to the staging host and staging database. The previous application tag and backup must be named before deployment.

1. Freeze staging traffic and preserve logs.
2. Record the current release tag, image IDs and database backup ID.
3. Checkout the previous approved staging tag or restore the previous image by checksum.
4. Restore PostgreSQL only into the staging database from the approved backup when required.
5. Start the staging Compose project manually.
6. Run `AKULA_ENV=staging STAGING_HOST=<real-host> ./deploy/verify.sh`.
7. Record the result in the staging audit evidence.

`rollback.sh` prints this procedure and never deletes volumes or restores data by default. Any data restore requires the explicit `--confirm-data-restore` flag and a separate operator decision; the script remains non-destructive.
