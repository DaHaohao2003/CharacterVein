#!/bin/sh
set -eu

uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api python -m character_vein_api.evidence_import
