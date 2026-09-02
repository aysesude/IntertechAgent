"""Seed kullanıcılarının eksik anket puanını doldurur — VERİYİ SİLMEDEN.

    make survey-scores

ESKİ VERİ İÇİN TEK SEFERLİK ONARIM. Bugünkü `seed_ledger` puanı zaten atıyor;
sorun yalnızca anket özelliğinden ÖNCE seed edilmiş ve o günden beri
yenilenmemiş ortamlarda. `risk_survey_score` sütununu migration `NULL` olarak
ekledi ve `backfill_credentials` yalnızca giriş alanlarını doldurduğu için o
kullanıcılar puansız kaldı. Arayüz puanı olmayan kullanıcıyı ilk girişte
kapatılamaz anket ekranına alıyor (bkz.
`frontend-v2/src/components/survey/SurveyGate.tsx`), yani o ortamdaki HER demo
hesabı 18 soruluk anketle karşılaşıyor ve "giriş yap, panele düş" akışı orada
takılıyor.

Taze seed edilmiş bir ortamda bu betik "yapılacak bir şey yok" der; beklenen
davranış budur.

NEDEN `make seed` DEĞİL. Seed puanları doğru üretir ama önce `wipe_user_data`
ile kullanıcıları, portföyleri, işlem defterini ve SOHBET GEÇMİŞİNİ siler.
Kullanımdaki bir ortamda (test/canlı) bu kabul edilemez. Bu betik yalnızca boş
puanları doldurur, başka hiçbir satıra dokunmaz.

PUAN UYDURULMUYOR. Değer, `make seed` o kullanıcıya ne yazacak idiyse tam
olarak odur: seed kimlikleri `uuid5(USER_UUID_NAMESPACE, f"user-{i}")` ile
deterministik üretiliyor, dolayısıyla UUID'den kullanıcının seed sırası geri
çözülebiliyor ve `data.seed_ledger._survey_score` aynı sırayla çağrılabiliyor.
Sıradan biri elle "hadi 4 olsun" demiyor.

SEED DIŞI KULLANICILARA DOKUNULMAZ. "Üye ol" ile açılmış bir hesabın puanı
boşsa bu bir eksiklik değil, ANLAMLI bir durumdur: o kişi anketi henüz
doldurmadı ve doldurmalı. Ona puan yazmak, alınmamış bir uygunluk beyanını
alınmış gibi göstermek olurdu.

Betik yeniden çalıştırılabilir (idempotent): puanı olan kullanıcı atlanır.
"""

import argparse
import uuid

from sqlalchemy import select

from app.core.config import risk_profile_for_survey_score
from app.core.db import SessionLocal
from app.models import User
from data.seed_ledger import USER_UUID_NAMESPACE, _survey_score

# Seed'in ürettiği kullanıcı sayısından güvenli biçimde büyük bir üst sınır:
# sıra->UUID haritası bu aralık için kurulur. Seed 50 kullanıcı üretiyor;
# ileride artarsa burayı büyütmek yeter, harita kurmak ucuz.
_AZAMI_SEED_KULLANICI = 500


def _sira_haritasi() -> dict[uuid.UUID, int]:
    """UUID -> seed sırası. `seed_ledger._user_id`'nin tersi."""
    return {uuid.uuid5(USER_UUID_NAMESPACE, f"user-{i}"): i for i in range(_AZAMI_SEED_KULLANICI)}


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
        puansiz = (
            db.execute(
                select(User).where(User.risk_survey_score.is_(None))
                # Belirlenimcilik: sıralama sabit olmazsa iki koşu farklı
                # sırada ilerler ve çıktıyı karşılaştırmak zorlaşır.
                .order_by(User.created_at, User.id)
            )
            .scalars()
            .all()
        )

        seed_sirasi = _sira_haritasi()
        seedden = [u for u in puansiz if u.id in seed_sirasi]
        digerleri = [u for u in puansiz if u.id not in seed_sirasi]

        if not seedden:
            print("Puanı eksik seed kullanıcısı yok, yapılacak bir şey yok.")
        else:
            print(f"{len(seedden)} seed kullanıcısının anket puanı eksik.")

        if digerleri:
            print(
                f"{len(digerleri)} seed DIŞI kullanıcı puansız — dokunulmuyor, "
                "anketi kendileri dolduracak:"
            )
            for u in digerleri:
                print(f"  - {u.full_name} <{u.email}>")

        if args.dry_run:
            print("--dry-run: hiçbir şey yazılmadı.")
            return

        for user in seedden:
            puan = _survey_score(seed_sirasi[user.id], user.risk_profile)
            user.risk_survey_score = puan
            # Profil PUANDAN TÜRETİLİR. Mevcut `risk_profile` ile yeniden
            # hesaplanan aynı çıkmalı (puan zaten o profilin bandından
            # seçiliyor); yine de açıkça yazıyoruz ki ikisi ayrışmasın.
            user.risk_profile = risk_profile_for_survey_score(puan)

        db.commit()
        print(f"{len(seedden)} kullanıcıya anket puanı yazıldı.")
        print("Kontrol: make demo-users")
    finally:
        db.close()


if __name__ == "__main__":
    main()
