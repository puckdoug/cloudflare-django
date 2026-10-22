#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN}"
: "${CLOUDFLARE_ACCOUNT_ID:?set CLOUDFLARE_ACCOUNT_ID}"
: "${DJANGO_SECRET_KEY:?set DJANGO_SECRET_KEY}"
: "${BOOTSTRAP_TOKEN:?set BOOTSTRAP_TOKEN}"
: "${DJANGO_SUPERUSER_USERNAME:?set DJANGO_SUPERUSER_USERNAME}"
: "${DJANGO_SUPERUSER_EMAIL:?set DJANGO_SUPERUSER_EMAIL}"
: "${DJANGO_SUPERUSER_PASSWORD:?set DJANGO_SUPERUSER_PASSWORD}"

command -v uv >/dev/null || { echo "uv is required" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

if ! npx cf zones list 2>/dev/null | grep -q "heroic.ch"; then
  echo "warning: heroic.ch was not listed; deployment will fail if the zone is absent" >&2
fi

uv sync --locked
npm ci
./scripts/vendor.sh

secrets_file="$(mktemp)"
trap 'rm -f "$secrets_file"' EXIT

jq -n \
  --arg secret_key "$DJANGO_SECRET_KEY" \
  --arg bootstrap_token "$BOOTSTRAP_TOKEN" \
  --arg username "$DJANGO_SUPERUSER_USERNAME" \
  --arg email "$DJANGO_SUPERUSER_EMAIL" \
  --arg password "$DJANGO_SUPERUSER_PASSWORD" \
  '{
    DJANGO_SECRET_KEY: $secret_key,
    BOOTSTRAP_TOKEN: $bootstrap_token,
    DJANGO_SUPERUSER_USERNAME: $username,
    DJANGO_SUPERUSER_EMAIL: $email,
    DJANGO_SUPERUSER_PASSWORD: $password
  }' > "$secrets_file"

npx cf deploy --secrets-file "$secrets_file"

for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null https://dj.heroic.ch/; then
    break
  fi
  sleep 5
done

curl -fsS -X POST \
  -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
  https://dj.heroic.ch/__bootstrap/migrate/
echo
curl -fsS -X POST \
  -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
  https://dj.heroic.ch/__bootstrap/admin/
echo
