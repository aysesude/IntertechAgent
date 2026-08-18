"""Uygulama genelindeki tüm yapılandırma buradan okunur. Kodun başka hiçbir
yerinde sabit bağlantı adresi, anahtar veya model adı bulunmamalıdır."""

from datetime import date
from enum import Enum
from functools import lru_cache

from pydantic import Field
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


class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


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


class AssetSubType(str, Enum):
    """assets.sub_type için bilinen değerler. DB kolonu String'dir (yeni
    enstrüman tipi migration istemesin); doğrulama seed anında Python
    tarafında yapılır. Risk motoru buna göre dallanmaz — sunum/filtreleme
    metadata'sıdır."""

    EQUITY_FUND = "equity_fund"
    MONEY_MARKET_FUND = "money_market_fund"
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
    openai_model: str = "gpt-4o-mini"

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

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # --- Chat ---
    # Orchestrator'a bağlam olarak geçilen son mesaj sayısı.
    chat_context_message_limit: int = 10

    # --- RAG ---
    rag_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # Kaç doküman parçası getirilecek.
    rag_top_k: int = 3
    # Chroma cosine mesafesi (0 = birebir, 2 = alakasız). Bu eşiğin üzerindeki
    # sonuçlar "alakasız" sayılıp elenir — RAG'ın LLM'siz "veri var/yok" kararını
    # bu eşik verir.
    #
    # paraphrase-multilingual-MiniLM-L12-v2 için tek örnek dokümanla ölçülen
    # gerçek değerler: alakalı sorgu ~0.82-0.84, alakasız sorgu ~0.86-0.90
    # (bkz. data/documents/ornek-dokuman.md). 0.85 bu ikisini ayırıyor ama tek
    # dokümanlık bir örnekleme — hedef 30-50 dokümanlık gerçek külliyat
    # yüklenince (docs/AGENTS.md) bu değeri gerçek sorgularla yeniden kalibre
    # edin.
    rag_distance_threshold: float = 0.85

    # --- Veri katmanı ---
    # Sentetik üretimin "bugün"ü. date.today() KULLANILMAZ: her seed geçmişi
    # kaydırırsa "o tarihten bugüne" izlenemez hale gelir (plan kararı 8.5).
    anchor_date: date = date(2026, 8, 1)
    # TCMB EVDS tarihsel seriler için ücretsiz API anahtarı (evds2.tcmb.gov.tr).
    # Anahtar yoksa tarihsel kur yfinance'ten çekilir (yedek kaynak).
    evds_api_key: str | None = None

    # --- Sabitler (sihirli sayı yerine config) ---
    supported_asset_classes: list[AssetClass] = list(AssetClass)

    # TODO: Risk/Strateji Ajanı uygulanırken risk eşikleri (ör. volatilite, yoğunlaşma
    # limitleri) buraya eklenecek. Tanımları kullanıcıyla netleştirilmeden eklenmedi.

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
