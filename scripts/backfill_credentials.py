"""Mevcut kullanıcılara giriş bilgisi atar — VERİYİ SİLMEDEN.

    make credentials

NEDEN GEREKLİ. `c5d81a3f7b60` migration'ı `national_id` ve `password_hash`
sütunlarını NULL olarak ekler; bir migration içinde bcrypt özeti üretilemez.
Dolayısıyla göç sonrası veritabanındaki mevcut kullanıcıların hiçbiri giriş
YAPAMAZ.

NEDEN `make seed` DEĞİL. Seed kimlikleri doğru şekilde üretir ama önce
`wipe_user_data` ile kullanıcıları, portföyleri, işlem defterini ve SOHBET
GEÇMİŞİNİ siler. Zaten kullanılan bir ortamda (test/canlı) bu kabul edilemez.
Bu betik yalnızca eksik iki alanı doldurur, başka hiçbir satıra dokunmaz.

Betik yeniden çalıştırılabilir (idempotent): kimliği olan kullanıcı atlanır,
dolayısıyla mevcut kimlikler ve şifreler DEĞİŞMEZ. Şifre değiştirmek için
önce ilgili sütunları elle NULL yapmak gerekir — kazara şifre sıfırlama
olmasın diye.
"""

import argparse

from faker import Faker
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import User

# `data/seed_ledger.py` ile aynı tohum: aynı kullanıcı kümesi üzerinde iki yol
# da aynı numaraları üretsin, ekip iki farklı liste ezberlemek zorunda kalmasın.
SEED = 42


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Hiçbir şey yazma, yalnızca kaç kullanıcının etkileneceğini söyle",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        eksik = (
            db.execute(
                select(User).where((User.national_id.is_(None)) | (User.password_hash.is_(None)))
                # Belirlenimcilik: sıralama sabit olmazsa aynı veritabanında
                # ikinci koşu farklı kullanıcıya farklı numara verebilirdi.
                .order_by(User.created_at, User.id)
            )
            .scalars()
            .all()
        )

        if not eksik:
            print("Tüm kullanıcıların giriş bilgisi zaten var, yapılacak bir şey yok.")
            return

        print(f"{len(eksik)} kullanıcının giriş bilgisi eksik.")
        if args.dry_run:
            print("--dry-run: hiçbir şey yazılmadı.")
            return

        # Halihazırda kullanılan numaralar: üretilen numara bunlarla
        # çakışırsa atlanır (national_id UNIQUE).
        kullanilan = {
            n for (n,) in db.execute(select(User.national_id).where(User.national_id.is_not(None)))
        }

        fake = Faker("tr_TR")
        fake.seed_instance(SEED)

        # Şifre özeti BİR KEZ hesaplanır (bkz. config.py: demo kullanıcıları
        # ortak şifre paylaşır). 50 ayrı bcrypt çağrısı gereksiz yere yavaş.
        ortak_ozet = hash_password(settings.demo_user_password)

        for user in eksik:
            if user.national_id is None:
                numara = fake.unique.ssn()
                while numara in kullanilan:
                    numara = fake.unique.ssn()
                kullanilan.add(numara)
                user.national_id = numara
            if user.password_hash is None:
                user.password_hash = ortak_ozet

        db.commit()
        print(f"{len(eksik)} kullanıcıya giriş bilgisi atandı.")
        print(f"Ortak şifre: {settings.demo_user_password}")
        print("Listeyi görmek için: make demo-users")
    finally:
        db.close()


if __name__ == "__main__":
    main()
