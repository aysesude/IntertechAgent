"""Kullanıcının alım/satım emirlerini deftere yazar.

Bu servis defterin ÜSTÜNDE ince bir katman: muhasebenin kendisi
`ledger_service.record_transaction` içinde ve orada zaten yetersiz nakit ile
eldekinden fazla satış engelli. Buradaki iş üç şey:

  1. emrin fiyatını ve kurunu SUNUCUDA çözmek (istemciye bırakılmaz),
  2. uygunluk kuralını uygulamak (puanının üstündeki varlık ALINAMAZ),
  3. defterden sonra `holdings` önbelleğini yeniden kurmak.

NEDEN AJANA AÇILMIYOR. Bu fonksiyonlar için MCP tool'u YAZILMADI ve
yazılmamalı. `agents/scope.yaml` alım/satım fiillerini `UNAUTHORIZED_ACTION`
sayıyor; sohbet üzerinden bir modelin emir geçebilmesi, prompt
enjeksiyonuyla portföyün ele geçirilmesi demek olurdu. Risk profilinde de
aynı gerekçe yazılı (`user_service`), ama orada beyan değişiyordu — burada
para hareket ediyor.
"""

import time
from datetime import date, datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ASSET_QUANTITY_PRECISION, AssetClass, settings
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models import Asset, Portfolio, PriceHistory, TransactionType, User
from app.providers.registry import latest_chain
from app.providers.universe import SPEC_BY_SYMBOL
from app.schemas.trade import (
    TradableAsset,
    TradableList,
    TradePreview,
    TradeResult,
    TradeSide,
)
from app.services.advice_eligibility import asset_risk_level
from app.services.ledger_service import (
    cash_balance_as_of,
    position_as_of,
    rebuild_holdings,
    record_transaction,
)

# Kullanıcı emirlerinin defterdeki imzası.
#
# `scripts/data_doctor` §3 her BUY/SELL'in fiyatını O GÜNÜN kapanışıyla
# karşılaştırıyor; o kontrol seed'in ürettiği veriyi denetlemek için var
# ("backfill seed'den sonra mı koştu"). Kullanıcı emri GÜN İÇİ fiyattan
# yazılıyor ve kapanıştan farklı olması normal — ayırt edilmezse doktor
# her gerçek işlemi sahte bir bulgu olarak raporlardı.
USER_ORDER_NOTE = "Kullanıcı emri (Al/Sat ekranı)"

_TRY_QUANT = Decimal("0.0001")
_ZERO = Decimal(0)

# Komisyon YOK (ürün kararı, 27 Ağustos 2026). Sabit burada duruyor ki
# ileride açılacaksa tek yerden açılsın; `record_transaction` zaten
# `fee_try`'ı maliyete katıyor.
FEE_RATE = Decimal(0)

# Kur çevrimi için taban sembol. TRY dışı her varlık bunun üzerinden çevrilir
# (evrende USD dışı yabancı para birimi yok; çıkarsa burası genişler).
_FX_SYMBOL_BY_CURRENCY = {"USD": "USDTRY"}


def _get_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"Kullanıcı bulunamadı: {user_id}")
    return user


def _get_portfolio(db: Session, user_id: UUID) -> Portfolio:
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portföy bulunamadı: {user_id}")
    return portfolio


def _son_fiyat(db: Session, asset_id: UUID) -> PriceHistory | None:
    return db.execute(
        select(PriceHistory)
        .where(PriceHistory.asset_id == asset_id)
        .order_by(PriceHistory.price_date.desc())
        .limit(1)
    ).scalar_one_or_none()


class CanliFiyat(NamedTuple):
    """Bir emrin fiyatı ve nereden geldiği."""

    fiyat: Decimal
    gun: date
    canli: bool


# Ön izleme ile onay arasındaki fiyat, aynı kalmalı.
#
# Kullanıcı bir rakam görüp onaylıyor; onaya kadar geçen saniyelerde fiyat
# yeniden çekilseydi ONAYLADIĞINDAN BAŞKA bir fiyattan işlem görürdü. İstemciye
# fiyat yazdırmak da çözüm değil (bkz. şema başlığı), o yüzden fiyat kısa
# ömürlü olarak SUNUCUDA tutuluyor: ön izleme doldurur, onay aynı değeri
# okur. Süre dolduysa yeniden çekilir — bayat bir fiyattan işlem yapmak,
# fiyatın oynamasından kötüdür.
_FIYAT_TTL_SN = 45
_fiyat_onbellegi: dict[str, tuple[float, CanliFiyat]] = {}


def _onbellekten(sembol: str) -> CanliFiyat | None:
    kayit = _fiyat_onbellegi.get(sembol)
    if kayit is None:
        return None
    yazilma, deger = kayit
    if time.monotonic() - yazilma > _FIYAT_TTL_SN:
        _fiyat_onbellegi.pop(sembol, None)
        return None
    return deger


def temizle_fiyat_onbellegi() -> None:
    """Önbelleği boşaltır. YALNIZCA TESTLER İÇİN."""
    _fiyat_onbellegi.clear()


def _canli_cek(sembol: str) -> CanliFiyat | None:
    """Sağlayıcıdan o anki fiyatı çeker; başarısızsa `None`.

    Ölçüldü (27 Ağustos 2026, BIST açıkken): sembol başına ~0,4 sn ve
    kayıtlı kapanışla arasında THYAO'da %0,97 fark vardı. İşlem, kullanıcının
    bilinçli tek seferlik eylemi olduğu için bu gecikme kabul edilebilir —
    sohbet akışında olmazdı.

    Hata YUTULUR ve `None` döner: ağ tökezlediğinde işlem tamamen
    engellenmemeli, kayıtlı kapanışa düşülüp bu kullanıcıya söylenmeli
    (zarif düşüş).
    """
    spec = SPEC_BY_SYMBOL.get(sembol)
    if spec is None or not settings.trade_live_price_enabled:
        return None
    onbellek = _onbellekten(sembol)
    if onbellek is not None:
        return onbellek
    for saglayici, saglayici_sembolu in latest_chain(spec):
        try:
            nokta = saglayici.fetch_latest(saglayici_sembolu)
        except Exception:  # sağlayıcı hataları çeşitli tiplerde gelir
            continue
        if nokta is not None and nokta.close_price > 0:
            deger = CanliFiyat(Decimal(nokta.close_price), nokta.price_date, True)
            _fiyat_onbellegi[sembol] = (time.monotonic(), deger)
            return deger
    return None


def _islem_fiyati(db: Session, asset: Asset) -> CanliFiyat:
    """Emrin fiyatı: önce canlı, olmazsa kayıtlı son kapanış.

    İkisi de yoksa işlem YAPILMAZ — fiyat uydurulmaz (AK 5.5).
    """
    canli = _canli_cek(asset.symbol)
    if canli is not None:
        return canli
    kayit = _son_fiyat(db, asset.id)
    if kayit is None:
        raise ValidationAppError(f"{asset.symbol} için fiyat alınamadı; işlem yapılamaz.")
    return CanliFiyat(Decimal(kayit.close_price), kayit.price_date, False)


def _fx_kuru(db: Session, currency: str) -> Decimal:
    """TRY dışı varlık için o anki kur. TRY ise 1.

    Kur işlem anında OKUNUR ve deftere DONDURULARAK yazılır
    (`transactions.fx_rate_to_try`). Sonradan hesaplansaydı geçmiş bir alımın
    TRY maliyeti bugünkü kura göre değişir ve kâr/zarar oynardı.
    """
    if currency == "TRY":
        return Decimal(1)
    sembol = _FX_SYMBOL_BY_CURRENCY.get(currency)
    if sembol is None:
        raise ValidationAppError(f"{currency} için kur kaynağı tanımlı değil")
    asset = db.execute(select(Asset).where(Asset.symbol == sembol)).scalar_one_or_none()
    if asset is None:
        raise ValidationAppError(f"{sembol} kuru bulunamadı; {currency} işlemi yapılamaz")
    # Kur da fiyatla aynı yoldan: canlı, olmazsa kayıtlı. Varlığı gün içi
    # fiyattan alıp kuru dünden almak, TRY maliyeti tutarsız yapardı.
    return _islem_fiyati(db, asset).fiyat


def _kayitli_kur(db: Session, currency: str) -> Decimal | None:
    """Liste için kur: KAYITLI son kapanış, canlı değil.

    `_fx_kuru` işlem anında canlı çekiyor; liste öyle yapamaz. Listedeki
    fiyatlar zaten kayıtlı kapanış (141 varlık için sağlayıcıya gitmek ~56
    saniye) ve kuru canlı çekmek, fiyatla kuru FARKLI ANLARA ait yapardı.

    Kur bulunamazsa `None` — uydurulmaz; çağıran satırı TL'siz bırakır ve
    alımı engeller (AK 5.5).
    """
    if currency == "TRY":
        return Decimal(1)
    sembol = _FX_SYMBOL_BY_CURRENCY.get(currency)
    if sembol is None:
        return None
    asset = db.execute(select(Asset).where(Asset.symbol == sembol)).scalar_one_or_none()
    if asset is None:
        return None
    kayit = _son_fiyat(db, asset.id)
    return Decimal(kayit.close_price) if kayit is not None else None


def _yuvarla(quantity: Decimal, asset_class: AssetClass) -> Decimal:
    """Miktarı sınıfın hassasiyetine AŞAĞI yuvarlar.

    Aşağı, bilerek: yukarı yuvarlamak kullanıcının istemediği kadar alım
    yaptırır ve alım tarafında bakiyeyi hak etmediği kadar düşürür.
    """
    return quantity.quantize(ASSET_QUANTITY_PRECISION[asset_class], rounding=ROUND_DOWN)


def _engel_sebebi(asset: Asset, survey_score: int | None) -> str | None:
    """Bu varlık ALINABİLİR mi; alınamıyorsa kullanıcıya söylenecek sebep.

    Satış BU KONTROLDEN GEÇMEZ, bilerek: elindeki uyumsuz varlıktan çıkışın
    tek yolu satmaktır. Satışı da engellemek kullanıcıyı uyumsuz pozisyonda
    kilitler.
    """
    if not asset.is_active:
        return f"{asset.symbol} artık işlem görmüyor."
    if survey_score is None:
        return "Risk anketiniz kayıtlı değil; alım için önce anketi doldurmalısınız."
    seviye = asset_risk_level(asset.symbol, asset.asset_class)
    if seviye > survey_score:
        return (
            f"Bu varlığın risk seviyesi {seviye}, sizin anket puanınız {survey_score}. "
            "Profilinize uymayan varlıklar için alım yapılamaz."
        )
    return None


def get_tradable_assets(db: Session, user_id: UUID) -> TradableList:
    """Al/Sat ekranının listesi: evrendeki tutulabilir varlıklar + uygunluk.

    UÇ, UYGUN OLMAYANLARI DA DÖNER. Arayüz onları Al sekmesinde gizliyor
    (28 Ağustos 2026 ürün kararı: kullanıcı alamayacağı varlıkla
    uğraşmasın), ama eleme SUNUCUDA yapılmıyor: sözleşme tam listeyi
    verdiği sürece arayüz kaç varlığın neden gizlendiğini sayabiliyor ve
    ileride "puanınızı yükseltirseniz şunlar açılır" ekranı aynı uçtan
    beslenebilir. Sunucuda elemek bu bilgiyi tamamen yok ederdi.
    """
    user = _get_user(db, user_id)
    portfolio = _get_portfolio(db, user_id)

    pozisyonlar = position_as_of(db, portfolio.id, datetime.now(timezone.utc).date())
    # `tradable` süzgeci ŞART: endeksler (XU100, SPX) ve emtia (BRENT)
    # fiyatlanıp saklanıyor — kıyaslama ve piyasa şeridi onlara dayanıyor —
    # ama satın alınamazlar. Süzgeç yokken BIST 100 endeksi Al/Sat listesinde
    # sıradan bir hisse gibi görünüyordu.
    varliklar = db.execute(select(Asset).where(Asset.is_active, Asset.tradable)).scalars().all()

    # Kur para birimi başına BİR KEZ okunur: evrende 22 USD varlık var ve
    # her satır için ayrı sorgu aynı kaydı yirmi iki kez okumak olurdu.
    kurlar: dict[str, Decimal | None] = {}

    satirlar: list[TradableAsset] = []
    for asset in sorted(varliklar, key=lambda a: a.symbol):
        fiyat = _son_fiyat(db, asset.id)
        yas = (datetime.now(timezone.utc).date() - fiyat.price_date).days if fiyat else None
        if asset.currency not in kurlar:
            kurlar[asset.currency] = _kayitli_kur(db, asset.currency)
        kur = kurlar[asset.currency]
        fiyat_try = (
            (Decimal(fiyat.close_price) * kur).quantize(_TRY_QUANT, rounding=ROUND_HALF_UP)
            if fiyat is not None and kur is not None
            else None
        )

        engel = _engel_sebebi(asset, user.risk_survey_score)
        if engel is None and fiyat is not None and kur is None:
            # Kuru olmayan varlık TL'ye çevrilemez; alım denemesi ön izlemede
            # zaten hata verirdi. Sunup sonra reddetmektense burada söylenir.
            engel = f"{asset.symbol} için {asset.currency}/TRY kuru bulunamadı."
        satirlar.append(
            TradableAsset(
                symbol=asset.symbol,
                name=asset.name,
                asset_class=asset.asset_class,
                currency=asset.currency,
                risk_level=asset_risk_level(asset.symbol, asset.asset_class),
                price=Decimal(fiyat.close_price) if fiyat else None,
                price_try=fiyat_try,
                fx_rate_to_try=kur,
                price_date=fiyat.price_date if fiyat else None,
                price_source=fiyat.source.value if fiyat else None,
                price_stale=yas is not None and yas > settings.current_price_stale_days,
                can_buy=engel is None and fiyat is not None,
                block_reason=engel
                or (None if fiyat else f"{asset.symbol} için kayıtlı fiyat yok."),
                held_quantity=pozisyonlar.get(asset.id, _ZERO),
                quantity_step=ASSET_QUANTITY_PRECISION[asset.asset_class],
            )
        )

    return TradableList(
        user_id=user_id,
        survey_score=user.risk_survey_score,
        cash_balance=cash_balance_as_of(db, portfolio.id),
        assets=satirlar,
    )


def preview_trade(
    db: Session, user_id: UUID, symbol: str, side: TradeSide, quantity: Decimal
) -> TradePreview:
    """Emri hesaplar ama DEFTERE YAZMAZ.

    Aynı hesap `execute_trade` tarafından da kullanılıyor; ön izlemede
    gösterilen rakam ile yazılan rakamın farklı yollardan gelmesi, ikisinin
    ayrışması demek olurdu.
    """
    user = _get_user(db, user_id)
    portfolio = _get_portfolio(db, user_id)

    asset = db.execute(select(Asset).where(Asset.symbol == symbol.upper())).scalar_one_or_none()
    if asset is None:
        raise NotFoundError(f"Varlık bulunamadı: {symbol}")

    islem_fiyati = _islem_fiyati(db, asset)

    miktar = _yuvarla(quantity, asset.asset_class)
    if miktar <= 0:
        adim = ASSET_QUANTITY_PRECISION[asset.asset_class]
        raise ValidationAppError(
            f"{asset.symbol} için en küçük işlem miktarı {adim}. Girilen miktar aşağı "
            "yuvarlandığında sıfır kalıyor."
        )

    if side is TradeSide.BUY:
        engel = _engel_sebebi(asset, user.risk_survey_score)
        if engel is not None:
            raise ValidationAppError(engel)

    elde = position_as_of(db, portfolio.id, datetime.now(timezone.utc).date()).get(asset.id, _ZERO)
    if side is TradeSide.SELL and miktar > elde:
        raise ValidationAppError(
            f"Elinizde {elde} adet {asset.symbol} var, {miktar} adet satılamaz."
        )

    fiyat = islem_fiyati.fiyat
    kur = _fx_kuru(db, asset.currency)
    brut = (miktar * fiyat * kur).quantize(_TRY_QUANT, rounding=ROUND_HALF_UP)
    komisyon = (brut * FEE_RATE).quantize(_TRY_QUANT, rounding=ROUND_HALF_UP)
    nakit_delta = -(brut + komisyon) if side is TradeSide.BUY else brut - komisyon

    nakit_once = cash_balance_as_of(db, portfolio.id)
    if side is TradeSide.BUY and nakit_once + nakit_delta < 0:
        raise ValidationAppError(
            f"Yetersiz bakiye: {nakit_once} TL var, bu işlem {-nakit_delta} TL istiyor."
        )

    yas = (datetime.now(timezone.utc).date() - islem_fiyati.gun).days
    return TradePreview(
        symbol=asset.symbol,
        name=asset.name,
        side=side,
        quantity=miktar,
        price=fiyat,
        price_date=islem_fiyati.gun,
        price_stale=yas > settings.current_price_stale_days,
        price_is_live=islem_fiyati.canli,
        currency=asset.currency,
        fx_rate_to_try=kur,
        gross_try=brut,
        fee_try=komisyon,
        cash_delta_try=nakit_delta,
        cash_before=nakit_once,
        cash_after=nakit_once + nakit_delta,
        held_before=elde,
        held_after=elde + miktar if side is TradeSide.BUY else elde - miktar,
    )


def execute_trade(
    db: Session, user_id: UUID, symbol: str, side: TradeSide, quantity: Decimal
) -> TradeResult:
    """Emri deftere yazar ve `holdings` önbelleğini yeniden kurar.

    `preview_trade` tekrar çağrılıyor: doğrulamaların TAMAMI orada ve tek
    yerde durması gerekiyor. İki ayrı kontrol listesi olsaydı biri
    güncellenip diğeri unutulurdu.
    """
    onizleme = preview_trade(db, user_id, symbol, side, quantity)
    portfolio = _get_portfolio(db, user_id)
    asset = db.execute(select(Asset).where(Asset.symbol == onizleme.symbol)).scalar_one_or_none()

    islem = record_transaction(
        db,
        portfolio.id,
        TransactionType.BUY if side is TradeSide.BUY else TransactionType.SELL,
        transaction_date=datetime.now(timezone.utc),
        asset_id=asset.id,
        quantity=onizleme.quantity,
        price=onizleme.price,
        currency=onizleme.currency,
        fx_rate_to_try=onizleme.fx_rate_to_try,
        fee_try=onizleme.fee_try,
        note=USER_ORDER_NOTE,
    )
    # Defter tek gerçek; `holdings` ondan TÜRETİLEN önbellek. Yeniden
    # kurulmazsa portföy ekranı işlemi hiç olmamış gibi gösterir.
    rebuild_holdings(db, portfolio.id)
    db.commit()

    return TradeResult(
        transaction_id=islem.id,
        executed_at=islem.transaction_date,
        preview=onizleme,
    )


def deposit_cash(db: Session, user_id: UUID, amount: Decimal) -> Decimal:
    """Nakit yatırır ve yeni bakiyeyi döner.

    Demo akışı için: bakiyesi biten kullanıcı bir daha alım yapamaz ve
    ekranda yapacak bir şey kalmaz. GERÇEK BİR ÖDEME AKIŞI DEĞİLDİR; arayüz
    bunu böyle sunmalı, "para yatırdım" hissi vermemeli.
    """
    portfolio = _get_portfolio(db, user_id)
    tutar = amount.quantize(_TRY_QUANT, rounding=ROUND_DOWN)
    if tutar <= 0:
        raise ValidationAppError("Yatırılacak tutar sıfırdan büyük olmalı.")

    record_transaction(
        db,
        portfolio.id,
        TransactionType.DEPOSIT,
        transaction_date=datetime.now(timezone.utc),
        cash_amount_try=tutar,
        note="Demo nakit yatırma",
    )
    db.commit()
    return cash_balance_as_of(db, portfolio.id)
