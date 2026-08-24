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
    def __init__(self, base_url: str, model: str, temperature: float = 0.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        # Ollama'nın varsayılan sıcaklığı 0.8 — yaratıcı yazım için tasarlanmış.
        # Küçük modellerde bu değer dil kaymasına yol açıyor: cümlenin ortasında
        # İngilizce/Fransızca kelimelere geçiyor ("valueye", "which accounts for").
        # Finansal özet deterministik bir görev, düşük sıcaklık doğru tercih.
        #
        # 0.1 -> 0.0 (2026-08-24): 0.1 hâlâ örnekleme rastgeleliği taşıyordu —
        # ölçümle doğrulandı, `detect_intent`'in niyet sınıflandırma çağrısı
        # AYNI sorguda (Kardemir/Astor Enerji gibi) bazen doğru ajana
        # yönlendiriyor, bazen "anlayamadım"a düşüyordu; kural tabanlı
        # `check_scope()` ve RAG katmanı aynı sorgularda tam deterministikti
        # (3/3 tekrarda birebir aynı), yani rastgelelik yalnızca bu LLM
        # çağrısındaydı. Niyet sınıflandırması "doğru ajana git ya da hiç
        # cevap verme" gibi ikili/yüksek riskli bir karar — çeşitlilik
        # istenmeyen, tam deterministik olması gereken bir görev.
        self._options = {"temperature": temperature}

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": self._options,
        }
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self._base_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json()["response"]

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        payload = {"model": self._model, "prompt": prompt, "stream": True, "options": self._options}
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
    """OpenAI Chat Completions uyumlu her sağlayıcı için istemci.

    `openai` paketi yerine httpx kullanılıyor: OllamaClient zaten httpx ile
    yazılmış, tek bir HTTP kalıbı korunuyor ve yeni bir bağımlılık gelmiyor.
    Chat Completions sözleşmesi sağlayıcılar arasında sabit olduğu için
    `base_url` değiştirerek resmi API, kurum içi vekil veya üçüncü taraf bir
    ağ geçidi arasında geçiş yapmak yeterli.
    """

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        temperature: float | None = 0.0,
    ) -> None:
        if not api_key:
            # Anahtarsız istek sağlayıcıdan 401 dönerdi; hatayı burada, ne
            # yapılacağını söyleyen bir mesajla veriyoruz.
            raise ValueError(
                "LLM_PROVIDER=openai seçildi ama OPENAI_API_KEY boş. "
                "Anahtarı .env dosyasına ekleyin (koda gömmeyin)."
            )
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature

    def _payload(self, prompt: str, system: str | None, *, stream: bool) -> dict:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {"model": self._model, "messages": messages, "stream": stream}
        # None ise parametre HİÇ gönderilmez — bazı modeller varsayılan dışında
        # bir temperature gördüğünde isteği 400 ile reddediyor.
        if self._temperature is not None:
            payload["temperature"] = self._temperature
        return payload

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                json=self._payload(prompt, system, stream=False),
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"] or ""

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=self._payload(prompt, system, stream=True),
                headers=self._headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    # SSE: yalnızca "data:" satırları taşır; boş satırlar
                    # çerçeve ayırıcıdır, yorum satırları (":") atlanır.
                    if not line.startswith("data:"):
                        continue
                    veri = line[len("data:") :].strip()
                    if veri == "[DONE]":
                        break
                    chunk = json.loads(veri)
                    secenekler = chunk.get("choices") or []
                    if not secenekler:
                        # Bazı ağ geçitleri araya boş `choices` taşıyan kullanım
                        # (usage) çerçeveleri sıkıştırıyor; bunlar atlanmalı.
                        continue
                    parca = (secenekler[0].get("delta") or {}).get("content")
                    if parca:
                        yield parca


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
        return OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            temperature=settings.openai_temperature,
        )
    if settings.llm_provider == LLMProvider.AZURE:
        return AzureOpenAIClient(
            endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            deployment=settings.azure_openai_deployment,
        )
    raise ValueError(f"Bilinmeyen LLM_PROVIDER: {settings.llm_provider}")
