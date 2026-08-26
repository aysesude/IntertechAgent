"""Uygulama genelindeki tüm yapılandırma buradan okunur. Kodun başka hiçbir
yerinde sabit bağlantı adresi, anahtar veya model adı bulunmamalıdır."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    OPENAI = "openai"
    AZURE = "azure"
    OLLAMA = "ollama"


class AssetClass(str, Enum):
    STOCK = "stock"
    PRECIOUS_METAL = "precious_metal"
    CURRENCY = "currency"
    BOND = "bond"
    CASH = "cash"


class TimeWindow(str, Enum):
    """Grafik ve kıyaslama pencereleri. Portföy bu pencereden gençse başlangıç
    ilk işlem tarihine kırpılır ve bu durum çıktıda bildirilir."""

    M1 = "1m"
    M3 = "3m"
    M6 = "6m"
    M12 = "12m"


class Granularity(str, Enum):
    """Seri çözünürlüğü. AUTO ~60-120 nokta hedefler: 1m/3m/6m günlük,
    12m haftalık. Volatilite günlük getirilerden hesaplandığı için risk
    tarafı DAILY istemek zorundadır."""

    AUTO = "auto"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class PriceCurrency(str, Enum):
    """TRY: o günün kuruyla çevrilmiş. NATIVE: varlığın kendi para birimi."""

    TRY = "try"
    NATIVE = "native"


class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    GROWTH = "growth"
    AGGRESSIVE = "aggressive"


class RiskLevel(str, Enum):
    """Yıllık portföy volatilitesinden (kategori bazlı kovaryans hesabından)
    türetilen 7 kademeli risk etiketi (bkz. RISK_LEVEL_VOLATILITY_UPPER_BOUNDS).

    Eski 3 kademeli (low/medium/high) kompozit skor sistemi kaldırıldı: risk
    seviyesi artık yalnızca volatiliteden gelir, yoğunlaşma/çeşitlendirme gibi
    ölçütler skora karışmaz — onlar risk_service.py'de yalnızca kök neden
    teşhisinde (risk neden yüksek çıktı) kullanılır."""

    VERY_LOW = "very_low"  # Çok Düşük
    LOW = "low"  # Düşük
    LOW_MEDIUM = "low_medium"  # Düşük-Orta
    MEDIUM = "medium"  # Orta
    MEDIUM_HIGH = "medium_high"  # Orta-Yüksek
    HIGH = "high"  # Yüksek
    VERY_HIGH = "very_high"  # Çok Yüksek


# Yıllık portföy volatilitesi (oran, 0.05 = %5) -> risk seviyesi. Üst sınıra
# kadar dahildir (tam %5 -> VERY_LOW). Listedeki son sınırın (0.40) üzerindeki
# her volatilite VERY_HIGH sayılır. Analist notu: bu tablo değiştiğinde
# risk_service.py'ye dokunmaya gerek yok.
RISK_LEVEL_VOLATILITY_UPPER_BOUNDS: list[tuple[Decimal, RiskLevel]] = [
    (Decimal("0.05"), RiskLevel.VERY_LOW),
    (Decimal("0.10"), RiskLevel.LOW),
    (Decimal("0.15"), RiskLevel.LOW_MEDIUM),
    (Decimal("0.20"), RiskLevel.MEDIUM),
    (Decimal("0.30"), RiskLevel.MEDIUM_HIGH),
    (Decimal("0.40"), RiskLevel.HIGH),
]


class PriceSource(str, Enum):
    """Bir fiyat satırının nereden geldiği (AK 5.1, 5.3).

    Sıralama önemli değildir; öncelik PRICE_SOURCE_PRIORITY'de tanımlıdır.
    """

    SYNTHETIC = "synthetic"  # üretilmiş (dummy) seri
    DERIVED = "derived"  # başka bir varlıktan katsayıyla hesaplandı
    YFINANCE = "yfinance"
    TEFAS = "tefas"
    ISPORTFOY = "isportfoy"
    TCMB = "tcmb"  # today.xml (spot)
    TCMB_EVDS = "tcmb_evds"  # EVDS (tarihsel)


# Upsert çakışmasında hangi kaynağın hangisini ezebileceği: yalnızca daha
# yüksek öncelikli kaynak mevcut satırı günceller. Gerçek veri sentetiği
# ezer; sentetik gerçeği asla ezemez (bkz. services/price_ingest.py).
PRICE_SOURCE_PRIORITY: dict[PriceSource, int] = {
    PriceSource.SYNTHETIC: 0,
    PriceSource.DERIVED: 1,
    PriceSource.YFINANCE: 2,
    PriceSource.TEFAS: 3,
    PriceSource.ISPORTFOY: 3,
    PriceSource.TCMB: 4,
    PriceSource.TCMB_EVDS: 4,
}


# AK 2.6 / BR: varlık sınıfının, geçmiş fiyat verisinden bağımsız "içkin"
# risk seviyesi (0-100 ölçekte, risk_service._composite_score'un diğer
# bileşenleriyle aynı ölçek). Hisse en riskli, tahvil en az riskli kabul
# edilir; döviz orta-yüksek (3 seviyeli bir enum'a sığmadığı için sayısal
# ölçek kullanılır — "orta-yüksek" burada 65 gibi bir ara değerle ifade
# edilir). Analistler bu tabloyu risk_service.py'ye dokunmadan kalibre
# edebilir.
ASSET_CLASS_BASE_RISK_SCORE: dict[AssetClass, Decimal] = {
    AssetClass.STOCK: Decimal(85),
    AssetClass.CURRENCY: Decimal(65),
    AssetClass.PRECIOUS_METAL: Decimal(50),
    AssetClass.BOND: Decimal(20),
    AssetClass.CASH: Decimal(5),
}

# --- Varlık sınıfı uygunluk tablosu (İŞ ANALİSTİ, 2026-08 güncellemesi) ---
#
# Şartnamedeki tanım aynen şöyle: "Kullanıcıların çözdüğü anket sonucu 1-7
# arası bir risk puanı olur. Aşağıdaki risk seviyesi kullanıcının risk
# seviyesinden büyükse kişi o varlık türünden satın alım ya da yatırım
# TAVSİYESİ alamaz."
#
# Buradaki 1-7, volatiliteden hesaplanan `RiskLevel` ile AYNI ŞEY DEĞİLDİR —
# ikisi de yedi kademeli olduğu için karıştırılmaya çok müsait. Bu tablo
# ANKET puanıyla karşılaştırılır; `RiskLevel` ise portföyün ölçülen
# oynaklığından çıkar. Aynı ölçekte oldukları için değil, tesadüfen ikisi de
# 1-7 olduğu için benzer görünürler.
#
# --- Tablo 26 Ağustos 2026'da yeniden kalibre edildi ---
#
# Önceki hâli şartnameden birebir alınmıştı (CASH 1, BOND 3, CURRENCY 4,
# PRECIOUS_METAL 4, STOCK 6). ÖLÇÜLDÜ: yedi puan yalnızca DÖRT farklı sonuç
# üretiyordu — 2, 5 ve 7 puanları bir öncekine hiçbir şey eklemiyordu:
#
#     1 -> nakit          2 -> nakit           (aynı)
#     3 -> +tahvil        4 -> +döviz, maden
#     5 -> (aynı)         6 -> +hisse          7 -> (aynı)
#
# Yani anket 1-7 arası puan verirken sistemin ayırt edebildiği yalnızca dört
# kademe vardı; aradaki puanları kazanmak ya da kaybetmek kullanıcı için
# hiçbir şeyi değiştirmiyordu. Yeni tablo her kademeyi bir kategoriye
# karşılık getiriyor (7 hariç, bilerek boş — aşağıya bakın).
#
# BU ÖLÇEK SRRI DEĞİLDİR. İkisi de 1-7 olduğu için benzer görünür ama SRRI
# volatilite bandından hesaplanır; bu tablo UYGUNLUK (suitability) sıralaması,
# yani "hangi ürün hangi yatırımcıya sunulabilir" sorusunun cevabı. Volatilite
# sıralamayı doğrularken kullanıldı, sıralamayı BELİRLEMEDİ — ölçümle
# ayrıştığı iki yer aşağıda açıkça yazılı.
#
#   1  Serbest nakit, para piyasası fonu     (ölçülen: %0 / IOO %1,42)
#   2  TL borçlanma araçları fonu            (AYR %1,5 · APT %7,1 · AK2 %10,0)
#   3  Döviz, eurobond fonu                  (USDTRY ~%1 · AKE %4,6)
#   4  Kıymetli maden, altın fonu            (gram altın %24 · GTA %25,6)
#   5  Yerli hisse, yerli hisse fonu         (BIST ort. %38,6)
#   6  Yabancı hisse, yabancı hisse fonu     (ABD ort. %28,8)
#   7  (boş — türev/kaldıraçlı ürünler için ayrıldı)
#
# ÖLÇÜMLE AYRIŞAN İKİ YER, ikisi de bilinçli:
#
# (a) Döviz (3) TL tahvil fonundan (2) YÜKSEK, oysa ölçülen volatilitesi çok
#     daha düşük (~%1'e karşı %10'a kadar). Dövizin TL cinsinden düşük
#     oynaklığı düşük risk değil, TL'nin düzenli değer kaybının yan ürünüdür:
#     seri neredeyse tek yönlü tırmandığı için standart sapma küçük çıkar.
#     Döviz TL'li yatırımcı için yönlü bir kur bahsidir. `gerek.md` de dövizi
#     tahvilin üstünde ("Orta-Yüksek") sıralıyor.
#
# (b) Yabancı hisse (6) yerli hisseden (5) YÜKSEK, oysa ABD ortalaması
#     BIST'in ALTINDA (%28,8'e karşı %38,6). Gerekçe volatilite değil ERİŞİM
#     ve KARMAŞIKLIK: kur maruziyeti, sınır ötesi saklama, yerel yatırımcı
#     korumasının bulunmaması, farklı vergi rejimi. Bunu "daha oynak" diye
#     yazmak rakamlara bakan ilk kişi tarafından yakalanırdı.
#
# ŞARTNAMEDEN SAPMA — analist onayına sunulacak:
#   - BOND 3 -> 2, CURRENCY 4 -> 3, STOCK 6 -> 5 (kademelerin yayılması).
#   - Kıymetli maden 4'te KALDI; şartnamede döviz ile aynı seviyedeydi, artık
#     dövizin bir üstünde. `gerek.md` §2 ise tersini söylüyor (maden "Orta",
#     döviz "Orta-Yüksek") — ölçüm bizim sıralamamızı destekliyor
#     (altın %24 > döviz ~%1), bu çelişki analiste bildirildi.
#
# Bu tablo TİPİK varlık içindir ve varlık düzeyinde ezilebilir: bkz.
# `providers/universe.AssetSpec.risk_level` ve
# `services/advice_eligibility.asset_risk_level`. Bir varlık sınıfının
# altında da (IOO para piyasası fonu: sınıfı BOND=2, kendisi 1) üstünde de
# (AAPL: sınıfı STOCK=5, kendisi 6) olabilir.
ASSET_CLASS_ADVICE_RISK_LEVEL: dict[AssetClass, int] = {
    AssetClass.CASH: 1,
    AssetClass.BOND: 2,
    AssetClass.CURRENCY: 3,
    AssetClass.PRECIOUS_METAL: 4,
    AssetClass.STOCK: 5,
}

# Anket puanının alabileceği aralık (dahil). Tabloyla karşılaştırma bu
# aralıkta anlamlıdır; dışında bir değer gelirse çağıran taraf hata verir.
RISK_SURVEY_SCORE_MIN = 1
RISK_SURVEY_SCORE_MAX = 7

if set(ASSET_CLASS_ADVICE_RISK_LEVEL) != set(AssetClass):
    # Yeni bir varlık sınıfı eklenip bu tabloya yazılmazsa, uygunluk kontrolü
    # o sınıfı sessizce "serbest" sayardı — yani profili tutmayan bir varlık
    # tavsiye edilebilir hale gelirdi. Açılışta patlaması, sessizce yanlış
    # davranmasından iyidir.
    raise ValueError(
        "ASSET_CLASS_ADVICE_RISK_LEVEL her AssetClass icin bir seviye tanimlamali: "
        f"eksik={set(AssetClass) - set(ASSET_CLASS_ADVICE_RISK_LEVEL)}"
    )

# Risk profiline göre hedef varlık sınıfı dağılımı (yüzde, toplamı 100
# olmalı). Yeniden dengeleme önerisi (risk_service._rebalance_actions) bunu
# mevcut dağılımla kıyaslar.
RISK_PROFILE_TARGET_ALLOCATION: dict[RiskProfile, dict[AssetClass, Decimal]] = {
    RiskProfile.CONSERVATIVE: {
        AssetClass.STOCK: Decimal(15),
        AssetClass.BOND: Decimal(40),
        AssetClass.PRECIOUS_METAL: Decimal(15),
        AssetClass.CURRENCY: Decimal(10),
        AssetClass.CASH: Decimal(20),
    },
    RiskProfile.BALANCED: {
        AssetClass.STOCK: Decimal(35),
        AssetClass.BOND: Decimal(25),
        AssetClass.PRECIOUS_METAL: Decimal(15),
        AssetClass.CURRENCY: Decimal(15),
        AssetClass.CASH: Decimal(10),
    },
    RiskProfile.AGGRESSIVE: {
        AssetClass.STOCK: Decimal(55),
        AssetClass.BOND: Decimal(10),
        AssetClass.PRECIOUS_METAL: Decimal(15),
        AssetClass.CURRENCY: Decimal(15),
        AssetClass.CASH: Decimal(5),
    },
}

for _profile, _targets in RISK_PROFILE_TARGET_ALLOCATION.items():
    if sum(_targets.values()) != Decimal(100):
        raise ValueError(
            f"RISK_PROFILE_TARGET_ALLOCATION[{_profile.value}] toplami 100 olmali, "
            f"su an {sum(_targets.values())}."
        )
# ANALİST NOTU: RISK_PROFILE_TARGET_ALLOCATION yalnızca eski basit "hedef % -
# mevcut %" yeniden dengeleme yolunun kalıntısı; yeni senaryo motoru
# (Aksiyon A/B/C) devreye girince bu tablo ve onu kullanan
# risk_service._rebalance_actions kaldırılacak. Bilerek Büyüme profiline
# genişletilmedi.


# --- Senaryo üretimi kısıtları (profil bağımlı) ---
# Analist notu: tüm değerler Risk/Strateji Ajanı belgesindeki tablolarla
# birebir aynıdır (Korumacı/Dengeli/Büyüme/Agresif).
#
# ÜRÜN SAHİBİ NOTU (2026-08): Bu tablolar (özellikle RISK_MAX_ASSET_WEIGHT ve
# RISK_MAX_CATEGORY_WEIGHT) şu an yalnızca risk_service.py'nin OKUMA tarafında
# (kök neden teşhisi, is_within_profile) kullanılıyor. PO kararına göre asıl
# hedef, kullanıcının profiliyle uyuşmayan bir varlığı zaten SATIN ALAMAMASI
# — profil önce (anket ile) belirlenir, portföy ona göre kurulur, tersi değil.
# Bunu şu an burada uygulamıyoruz çünkü projede henüz canlı bir işlem/alım
# (BUY) endpoint'i yok (yalnızca okuma amaçlı MCP tool'ları var). O endpoint
# eklendiğinde, işlem kaydı oluşturmadan önce bu tablolara karşı bir doğrulama
# eklenmesi gerekir (bkz. app/services/ledger_service.record_transaction) —
# bilinen, kasıtlı bir eksik, şimdilik yalnızca not olarak duruyor.

# Tek varlığın portföy içindeki üst sınırı (oran, 0.20 = %20).
RISK_MAX_ASSET_WEIGHT: dict[RiskProfile, Decimal] = {
    RiskProfile.CONSERVATIVE: Decimal("0.20"),
    RiskProfile.BALANCED: Decimal("0.35"),
    RiskProfile.GROWTH: Decimal("0.40"),
    RiskProfile.AGGRESSIVE: Decimal("0.50"),
}

# Kategori üst sınırları (oran). Tahvil/Nakit'te Korumacı ve Dengeli'de
# %100 olabilmesi kasıtlı — bu profillerde savunma kategorilerinin üst
# sınırı yok, alt sınırı (RISK_DEFENSE_FLOOR) var.
RISK_MAX_CATEGORY_WEIGHT: dict[RiskProfile, dict[AssetClass, Decimal]] = {
    RiskProfile.CONSERVATIVE: {
        AssetClass.STOCK: Decimal("0.25"),
        AssetClass.PRECIOUS_METAL: Decimal("0.25"),
        AssetClass.CURRENCY: Decimal("0.30"),
        AssetClass.BOND: Decimal("1.00"),
        AssetClass.CASH: Decimal("1.00"),
    },
    RiskProfile.BALANCED: {
        AssetClass.STOCK: Decimal("0.50"),
        AssetClass.PRECIOUS_METAL: Decimal("0.30"),
        AssetClass.CURRENCY: Decimal("0.30"),
        AssetClass.BOND: Decimal("0.80"),
        AssetClass.CASH: Decimal("0.40"),
    },
    RiskProfile.GROWTH: {
        AssetClass.STOCK: Decimal("0.70"),
        AssetClass.PRECIOUS_METAL: Decimal("0.30"),
        AssetClass.CURRENCY: Decimal("0.35"),
        AssetClass.BOND: Decimal("0.60"),
        AssetClass.CASH: Decimal("0.30"),
    },
    RiskProfile.AGGRESSIVE: {
        AssetClass.STOCK: Decimal("0.85"),
        AssetClass.PRECIOUS_METAL: Decimal("0.35"),
        AssetClass.CURRENCY: Decimal("0.40"),
        AssetClass.BOND: Decimal("0.50"),
        AssetClass.CASH: Decimal("0.25"),
    },
}

for _profile in RiskProfile:
    if _profile not in RISK_MAX_CATEGORY_WEIGHT or set(RISK_MAX_CATEGORY_WEIGHT[_profile]) != set(
        AssetClass
    ):
        raise ValueError(f"RISK_MAX_CATEGORY_WEIGHT[{_profile.value}] tum kategorileri icermeli.")

# Savunma tabanı: senaryo sonunda Tahvil + Nakit toplam ağırlığı bu oranın
# altına inemez (oran, 0.40 = %40).
RISK_DEFENSE_FLOOR: dict[RiskProfile, Decimal] = {
    RiskProfile.CONSERVATIVE: Decimal("0.40"),
    RiskProfile.BALANCED: Decimal("0.20"),
    RiskProfile.GROWTH: Decimal("0.10"),
    RiskProfile.AGGRESSIVE: Decimal("0.00"),
}

# Aksiyon B'nin durma koşulu: hedef yıllık volatilite bandı (alt, üst), oran.
# Mevcut volatilite bandın üst sınırını <=5 puan aşıyorsa hedef=üst sınır,
# >5 puan aşıyorsa hedef=bandın orta noktası (risk_service.py'de uygulanır).
RISK_TARGET_VOLATILITY_BAND: dict[RiskProfile, tuple[Decimal, Decimal]] = {
    RiskProfile.CONSERVATIVE: (Decimal("0.00"), Decimal("0.10")),
    RiskProfile.BALANCED: (Decimal("0.10"), Decimal("0.20")),
    RiskProfile.GROWTH: (Decimal("0.20"), Decimal("0.30")),
    RiskProfile.AGGRESSIVE: (Decimal("0.30"), Decimal("0.40")),
}

# AK-4: alıcı kategori seçiminde korelasyon farkı eşiğin altındaysa (bkz.
# Settings.risk_scenario_correlation_tie_threshold) bu sıra belirleyicidir.
RISK_RECEIVER_PREFERENCE_ORDER: dict[RiskProfile, list[AssetClass]] = {
    RiskProfile.CONSERVATIVE: [
        AssetClass.BOND,
        AssetClass.CASH,
        AssetClass.PRECIOUS_METAL,
        AssetClass.CURRENCY,
        AssetClass.STOCK,
    ],
    RiskProfile.BALANCED: [
        AssetClass.BOND,
        AssetClass.PRECIOUS_METAL,
        AssetClass.CURRENCY,
        AssetClass.CASH,
        AssetClass.STOCK,
    ],
    RiskProfile.GROWTH: [
        AssetClass.PRECIOUS_METAL,
        AssetClass.CURRENCY,
        AssetClass.BOND,
        AssetClass.STOCK,
        AssetClass.CASH,
    ],
    RiskProfile.AGGRESSIVE: [
        AssetClass.PRECIOUS_METAL,
        AssetClass.CURRENCY,
        AssetClass.STOCK,
        AssetClass.BOND,
        AssetClass.CASH,
    ],
}

for _profile in RiskProfile:
    if _profile not in RISK_RECEIVER_PREFERENCE_ORDER or set(
        RISK_RECEIVER_PREFERENCE_ORDER[_profile]
    ) != set(AssetClass):
        raise ValueError(
            f"RISK_RECEIVER_PREFERENCE_ORDER[{_profile.value}] tum kategorileri icermeli."
        )


class AssetSubType(str, Enum):
    """assets.sub_type için bilinen değerler. DB kolonu String'dir (yeni
    enstrüman tipi migration istemesin); doğrulama seed anında Python
    tarafında yapılır. Risk motoru buna göre dallanmaz — sunum/filtreleme
    metadata'sıdır.

    Fon alt türleri varlık SINIFINI belirler (universe._FUND_ASSET_CLASS):
    fonun ekonomik riski neyse sınıfı odur. Doğrudan tahvil değerleri
    (GOVERNMENT_BOND, CORPORATE_BOND, EUROBOND) şu an evrende kullanılmıyor —
    gerçek ISIN'li bir tahvil eklenirse yerleri hazır."""

    EQUITY_FUND = "equity_fund"
    MONEY_MARKET_FUND = "money_market_fund"
    GOLD_FUND = "gold_fund"
    BOND_FUND = "bond_fund"
    CORPORATE_BOND_FUND = "corporate_bond_fund"
    EUROBOND_FUND = "eurobond_fund"
    GOVERNMENT_BOND = "government_bond"
    CORPORATE_BOND = "corporate_bond"
    EUROBOND = "eurobond"
    TIME_DEPOSIT = "time_deposit"
    DEMAND_DEPOSIT = "demand_deposit"
    GOLD_COIN = "gold_coin"


class IngestStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"

    # --- PostgreSQL ---
    database_url: str = Field(
        default="postgresql+psycopg://finans:finans@localhost:5432/finans_danismani"
    )

    # --- Chroma ---
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "financial_documents"

    # --- LLM sağlayıcı ---
    llm_provider: LLMProvider = LLMProvider.OLLAMA

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    # OpenAI uyumlu her ağ geçidi (gateway/proxy) buradan yönlendirilir —
    # resmi API, kurum içi bir vekil ya da apimaster.ai gibi bir kanal
    # toplayıcı. Kod değişmiyor, yalnızca .env değişiyor.
    openai_base_url: str = "https://api.openai.com/v1"
    # Bazı yeni nesil modeller `temperature` parametresini reddediyor
    # (yalnızca varsayılan değeri kabul ediyorlar) — ölçümle doğrulandı:
    # gerçek sağlayıcıya karşı canlı çağrıda "gpt-5.6-luna" modeli HEM 0.1
    # HEM 0.0 için "Only the default (1) value is supported" diyerek 400
    # döndü. Varsayılan bu yüzden None: temperature isteğe hiç eklenmez
    # (bkz. OpenAIClient._payload — `if self._temperature is not None`).
    # Modeliniz temperature'ı destekliyorsa .env'de OPENAI_TEMPERATURE'ı
    # açıkça bir sayıya ayarlayabilirsiniz (ör. 0.0, deterministik niyet
    # sınıflandırması için tercih edilir).
    #
    # DİKKAT: .env'de bu satırı BOŞ DEĞERLE bırakmak (`OPENAI_TEMPERATURE=`)
    # pydantic-settings'te float parse hatasıyla TÜM UYGULAMAYI ÇÖKERTİR —
    # `env_parse_none_str` yapılandırılmadığı için boş dize None'a
    # dönüşmüyor. "Boş bırakmak" istenen davranış için satırın .env'den
    # TAMAMEN SİLİNMESİ gerekir, boş değerle bırakılması değil.
    openai_temperature: float | None = None

    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str = "2024-08-01-preview"

    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.1"

    # --- MCP Server ---
    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8100
    # Ajanların (bağlanan taraf olarak) MCP sunucusuna ulaştığı adres; yukarıdaki
    # host/port sunucunun *dinlediği* adrestir, bu ise docker ağı üzerinden
    # *erişilen* adrestir (compose'da servis adı: mcp_server).
    mcp_server_url: str = "http://mcp_server:8100/mcp"

    # Tool zaman aşımları (saniye). Performans hedefi değil, asılı kalan çağrıya
    # karşı emniyet supabıdır: süre dolunca ajan çökmek yerine TIMEOUT zarfı alır
    # (bkz. mcp_server/tools/_base.py, docs/MCP-TOOLS.md). DB okuması milisaniye
    # mertebesindedir; RAG ilk çağrıda embedding modelini ve indeksi yükler.
    mcp_tool_timeout_default: float = 10.0
    mcp_tool_timeout_rag: float = 60.0
    # KAP canlı bildirim sorgusu: RAG'ın aksine embedding modeli yüklemiyor
    # ama dış siteye HTTP isteği + sayfa ayrıştırma yapıyor (pykap). 60 sn'lik
    # RAG payına gerek yok, 10 sn'lik varsayılan ise KAP yavaşladığında dar
    # gelebilir — ikisi arasında ayrı bir değer.
    mcp_tool_timeout_live_news: float = 20.0

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # --- Kimlik doğrulama ---
    # Koda gömülü bir varsayılanı YOK, bilerek (CLAUDE.md: gizli bilgi yalnızca
    # .env'de). Boş bırakılırsa uygulama hiç başlamaz — sessizce sabit bir
    # anahtarla çalışıp herkesin token üretebilmesindense açıkça patlaması
    # daha iyi. Alan `str = ""` olarak tanımlı ve kontrolü aşağıdaki
    # doğrulayıcı yapıyor; Pydantic'in ham "Field required" hatası yerine ne
    # yapılması gerektiğini söyleyen bir mesaj verebilmek için.
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    # Bir demo günü. Yenileme (refresh) token'ı kapsam dışı: süre dolunca
    # kullanıcı yeniden giriş yapar.
    jwt_expire_minutes: int = 480

    # Geçiş bayrağı. VARSAYILANI True — yani unutulursa auth AÇIK kalır,
    # kapalı değil. Token göndermeyen eski `frontend/` ile çalışmayı sürdüren
    # geliştirici bunu kendi .env'inde False yapar. frontend-v2'nin sohbeti
    # uçtan uca çalışır hale geldiğinde (Faz 3) bu bayrak silinecek.
    auth_enforce: bool = True

    # Sentetik demo kullanıcılarının ortak şifresi. GİZLİ DEĞİL ve olmamalı:
    # `make demo-users` çıktısında kullanıcıların T.C. kimlik numaralarıyla
    # birlikte zaten basılıyor — sentetik veriye erişim anahtarıdır, gerçek
    # bir sır değil. Giriş ekranı 6 haneli sayısal şifre bekliyor.
    # Doğrulama yolu buna rağmen tamamen gerçek (bcrypt); yalnızca seed
    # verisi tekdüze, çünkü 50 ayrı şifreyi ezberlemenin demoya katkısı yok.
    demo_user_password: str = "460213"

    # --- Şifre yenileme (DEMO) ---
    #
    # AKIŞ TEMSİLİDİR: e-posta GÖNDERİLMEZ, kod sunucuda üretilmez ve
    # saklanmaz — aşağıdaki sabit kod kabul edilir. Şifre ise GERÇEKTEN
    # güncellenir.
    #
    # GÜVENLİK SINIRI, açıkça: bu uç kimlik doğrulaması istemez. T.C. kimlik
    # numarasını ve bu kodu bilen biri o hesabın şifresini değiştirebilir —
    # yani kimlik doğrulamasının etrafından dolaşan bir kapıdır. Sentetik
    # demo verisiyle çalışan, süreli bir gösterim için kabul edildi.
    # GERÇEK BİR DAĞITIMDA `DEMO_PASSWORD_RESET_ENABLED=false` yapılmalı;
    # yerine e-posta doğrulaması, sunucuda üretilen tek kullanımlık kod,
    # süre ve deneme sınırı gerekir.
    demo_password_reset_enabled: bool = True
    demo_reset_code: str = "123456"
    # Arayüzdeki geri sayımın kaynağı; sunucu şu an süreyi denetlemiyor
    # (kod saklanmadığı için denetlenecek bir şey yok).
    password_reset_code_ttl_seconds: int = 180

    # --- Chat ---
    # Orchestrator'a bağlam olarak geçilen son mesaj sayısı.
    chat_context_message_limit: int = 10

    # --- RAG ---
    rag_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # Kaç doküman parçası getirilecek.
    rag_top_k: int = 3
    # Chroma cosine mesafesi (0 = birebir, 2 = alakasız). Bu eşiğin üzerindeki
    # sonuçlar elenir — ama asıl "alakasız" kararını (rag/retriever.py'deki)
    # kelime örtüşmesi eşiği veriyor, bu değer yalnızca gevşek bir emniyet
    # supabı.
    #
    # 6 gerçek dokümanlık (THYAO/ASELS/TCMB/BIST/analist raporu) külliyatla
    # ölçüldü: paraphrase-multilingual-MiniLM-L12-v2 mesafesi alakalı ve
    # alakasız sorguları GÜVENİLİR AYIRMIYOR — "Bitcoin fiyatı ne kadar"
    # (0.58) gerçekten alakalı bir sorgudan ("ASELSAN FAVÖK marjı", 0.73-0.89)
    # daha düşük (daha "yakın") mesafe alabiliyor. 0.85 gibi sıkı bir eşik
    # gerçek eşleşmeleri eliyordu (ör. 0.886 mesafeli doğru FAVÖK verisi).
    # Bu yüzden eşik gevşetildi; alakasızlığı asıl kelime örtüşmesi eşiği
    # (_MIN_KEYWORD_OVERLAP_RATIO, rag/retriever.py) engelliyor.
    rag_distance_threshold: float = 0.95

    # --- Portföy bazlı doküman getirme (get_portfolio_news) ---
    # İŞ ANALİSTİ NOTU (2026-08 güncellemesi): "portföydeki varlıklarla ilgili
    # güncel haber, market bilgileri ve analist yorumlarını çekip LLM'e
    # verirsiniz" ve "her bulgu en az bir kaynak dokümana referans verir".
    # Aşağıdakiler o getirmenin ayar noktalarıdır.

    # Varlık başına kaç doküman parçası döneceği. Küçük tutuluyor: bir
    # portföyde 15 varlık olabilir, her biri için 5 parça LLM bağlamını
    # gereksiz şişirir ve asıl bulguyu boğar.
    portfolio_news_per_asset: int = 2
    # Portföy dokümanı getirmede dikkate alınan doküman türleri. `makro`
    # kasıtlı olarak DIŞARIDA: makro dokümanların `sirket` alanı boştur,
    # belirli bir varlığa bağlanamaz; strateji bölümünün "yalnızca portföyde
    # fiilen bulunan varlıklar üzerinden kurulur" kuralını ihlal ederdi.
    portfolio_news_types: list[str] = ["bilanco", "analiz", "haber", "duyuru"]
    # Güven düzeyi eşiği: dokümanla desteklenen varlıkların portföy ağırlığı
    # bu yüzdenin altındaysa çıktı "düşük güven" olarak işaretlenir.
    # KABUL KRİTERİ KARŞILIĞI: "İlgili doküman bulunamadığında güven düzeyi
    # düşük olarak döner ve durum kullanıcıya açıkça bildirilir."
    # DİKKAT: 50 değeri bir POLİTİKA TERCİHİDİR, ölçülmüş bir eşik değildir —
    # iş analistiyle teyit edilmeli.
    portfolio_news_low_confidence_weight_percent: float = 50.0

    # --- Veri katmanı ---
    # Sentetik üretimin "bugün"ü — SABİT DEĞİL, override.
    #
    # Boş bırakılırsa (varsayılan) seed ankrajı gerçek verinin bittiği güne
    # bağlar; böylece "son işlem" ile "son fiyat" arasında açık kalmaz.
    # Sabit bir tarih yazılırsa her şeyi ezer: testler ve yeniden üretilebilir
    # koşular bunu kullanır.
    #
    # Çözüm mantığı ve neden sabit tarihten vazgeçildiği: data/anchor.py
    anchor_date: date | None = None

    @field_validator("anchor_date", mode="before")
    @classmethod
    def _bos_ankraj_none_sayilir(cls, deger: object) -> object:
        """`ANCHOR_DATE=` (boş) -> `None`.

        `.env.example` "boş bırakın" diyor ama boş bir ortam değişkeni
        pydantic'e `None` değil BOŞ STRING olarak geliyor ve tarih olarak
        ayrıştırılamayıp uygulamayı hiç başlatmıyordu. Belge bir kullanımı
        tarif ediyorsa kod onu kabul etmek zorunda; kullanıcıyı satırı yorum
        satırı yapmaya zorlamak, üstelik hata mesajı bunu hiç söylemezken,
        gereksiz bir tuzak.

        Yalnızca boşluk içeren değer de aynı sayılır: `.env` düzenlerken
        sonda kalan boşluk yaygın.
        """
        if isinstance(deger, str) and not deger.strip():
            return None
        return deger

    # Güncel fiyat bu kadar takvim gününden eskiyse "eski" işaretlenir.
    # 4 gün: piyasa Cuma kapanır, Pazartesi açılır — Pazar günü sorulan bir
    # fiyat 2 günlüktür ve normaldir. Araya resmî tatil girdiğinde 3-4 güne
    # çıkabilir. Bunun üstü, günlük toplama işinin durduğu anlamına gelir ve
    # kullanıcıya söylenmelidir.
    current_price_stale_days: int = 4

    # TCMB EVDS tarihsel seriler için ücretsiz API anahtarı (evds2.tcmb.gov.tr).
    # Anahtar yoksa tarihsel kur yfinance'ten çekilir (yedek kaynak).
    evds_api_key: str | None = None

    # --- Sabitler (sihirli sayı yerine config) ---
    supported_asset_classes: list[AssetClass] = list(AssetClass)

    # --- Risk/Strateji Ajanı ---
    # ANALİST NOTU: risk metodolojisinin ayarlanabilir tek adresi burasıdır —
    # app/services/risk_service.py'de hiçbir eşik/ağırlık sabit sayı olarak
    # yazılmaz. Değer değiştirmek için servis koduna dokunmak gerekmez.

    # Volatilite/korelasyon/kovaryans hesabı için gereken en az ortak fiyat
    # günü sayısı. Altında kalınırsa AK 2.7 gereği hesaplanamaz, uyarıyla
    # birlikte kalan ölçütlerle skorlanır (uydurulmaz).
    risk_min_price_points: int = 30
    # Günlük volatiliteyi/getiriyi yıllıklandırmak için işlem günü sayısı.
    risk_trading_days_per_year: int = 252
    # VaR (Value at Risk) güven seviyesi (AK 2.4). %95 sektör standardıdır.
    risk_var_confidence: float = 0.95
    # VaR ufku (gün). 1 = ertesi gün için parametrik VaR.
    risk_var_horizon_days: int = 1

    # Sharpe oranı (AK 2.5) için risksiz getiri oranı. Önce TCMB EVDS'ten canlı
    # çekilir (risk_free_rate_evds_series doluysa); seri boş/tanımsız, anahtar
    # eksik ya da istek başarısızsa bu sabit yedeğe düşülür (aynı öncelik
    # mantığı: gerçek veri > yedek, hiçbir zaman uydurma). Yedek değer TCMB'nin
    # Temmuz 2026 itibarıyla göstergesel gecelik faiz oranına (%37) dayanır,
    # periyodik olarak elle güncellenmelidir.
    risk_free_rate_fallback_annual: float = 0.37
    # Doğru EVDS seri kodu doğrulanana kadar boş bırakılır (bkz. proje notları);
    # boşken doğrudan yedek orana düşülür.
    risk_free_rate_evds_series: str | None = None

    # Hedeften bu kadar puandan az sapan varlık sınıfı "dengede" sayılır.
    # ANALİST NOTU: yalnızca eski RISK_PROFILE_TARGET_ALLOCATION yolu
    # kaldırılana kadar kullanılır (bkz. o tablonun yanındaki not).
    risk_rebalance_tolerance_percent: float = 5.0

    # --- Kök neden teşhisi eşikleri ("risk neden yüksek çıktı") ---
    # Bunlar risk SEVİYESİNİ (RiskLevel) etkilemez, yalnızca yüksek risk
    # çıktığında sebebi açıklamak için kullanılır.
    #
    # Neden 1 — Yoğunlaşma: aşağıdakilerden en az biri doğruysa tetiklenir.
    risk_cause_max_asset_weight: float = 0.35
    risk_cause_max_category_weight: float = 0.60
    risk_cause_hhi_threshold: float = 0.25
    #
    # Neden 2 — Yüksek volatiliteli varlık: aşağıdakilerden en az biri.
    risk_cause_high_vol_asset_annual_vol: float = 0.35
    risk_cause_high_vol_asset_weight: float = 0.30
    risk_cause_risk_contribution_threshold: float = 0.50
    risk_cause_risk_contribution_excess: float = 0.15
    #
    # Neden 3 — Korelasyon: aşağıdakilerden en az biri.
    risk_cause_pairwise_correlation: float = 0.60
    risk_cause_pairwise_weight_sum: float = 0.40
    risk_cause_dr_threshold: float = 1.10
    risk_cause_hhi_low_threshold: float = 0.25

    # --- Senaryo üretim motoru ---
    # ÜRÜN SAHİBİ KARARI (2026-08): yeniden dengeleme senaryo önerisi ürün
    # kapsamından çıkarıldı — "risk kişinin kendi yatırım eylemidir, profil
    # uyuşmuyorsa sistem yalnızca uyarır, ne yapılacağını önermez" (bkz. PO
    # notları). Motor kod olarak DURUYOR (ileride fikir değişirse tek satırla
    # geri açılabilsin diye) ama bu bayrak False olduğu sürece
    # get_risk_assessment hiçbir zaman senaryo üretmez — `include_scenarios`
    # çağıran tarafından True verilse bile. Aksiyon A/B/C mantığına
    # dokunulmadı, yalnızca bu tek nokta ekiplendi.
    risk_scenarios_enabled: bool = False

    # STEP: her transferin büyüklüğü (puan).
    risk_scenario_step_percent: float = 5.0
    # Yeni açılan bir kategoriye ilk transferde verilecek en az pay (puan).
    risk_scenario_min_new_category_weight_percent: float = 5.0
    # Sonsuz döngü koruması: aksiyon başına en fazla adım sayısı.
    risk_scenario_max_iterations: int = 20
    # Senaryo başına toplam değişim (turnover) tavanı (puan). ANALİST NOTU:
    # kaynak belgede hem %25 (KK-2) hem %30 (skor formülü) yazıyor,
    # netleşene kadar %30 kullanılıyor (Yağız onayıyla).
    risk_scenario_max_turnover_percent: float = 30.0
    # Eleme kuralı: bu puandan küçük turnover anlamsız sayılır.
    risk_scenario_min_turnover_percent: float = 2.0
    # Eleme kuralı: "yeterli" risk azalması için göreli azalma eşiği (oran).
    risk_scenario_min_relative_risk_reduction: float = 0.15
    # Sıralama skoru ağırlıkları (toplamı 1.0 olmalı).
    risk_scenario_score_risk_weight: float = 0.7
    risk_scenario_score_turnover_weight: float = 0.3
    # Kullanıcıya gösterilecek en iyi senaryo sayısı.
    risk_scenario_top_n: int = 3
    # Aksiyon C'nin durma koşulu: çeşitlendirme oranı (DR) hedefi.
    risk_scenario_dr_target: float = 1.15
    # AK-4: iki adayın korelasyon farkı bu değerden küçükse profil tercih
    # sırası (RISK_RECEIVER_PREFERENCE_ORDER) belirleyici olur.
    risk_scenario_correlation_tie_threshold: float = 0.10
    # Senaryo etiketleme eşikleri (turnover, puan).
    risk_scenario_label_small_max_turnover: float = 10.0
    risk_scenario_label_balanced_max_turnover: float = 18.0

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _validate_jwt_secret_key(self) -> "Settings":
        """Anahtar yoksa uygulamayı açılışta durdurur.

        Alan `str = ""` olarak tanımlı ve kontrol burada yapılıyor; Pydantic'in
        ham "Field required" hatası yerine ne yapılması gerektiğini söyleyen
        bir mesaj verebilmek için (bkz. jwt_secret_key tanımındaki not).
        """
        if not self.jwt_secret_key.strip():
            raise ValueError(
                "JWT_SECRET_KEY tanımlı değil. .env dosyanıza ekleyin: "
                "JWT_SECRET_KEY=<uzun-rastgele-bir-değer>  "
                '(üretmek için: python -c "import secrets; '
                'print(secrets.token_urlsafe(48))")'
            )
        return self

    @model_validator(mode="after")
    def _validate_risk_scenario_score_weights(self) -> "Settings":
        total = self.risk_scenario_score_risk_weight + self.risk_scenario_score_turnover_weight
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                "RISK_SCENARIO_SCORE_* ağırlıklarının toplamı 1.0 olmalı, "
                f"şu an {total}. (.env dosyanızı kontrol edin.)"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Türkiye 2016'dan beri kalıcı olarak UTC+3; yaz saati uygulaması yok.
# Sabit fark kullanmak `zoneinfo`'ya (ve Windows'ta `tzdata` paketine)
# bağımlılığı ortadan kaldırıyor ve bu ülke için sonucu birebir aynı.
TURKEY_UTC_OFFSET = timezone(timedelta(hours=3))


def turkey_today() -> date:
    """Türkiye saatiyle bugünün tarihi.

    Sunucu UTC çalışıyor. `date.today()` kullanılsaydı gece yarısı ile 03:00
    arasında ekranda ve sohbette DÜNÜN tarihi görünürdü — Türkçe bir finans
    ürününde kullanıcının takvimi esas alınmalı.

    `settings.anchor_date` ile KARIŞTIRILMAMALI: o, sentetik verinin donmuş
    "bugün"üdür ve yalnızca üretim/seed tarafını ilgilendirir. Kullanıcıya
    bugünün ne olduğunu söyleyen tek doğru kaynak burasıdır.
    """
    return datetime.now(TURKEY_UTC_OFFSET).date()
