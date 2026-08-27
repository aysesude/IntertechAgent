"""LLM sağlayıcı teşhis betiği: generate() ve stream() gerçekten çalışıyor mu.

Boş sohbet cevabı aldığında bunu çalıştır. Ağ geçidinin akış (SSE) desteğini
ve yanıt biçimini gösterir. API anahtarını ASLA yazdırmaz.

Kullanım:
    docker compose exec -w / api python scripts/llm_smoke.py
"""

import asyncio

import httpx

from app.core.config import settings
from app.core.llm_client import get_llm_client

SORU = "Portföyün toplam değeri 1.653.329 TL. Bunu tek cümleyle özetle."


def _maskele(anahtar: str | None) -> str:
    if not anahtar:
        return "(BOŞ)"
    return f"{anahtar[:4]}...{anahtar[-4:]} ({len(anahtar)} karakter)"


async def main() -> None:
    print("=" * 70)
    print("AYARLAR")
    print("=" * 70)
    print(f"  LLM_PROVIDER      : {settings.llm_provider}")
    print(f"  OPENAI_MODEL      : {settings.openai_model}")
    print(f"  OPENAI_BASE_URL   : {settings.openai_base_url}")
    print(f"  OPENAI_TEMPERATURE: {settings.openai_temperature!r}")
    print(f"  OPENAI_API_KEY    : {_maskele(settings.openai_api_key)}")

    print()
    print("=" * 70)
    print("1) generate() - akissiz cagri")
    print("=" * 70)
    llm = get_llm_client()
    try:
        metin = await llm.generate(SORU, system="Kisa ve Turkce cevap ver.")
        print(f"  UZUNLUK: {len(metin)}")
        print(f"  ICERIK : {metin[:300]!r}")
        print("  SONUC  : " + ("OK" if metin.strip() else "!! BOS DONDU"))
    except Exception as exc:
        print(f"  !! HATA: {type(exc).__name__}: {exc}")

    print()
    print("=" * 70)
    print("2) stream() - akisli cagri")
    print("=" * 70)
    adet, birikim = 0, ""
    try:
        async for parca in llm.stream(SORU, system="Kisa ve Turkce cevap ver."):
            adet += 1
            birikim += parca
        print(f"  PARCA SAYISI: {adet}")
        print(f"  ICERIK      : {birikim[:300]!r}")
        print("  SONUC       : " + ("OK" if adet else "!! HIC PARCA GELMEDI"))
    except Exception as exc:
        print(f"  !! HATA: {type(exc).__name__}: {exc}")

    print()
    print("=" * 70)
    print("3) HAM yanit - ag gecidi gercekte ne donuyor")
    print("=" * 70)
    govde = {
        "model": settings.openai_model,
        "messages": [{"role": "user", "content": SORU}],
        "stream": True,
    }
    if settings.openai_temperature is not None:
        govde["temperature"] = settings.openai_temperature
    basliklar = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as istemci:
            async with istemci.stream(
                "POST",
                f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                json=govde,
                headers=basliklar,
            ) as yanit:
                print(f"  HTTP DURUM  : {yanit.status_code}")
                print(f"  CONTENT-TYPE: {yanit.headers.get('content-type')}")
                print("  ILK 8 SATIR :")
                sayac = 0
                async for satir in yanit.aiter_lines():
                    if not satir:
                        continue
                    sayac += 1
                    print(f"    [{sayac}] {satir[:200]}")
                    if sayac >= 8:
                        break
                if sayac == 0:
                    print("    (hic satir gelmedi)")
    except Exception as exc:
        print(f"  !! HATA: {type(exc).__name__}: {exc}")

    print()
    print("=" * 70)
    print("YORUM")
    print("=" * 70)
    print("  - CONTENT-TYPE 'text/event-stream' DEGILSE ve satirlar 'data:' ile")
    print("    BASLAMIYORSA: ag gecidi akis desteklemiyor. llm_client.stream()")
    print("    bu durumda sifir parca uretir -> bos sohbet cevabi.")
    print("  - HTTP DURUM 400 ise: muhtemelen 'temperature' reddedildi.")
    print("    .env'de OPENAI_TEMPERATURE= satirini bos birak.")


if __name__ == "__main__":
    asyncio.run(main())
