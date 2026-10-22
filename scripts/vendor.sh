#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf src/vendor
uv export --locked --format requirements-txt --no-dev --no-emit-project --no-hashes \
  --output-file .vendor-requirements.txt
uv pip install --target src/vendor --no-compile -r .vendor-requirements.txt
rm -f .vendor-requirements.txt
