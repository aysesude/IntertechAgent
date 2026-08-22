.PHONY: up down seed demo-users backfill daily-update test lint

up:
	docker compose up --build

down:
	docker compose down

seed:
	docker compose exec -w / api python -m data.generate_dummy

# Demo kullanicilarinin giris bilgileri (T.C. kimlik no + ortak sifre).
# Tumu icin: make demo-users ARGS="--limit 0"
demo-users:
	docker compose exec -w / api python -m scripts.demo_users $(ARGS)

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
