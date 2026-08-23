"""Demo kullanıcılarının giriş bilgilerini listeler.

    make demo-users

Kimlik doğrulama geldikten sonra arayüze "hangi kullanıcı?" diye sorulacak
bir kutu KOYULMADI: gerçek bir giriş ekranında kullanıcı listesi sergilenmez
ve giriş yapmadan erişilebilen bir `GET /api/users` ucu, tüm demo
kullanıcılarını (ve T.C. kimlik numaralarını) kimliksiz dışarı vermek olurdu.
Onun yerine liste burada, terminalde duruyor.

Şifre `.env`'deki DEMO_USER_PASSWORD'dür ve tüm demo kullanıcıları için
aynıdır (bkz. config.py'deki gerekçe). Gizli bir değer değildir: sentetik
veriye erişim anahtarıdır, gerçek bir sır değil.
"""

import argparse

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import User

# Terminal genişliğine sığan sabit sütunlar; ad alanı en uzun Türkçe adları
# da kesmeden alacak kadar geniş.
_ROW = "{national_id:<13} {full_name:<28} {risk_profile:<14} {user_id}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Kaç kullanıcı listelensin (varsayılan 10; tümü için 0)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = select(User).order_by(User.full_name)
        if args.limit > 0:
            query = query.limit(args.limit)
        users = db.execute(query).scalars().all()

        if not users:
            print("Kullanıcı yok. Önce: make seed")
            return

        print()
        print(f"Ortak şifre: {settings.demo_user_password}")
        print()
        print(
            _ROW.format(
                national_id="T.C. KİMLİK",
                full_name="AD SOYAD",
                risk_profile="RİSK PROFİLİ",
                user_id="UUID",
            )
        )
        print("-" * 100)
        for user in users:
            print(
                _ROW.format(
                    # Kimlik bilgisi atanmamış kullanıcı (national_id NULL)
                    # giriş yapamaz; listede görünür ama işaretli olur.
                    national_id=user.national_id or "— (giriş yok)",
                    full_name=user.full_name,
                    risk_profile=user.risk_profile.value,
                    user_id=str(user.id),
                )
            )
        print()
        if args.limit > 0:
            print(f"(ilk {args.limit} kullanıcı; tümü için: --limit 0)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
