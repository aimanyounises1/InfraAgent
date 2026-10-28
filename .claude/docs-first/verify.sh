#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
.venv/bin/python -m pytest -q
.venv/bin/ruff check mcp_servers/policy.py tests/test_mutation_policy.py tests/mcp_servers/test_gpu_mcp.py
(cd dashboard && npm run build)
printf '%s\n' 'docs-first verification: PASS (backend tests, scoped lint, dashboard build)'
