#!/usr/bin/env bash
set -euo pipefail

if [ -n "${CLIENT_SECRETS_B64:-}" ]; then
  echo "$CLIENT_SECRETS_B64" | base64 -d > /app/client_secrets.json
  echo "Wrote /app/client_secrets.json"
fi

if [ -n "${TOKEN_JSON_B64:-}" ]; then
  echo "$TOKEN_JSON_B64" | base64 -d > /app/token.json
  echo "Wrote /app/token.json"
fi

echo "Starting bot (UPLOAD_TO_YOUTUBE=${UPLOAD_TO_YOUTUBE:-})"
exec python /app/bot_voice.py
