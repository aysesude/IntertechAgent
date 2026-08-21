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

  **Uydurulmaz, ölçülür.** Fon değerleri bir kez uydurulmuştu ve gerçekten
  kat kat sapıyordu (`TI2` 2,1450 yazılıydı, gerçek fiyatı 0,11 — 20 kat).
  Gerçek verinin bulunduğu ortamda sapma zararsız (upsert onu eziyor), ama
  backfill hiç koşmamış bir kurulumda gerçekle alakasız bir evren üretiyordu.
  Tazelemek için serinin İLK gerçek fiyatı okunur — bugünkü değil, çünkü
  `base_price` serinin başlangıcıdır:

      SELECT a.symbol,
             (SELECT p.close_price FROM price_history p
              WHERE p.asset_id = a.id AND p.source <> 'synthetic'
              ORDER BY p.price_date LIMIT 1) AS ilk_gercek_fiyat
      FROM assets a WHERE a.is_active ORDER BY a.symbol;

  Aşağıdaki TEFAS fon değerleri 21 Ağustos 2026'da bu sorguyla alındı
  (serinin başı: 21 Ağustos 2025). Hisse, maden ve döviz değerleri hâlâ
  elle konmuş yaklaşık değerler; mertebeleri doğru olduğu için
  güncellenmedi.
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
    # Sentetik üretimde sınıf varsayılanını ezen günlük drift/volatilite
    # (bkz. seed_prices_synthetic.ASSET_CLASS_DAILY_DRIFT_VOLATILITY). Yalnızca
    # varlık, sınıfının tipik davranışından ayrıldığında verilir — ör. para
    # piyasası fonu CASH sınıfındadır ama mevduat gibi sabit durmaz, fiyatı
    # üzerinden getiri biriktirir.
    synthetic_daily_drift: float | None = None
    synthetic_daily_volatility: float | None = None


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


# Fon alt türü -> varlık sınıfı. Fonun ekonomik riski neyse sınıfı odur:
# para piyasası fonu nakit gibi, altın fonu altın gibi, borçlanma araçları
# fonu tahvil gibi davranır.
#
# Eskiden tüm fonlar AssetClass.STOCK idi ("gerek.md §2 fonları hisse senedi
# başlığı altında gruplar" gerekçesiyle). §2'nin listesi sınıf başına kendi
# enstrümanlarını sayıyor ("Kıymetli Madenler (Altın, Gümüş, Platin)"), yani
# "(Hisse, Fon)" ifadesi HİSSE fonunu kastediyor. Kuralı harfi harfine
# uygulamak altın fonuna ve para piyasası fonuna FR-4'ün "Hisse -> Yüksek"
# risk etiketini düşürüyordu; para piyasası fonu en düşük riskli
# enstrümandır, risk motorunda savunma tarafında (BOND+CASH) sayılmalıdır.
_FUND_ASSET_CLASS: dict[AssetSubType, AssetClass] = {
    AssetSubType.EQUITY_FUND: AssetClass.STOCK,
    AssetSubType.MONEY_MARKET_FUND: AssetClass.CASH,
    AssetSubType.GOLD_FUND: AssetClass.PRECIOUS_METAL,
    AssetSubType.BOND_FUND: AssetClass.BOND,
    AssetSubType.CORPORATE_BOND_FUND: AssetClass.BOND,
    AssetSubType.EUROBOND_FUND: AssetClass.BOND,
}


def _fund(
    symbol: str,
    name: str,
    sub_type: AssetSubType,
    base_price: str,
    currency: str = "TRY",
    synthetic_daily_drift: float | None = None,
    synthetic_daily_volatility: float | None = None,
) -> AssetSpec:
    """TEFAS fonu. Sembol = fon kodu = sağlayıcı sembolü.

    `currency`: TEFAS fiyatları kural olarak TL'dir; döviz cinsi fonlarda
    (ör. AKE eurobond fonu) birim fiyat kendi para biriminde yayımlanır ve
    değerleme o günün kuruyla TRY'ye çevrilir (AK 5.7).
    """
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=_FUND_ASSET_CLASS[sub_type],
        base_price=Decimal(base_price),
        currency=currency,
        sub_type=sub_type,
        data_source=PriceSource.TEFAS,
        provider_symbol=symbol,
        synthetic_daily_drift=synthetic_daily_drift,
        synthetic_daily_volatility=synthetic_daily_volatility,
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
    # --- Tahvil: TEFAS borçlanma araçları fonları ---
    # Türk tahvillerinin ücretsiz ve güvenilir bir fiyat kaynağı yok. Önceki
    # sürümde burada dört UYDURMA enstrüman vardı (TRT101/TRT052/EUROBOND1/
    # OST2027); gerçek bir ISIN'e karşılık gelmedikleri için hiçbir sağlayıcı
    # onları çekemiyordu ve fiyatları sonsuza kadar sentetik kalıyordu —
    # portföyün ~%21'i bayat veriyle değerleniyor, tahvil volatilitesi son
    # pencerede sıfır çıkıp riski olduğundan düşük gösteriyordu.
    #
    # Yerlerine aynı riski taşıyan GERÇEK TEFAS fonları kondu: günlük fiyat,
    # resmî kaynak (AK 5.1), zaten çalışan TefasProvider. Fon tahvil değildir
    # (vadesi/kuponu yok, yönetim ücreti var) ama tahvil riski taşır ve
    # uydurma enstrümandan her koşulda daha dürüsttür.
    _fund(
        "AK2", "Ak Portföy Uzun Vadeli Borçlanma Araçları Fonu", AssetSubType.BOND_FUND, "0.435853"
    ),
    _fund(
        "APT", "Ak Portföy Orta Vadeli Borçlanma Araçları Fonu", AssetSubType.BOND_FUND, "0.122145"
    ),
    # Birim fiyatı USD yayımlanır; ölçüldü (getiri korelasyonu USDTRY ile
    # -0.11, TL fiyatlı olsaydı ~0.8 beklenirdi). Evrendeki tek TRY dışı
    # varlık, dolayısıyla AK 5.7 kur dönüşümünü egzersiz eden tek enstrüman.
    _fund(
        "AKE",
        "Ak Portföy Eurobond (ABD Doları) Borçlanma Araçları Fonu",
        AssetSubType.EUROBOND_FUND,
        "0.430407",
        currency="USD",
    ),
    _fund(
        "AYR",
        "Ak Portföy Özel Sektör Borçlanma Araçları (TL) Fonu",
        AssetSubType.CORPORATE_BOND_FUND,
        "0.095774",
    ),
    # --- TEFAS fonları ---
    _fund("TI2", "İş Portföy Hisse Senedi Fonu", AssetSubType.EQUITY_FUND, "0.110169"),
    _fund("TCD", "İş Portföy Değişken Fon", AssetSubType.EQUITY_FUND, "35.646015"),
    _fund("AFT", "Ak Portföy Yeni Teknolojiler Fonu", AssetSubType.EQUITY_FUND, "0.669568"),
    # PPF nakit, GTA kıymetli maden sınıfına düşer (bkz. _FUND_ASSET_CLASS).
    #
    # PPF sınıf varsayılanını ezer: CASH sınıfının sentetik parametreleri
    # MEVDUAT için yazılmış (drift 0, volatilite 0 — birim fiyat sabit 1 TL,
    # getiri INTEREST işlemlerinden gelir). Para piyasası fonu ise getirisini
    # FİYATI üzerinden biriktirir; sınıf varsayılanıyla çevrimdışı modda düz
    # çizgi kalıyor ve hiç getiri üretmiyordu.
    # Günlük drift 0.00159 ≈ yıllık %40 (252 işlem günü); volatilite 0.0004
    # ≈ yıllık %0,6 — para piyasası fonunun gerçek oynaklığı bu mertebede.
    _fund(
        "PPF",
        "Para Piyasası Fonu",
        AssetSubType.MONEY_MARKET_FUND,
        "3.502603",
        synthetic_daily_drift=0.00159,
        synthetic_daily_volatility=0.0004,
    ),
    _fund("GTA", "Garanti Portföy Altın Fonu", AssetSubType.GOLD_FUND, "1.078670"),
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
