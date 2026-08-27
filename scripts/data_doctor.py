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
from app.services.trade_service import USER_ORDER_NOTE

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
        kullanici_emri = 0
        sapmalar: list[tuple] = []
        for islem in db.execute(
            select(Transaction).where(
                Transaction.transaction_type.in_([TransactionType.BUY, TransactionType.SELL])
            )
        ).scalars():
            # KULLANICI EMIRLERI BU KONTROLUN DISINDA.
            #
            # Bu kontrol seed'in urettigi veriyi denetliyor: "islem fiyati o
            # gunun kapanisiyla ayni mi", yani "backfill seed'den sonra mi
            # kostu". Al/Sat ekranindan gecen emir ise GUN ICI fiyattan
            # yaziliyor (bkz. trade_service) ve kapanistan farkli olmasi
            # NORMAL. Ayirt edilmezse doktor her gercek islemi sahte bir
            # bulgu olarak raporlar ve asil sinyali bogardi.
            if islem.note == USER_ORDER_NOTE:
                kullanici_emri += 1
                continue
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
        print(f"  kullanici emri : {kullanici_emri} (kapsam disi - gun ici fiyat)")
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

        # Sicramanin IKI TURU var ve karistirilmamalari gerekiyor:
        #
        #   ekleme yeri  - iki gunun kaynagi farkli ya da biri sentetik. Sentetik
        #                  taban fiyat gercek fiyattan kat kat sapabildigi icin
        #                  (PPF: 118,50 sentetik vs 3,50 gercek) burada onlarca
        #                  kat sahte getiri olusur. Bu bir SIRA hatasidir,
        #                  yeniden seed ile duzelir.
        #   ayni kaynak  - iki yani da ayni gercek saglayici. Sentetik bulasma
        #                  YOK; ya gercekten oyle hareket etmis ya da saglayici
        #                  hatali fiyat yayimlamis. Yeniden seed BUNU DUZELTMEZ,
        #                  cunku ayni fiyati tekrar ceker.
        #
        # Ayrim yapilmadiginda arac, saglayici kaynakli tek bir sicrama icin
        # "yeniden seed" oneriyordu - bosuna is ve yanlis teshis.
        ekleme_yeri = 0
        ayni_kaynak: list[tuple] = []
        for aid, seri in seriler.items():
            for (gun0, fiyat0, kaynak0), (gun1, fiyat1, kaynak1) in zip(seri, seri[1:]):
                if fiyat0 <= 0:
                    continue
                degisim = abs(fiyat1 / fiyat0 - 1) * 100
                if degisim <= SICRAMA_ESIGI:
                    continue
                sentetik_bulasik = "synthetic" in (kaynak0, kaynak1)
                if kaynak0 != kaynak1 or sentetik_bulasik:
                    ekleme_yeri += 1
                    etiket = "EKLEME YERI"
                else:
                    ayni_kaynak.append((semboller.get(aid, "?"), gun0, gun1, kaynak0, degisim))
                    etiket = "ayni kaynak"
                if ekleme_yeri + len(ayni_kaynak) <= 10:
                    print(
                        f"  {semboller.get(aid, '?'):<12} {gun0}({kaynak0}) -> "
                        f"{gun1}({kaynak1})  %{degisim:.1f}  [{etiket}]"
                    )
        if ekleme_yeri:
            bulgular.append(f"{ekleme_yeri} sicrama sentetik/gercek EKLEME YERINDE")
            sira_hatasi = True
        if ayni_kaynak:
            bulgular.append(
                f"{len(ayni_kaynak)} sicrama ayni gercek kaynagin icinde "
                "(saglayici verisi - yeniden seed cozmez)"
            )
        if not ekleme_yeri and not ayni_kaynak:
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
            # Aşırı K/Z tek başına SIRA HATASI DEĞİLDİR.
            #
            # Bu kontrol, maliyetin bir evrenden değerlemenin başka evrenden
            # geldiği durumu yakalamak için eklendi. Ama aynı belirti gerçek
            # bir piyasa hareketinden de doğabilir: TL'de bir yılda üçe
            # katlanan hisse olağandışı değil, ayrıca sermaye artırımı
            # (bölünme) ham fiyat serisinde kopukluk bırakıyor.
            #
            # Ayırt edici olan 3. KONTROL: işlem fiyatları o günün
            # `price_history` kaydıyla uyuşuyorsa maliyet ve değerleme aynı
            # evrendendir ve yeniden seed hiçbir şeyi değiştirmez. Yalnızca
            # ikisi BİRLİKTE görüldüğünde sıra hatasından söz edilebilir.
            if sapmalar:
                bulgular.append(
                    f"{asiri} pozisyonda |K/Z| > %{ASIRI_KZ_ESIGI} "
                    "(islem fiyatlari da uyumsuz - sira hatasi)"
                )
                sira_hatasi = True
            else:
                bulgular.append(
                    f"{asiri} pozisyonda |K/Z| > %{ASIRI_KZ_ESIGI} "
                    "(islem fiyatlari UYUMLU - piyasa hareketi ya da bolunme)"
                )
        else:
            print("  temiz")

        # --- 7. risk_level: DB ile kod ayrismis mi ---------------------------
        # `assets.risk_level` TUREV bir kopyadir; tanimi providers/universe.py
        # icinde durur ve seed_assets her kosuda yeniden yazar. Ayrisma
        # yalnizca iki yolla olur: kod degisti ama seed/backfill kosmadi, ya
        # da sutuna elle yazildi. Ikisi de sessiz; sorgular eski seviyeye
        # gore filtreler ve kimse fark etmez.
        _baslik("7. Varlik risk seviyesi (DB <-> kod)")
        from app.services.advice_eligibility import asset_risk_level

        ayrisan: list[str] = []
        bos: list[str] = []
        for asset in db.execute(select(Asset).where(Asset.is_active)).scalars():
            beklenen = asset_risk_level(asset.symbol, asset.asset_class)
            if asset.risk_level is None:
                bos.append(asset.symbol)
            elif asset.risk_level != beklenen:
                ayrisan.append(f"{asset.symbol}: DB {asset.risk_level} != kod {beklenen}")
        if bos:
            print(f"  seviyesi BOS aktif varlik: {len(bos)} -> {', '.join(sorted(bos)[:8])}")
            bulgular.append(f"{len(bos)} aktif varligin risk seviyesi bos (seed kosmamis)")
            sira_hatasi = True
        for satir in ayrisan[:8]:
            print(f"  {satir}")
        if ayrisan:
            bulgular.append(f"{len(ayrisan)} varligin risk seviyesi DB ile kod arasinda ayrismis")
            sira_hatasi = True
        if not bos and not ayrisan:
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
