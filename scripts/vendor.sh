#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf python_modules
mkdir -p python_modules
cp -R src/app python_modules/app

uv export --locked --format requirements-txt --no-dev --no-emit-project --no-hashes \
  --output-file .vendor-requirements.txt
uv pip install --target python_modules --no-compile -r .vendor-requirements.txt
rm -f .vendor-requirements.txt
