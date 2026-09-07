#!/usr/bin/env sh
set -eu

if [ "${AKULA_ENV:-}" != "staging" ]; then
  echo "Refusing: set AKULA_ENV=staging" >&2
  exit 2
fi

echo "Rollback is manual and staging-only."
echo "1. Stop the application with the operator-approved staging command."
echo "2. Checkout the approved previous staging tag and verify its checksum."
echo "3. Restore the staging database only if the named staging backup is approved."
echo "4. Re-run verify.sh and retain the audit log."

if [ "${1:-}" != "--confirm-data-restore" ]; then
  echo "No data restore or deletion executed. Add --confirm-data-restore only after an explicit staging backup decision."
  exit 0
fi

echo "Confirmation flag received; this bundle still does not execute destructive commands."
