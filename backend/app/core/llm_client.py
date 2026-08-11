"""Tek LLM soyutlaması. Ajanlar hiçbir zaman doğrudan bir sağlayıcı SDK'sı
import etmez, sadece bu modüldeki `get_llm_client()` fonksiyonunu kullanır.
Sağlayıcı `LLM_PROVIDER` .env değişkeni ile seçilir (openai | azure | ollama).
"""

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx

from app.core.config import LLMProvider, settings


class LLMClient(ABC):
    """Tüm sağlayıcı implementasyonlarının uyması gereken arayüz."""

    @abstractmethod
    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        """Tek seferde tam yanıt döndürür."""

    @abstractmethod
    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        """Yanıtı parça parça (token/chunk) üretir."""


class OllamaClient(LLMClient):
    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        payload = {"model": self._model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self._base_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json()["response"]

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        payload = {"model": self._model, "prompt": prompt, "stream": True}
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/generate", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if chunk.get("response"):
                        yield chunk["response"]
                    if chunk.get("done"):
                        break


class OpenAIClient(LLMClient):
    """TODO: openai paketiyle gerçek implementasyon eklenecek."""

    def __init__(self, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        raise NotImplementedError("TODO: OpenAI sağlayıcısı henüz uygulanmadı")

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        raise NotImplementedError("TODO: OpenAI sağlayıcısı henüz uygulanmadı")
        yield ""  # pragma: no cover - async generator şeklini korumak için


class AzureOpenAIClient(LLMClient):
    """TODO: azure-openai paketiyle gerçek implementasyon eklenecek."""

    def __init__(self, endpoint: str | None, api_key: str | None, deployment: str | None) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._deployment = deployment

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        raise NotImplementedError("TODO: Azure OpenAI sağlayıcısı henüz uygulanmadı")

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        raise NotImplementedError("TODO: Azure OpenAI sağlayıcısı henüz uygulanmadı")
        yield ""  # pragma: no cover - async generator şeklini korumak için


def get_llm_client() -> LLMClient:
    if settings.llm_provider == LLMProvider.OLLAMA:
        return OllamaClient(base_url=settings.ollama_base_url, model=settings.ollama_model)
    if settings.llm_provider == LLMProvider.OPENAI:
        return OpenAIClient(api_key=settings.openai_api_key, model=settings.openai_model)
    if settings.llm_provider == LLMProvider.AZURE:
        return AzureOpenAIClient(
            endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            deployment=settings.azure_openai_deployment,
        )
    raise ValueError(f"Bilinmeyen LLM_PROVIDER: {settings.llm_provider}")
