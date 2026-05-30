#!/bin/bash
set -euo pipefail

# Cloud Run mounts the token.json secret read-only at /secrets/token.json.
# Copy it to the working directory so scanner.py can write back a refreshed token.
cp /secrets/token.json /app/backend/token.json

exec python scanner.py