#!/bin/sh
set -eu

uv run --no-sync --package character-vein-api alembic -c apps/api/alembic.ini upgrade head
exec uv run --no-sync --package character-vein-api python -m character_vein_api.glyph_import
