"""Veri katmanı tutarlılık teşhisi — okuma amaçlı, hiçbir şey YAZMAZ.

Cevapladığı asıl soru: portföylerin MALİYETİ ile DEĞERLEMESİ aynı evrenden mi
geliyor?

`seed_ledger` işlem fiyatlarını `price_history`'den, işlemin yapıldığı GÜNE
bakarak okur. Bu doğru davranıştır ama tek yönlü korur: `make backfill`
`make seed`'den SONRA çalıştırılırsa gerçek fiyatlar, defterin dayandığı
sentetik satırların üzerine yazılır. Defterdeki maliyet artık var olmayan bir
fiyattan alınmış görünür, değerleme ise gerçek fiyattan yapılır. Sonuç uydurma
kâr/zarardır — 20 Ağustos 2026'da ölçüldü: 151 işlem, 50 portföyün 48'i bozuk,
bir varlıkta +%292 sahte kâr.

Doğru sıra `docs/DATA.md` §"Gerçek fiyat verisi çekmek"te: önce backfill,
sonra seed. Bu betik o sıranın tutulup tutulmadığını ÖLÇER.

Kullanım (sunucuda, git pull gerektirmeden):

    sudo docker compose -p finans-test exec -T -w / api python - < scripts/data_doctor.py

Çıkış kodu: 0 temiz, 1 bulgu var.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import Asset, Holding, Portfolio, PriceHistory, Transaction, TransactionType

# Günlük yüzde eşiği. Sentetik ve gerçek serinin ekleme yerinde fiyat bir
# günde kat değiştirebiliyor (ölçülen: TCD 5,42 -> 35,63); normal bir piyasa
# günü bu kadar oynamaz, dolayısıyla eşiği aşan gün "ekleme yeri" şüphesidir.
SICRAMA_ESIGI = Decimal("25")

# Pozisyon bazında kâr/zarar eşiği. Bir yılda %200 mümkün ama nadirdir;
# toplu halde çıkıyorsa maliyet ile değerleme farklı evrenlerden geliyordur.
ASIRI_KZ_ESIGI = Decimal("200")


def _baslik(s: str) -> None:
    print("\n" + "=" * 68)
    print(s)
    print("=" * 68)


def _kaynak_adi(src: object) -> str:
    return str(getattr(src, "value", src))


def main() -> int:
    db = SessionLocal()
    bulgular: list[str] = []
    # Sira hatasindan (backfill sonra seed) kaynaklanan bulgu var mi.
    # ANCHOR acigi da bir bulgudur ama yeniden seed ile COZULMEZ;
    # ayirt edilmezse yanlis tavsiye verilir.
    sira_hatasi = False
    try:
        semboller = {a.id: a.symbol for a in db.execute(select(Asset)).scalars()}

        # --- 1. Fiyat kaynakları --------------------------------------------
        _baslik("1. price_history kaynak dagilimi")
        for src, adet, ilk, son in db.execute(
            select(
                PriceHistory.source,
                func.count(),
                func.min(PriceHistory.price_date),
                func.max(PriceHistory.price_date),
            ).group_by(PriceHistory.source)
        ).all():
            print(f"  {_kaynak_adi(src):<14} {adet:>7} satir   {ilk} -> {son}")

        # --- 2. Gercek araligin ICINDE kalan sentetik satirlar ---------------
        # Gercek kaynaklar tatilde fiyat yayimlamaz. Temizlik calismadiysa
        # serinin ORTASINDA sentetik satir kalir; o gunden gecen her islem
        # yanlis fiyatlanir.
        _baslik("2. Gercek serinin ICINDE kalan sentetik satir (ekleme yeri)")
        toplam_delik = 0
        for asset_id, ilk, son, _adet in db.execute(
            select(
                PriceHistory.asset_id,
                func.min(PriceHistory.price_date),
                func.max(PriceHistory.price_date),
                func.count(),
            )
            .where(PriceHistory.source != "synthetic")
            .group_by(PriceHistory.asset_id)
        ).all():
            delik = db.execute(
                select(func.count()).where(
                    PriceHistory.asset_id == asset_id,
                    PriceHistory.source == "synthetic",
                    PriceHistory.price_date.between(ilk, son),
                )
            ).scalar_one()
            if delik:
                toplam_delik += delik
                print(
                    f"  {semboller.get(asset_id, '?'):<12} {delik:>3} sentetik satir  ({ilk}..{son})"
                )
        if toplam_delik:
            bulgular.append(f"{toplam_delik} sentetik satir gercek serinin ICINDE kalmis")
            sira_hatasi = True
        else:
            print("  temiz - gercek araliklarda sentetik satir yok")

        # --- 3. ASIL KONTROL -------------------------------------------------
        _baslik("3. Islem fiyati <-> o tarihteki price_history")
        kitap: dict[tuple, Decimal] = {}
        for aid, gun, fiyat in db.execute(
            select(PriceHistory.asset_id, PriceHistory.price_date, PriceHistory.close_price)
        ).all():
            kitap[(aid, gun)] = fiyat

        uyum = 0
        eksik = 0
        sapmalar: list[tuple] = []
        for islem in db.execute(
            select(Transaction).where(
                Transaction.transaction_type.in_([TransactionType.BUY, TransactionType.SELL])
            )
        ).scalars():
            gun = islem.transaction_date.date()
            gecmis = kitap.get((islem.asset_id, gun))
            if gecmis is None:
                eksik += 1
                continue
            if abs(Decimal(islem.price) - Decimal(gecmis)) <= Decimal("0.0001"):
                uyum += 1
            else:
                oran = (
                    (Decimal(islem.price) / Decimal(gecmis) - 1) * 100
                    if Decimal(gecmis) > 0
                    else Decimal(0)
                )
                sapmalar.append(
                    (semboller.get(islem.asset_id, "?"), gun, islem.price, gecmis, oran)
                )

        print(f"  uyumlu         : {uyum}")
        print(f"  UYUMSUZ        : {len(sapmalar)}")
        print(f"  o gun fiyat yok: {eksik}")
        if sapmalar:
            bulgular.append(
                f"{len(sapmalar)} islem o tarihteki fiyattan FARKLI yazilmis "
                "(backfill, seed'den SONRA calismis)"
            )
            sira_hatasi = True
            print("\n  en buyuk sapmalar (islem / bugunku gecmis / fark):")
            for sembol, gun, islem_f, gecmis_f, oran in sorted(sapmalar, key=lambda x: -abs(x[4]))[
                :10
            ]:
                print(f"    {sembol:<12} {gun}  {islem_f:>12} / {gecmis_f:>12}  %{oran:>9.1f}")

        # --- 4. Tarih araliklari ---------------------------------------------
        _baslik("4. Tarih araliklari")
        ilk_islem, son_islem = db.execute(
            select(func.min(Transaction.transaction_date), func.max(Transaction.transaction_date))
        ).one()
        ilk_fiyat, son_fiyat = db.execute(
            select(func.min(PriceHistory.price_date), func.max(PriceHistory.price_date))
        ).one()
        print(f"  islem defteri : {ilk_islem} -> {son_islem}")
        print(f"  fiyat gecmisi : {ilk_fiyat} -> {son_fiyat}")
        if son_islem is not None and son_fiyat is not None:
            fark = (son_fiyat - son_islem.date()).days
            print(f"  son islem ile son fiyat arasi: {fark} gun")
            if fark > 14:
                bulgular.append(
                    f"son islem {fark} gun geride (ANCHOR_DATE sabit) - "
                    "'son islemler' listesi bayat gorunur"
                )

        # --- 5. Supheli sicramalar -------------------------------------------
        _baslik(f"5. Gunluk |degisim| > %{SICRAMA_ESIGI} olan fiyat gunleri")
        seriler: dict = defaultdict(list)
        for aid, gun, fiyat, src in db.execute(
            select(
                PriceHistory.asset_id,
                PriceHistory.price_date,
                PriceHistory.close_price,
                PriceHistory.source,
            ).order_by(PriceHistory.asset_id, PriceHistory.price_date)
        ).all():
            seriler[aid].append((gun, Decimal(fiyat), _kaynak_adi(src)))

        sicrama = 0
        for aid, seri in seriler.items():
            for (gun0, fiyat0, kaynak0), (gun1, fiyat1, kaynak1) in zip(seri, seri[1:]):
                if fiyat0 <= 0:
                    continue
                degisim = abs(fiyat1 / fiyat0 - 1) * 100
                if degisim > SICRAMA_ESIGI:
                    sicrama += 1
                    if sicrama <= 10:
                        print(
                            f"  {semboller.get(aid, '?'):<12} {gun0}({kaynak0}) -> "
                            f"{gun1}({kaynak1})  %{degisim:.1f}"
                        )
        if sicrama:
            print(f"  toplam: {sicrama}")
            bulgular.append(f"{sicrama} supheli gunluk sicrama (sentetik/gercek ekleme yeri)")
            sira_hatasi = True
        else:
            print("  temiz")

        # --- 6. Asiri kar/zarar ----------------------------------------------
        _baslik(f"6. |kar/zarar| > %{ASIRI_KZ_ESIGI} olan pozisyonlar")
        asiri = 0
        for h in db.execute(select(Holding).where(Holding.quantity > 0)).scalars():
            son_fiyat_h = db.execute(
                select(PriceHistory.close_price)
                .where(PriceHistory.asset_id == h.asset_id)
                .order_by(PriceHistory.price_date.desc())
                .limit(1)
            ).scalar_one_or_none()
            if son_fiyat_h is None or not h.avg_cost_price:
                continue
            maliyet = Decimal(h.avg_cost_price)
            if maliyet <= 0:
                continue
            kz = (Decimal(son_fiyat_h) / maliyet - 1) * 100
            if abs(kz) > ASIRI_KZ_ESIGI:
                asiri += 1
                if asiri <= 10:
                    print(
                        f"  {semboller.get(h.asset_id, '?'):<12} maliyet={maliyet:>12} "
                        f"son={son_fiyat_h:>12}  %{kz:>9.1f}"
                    )
        if asiri:
            print(f"  toplam: {asiri} pozisyon")
            bulgular.append(f"{asiri} pozisyonda |K/Z| > %{ASIRI_KZ_ESIGI}")
            sira_hatasi = True
        else:
            print("  temiz")

        # --- Karar -------------------------------------------------------------
        _baslik("KARAR")
        print(
            f"  portfoy sayisi: {db.execute(select(func.count()).select_from(Portfolio)).scalar_one()}"
        )
        if not bulgular:
            print("\n  TEMIZ - maliyet ve degerleme ayni evrenden geliyor.")
            return 0
        print()
        for b in bulgular:
            print(f"  [!] {b}")
        if sira_hatasi:
            print("\n  Cozum: once `make backfill`, SONRA `make seed` (docs/DATA.md).")
        else:
            # Tek bulgu ANCHOR acigi ise yeniden seed BIR SEY DEGISTIRMEZ:
            # defter settings.anchor_date'e sabitli, her seed ayni gunde biter.
            # Yanlis tavsiye vermemek icin ayirt ediliyor.
            print("\n  Maliyet/degerleme TUTARLI. Kalan bulgu yeniden seed ile cozulmez.")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
