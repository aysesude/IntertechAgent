.PHONY: up down seed backfill daily-update test lint

up:
	docker compose up --build

down:
	docker compose down

seed:
	docker compose exec -w / api python -m data.generate_dummy

backfill:
	docker compose exec -w / api python -m data.backfill --days 365

daily-update:
	docker compose exec -w / api python -m data.daily_update

test:
	docker compose exec -w / api pytest

lint:
	docker compose exec api ruff check .
	docker compose exec api black --check .
	docker compose exec frontend npm run lint
