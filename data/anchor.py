"""Sentetik üretimin "bugün"ünü belirler.

`anchor_date`, seed'in referans günüdür: "Ahmet 3 ay önce THYAO aldı"
diyebilmek için neyin üç ay öncesi olduğunu bilmek gerekiyor. Defter bu günde
biter.

**Neden sabit bir tarih değil.** Eskiden `settings.anchor_date` sabit bir
gündü (2026-08-01). Gerçek fiyatlar ise günlük toplama işiyle ilerlemeye devam
ediyor, dolayısıyla "son işlem" ile "son fiyat" arasındaki açık HER GÜN BİR
GÜN büyüyordu. Ölçülen: 23 Ağustos'ta 21 gün — kullanıcı "Son İşlemler"
listesine baktığında her şey üç haftalıktı. Kapatmak için birinin `.env`'i
elle güncelleyip yeniden seed etmesi gerekiyordu ve unutulduğunda kimse fark
etmiyordu.

Ankraj artık **gerçek verinin bittiği yere** bağlanıyor: defter, fiyatların
bittiği gün biter, açık yapısal olarak sıfır olur.

**Yeniden üretilebilirlik kayboluyor mu?** Sabit ankrajın gerekçesi buydu
("her seed geçmişi kaydırırsa 'o tarihten bugüne' izlenemez hale gelir") ama
pratikte zaten korumuyordu: iki farklı günün seed'i, fiyatlar farklı olduğu
için nasılsa aynı çıkmıyor. Koşu içindeki determinizm ankrajdan değil
`SEED=42`'den geliyor. Sabit bir tarih gerektiğinde `ANCHOR_DATE` ortam
değişkeni hâlâ her şeyi ezer — testler ve karşılaştırmalı koşular bunu
kullanır.
"""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import PriceSource, settings, turkey_today
from app.models import PriceHistory


def son_is_gunu(gun: date) -> date:
    """`gun` veya ondan önceki en yakın hafta içi gün."""
    while gun.weekday() >= 5:  # 5=Cumartesi, 6=Pazar
        gun -= timedelta(days=1)
    return gun


def resolve_anchor_date(session: Session) -> date:
    """Seed'in kullanacağı ankraj gününü belirler.

    Sıra:
      1. `ANCHOR_DATE` ortam değişkeni verilmişse O. Testler ve yeniden
         üretilebilir koşular için açık kapı.
      2. Veritabanındaki en son GERÇEK fiyat günü. Sentetik satırlar bilerek
         sayılmıyor: onların son günü zaten bir önceki ankrajdan geliyor,
         yani kendi kuyruğumuzu yerdik ve ankraj hiç ilerlemezdi.
      3. Hiç gerçek fiyat yoksa (temiz kurulum, `make backfill` çalışmamış)
         bugünden geriye en yakın iş günü.
    """
    if settings.anchor_date is not None:
        return settings.anchor_date

    son_gercek = session.execute(
        select(func.max(PriceHistory.price_date)).where(
            PriceHistory.source != PriceSource.SYNTHETIC
        )
    ).scalar_one_or_none()
    if son_gercek is not None:
        return son_gercek

    return son_is_gunu(turkey_today())
