#!/usr/bin/env bash
# One-shot verification entry point. Any failing step aborts with a non-zero
# exit code, which `docker compose run` / `docker compose up` reports.
set -euo pipefail

cd "$(dirname "$0")/.."

API_BASE="${API_BASE:-http://api:8000}"
WEB_BASE="${WEB_BASE:-http://web}"

banner() { printf '\n==================== %s ====================\n' "$1"; }

banner '1/6 Backend unit tests (solver + API)'
( cd api && /opt/venv/bin/python -m pytest tests -q )

banner '2/6 Frontend unit tests (parsers/validators)'
( cd web && node --test tests/model.test.mjs )

banner '3/6 Backend build check (byte-compile)'
/opt/venv/bin/python -m compileall -q api/app

banner '4/6 Frontend build (vite)'
( cd web && npm run build )
test -f web/dist/index.html

banner '5/6 Real HTTP smoke tests (api directly + through web nginx proxy)'
API_BASE="$API_BASE" WEB_BASE="$WEB_BASE" /opt/venv/bin/python verify/smoke.py

banner '6/6 Health endpoints'
/opt/venv/bin/python - <<PY
import json, os, urllib.request
api = os.environ.get('API_BASE', 'http://api:8000')
web = os.environ.get('WEB_BASE', 'http://web')
h = json.load(urllib.request.urlopen(api + '/health', timeout=5))
assert h['status'] == 'ok', h
assert urllib.request.urlopen(web + '/healthz', timeout=5).status == 200
print('health ok:', h)
PY

banner 'ALL VERIFICATION STEPS PASSED'
