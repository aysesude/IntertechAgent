"""Fiyat serisinde sahte sicrama / sinif etiketi tutarsizligi teshisi.

Neden bu betik var. `varlik_risk_olcum.py` calistirildiginda PPF (%5208),
TI2 (%4137), GTA (%257) gibi gercekci olmayan yillik volatilite degerleri
gorundu; ayrica PPF ve GTA "stock" sinifinda listelendi — oysa
`providers/universe.py` her ikisini de baska siniflara atiyor (PPF -> CASH,
GTA -> PRECIOUS_METAL, bkz. `_FUND_ASSET_CLASS`). Bu betik iki ayri hipotezi
DOGRUDAN veriden dogrular/eler, tahminle degil:

  1. DB'deki Asset.asset_class, universe.py'deki guncel tanimla ayni mi?
     (Farkliysa: `python -m data.generate_dummy` DB'yi bu duzeltmeden SONRA
     hic calistirmamis demektir — Asset satirlari eski siniflari tasiyor.)

  2. Fiyat serisinde tek gunluk sahte bir sicrama var mi? (`seed_prices_synthetic.py`
     bunu belgeliyor: sentetik taban fiyati gercek fiyattan kat kat sapabiliyor
     — orn. PPF: 118.50 sentetik vs 3.50-5.17 gercek — ve bu delikler
     temizlenmezse tek bir gunde onlarca kat sahte getiri olusuyor.)

Hicbir sey yazmaz, sadece okur ve rapor basar.

Kullanim:
    docker compose exec -w / api python scripts/fiyat_sicrama_teshis.py
    docker compose exec -w / api python scripts/fiyat_sicrama_teshis.py --sembol PPF,GTA,TI2
"""

import argparse
from decimal import Decimal

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Asset, PriceHistory
from app.providers.universe import SPEC_BY_SYMBOL

_SEMBOL_G = 12
_EN_BUYUK_SICRAMA = 3  # varlik basina rapor edilecek en buyuk getiri sayisi


def _sinif_tutarsizliklarini_bul(varliklar: list[Asset]) -> list[tuple[str, str, str]]:
    """DB'deki asset_class ile universe.py'deki guncel tanimi karsilastirir.

    Donen liste (sembol, db_sinifi, universe_sinifi) — yalnizca farkli olanlar.
    """
    farklar = []
    for varlik in varliklar:
        spec = SPEC_BY_SYMBOL.get(varlik.symbol)
        if spec is None:
            continue
        if varlik.asset_class != spec.asset_class:
            farklar.append((varlik.symbol, varlik.asset_class.value, spec.asset_class.value))
    return farklar


def _en_buyuk_sicramalar(
    satirlar: list[PriceHistory],
) -> list[tuple[Decimal, PriceHistory, PriceHistory]]:
    """Gun-gun getiriyi kaynagi karistirmadan (ham fiyat, TRY'ye cevrilmeden)
    hesaplar; buyukluge gore siralar. Amac risk_service'i tekrar etmek degil,
    serideki tek bir sahte sicramayi gozle gorulur kilmak."""
    sirali = sorted(satirlar, key=lambda r: r.price_date)
    sicramalar = []
    for onceki, simdiki in zip(sirali, sirali[1:]):
        if onceki.close_price <= 0:
            continue
        getiri = (simdiki.close_price / onceki.close_price) - Decimal(1)
        sicramalar.append((abs(getiri), onceki, simdiki))
    sicramalar.sort(key=lambda s: s[0], reverse=True)
    return sicramalar[:_EN_BUYUK_SICRAMA]


def main() -> None:
    ayristirici = argparse.ArgumentParser(description="Fiyat sicramasi / sinif teshisi")
    ayristirici.add_argument(
        "--sembol",
        type=str,
        default=None,
        help="Virgulle ayrilmis sembol listesi (varsayilan: en yuksek volatiliteli "
        "adaylar: PPF,GTA,TI2,TCD,AFT,PGSUS,XAGTRY,XAUTRY)",
    )
    argumanlar = ayristirici.parse_args()
    hedef_semboller = (
        [s.strip().upper() for s in argumanlar.sembol.split(",")]
        if argumanlar.sembol
        else ["PPF", "GTA", "TI2", "TCD", "AFT", "PGSUS", "XAGTRY", "XAUTRY"]
    )

    with SessionLocal() as db:
        tum_varliklar = db.execute(select(Asset).where(Asset.is_active)).scalars().all()
        sinif_farklari = _sinif_tutarsizliklarini_bul(tum_varliklar)

        by_symbol = {a.symbol: a for a in tum_varliklar}
        hedefler = [by_symbol[s] for s in hedef_semboller if s in by_symbol]
        eksikler = [s for s in hedef_semboller if s not in by_symbol]

        print(f"\n{'=' * 78}")
        print("1) DB Asset.asset_class vs providers/universe.py (guncel tanim)")
        print(f"{'=' * 78}\n")
        if sinif_farklari:
            print("TUTARSIZLIK BULUNDU — asagidaki varliklarin DB'deki sinifi, kaynak")
            print("koddaki (universe.py) guncel tanimla ESLESMIYOR:\n")
            for sembol, db_sinif, universe_sinif in sinif_farklari:
                print(f"  {sembol:<{_SEMBOL_G}} DB={db_sinif:<16} universe.py={universe_sinif}")
            print(
                "\nOlasi neden: universe.py bu varliklarin sinifini degistirdikten sonra "
                "`python -m data.generate_dummy` hic calistirilmadi (seed_assets upsert'i "
                "yalniz o komutla tetiklenir). Cozum: asagidaki komutu calistirip DB'yi "
                "guncel universe.py ile yeniden esitleyin, sonra bu betigi tekrar calistirin:\n"
                "  docker compose exec -w / api python -m data.generate_dummy"
            )
        else:
            print("Fark yok: DB'deki asset_class degerleri universe.py ile birebir ayni.")

        print(f"\n{'=' * 78}")
        print("2) Fiyat serisinde en buyuk gunluk sicramalar (ham, TRY'ye cevrilmemis)")
        print(f"{'=' * 78}\n")
        if eksikler:
            print(f"Bulunamayan semboller (atlaniyor): {', '.join(eksikler)}\n")

        for varlik in hedefler:
            satirlar = (
                db.execute(
                    select(PriceHistory)
                    .where(PriceHistory.asset_id == varlik.id)
                    .order_by(PriceHistory.price_date)
                )
                .scalars()
                .all()
            )
            print(
                f"{varlik.symbol} (DB sinifi={varlik.asset_class.value}, "
                f"{len(satirlar)} fiyat satiri):"
            )
            if len(satirlar) < 2:
                print("  Yetersiz veri — sicrama hesaplanamiyor.")
                print()
                continue

            for getiri, onceki, simdiki in _en_buyuk_sicramalar(satirlar):
                yon = "+" if simdiki.close_price >= onceki.close_price else "-"
                print(
                    f"  {onceki.price_date} -> {simdiki.price_date}  "
                    f"{yon}%{getiri * 100:.2f}   "
                    f"{onceki.close_price} [{onceki.source.value}] -> "
                    f"{simdiki.close_price} [{simdiki.source.value}]"
                )
            print()

    print(f"{'=' * 78}")
    print(
        "Kaynak (SIRA/kaynak sutunu) sicramanin iki yaninda FARKLIYSA (orn. "
        "synthetic -> real) bu, seed_prices_synthetic.py'nin belgeledigi taban "
        "fiyat uyusmazligi/delik sorunudur, gercek piyasa hareketi degildir."
    )
    print()


if __name__ == "__main__":
    main()
