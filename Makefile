.PHONY: up down seed credentials demo-users backfill daily-update data-doctor test lint

up:
	docker compose up --build

down:
	docker compose down

seed:
	docker compose exec -w / api python -m data.generate_dummy

# Mevcut kullanicilara giris bilgisi atar, VERIYI SILMEDEN.
# Migration sonrasi test/canli ortamda `make seed` YERINE bu kullanilir:
# seed once tum kullanici verisini (sohbet gecmisi dahil) siliyor.
credentials:
	docker compose exec -w / api python -m scripts.backfill_credentials $(ARGS)

# Demo kullanicilarinin giris bilgileri (T.C. kimlik no + ortak sifre).
# Tumu icin: make demo-users ARGS="--limit 0"
demo-users:
	docker compose exec -w / api python -m scripts.demo_users $(ARGS)

backfill:
	docker compose exec -w / api python -m data.backfill --days 365

daily-update:
	docker compose exec -w / api python -m data.daily_update

# Maliyet ile degerleme ayni evrenden mi geliyor? Backfill seed'den SONRA
# calistiysa islem fiyatlari artik var olmayan fiyatlari gosterir ve K/Z
# uydurma cikar. Sadece OKUR. Ayrinti: scripts/README.md
data-doctor:
	docker compose exec -w / api python -m scripts.data_doctor

test:
	docker compose exec -w / api pytest

lint:
	docker compose exec api ruff check .
	docker compose exec api black --check .
	docker compose exec frontend npm run lint
