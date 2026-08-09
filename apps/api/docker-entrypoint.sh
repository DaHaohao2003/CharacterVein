#!/bin/sh
set -eu

uv run --no-sync --package character-vein-api alembic -c apps/api/alembic.ini upgrade head
exec uv run --no-sync --package character-vein-api uvicorn character_vein_api.main:app --host 0.0.0.0 --port 8000
