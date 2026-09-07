#!/usr/bin/env sh
set -eu

if [ "${AKULA_ENV:-}" != "staging" ]; then
  echo "Refusing: set AKULA_ENV=staging" >&2
  exit 2
fi

if [ -z "${STAGING_HOST:-}" ] || [ "$STAGING_HOST" = "staging.example.invalid" ]; then
  echo "Set STAGING_HOST to the real staging hostname." >&2
  exit 2
fi

base="https://${STAGING_HOST}"
curl --fail --silent --show-error --location "$base/ready" >/dev/null
curl --fail --silent --show-error --location "$base/scout/core" >/dev/null
curl --fail --silent --show-error --location "$base/scout/constructive" >/dev/null
if curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$base/core" | grep -qx '404'; then
  echo "Routes verified: /scout/core, /scout/constructive, /core=404"
else
  echo "Unexpected /core response" >&2
  exit 1
fi
