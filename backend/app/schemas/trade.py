"""Al/Sat uçlarının şemaları.

Bu, projedeki İLK PARA HAREKET ETTİREN sözleşme. Şimdiye kadarki tek yazan uç
risk profiliydi ve o yalnızca bir beyanı güncelliyordu; buradaki her istek
defterin kendisine kayıt düşüyor.

FİYAT KULLANICIYA GÖSTERİLİR, KULLANICIDAN ALINMAZ. İstek gövdesinde fiyat
alanı YOKTUR ve olmamalıdır: istemciye fiyat yazdırmak, tarayıcı üzerinden
istediği fiyattan alım yapmaya açık kapı bırakır. Fiyat her zaman sunucudaki
son kapanıştan okunur; kullanıcının gördüğü rakam `preview` ile aynı yoldan
gelir.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import AssetClass

Money = Decimal


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradableAsset(BaseModel):
    """Al/Sat ekranındaki bir satır."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    asset_class: AssetClass
    currency: str
    risk_level: int
    # Son kapanış. `price_date` "bugün" DEĞİL: piyasa hafta sonu ve tatilde
    # kapalı. Arayüz tarihi göstermek zorunda, yoksa kullanıcı canlı fiyat
    # sanır.
    # Listedeki fiyat KAYITLI kapanıştır, canlı değil: 141 varlık için
    # sağlayıcıya gitmek ~56 saniye sürerdi (ölçüldü). Canlı fiyat yalnızca
    # kullanıcı bir varlık seçtiğinde, ön izlemede çekilir.
    price: Money | None
    price_date: date | None
    price_source: str | None
    price_stale: bool
    # Kullanıcının anket puanı bu varlığı ALMAYA yetiyor mu.
    can_buy: bool
    # Yetmiyorsa sebebi — kilitli bir satırın neden kilitli olduğu
    # söylenmezse kullanıcı hatayı kendinde arar.
    block_reason: str | None
    # Kullanıcının elindeki miktar (satış için). 0 ise satılamaz.
    held_quantity: Money
    # Miktar kaç ondalıkla girilebilir (hisse tam sayı, maden 0,01).
    quantity_step: Money


class TradableList(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    survey_score: int | None
    cash_balance: Money
    assets: list[TradableAsset]


class TradeRequest(BaseModel):
    """Alım/satım emri.

    `quantity` POZİTİF; yön `side` alanından okunur — negatif miktarla ters
    işlem yaptırmak, defterin işaret sözleşmesini istemciye açmak olurdu.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=32)
    side: TradeSide
    quantity: Decimal = Field(gt=0)


class DepositRequest(BaseModel):
    """Nakit yatırma.

    Demo akışında bakiyesi biten kullanıcının kilitlenmemesi için var; gerçek
    bir ödeme akışı DEĞİLDİR ve öyle sunulmamalı.
    """

    model_config = ConfigDict(frozen=True)

    amount: Decimal = Field(gt=0, le=Decimal("10000000"))


class TradePreview(BaseModel):
    """Onaydan önce gösterilen hesap.

    Kullanıcı "ne ödeyeceğim, sonrasında bakiyem ne olacak" sorusunu
    onaylamadan önce görmeli; emri kör onaylatmak bu ekranın en kolay
    hatası olurdu.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    side: TradeSide
    # Emir, varlık sınıfının hassasiyetine yuvarlanmış hâli. Kullanıcının
    # yazdığından FARKLI olabilir (3,7 hisse -> 3) ve bu gösterilmeli.
    quantity: Money
    price: Money
    price_date: date
    price_stale: bool
    # Fiyat sağlayıcıdan O AN mı çekildi, yoksa kayıtlı son kapanış mı?
    # Kullanıcı neyi onayladığını bilmeli: gün içi fiyatla dünkü kapanış
    # arasında yüzde birlik farklar oluyor (ölçüldü).
    price_is_live: bool
    currency: str
    fx_rate_to_try: Money
    gross_try: Money
    fee_try: Money
    # İşlemin nakit ayağı: alımda negatif, satımda pozitif.
    cash_delta_try: Money
    cash_before: Money
    cash_after: Money
    held_before: Money
    held_after: Money


class TradeResult(BaseModel):
    """Gerçekleşen işlem."""

    model_config = ConfigDict(frozen=True)

    transaction_id: UUID
    executed_at: datetime
    preview: TradePreview
