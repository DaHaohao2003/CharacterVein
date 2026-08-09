.PHONY: install dev-web dev-api lint typecheck test build up down logs

install:
	pnpm install
	uv sync --all-packages

dev-web:
	pnpm dev:web

dev-api:
	pnpm dev:api

lint:
	pnpm lint

typecheck:
	pnpm typecheck

test:
	pnpm test

build:
	pnpm build

up:
	pnpm compose:up

down:
	pnpm compose:down

logs:
	pnpm compose:logs

