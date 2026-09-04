.PHONY: dev api worker services test lint typecheck migrate eval-ai
dev:
	pnpm dev
api:
	pnpm dev:api
worker:
	pnpm dev:worker
services:
	pnpm check:services
test:
	pnpm test
lint:
	pnpm lint
typecheck:
	pnpm typecheck
migrate:
	pnpm migrate
eval-ai:
	pnpm eval-ai
