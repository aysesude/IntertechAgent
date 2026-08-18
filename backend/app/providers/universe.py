"""Varlık evreninin TEK tanım noktası.

`data/seed_assets.py` bu listeyi DB'ye yazar; `providers/registry.py` sağlayıcı
zincirini bu listedeki eşlemeden kurar; sentetik üretici `base_price`'ı buradan
okur. Yeni varlık eklemek = bu listeye bir satır eklemek; başka kod değişmez.

Alan notları:
- `provider_symbol`: birincil kaynaktaki sembol (THYAO -> 'THYAO.IS',
  USDTRY -> EVDS serisi 'TP.DK.USD.S.YTL', TI2 -> TEFAS fon kodu 'TI2').
- `tcmb_code`: today.xml spot kuru için para birimi kodu (yalnızca döviz).
- `yf_symbol`: yedek yfinance sembolü (EVDS anahtarı yoksa tarihsel kur buradan).
- `ons_to_gram`: GC=F gibi ons-USD vadeli fiyatın gram-TRY'ye çevrilmesi
  (ons / 31.1034768 × o günün USDTRY kuru).
- `base_price`: sentetik serinin başlangıç değeri. Tüm varlıklarda dolu ki
  sistem tamamen çevrimdışı da çalışabilsin (A1); gerçek veri geldiğinde
  upsert önceliği sentetiği ezer, tersi asla olmaz.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.config import AssetClass, AssetSubType, PriceSource

TROY_OUNCE_GRAMS = Decimal("31.1034768")


@dataclass(frozen=True)
class AssetSpec:
    symbol: str
    name: str
    asset_class: AssetClass
    base_price: Decimal
    currency: str = "TRY"
    sub_type: AssetSubType | None = None
    data_source: PriceSource = PriceSource.SYNTHETIC
    provider_symbol: str | None = None
    tcmb_code: str | None = None
    yf_symbol: str | None = None
    ons_to_gram: bool = False
    derived_from: str | None = None
    derived_factor: Decimal | None = None


def _stock(symbol: str, name: str, base_price: str) -> AssetSpec:
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=AssetClass.STOCK,
        base_price=Decimal(base_price),
        data_source=PriceSource.YFINANCE,
        provider_symbol=f"{symbol}.IS",
    )


def _fx(symbol: str, name: str, tcmb_code: str, base_price: str) -> AssetSpec:
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=AssetClass.CURRENCY,
        base_price=Decimal(base_price),
        data_source=PriceSource.TCMB_EVDS,
        provider_symbol=f"TP.DK.{tcmb_code}.S.YTL",
        tcmb_code=tcmb_code,
        yf_symbol=f"{tcmb_code}TRY=X",
    )


def _gram_metal(symbol: str, name: str, yf_future: str, base_price: str) -> AssetSpec:
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=AssetClass.PRECIOUS_METAL,
        base_price=Decimal(base_price),
        data_source=PriceSource.YFINANCE,
        provider_symbol=yf_future,
        ons_to_gram=True,
    )


def _gold_coin(symbol: str, name: str, factor: str, base_price: str) -> AssetSpec:
    # Katsayı = sikke ağırlığı (g) × milyem. Çeyrek: 1.75 × 0.916 = 1.6030.
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=AssetClass.PRECIOUS_METAL,
        base_price=Decimal(base_price),
        sub_type=AssetSubType.GOLD_COIN,
        data_source=PriceSource.DERIVED,
        derived_from="XAUTRY",
        derived_factor=Decimal(factor),
    )


def _fund(symbol: str, name: str, sub_type: AssetSubType, base_price: str) -> AssetSpec:
    # gerek.md §2 fonları hisse senedi başlığı altında gruplar; ayrı AssetClass
    # açılmadı (plan kararı 8.2), ayrım sub_type ile yapılır.
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=AssetClass.STOCK,
        base_price=Decimal(base_price),
        sub_type=sub_type,
        data_source=PriceSource.TEFAS,
        provider_symbol=symbol,
    )


ASSET_UNIVERSE: list[AssetSpec] = [
    # --- Hisse (BIST, yfinance) ---
    _stock("THYAO", "Türk Hava Yolları", "285.00"),
    _stock("ASELS", "Aselsan", "62.50"),
    _stock("GARAN", "Garanti BBVA", "98.30"),
    _stock("AKBNK", "Akbank", "58.20"),
    _stock("BIMAS", "BİM Mağazalar", "540.00"),
    _stock("EREGL", "Ereğli Demir Çelik", "45.10"),
    _stock("KCHOL", "Koç Holding", "175.00"),
    _stock("SASA", "Sasa Polyester", "12.80"),
    _stock("TUPRS", "Tüpraş", "165.00"),
    _stock("PGSUS", "Pegasus Hava Taşımacılığı", "425.00"),
    _stock("SISE", "Şişecam", "38.90"),
    _stock("FROTO", "Ford Otosan", "890.00"),
    _stock("TCELL", "Turkcell", "82.40"),
    _stock("YKBNK", "Yapı Kredi Bankası", "27.60"),
    _stock("VESTL", "Vestel", "44.30"),
    # --- Kıymetli maden: gram fiyatlar (ons vadeli × USDTRY) ---
    _gram_metal("XAUTRY", "Gram Altın", "GC=F", "2450.00"),
    _gram_metal("XAGTRY", "Gram Gümüş", "SI=F", "38.00"),
    _gram_metal("XPTTRY", "Gram Platin", "PL=F", "1550.00"),
    # --- Kıymetli maden: sikke (gram altından türetilir) ---
    _gold_coin("CEYREK", "Çeyrek Altın", "1.6030", "4020.00"),
    _gold_coin("YARIM", "Yarım Altın", "3.2060", "8040.00"),
    _gold_coin("TAMALTIN", "Tam Altın", "6.4120", "16080.00"),
    _gold_coin("CUMHUR", "Cumhuriyet Altını", "6.6150", "16500.00"),
    # --- Döviz (tarihsel: EVDS, yedek yfinance; spot: today.xml) ---
    _fx("USDTRY", "Amerikan Doları", "USD", "34.20"),
    _fx("EURTRY", "Euro", "EUR", "37.10"),
    _fx("GBPTRY", "İngiliz Sterlini", "GBP", "43.50"),
    _fx("CHFTRY", "İsviçre Frangı", "CHF", "38.90"),
    # --- Tahvil (ücretsiz güvenilir kaynak yok; sentetik kalır) ---
    AssetSpec(
        symbol="TRT101",
        name="Devlet Tahvili 10Y",
        asset_class=AssetClass.BOND,
        base_price=Decimal("980.00"),
        sub_type=AssetSubType.GOVERNMENT_BOND,
    ),
    AssetSpec(
        symbol="TRT052",
        name="Devlet Tahvili 5Y",
        asset_class=AssetClass.BOND,
        base_price=Decimal("990.00"),
        sub_type=AssetSubType.GOVERNMENT_BOND,
    ),
    AssetSpec(
        symbol="EUROBOND1",
        name="Hazine Eurobond",
        asset_class=AssetClass.BOND,
        base_price=Decimal("97.50"),
        currency="USD",
        sub_type=AssetSubType.EUROBOND,
    ),
    AssetSpec(
        symbol="OST2027",
        name="Özel Sektör Tahvili 2027",
        asset_class=AssetClass.BOND,
        base_price=Decimal("950.00"),
        sub_type=AssetSubType.CORPORATE_BOND,
    ),
    # --- TEFAS fonları ---
    _fund("TI2", "İş Portföy Hisse Senedi Fonu", AssetSubType.EQUITY_FUND, "2.1450"),
    _fund("TCD", "İş Portföy Değişken Fon", AssetSubType.EQUITY_FUND, "5.4200"),
    _fund("AFT", "Ak Portföy Yeni Teknolojiler Fonu", AssetSubType.EQUITY_FUND, "0.3250"),
    _fund("PPF", "Para Piyasası Fonu", AssetSubType.MONEY_MARKET_FUND, "118.5000"),
    _fund("GTA", "Garanti Portföy Altın Fonu", AssetSubType.EQUITY_FUND, "2.5800"),
    # --- Nakit (birim fiyatı 1 TL sabit varlık olarak modellenir; mevduat
    #     faizi INTEREST işlemiyle deftere yazılır) ---
    AssetSpec(
        symbol="MEVDUAT-VS",
        name="Vadesiz Mevduat",
        asset_class=AssetClass.CASH,
        base_price=Decimal("1.00"),
        sub_type=AssetSubType.DEMAND_DEPOSIT,
    ),
    AssetSpec(
        symbol="MEVDUAT-V",
        name="Vadeli Mevduat",
        asset_class=AssetClass.CASH,
        base_price=Decimal("1.00"),
        sub_type=AssetSubType.TIME_DEPOSIT,
    ),
]

SPEC_BY_SYMBOL: dict[str, AssetSpec] = {spec.symbol: spec for spec in ASSET_UNIVERSE}

assert len(SPEC_BY_SYMBOL) == len(ASSET_UNIVERSE), "Varlık evreninde tekrar eden sembol var"
