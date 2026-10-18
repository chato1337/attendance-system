.PHONY: up down test lint

up:
	docker compose -f infra/docker-compose.yml up --build

down:
	docker compose -f infra/docker-compose.yml down

test:
	cd backend && .venv/bin/pytest
	cd frontend && npm test
	cd edge && go test ./...

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd frontend && npm run lint && npm run format:check
	cd edge && gofmt -l .
