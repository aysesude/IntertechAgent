"""Web Araştırma Ajanı: finansal kavram sorularını yanıtlar ("lot ne demek",
"temettü ne zaman verilir", "portföy kârı nasıl hesaplanır").

Adı "web araştırması" ama bugün **web'e çıkmıyor**; cevabı dil modelinin kendi
bilgisinden üretiyor. İsim, ileride eklenecek dış arama yolunu şimdiden
işaretliyor — bugün o kod yazılmadı, çünkü kullanılmayan yol ölü koddur.

NEDEN RAG DEĞİL. `data/documents/` altındaki belgelerin tamamı haber, bilanço,
analist raporu ve makro veri; tek bir kavram belgesi yok. "Lot ne demek"
sorusunda RAG ya hiçbir şey bulur ya da gevşek eşleşen bir bilanço parçası
döndürür — boşa gecikme, üstüne alakasız cevap riski.

NEDEN CANLI TOOL DEĞİL. Güncel fiyat/kur/haber zaten başka kapılardan geliyor
(`live_news_tools`, `price_tools`, Piyasa Ajanı). Bu ajan onların alanına
girmez; prompt'ta güncel değer vermesi açıkça yasaklandı, aksi halde iki kaynak
aynı ekranda çelişir.

Bu, sistemdeki TEK LLM-bilgisi ajanı. Diğerlerinde sayılar deterministik koddan
gelir ve LLM yalnızca anlatır; burada bilginin kendisi modelden geliyor.
Sınırlar bu yüzden prompt'ta sert: portföye atıf yok, güncel piyasa değeri yok,
kişiselleştirilmiş tavsiye yok, değişebilen olgularda resmî kaynak zorunlu.

EV KURALLARI. Prompt, bu uygulamanın kendi hesap tanımlarını (kâr tabanı, TWR,
t0 dondurma, nakit dahil ağırlık paydası) içeriyor. Sebebi: "portföy kârı nasıl
hesaplanır" sorusuna ders kitabı cevabı vermek, açıklamayla ekrandaki rakamın
birbirini yalanlaması demek. Tanımların kaynağı `docs/API.md`; oradaki kural
değişirse prompt da güncellenmeli.

Kapsam kararı burada verilmez. Hangi kavramın kapsam içi olduğu
`agents/scope.yaml` içindeki `kavram_kapsami` bölümünde tanımlı ve kontrolü
`scope_checker` yapar (NFR: kapsam kuralları koda gömülmez). Bu ajan yalnızca
`kisitli_konular` bayrağını okuyup prompt'a ek kural bloğu ekler.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from agents.base import AgentRequest, AgentResponse, BaseAgent
from agents.scope_checker import scope_config
from app.core.llm_client import get_llm_client

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "web_research_agent.md").read_text(
    encoding="utf-8"
)

_NO_RESTRICTION = ""


def _restricted_topics(query: str) -> list[str]:
    """Sorguda geçen kısıtlı konuları döndürür (bugün yalnızca vergi).

    Etiketler `scope.yaml` içindeki `kisitli_konular` bölümünden okunur; burada
    liste tutulmaz. Yapılandırma yoksa kısıt yok sayılır — eksik bir
    yapılandırma dosyası kullanıcının sorusunu cevapsız bırakmayı gerektirmez.

    Alt dize araması bilinçli: bu kontrol kullanıcıyı REDDETMİYOR, yalnızca
    prompt'a ek kural ekliyor. Türkçe çekim eklerini ("vergisi", "stopajdan")
    yakalamak istenen davranış ve yanlış pozitifin bedeli, gereksiz yere
    temkinli bir cümleden ibaret (bkz. scope_checker._matches_word ödünleşme
    notu).
    """
    kisitli = (scope_config or {}).get("kisitli_konular") or {}
    query_lower = query.lower()
    bulunan = []
    for konu, tanim in kisitli.items():
        if not isinstance(tanim, dict):
            continue  # "kural" gibi düz metin alanları atlanır
        etiketler = tanim.get("etiketler") or []
        if any(etiket.lower() in query_lower for etiket in etiketler):
            bulunan.append(konu)
    return bulunan


def _restriction_block(topics: list[str]) -> str:
    """Kısıtlı konular için prompt'a eklenecek ek kural metnini üretir.

    Kurallar `scope.yaml`'dan okunur, burada yeniden yazılmaz: mali müşavir
    yönlendirmesi, sayı yasağı ve koşul dili zorunluluğu tek kaynakta durur.
    """
    kisitli = (scope_config or {}).get("kisitli_konular") or {}
    bloklar = []
    for konu in topics:
        tanim = kisitli.get(konu) or {}
        kurallar = tanim.get("kurallar") or {}
        satirlar = [f"KISITLI KONU — {konu.upper()}:"]
        if kurallar.get("sayi_verilmez"):
            satirlar.append(
                "- Oran, tutar, istisna sınırı veya beyan eşiği gibi SAYI VERME. "
                "Bu değerler sık değişir ve kişinin durumuna göre farklılaşır."
            )
        if kurallar.get("kisisel_hesap_yapilmaz"):
            satirlar.append("- Kullanıcının durumuna özel hesap YAPMA.")
        if kurallar.get("kosul_dili_zorunlu"):
            satirlar.append(
                "- Koşul dili kullan: 'gerekebilir', 'durumunuza göre değişir', "
                "'genel kural olarak'. Kesinlik bildiren cümle kurma."
            )
        yonlendirme = (tanim.get("yonlendirme_metni") or "").strip()
        if yonlendirme and kurallar.get("uzman_yonlendirmesi") == "zorunlu":
            satirlar.append(f'- Yanıtını şu yönlendirmeyle bitir: "{yonlendirme}"')
        if len(satirlar) > 1:
            bloklar.append("\n".join(satirlar))
    return ("\n\n".join(bloklar) + "\n\n") if bloklar else _NO_RESTRICTION


class WebResearchAgent(BaseAgent):
    agent_name = "web_research_agent"

    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        topics = _restricted_topics(request.query)
        prompt = _PROMPT_TEMPLATE.format(
            kisitli_kurallar=_restriction_block(topics),
            query=request.query,
        )

        summary_text = ""
        try:
            async for chunk in get_llm_client().stream(prompt):
                summary_text += chunk
                if on_token is not None:
                    on_token(chunk)
        except Exception:
            logger.exception("[AJAN] web_research: LLM cagrisi basarisiz")
            return self.error_response("Açıklama şu anda üretilemedi.")

        # Boş metinle "başarılı" dönmek yasak: merge adımı success=True
        # gördüğünde metni anlatı için LLM'e veriyor; metin boşsa kullanıcı
        # bomboş bir baloncuk görüyor ve hiçbir yerde hata görünmüyor
        # (portfolio_agent'taki aynı koruma).
        if not summary_text.strip():
            logger.warning("[AJAN] web_research: LLM bos dondu, sorgu=%r", request.query[:80])
            return self.error_response("Açıklama şu anda üretilemedi.")

        logger.info("[AJAN] web_research: sorgu=%r kisitli_konular=%s", request.query[:60], topics)
        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text=summary_text,
            # Tool verisi yok; `data` yalnızca gözlemlenebilirlik için.
            data={"restricted_topics": topics},
        )
