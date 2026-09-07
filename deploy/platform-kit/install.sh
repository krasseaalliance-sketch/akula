#!/usr/bin/env sh
set -eu

if [ "${AKULA_ENV:-}" != "staging" ]; then
  echo "Refusing: set AKULA_ENV=staging" >&2
  exit 2
fi

if [ "${1:-}" != "--print-plan" ]; then
  echo "Safe mode: no deployment was executed." >&2
  echo "Usage: AKULA_ENV=staging ./install.sh --print-plan" >&2
  exit 2
fi

if [ ! -f env/shared.env ]; then
  echo "Missing env/shared.env; copy env/shared.env.example and fill staging-only values." >&2
  exit 2
fi

docker compose --env-file env/shared.env -f deploy/docker-compose.platform.yml config --quiet
echo "Validated staging configuration only."
echo "Manual deployment command: docker compose --env-file env/shared.env -f deploy/docker-compose.platform.yml up -d --build"
echo "No production URL, database, storage or secret is referenced by this script."
