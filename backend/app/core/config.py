"""Uygulama genelindeki tüm yapılandırma buradan okunur. Kodun başka hiçbir
yerinde sabit bağlantı adresi, anahtar veya model adı bulunmamalıdır."""

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
    GOLD = "gold"
    CURRENCY = "currency"
    BOND = "bond"


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
    # Chroma'nın kalıcı dosyalarını tuttuğu dizin. Konteyner içindeki mutlak yol
    # verilmeli; göreli yol çalışma dizinine göre değişir ve MCP sunucusu ile API
    # farklı dizinlerden başlatıldığı için tutarsızlık üretir.
    rag_persist_directory: str = "/data/chroma_db"
    rag_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    rag_company_mappings_path: str = "/data/company_mappings.json"
    # Kaç doküman parçası getirilecek.
    rag_top_k: int = 3

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
