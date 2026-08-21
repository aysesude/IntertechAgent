"""Varlik bazli risk olcumu: her varligin GERCEK yillik volatilitesi nedir?

Neden bu betik var. Risk motoru bugun volatiliteyi KATEGORI duzeyinde
hesapliyor (sabit 5x5 matris) ve 7 kademeli RiskLevel etiketini
`RISK_LEVEL_VOLATILITY_UPPER_BOUNDS` tablosuyla uretiyor. O tablo PORTFOY
volatilitesine gore kalibre edildi (<=%5 cok dusuk ... >%40 cok yuksek).
Portfoy, cesitlendirme sayesinde bilesenlerinden daha az oynaktir; tek bir
hissenin volatilitesi tipik olarak cok daha yuksektir.

"Portfoydeki varliklarin tek tek risk durumu" ozelligini yazmadan once
cevaplanmasi gereken soru su: ayni merdiveni varliga uygularsak kademeler
anlamli sekilde dagiliyor mu, yoksa butun hisseler en ust iki basamakta
yigilip birbirinden ayirt edilemez hale mi geliyor? Bunu tahminle degil
olcumle karara baglamak icin bu betik yazildi.

Hicbir sey yazmaz, sadece okur ve rapor basar.

Kullanim:
    docker compose exec -w / api python scripts/varlik_risk_olcum.py
    docker compose exec -w / api python scripts/varlik_risk_olcum.py --gun 252
"""

import argparse
import statistics
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.core.config import RISK_LEVEL_VOLATILITY_UPPER_BOUNDS, AssetClass, RiskLevel, settings
from app.core.db import SessionLocal
from app.models import Asset, PriceHistory
from app.services.risk_service import (
    _annualized_volatility,
    _price_series_by_asset,
    _returns_aligned,
    _risk_level_from_volatility,
    _try_convert,
)
from app.services.valuation_service import FX_SYMBOL_BY_CURRENCY, PriceBook

# Rapor sutun genislikleri; tabloyu terminalde hizali tutmak icin.
_SEMBOL_G = 12
_SINIF_G = 16


def _kur_defteri(db) -> tuple[dict[str, UUID], PriceBook]:
    """TRY disi varliklari cevirmek icin kur defteri. risk_service'in
    `get_risk_assessment` icindeki kurulumun aynisi — olcumun uretimden
    sapmamasi icin ayni yol izleniyor."""
    fx_asset_rows = db.execute(
        select(Asset.id, Asset.symbol).where(Asset.symbol.in_(FX_SYMBOL_BY_CURRENCY.values()))
    ).all()
    symbol_to_id = {symbol: aid for aid, symbol in fx_asset_rows}
    fx_ids = {
        currency: symbol_to_id[symbol]
        for currency, symbol in FX_SYMBOL_BY_CURRENCY.items()
        if symbol in symbol_to_id
    }
    if not fx_ids:
        return {}, PriceBook([])

    fx_rows = db.execute(
        select(PriceHistory.asset_id, PriceHistory.price_date, PriceHistory.close_price).where(
            PriceHistory.asset_id.in_(fx_ids.values())
        )
    ).all()
    return fx_ids, PriceBook([(r.asset_id, r.price_date, r.close_price) for r in fx_rows])


def _try_seri(
    raw_series: dict[UUID, dict[date, Decimal]],
    currency_by_asset: dict[UUID, str],
    fx_ids: dict[str, UUID],
    fx_book: PriceBook,
) -> dict[UUID, dict[date, Decimal]]:
    """Ham fiyatlari TRY'ye cevirir. Kur bilinmiyorsa o gun ATLANIR —
    eksik veri varsayimla doldurulmaz (AK 5.5)."""
    try_series: dict[UUID, dict[date, Decimal]] = {}
    for asset_id, native_by_date in raw_series.items():
        currency = currency_by_asset[asset_id]
        fx_asset_id = fx_ids.get(currency)
        cevrilmis: dict[date, Decimal] = {}
        for day, native_price in native_by_date.items():
            try_price = _try_convert(native_price, currency, day, fx_book, fx_asset_id)
            if try_price is not None:
                cevrilmis[day] = try_price
        try_series[asset_id] = cevrilmis
    return try_series


def _onerilen_merdiven(volatiliteler: list[float]) -> list[tuple[float, RiskLevel]]:
    """Olculen dagilimi 7 esit dilime bolen alternatif bir esik tablosu onerir.

    Amac tabloyu bu betikten uretmek DEGIL; mevcut merdivenin ne kadar
    saptigini gorunur kilmak. Kademeler gercekten ayrisiyorsa mevcut tabloyu
    korumak; yiginlasiyorsa buradaki dilimler tartisma icin baslangic noktasi
    olur."""
    if len(volatiliteler) < 7:
        return []
    sirali = sorted(volatiliteler)
    kademeler = list(RiskLevel)
    sinirlar: list[tuple[float, RiskLevel]] = []
    # Son kademenin ust siniri yok (VERY_HIGH her seyi yakalar), bu yuzden
    # 7 kademe icin 6 kesme noktasi uretiliyor.
    for i in range(1, len(kademeler)):
        kesme = sirali[round(len(sirali) * i / len(kademeler)) - 1]
        sinirlar.append((kesme, kademeler[i - 1]))
    return sinirlar


def main() -> None:
    ayristirici = argparse.ArgumentParser(description="Varlik bazli volatilite olcumu")
    ayristirici.add_argument(
        "--gun",
        type=int,
        default=None,
        help="Yalnizca son N islem gununu kullan (varsayilan: tum gecmis)",
    )
    argumanlar = ayristirici.parse_args()

    with SessionLocal() as db:
        varliklar = (
            db.execute(select(Asset).where(Asset.is_active).order_by(Asset.symbol)).scalars().all()
        )
        if not varliklar:
            print("Varlik bulunamadi — once `python -m data.generate_dummy` calistirin.")
            return

        asset_ids = [a.id for a in varliklar]
        currency_by_asset = {a.id: a.currency for a in varliklar}
        fx_ids, fx_book = _kur_defteri(db)
        raw_series = _price_series_by_asset(db, asset_ids)
        try_series = _try_seri(raw_series, currency_by_asset, fx_ids, fx_book)

    satirlar: list[tuple[str, AssetClass, int, float | None, RiskLevel | None]] = []
    for varlik in varliklar:
        gunler = sorted(try_series.get(varlik.id, {}))
        if argumanlar.gun is not None:
            gunler = gunler[-argumanlar.gun :]
        fiyatlar = [try_series[varlik.id][g] for g in gunler]

        # Uretimdeki kuralin aynisi: yeterli fiyat noktasi yoksa hesap
        # yapilmaz, None dondurulur (uydurma yasak — CLAUDE.md).
        if len(fiyatlar) < settings.risk_min_price_points:
            satirlar.append((varlik.symbol, varlik.asset_class, len(fiyatlar), None, None))
            continue

        vol = _annualized_volatility(_returns_aligned(fiyatlar))
        seviye = None if vol is None else _risk_level_from_volatility(vol)
        satirlar.append((varlik.symbol, varlik.asset_class, len(fiyatlar), vol, seviye))

    pencere = "tum gecmis" if argumanlar.gun is None else f"son {argumanlar.gun} gun"
    print(f"\n{'=' * 78}")
    print(f"VARLIK BAZLI YILLIK VOLATILITE — pencere: {pencere}")
    print(f"{'=' * 78}\n")

    print(
        f"{'SEMBOL':<{_SEMBOL_G}}{'SINIF':<{_SINIF_G}}{'GUN':>6}"
        f"{'VOLATILITE':>13}{'  RISK SEVIYESI':<18}"
    )
    print("-" * 78)
    for sembol, sinif, gun_sayisi, vol, seviye in sorted(
        satirlar, key=lambda s: (s[3] is None, -(s[3] or 0.0))
    ):
        vol_metin = "hesaplanamadi" if vol is None else f"%{vol * 100:.2f}"
        seviye_metin = "-" if seviye is None else seviye.value
        print(
            f"{sembol:<{_SEMBOL_G}}{sinif.value:<{_SINIF_G}}{gun_sayisi:>6}"
            f"{vol_metin:>13}  {seviye_metin:<18}"
        )

    olculen = [(s, v, lv) for s, _c, _g, v, lv in satirlar if v is not None]
    if not olculen:
        print("\nHicbir varlikta yeterli fiyat gecmisi yok; olcum yapilamadi.")
        return

    print(f"\n{'=' * 78}")
    print("KADEME DAGILIMI (mevcut RISK_LEVEL_VOLATILITY_UPPER_BOUNDS ile)")
    print(f"{'=' * 78}\n")
    for kademe in RiskLevel:
        dusen = [s for s, _v, lv in olculen if lv is kademe]
        cubuk = "#" * len(dusen)
        print(f"{kademe.value:<14}{len(dusen):>3}  {cubuk}")
        if dusen:
            print(f"{'':14}     {', '.join(dusen)}")

    bos_kademe = [k.value for k in RiskLevel if not any(lv is k for _s, _v, lv in olculen)]
    print(f"\nHic kullanilmayan kademe sayisi: {len(bos_kademe)}/{len(list(RiskLevel))}")
    if bos_kademe:
        print(f"Bos kademeler: {', '.join(bos_kademe)}")

    print(f"\n{'=' * 78}")
    print("VARLIK SINIFI OZETI")
    print(f"{'=' * 78}\n")
    print(f"{'SINIF':<{_SINIF_G}}{'ADET':>6}{'EN DUSUK':>12}{'ORTANCA':>12}{'EN YUKSEK':>12}")
    print("-" * 78)
    for sinif in AssetClass:
        vols = [v for _s, c, _g, v, _lv in satirlar if c is sinif and v is not None]
        if not vols:
            continue
        print(
            f"{sinif.value:<{_SINIF_G}}{len(vols):>6}"
            f"{'%' + format(min(vols) * 100, '.2f'):>12}"
            f"{'%' + format(statistics.median(vols) * 100, '.2f'):>12}"
            f"{'%' + format(max(vols) * 100, '.2f'):>12}"
        )

    print(f"\n{'=' * 78}")
    print("MEVCUT ESIK TABLOSU (portfoy icin kalibre edilmisti)")
    print(f"{'=' * 78}\n")
    for ust_sinir, kademe in RISK_LEVEL_VOLATILITY_UPPER_BOUNDS:
        print(f"  <= %{float(ust_sinir) * 100:>6.2f}  ->  {kademe.value}")
    print(f"  >  %{float(RISK_LEVEL_VOLATILITY_UPPER_BOUNDS[-1][0]) * 100:>6.2f}  ->  very_high")

    oneri = _onerilen_merdiven([v for _s, v, _lv in olculen])
    if oneri:
        print(f"\n{'=' * 78}")
        print("KARSILASTIRMA: olculen dagilimi 7 esit dilime bolen alternatif")
        print("(karar icin girdi — otomatik uygulanmaz)")
        print(f"{'=' * 78}\n")
        for kesme, kademe in oneri:
            print(f"  <= %{kesme * 100:>6.2f}  ->  {kademe.value}")
        print(f"  >  %{oneri[-1][0] * 100:>6.2f}  ->  very_high")

    print()


if __name__ == "__main__":
    main()
