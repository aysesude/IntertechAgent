"""Niyet yönlendirme duman testi: LLM her soruyu doğru ajana veriyor mu.

`plan_smoke.py` ile aynı kalıp. Yönlendirme kararı LLM'de olduğu için birim
testiyle tutulamıyor; `tests/test_orchestrator_routing.py` yalnızca etiket
AYRIŞTIRMASINI sınıyor (sahte LLM ile), etiketin DOĞRU seçildiğini değil.

Buradaki her satır bir kural sınırını temsil ediyor. Özellikle KAVRAM/VERİ
ayrımı: aynı kelime (temettü) sorunun türüne göre üç ayrı ajana gidiyor.

Kullanım:
    docker compose exec -w / api python scripts/intent_smoke.py
"""

import asyncio

from agents.orchestrator import detect_intent

# (soru, beklenen intent) — beklenen değer "+" ile birleşik olabilir.
SORULAR = [
    # --- kavram / prosedür: hepsi web_research -------------------------
    ("temettü nedir", "web_research"),
    ("lot ne demek", "web_research"),
    ("halka arz nasıl olur", "web_research"),
    ("takas kaç gün sürer", "web_research"),
    ("borsa saat kaçta kapanır", "web_research"),
    ("F/K oranı nasıl hesaplanır", "web_research"),
    ("TFRS 16 nedir", "web_research"),
    ("konsolide finansal tablo ne demek", "web_research"),
    ("portföy kârı nasıl hesaplanır", "web_research"),
    ("fon alım satımı kaç günde gerçekleşir", "web_research"),
    # --- aynı kavram, ama BELİRLİ bir şirkete ait veri: market ---------
    ("Akbank'ın 2026 temettüsü ne kadar", "market"),
    ("THYAO'nun F/K oranı kaç", "market"),
    ("Aselsan haberleri neler", "market"),
    ("dolar kuru ne durumda", "market"),
    # --- aynı kavram, ama kullanıcının kendi verisi: portfolio ---------
    ("ne kadar temettü aldım", "portfolio"),
    ("portföyüm ne durumda", "portfolio"),
    # --- diğer ajanlar ve erken çıkışlar -------------------------------
    ("riskim nedir", "risk"),
    ("portföyüm ve riskim nasıl", "portfolio+risk"),
    ("10 lot THYAO al", "UNAUTHORIZED_ACTION"),
    ("2027'de dolar kaç TL olur", "FUTURE_PREDICTION"),
    ("hava nasıl", "OUT_OF_SCOPE"),
]


async def main() -> None:
    basarili = 0
    for soru, beklenen in SORULAR:
        sonuc = await detect_intent(
            {"user_id": "-", "session_id": "-", "message": soru, "history": []}
        )
        alinan = sonuc["intent"]
        # Etiket sırası modele göre değişebilir; küme olarak karşılaştır.
        ok = set(alinan.split("+")) == set(beklenen.split("+"))
        basarili += ok
        print(f"{'OK  ' if ok else 'HATA'}  {soru:42s} beklenen={beklenen:20s} alinan={alinan}")

    print(f"\n{basarili}/{len(SORULAR)} dogru")


if __name__ == "__main__":
    asyncio.run(main())
