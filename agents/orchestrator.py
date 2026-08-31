"""Orkestratör (Orchestrator) Modülü

Bu modül, LangGraph kullanarak uygulamanın kalbini oluşturur.
Gelen isteği alır, niyetine göre uygun ajan(lar)a PARALEL olarak (fan-out) dağıtır ve
ajanlardan gelen yanıtları tek bir LLM çağrısıyla harmanlayarak (merge) son kullanıcıya sunar.

Özellikler:
- Kural tabanlı kapsam kontrolü (Scope Guard) ile kapsam dışı soruları anında reddeder.
- Ajanlar eşzamanlı olarak çalışır; böylece gecikme (latency) düşer.
- Sadece yapısal verileri (JSON/Dictionary) toplayıp tek bir birleştirme (merge) adımında son yanıtı üretir.
- Hata durumunda (örn. ajanlardan biri çökerse) çalışan diğer ajanın verilerini kurtarır.

`run_portfolio_agent` ve `run_market_agent` node'ları `writer: StreamWriter`
parametresi alır: LangGraph tarafından otomatik enjekte edilir,
`stream_mode="custom"` kullanılmadığında no-op'tur — böylece `run_orchestrator()`
(tek seferlik) ve `stream_orchestrator()` (SSE) aynı graf üzerinden çalışır.
"""

import logging
import operator
from collections.abc import AsyncIterator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import StreamWriter

from agents.base import AgentRequest, AgentResponse
from agents.market_agent import MarketAgent
from agents.market_query import portfoy_referansi_var_mi
from agents.portfolio_agent import PortfolioAgent
from agents.risk_agent import RiskAgent
from agents.scope_checker import check_scope
from agents.web_research_agent import WebResearchAgent
from app.core.config import settings
from app.core.llm_client import get_llm_client

logger = logging.getLogger(__name__)


class OrchestratorState(TypedDict):
    user_id: str
    session_id: str
    message: str
    # Son N mesajlık sohbet geçmişi ({"role": ..., "content": ...} sözlükleri).
    # TODO: Ajanlar şu an bunu prompt'larına dahil etmiyor (tek turluk
    # çalışıyorlar); alan, çok turlu bağlam gereken ajanlar için hazır tutuluyor.
    history: list[dict[str, str]]
    intent: str
    flags: list[str]
    agent_responses: Annotated[list[AgentResponse], operator.add]
    final_answer: str


# Ajana yönlendiren niyet etiketleri. `intent` alanı ya bir erken çıkış kodu
# (OUT_OF_SCOPE, AMBIGUOUS vb.) ya da bunlardan bir veya birkaçının "+" ile
# birleşmiş hâlidir ("risk", "portfolio+risk"). Alan orchestrator dışına
# çıkmıyor; tek tüketicisi _route_after_intent.
AGENT_INTENTS = ("portfolio", "market", "risk", "web_research")

AGENT_NODES = {
    "portfolio": "portfolio_agent",
    "market": "market_agent",
    "risk": "risk_agent",
    "web_research": "web_research_agent",
}


def _mesaj(anahtar: str, varsayilan: str) -> str:
    """Kullanıcıya gösterilen metni scope.yaml'dan okur.

    Metinler koddan ayrı tutuluyor (NFR: "kapsam kuralları koda gömülmez");
    içerik ekibi kod değişikliği olmadan güncelleyebilsin diye. Anahtar
    bulunamazsa kod içindeki yedek metin kullanılır — eksik bir YAML anahtarı
    yüzünden kullanıcıya boş yanıt dönmemeli.
    """
    from agents.scope_checker import scope_config

    metin = scope_config.get("mesajlar", {}).get(anahtar, {}).get("varsayilan")
    return metin.strip() if isinstance(metin, str) and metin.strip() else varsayilan


# Niyet tespitine verilen sohbet geçmişi uzunluğu (mesaj sayısı).
_INTENT_HISTORY_TURNS = 4

_AMBIGUOUS_MESSAGE = (
    "Sorunuzun tam olarak neyle ilgili olduğunu anlayamadım. Lütfen "
    "'Portföyüm ne durumda?', 'Riskim nedir?' veya 'Son piyasa haberleri neler?' "
    "şeklinde daha açık bir soru sorar mısınız?"
)


async def detect_intent(state: OrchestratorState) -> dict:
    """Kullanıcının niyetini LLM yardımıyla sınıflandırır. Kapsam dışı sorular baştan reddedilir."""
    query = state["message"].strip()

    # 1. Kural Tabanlı Kapsam Kontrolü (Scope Guard)
    scope_result = check_scope(query)
    if scope_result["intent"] != "pass_to_llm":
        logger.info("[ORCHESTRATOR] Kapsam kontrolü yakaladı: %s", scope_result["intent"])
        return {
            "intent": scope_result["intent"],
            "flags": scope_result.get("flags", []),
            "final_answer": scope_result.get(
                "message",
                "Finansal danışmanınız olarak yalnızca portföyünüz ve finansal piyasalar hakkındaki sorularınızı yanıtlayabilirim.",
            ),
        }

    # 2. LLM Tabanlı Niyet Tespiti
    #
    # KAVRAM SORULARININ TAMAMI WEB_RESEARCH'E GİDER — arşivde belgesi olsa
    # bile. Önce denenen ayrım ("arşivde belgesi varsa MARKET") iki yerden
    # birden kırıldı:
    #
    # 1. Sınıflandırıcı arşivde ne olduğunu bilemez; kararı tahmine bağlıyordu.
    # 2. Belgenin VAR OLMASI, GETİRİLEBİLECEĞİ anlamına gelmiyor.
    #    `rag/retriever.py` bir sonucu ancak sorguyla paylaşılan kelimelerden
    #    en az biri JENERİK DEĞİLSE kabul ediyor; `_GENERIC_FINANCE_TERMS`
    #    içinde `temettu`, `halka`, `arz` var — 31 şirket profilinin tamamında
    #    geçtikleri için oraya konmak zorunda kalındı (bkz. o listenin
    #    yorumları). Sonuç: "temettü nedir" sorgusu,
    #    `REFERANS_kurumsal-olay-terimleri.md` içinde "## Temettü (Kâr Payı)"
    #    başlığı AYNEN dururken bile hiçbir zaman sonuç döndüremiyor ve
    #    kullanıcı "Veritabanımızda bu sorguyla ilgili doğrulanmış bir bilgi
    #    bulunamadı" görüyordu (ölçüldü, 27 Ağustos; teşhis kelime kapısında).
    #
    # Bir terim ne kadar yaygınsa o kadar çok belgede geçiyor, o kadar jenerik
    # işaretleniyor ve tanımı o kadar bulunamıyor: en çok sorulan kavramlar
    # yapısal olarak en çok başarısız olanlar. Ayrım bu yüzden arşiv
    # üyeliğine değil SORUNUN TÜRÜNE bağlandı — kavram/prosedür mü, yoksa
    # belirli bir şirkete/döneme ait veri mi.
    llm = get_llm_client()
    system_prompt = (
        "Sen bir niyet sınıflandırma motorusun. Kullanıcının sorusunu aşağıdaki "
        "etiketlerden BİR VEYA BİRKAÇINA ata. SADECE etiketleri virgülle ayırarak "
        "yaz; açıklama, cümle, noktalama ekleme.\n\n"
        "PORTFOLIO — kullanıcının kendi varlıkları: değeri, dağılımı, getirisi, "
        "işlem geçmişi, tek tek pozisyonları.\n"
        "  Örnek: 'portföyüm ne durumda', 'geçen ay ne aldım', 'varlıklarımı listele'\n"
        "MARKET — BELİRLİ bir şirkete, varlığa ya da döneme ait VERİ: piyasa "
        "haberleri, şirket bilançoları, açıklanmış rakamlar, güncel "
        "fiyat/kur/faiz (döviz, altın, gümüş, platin dahil kıymetli madenler). "
        "Kavramın kendisi değil, o kavramın BİR ŞİRKETTEKİ değeri.\n"
        "  Örnek: 'Aselsan haberleri', 'dolar kuru ne durumda', 'BIST bugün nasıl', "
        "'gram altın kaç TL', 'gümüş fiyatı nedir', 'platin ne kadar', "
        "'THYAO'nun F/K oranı kaç', 'Tüpraş 2. çeyrek bilançosu nasıl', "
        "'Akbank'ın 2026 temettüsü ne kadar' (RAPORLANMIŞ bir rakam "
        "soruluyor, TAHMIN değil)\n"
        "RISK — portföyün riski, volatilitesi, yoğunlaşması, dengesi; yeniden "
        "dengeleme ve strateji önerisi. Soruda 'risk' kelimesi GEÇMESE DE bu "
        "etiket kullanılır.\n"
        "  Örnek: 'riskim nedir', 'portföyümde çok fazla hisse mi var', "
        "'nasıl dengelemeliyim', 'dağılımım dengeli mi', 'ne kadar güvendeyim', "
        "'çok mu riskli yatırım yapıyorum', 'volatilitem ne kadar', "
        "'oynaklığım iyi mi kötü mü', 'yeterince çeşitlendirilmiş miyim', "
        "'bir günde en fazla ne kaybederim', 'en riskli varlıklarım hangileri'\n\n"
        "WEB_RESEARCH — KAVRAM ve PROSEDÜR soruları: bir terim ne demek, bir "
        "süreç nasıl işler, bir hesap nasıl yapılır, bir uygulama genelde "
        "nasıldır. Muhasebe standartları ve düzenleyici çerçeve de buraya "
        "girer. Kavram sorusunun tamamı buraya gelir — soruda BELİRLİ bir "
        "şirket ya da dönem geçmiyorsa MARKET DEĞİLDİR.\n"
        "  Örnek: 'lot ne demek', 'temettü nedir', 'halka arz nasıl olur', "
        "'borsa saat kaçta kapanır', 'takas kaç gün sürer', "
        "'F/K oranı nasıl hesaplanır', 'TFRS 16 nedir', "
        "'konsolide finansal tablo ne demek', 'SPK ne iş yapar', "
        "'şirketler ne sıklıkla temettü verir', 'portföy kârı nasıl hesaplanır', "
        "'hisse ile fon arasındaki fark ne'\n\n"
        "TAHMIN — gelecekteki bir fiyatın, kurun veya getirinin ne olacağı;\n"
        "AÇIKÇA gelecek zaman/gelecek yıl belirten bir ifade GEREKİR "
        "('olur', 'olacak', 'yükselecek mi', 'gelecek yıl'). Bir yıl "
        "GEÇMESE veya belirtilse bile ('2026 temettüsü ne kadar' gibi) "
        "soru zaten AÇIKLANMIŞ/RAPORLANMIŞ bir rakamı soruyorsa (gelecek "
        "zaman eki YOK) bu TAHMIN DEĞİL, MARKET'tir — yıl geçmesi tek "
        "başına tahmin sayılmaz.\n"
        "  Örnek: '2027de dolar kaç TL olur', 'altın yükselecek mi', "
        "'bu hisse gelecek yıl ne kadar olur'\n"
        "KAPSAM_DISI — finansla ya da kullanıcının portföyüyle ilgisi olmayan "
        "her şey; ayrıca kripto, türev ve gayrimenkul gibi desteklenmeyen "
        "varlıklar.\n"
        "  Örnek: 'hava nasıl', 'maç kaç kaç bitti', 'yemek tarifi ver'\n\n"
        "Birden fazla konu varsa hepsini yaz: 'portföyüm ve riskim nasıl' → PORTFOLIO, RISK\n"
        "Sorulmayan konuyu EKLEME. Soru yalnızca değer/dağılım soruyorsa RISK "
        "yazma; yalnızca risk, denge veya öneri soruyorsa PORTFOLIO yazma. "
        "'nasıl dengelemeliyim' → sadece RISK (varlık dökümü istenmedi). "
        "'riskim nedir' → sadece RISK.\n"
        "KAVRAM mı VERİ mi — tek ayrım bu:\n"
        "  Kavramın ya da sürecin KENDİSİ soruluyorsa → WEB_RESEARCH\n"
        "  Aynı kavramın BELİRLİ BİR ŞİRKETTEKİ değeri → MARKET\n"
        "  Aynı kavramın KULLANICIDAKİ değeri → PORTFOLIO\n"
        "  'temettü nedir' → WEB_RESEARCH · 'Akbank'ın temettüsü ne kadar' → "
        "MARKET · 'ne kadar temettü aldım' → PORTFOLIO\n"
        "  'F/K oranı nasıl hesaplanır' → WEB_RESEARCH · 'THYAO'nun F/K'sı kaç' "
        "→ MARKET\n"
        "  'kâr nasıl hesaplanır' → WEB_RESEARCH · 'ne kadar kâr ettim' → "
        "PORTFOLIO\n"
        "TAHMIN ve KAPSAM_DISI TEK BAŞINA yazılır, başka etiketle birlikte değil.\n"
        "TAKİP SORUSU: Soru kendi başına anlaşılmıyorsa ('bunu açıkla', 'peki "
        "ya', 'neden böyle') ÖNCEKİ KONUŞMA'da neyin konuşulduğuna bak ve o "
        "konunun etiketini ver.\n"
        "TEKLİF KABULÜ: Asistanın ÖNCEKİ mesajı bir tahmin isteğini reddedip "
        "YERİNE bir ALTERNATİF önermişse ('...tahmin yapmıyorum ama geçmiş "
        "performansı/güncel durumu/açıklanmış sonuçları paylaşabilirim' "
        "gibi) ve kullanıcının şimdiki mesajı bu alternatifi KABUL ediyorsa "
        "('paylaş', 'evet', 'olur', 'lütfen', 'tamam' gibi kısa bir onay), "
        "önceki reddi TEKRARLAMA — asistanın teklif ettiği ALTERNATİFİN "
        "etiketini ver (ör. MARKET). Reddi tekrarlamak, kullanıcının kabul "
        "ettiği teklifi hiç yerine getirmemek demektir."
    )

    # Sınıflandırıcı sohbet geçmişini de görür.
    #
    # Görmediğinde takip soruları anlaşılmıyordu: "Riskim nedir?" cevabının
    # ardından gelen "Bunu biraz daha açıklar mısın?" sorusu, kendi başına
    # hiçbir konuya bağlanamadığı için AMBIGUOUS'a düşüyor ve kullanıcı
    # "sorunuzu anlayamadım" cevabı alıyordu (ölçüldü, 23 Ağustos test turu) —
    # oysa neyi kastettiği bir önceki mesajdan bellidir.
    #
    # Yalnızca son birkaç tur alınıyor: sınıflandırma tek bir kararlık iş,
    # uzun geçmiş hem token harcar hem de eski konuların etiketi yenisine
    # karışır.
    gecmis = (state.get("history") or [])[-_INTENT_HISTORY_TURNS:]
    if gecmis:
        satirlar = "\n".join(
            f"{'Kullanıcı' if m.get('role') == 'user' else 'Asistan'}: "
            f"{(m.get('content') or '')[:200]}"
            for m in gecmis
        )
        siniflandirma_girdisi = f"ÖNCEKİ KONUŞMA:\n{satirlar}\n\nSORU:\n{query}"
    else:
        siniflandirma_girdisi = query

    try:
        response = await llm.generate(siniflandirma_girdisi, system=system_prompt)
        response_text = response.strip().upper()

        # Bu iki etiket AJANA GİTMEZ, doğrudan yanıtla sonuçlanır — ve ajan
        # etiketlerinden ÖNCE bakılır: model ikisini birden yazdığında
        # (talimat aksini söylese de) reddetme kararı kazanmalı.
        #
        # Eskiden ikisi de yoktu ve sınıflandırıcının "hiçbiri" seçeneği
        # bulunmuyordu: hava durumu sorusu MARKET'e düşüp RAG'e gidiyor,
        # kullanıcı "veritabanımızda bu sorguyla ilgili doğrulanmış bir bilgi
        # bulunamadı" görüyordu — sistem arızalıymış gibi. Gelecek tahmini de
        # aynı yoldan geçiyordu (ölçüldü, 23 Ağustos test turu).
        if "TAHMIN" in response_text:
            return {
                "intent": "FUTURE_PREDICTION",
                "flags": scope_result.get("flags", []),
                "final_answer": _mesaj(
                    "gelecek_tahmini",
                    "Gelecekteki fiyat veya getiri tahmini yapmıyorum; elimdeki "
                    "veriler geçmişe ve bugüne ait.",
                ),
            }
        if "KAPSAM_DISI" in response_text:
            return {
                "intent": "OUT_OF_SCOPE",
                "flags": scope_result.get("flags", []),
                "final_answer": _mesaj(
                    "out_of_scope",
                    "Bu konuda yardımcı olamıyorum. Portföyünüz ve piyasalar "
                    "hakkındaki sorularınızı yanıtlayabilirim.",
                ),
            }

        labels = [label for label in AGENT_INTENTS if label.upper() in response_text]

        # Geriye dönük uyum: eski prompt tek kelimelik BOTH/RAG döndürüyordu.
        if not labels and "BOTH" in response_text:
            labels = ["portfolio", "market"]
        elif not labels and "RAG" in response_text:
            labels = ["market"]

        # Deterministik güvence (2026-08-27, bkz.
        # market_query.portfoy_referansi_var_mi docstring'i): sorgu
        # "portföyüm" gibi açık bir ifade taşıyorsa PORTFOLIO etiketi LLM
        # kaçırmış olsa bile eklenir — aksi hâlde kullanıcının gerçek
        # holdings'i hiçbir ajana ulaşmaz ve market_agent portföyde olmayan
        # şirketler hakkında cevap üretebilir (ölçüldü, analist test turu).
        if "portfolio" not in labels and portfoy_referansi_var_mi(query):
            labels.append("portfolio")

        intent = "+".join(labels) if labels else "AMBIGUOUS"

    except Exception as e:
        logger.error(f"[ORCHESTRATOR] Niyet tespiti LLM hatası: {e}")
        intent = "AMBIGUOUS"

    logger.info(
        "[ORCHESTRATOR] LLM niyet tespiti: %s | sorgu=%r",
        intent,
        state["message"][:80],
    )

    result = {"intent": intent, "flags": scope_result.get("flags", [])}
    if intent == "AMBIGUOUS":
        result["final_answer"] = _AMBIGUOUS_MESSAGE

    return result


def _build_request(state: OrchestratorState) -> AgentRequest:
    return AgentRequest(
        user_id=state["user_id"],
        session_id=state["session_id"],
        query=state["message"],
        context={"recent_messages": state["history"]},
    )


async def run_portfolio_agent(state: OrchestratorState) -> dict:
    agent = PortfolioAgent(mcp_server_url=settings.mcp_server_url)
    response = await agent.execute(_build_request(state), on_token=None)
    return {"agent_responses": [response]}


async def run_market_agent(state: OrchestratorState) -> dict:
    agent = MarketAgent(mcp_server_url=settings.mcp_server_url)
    response = await agent.execute(_build_request(state), on_token=None)
    return {"agent_responses": [response]}


async def run_risk_agent(state: OrchestratorState) -> dict:
    agent = RiskAgent(mcp_server_url=settings.mcp_server_url)
    response = await agent.execute(_build_request(state), on_token=None)
    return {"agent_responses": [response]}


async def run_web_research_agent(state: OrchestratorState) -> dict:
    agent = WebResearchAgent(mcp_server_url=settings.mcp_server_url)
    response = await agent.execute(_build_request(state), on_token=None)
    return {"agent_responses": [response]}


async def handle_out_of_scope(state: OrchestratorState, writer: StreamWriter) -> dict:
    """Kapsam dışı durumlarda LLM'e gitmeden doğrudan uyarı mesajını akıtır."""
    # Metni kelime kelime akıtarak animasyonlu hissi ver
    words = state["final_answer"].split(" ")
    for i, word in enumerate(words):
        writer({"delta": word + (" " if i < len(words) - 1 else "")})
    return {}


async def merge_responses(state: OrchestratorState, writer: StreamWriter) -> dict:
    successful = [r.summary_text for r in state["agent_responses"] if r.success]
    errors = [r.error for r in state["agent_responses"] if r.error]

    # Hiçbir ajan başarılı olmadı. Ajanların KENDİ hata mesajları gösterilir:
    # bunlar kullanıcıya gösterilmek üzere yazılmış metinlerdir
    # (mcp_server/tools/_base.py DEFAULT_MESSAGES) ve durumları ayırt eder —
    # "İstenen kayıt bulunamadı." ile "Veri kaynağına şu anda ulaşılamıyor."
    # aynı şey değildir.
    #
    # Eskiden ikisi de tek bir "sistemlerimize ulaşılamıyor" metnine düşüyordu;
    # RAG'de doküman bulunamaması (NOT_FOUND) sistem arızası gibi görünüyor,
    # kullanıcıya ayakta olan bir sistem çökmüş gibi sunuluyordu. İç hata
    # gizliliği korunuyor: bu metinler kod/istisna detayı içermez.
    if not successful:
        final_answer = (
            "\n\n".join(dict.fromkeys(errors))
            if errors
            else "Şu an sistemlerimize ulaşılamıyor, lütfen daha sonra tekrar deneyin."
        )
        writer({"delta": final_answer})
        return {"final_answer": final_answer}

    llm = get_llm_client()

    # Kısmi veya tam başarı durumu
    combined_texts = []
    if successful:
        combined_texts.append("BAŞARILI BİLGİLER:\n" + "\n\n---\n\n".join(successful))
    if errors:
        combined_texts.append("ALINAMAYAN BİLGİLER (KULLANICIYA BELİRT):\n" + "\n".join(errors))

    # Soru, verilerin ÜSTÜNE ve ayrı bir başlıkla konur: aynı bloğa
    # karıştırılsaydı model soru metnini de aktarılacak veri sanabilirdi.
    #
    # `.get` ile okunuyor: bu, nihai yanıtın yazıldığı yer. Alan beklenmedik
    # bir çağrı yolunda eksik kalırsa cevabın odağı zayıflar ama sohbet
    # ayakta kalır — bir KeyError burada tüm yanıtı düşürürdü.
    soru = (state.get("message") or "").strip()
    combined_text = "\n\n".join(combined_texts)
    if soru:
        combined_text = f"KULLANICININ SORUSU:\n{soru}\n\n{combined_text}"

    # SORU BU ADIMA GEÇİRİLİR.
    #
    # Eskiden geçirilmiyordu: merge yalnızca veri yığınını görüyor, üstüne
    # "hiçbir bilgiyi silme" talimatı alıyordu. Elinde soru olmayan ve eleme
    # hakkı bulunmayan bir modelin yapabileceği tek şey her şeyi tekrar
    # yazmaktı. Ölçülen sonuç: "en çok kazandıran varlığım hangisi?"
    # sorusuna sekiz varlık sıralanıyor ve cevap en sona gömülüyordu;
    # "volatilitem iyi mi kötü mü?" sorusunun yargı kısmı hiç
    # cevaplanmıyordu; "NVIDIA almalı mıyım?" sorusuna alakasız bir risk
    # özeti dönüyordu.
    #
    # "Hiçbir bilgiyi silme" kuralı tamamen kaldırılmadı, İKİYE AYRILDI:
    # veri elenebilir, UYARILAR elenemez. O kural aslında sorumluluk reddini
    # ve "şu veriye ulaşılamadı" bildirimlerini korumak için konmuştu;
    # elemeyi de yasaklaması yan etkiydi.
    system_prompt = (
        "Aşağıda kullanıcının SORUSU ve bu soruya cevap vermek için toplanmış "
        "ÖLÇÜLMÜŞ VERİLER var. Görevin, soruyu Türkçe ve doğrudan yanıtlamak.\n"
        "\n"
        "SORUYU CEVAPLA: Yanıtın ilk cümlesi sorulan şeye cevap versin. "
        "Kullanıcı tek bir şey sorduysa (hangi varlık, ne kadar, kaç tane) "
        "önce onu söyle; destekleyici ayrıntı sonra gelir.\n"
        "\n"
        "İLGİSİZ VERİYİ DIŞARIDA BIRAK: Verilerde soruyla ilgisi olmayan "
        "bölümler olabilir. Onları AKTARMA. Soru bir varlık hakkındaysa tüm "
        "portföyü listeleme; soru risk hakkındaysa portföy özetini tekrar "
        "etme.\n"
        "\n"
        "VERİDE YOKSA SÖYLE: Sorulan bilgi verilerde yoksa bunu açıkça "
        "belirt. Yakın duran başka bir veriyi cevap yerine koyma ve "
        "verilerden çıkmayan hiçbir sayı, oran veya isim üretme.\n"
        "\n"
        "HESAPLAMA YAPMA: Verilerde iki sayı (ör. başlangıç ve bitiş fiyatı) "
        "olsa bile aralarındaki FARKI, TOPLAMI ya da başka bir türetilmiş "
        "değeri KENDİN hesaplama — yalnızca verilerde YAZILI OLAN sayıyı "
        "aktar. Veride zaten hesaplanmış bir yüzde değişim varsa onu "
        "kullan; yoksa değişim miktarından hiç bahsetme, iki sayıyı olduğu "
        "gibi ver.\n"
        "\n"
        "UYARILARI KORU: 'ALINAMAYAN BİLGİLER' bölümü, hesaplanamayan "
        "metrikler ve veri eksikliği notları ELENEMEZ; doğal bir dille "
        "aktarılır ('Şu an piyasa verilerine ulaşamıyorum ancak "
        "portföyünüz...' gibi).\n"
        "\n"
        "KAYNAKLARI KORU: Verilerde 'Kaynaklar:' listesi varsa yanıtın sonunda "
        "AYNEN kalır — doküman adı, yayın ve tarih dahil. Bir bilgi hangi "
        "belgeye dayanıyorsa kullanıcı bunu görebilmelidir; kaynağı düşürmek "
        "bilgiyi doğrulanamaz hâle getirir.\n"
        "\n"
        "CANLI BLOKLARI KORU: Verilerde 'Güncel KAP Bildirimleri:' veya "
        "'Güncel Piyasa Başlıkları:' başlıklı bir liste varsa AYNEN, madde "
        "madde kalır — başlık, tarih, saat, bağlantı ve 'Kaynak:' satırı "
        "dahil. Bunları kendi cümlene çevirme, özetleme veya başka bir "
        "bilgiyle birleştirme: bu bloklar kaynağından o an çekilmiş ham "
        "veridir, yeniden ifade edilmesi (tarihi/başlığı doğru aktarsan bile) "
        "uydurma riski taşır.\n"
        "Bu bloklardaki bir maddeyi düzyazıda AYRICA anlatma. Liste zaten "
        "gösteriyor; tekrarı aynı bilgiyi iki ayrı ifadeyle sunar ve ikisi "
        "çeliştiğinde hangisinin doğru olduğu belirsiz kalır.\n"
        "Bu bloklardaki bir maddeyi 'belgelerde yer alan' diye de sunma: o "
        "bilgi arşiv dokümanlarından değil, canlı kaynaktan geldi.\n"
        "\n"
        "Verilerin hangi ajandan veya kaynaktan geldiğini söyleme. "
        "'Merhaba', 'Cevap:' gibi etiketler ekleme, sadece içeriği ver.\n"
        "Para ve oranlarda Türkçe biçim kullan: 1.234,56 TL ve +%8,41 "
        "(yüzde işareti sayıdan ÖNCE, artı/eksi en başta).\n"
        # Bu adım son LLM turu: ajan metnini yeniden yazarken terimi de
        # değiştirebiliyor. Ajan prompt'larında "volatilite" zorunlu kılındı
        # (bkz. prompts/risk_agent.md kural 1), burada da korunmazsa merge
        # onu "oynaklık"a çevirip kuralı etkisiz bırakır.
        "TERİM: Fiyat dalgalanmasından söz ederken 'volatilite' de. "
        "'Oynaklık', 'dalgalanma', 'değişkenlik' gibi karşılıklarını kullanma; "
        "gelen veride bu kelimelerden biri geçiyorsa 'volatilite' olarak "
        "aktar.\n"
        "\n"
        "UYUM KURALI: Gelen verilerde risk analizi veya yeniden dengeleme "
        "senaryoları varsa, HİÇBİR YORUM EKLEME. 'Şu varlığı alın', "
        "'Riskinizi azaltın' gibi eylem önerilerinde bulunma. Yalnızca "
        "veriyi nesnel bir şekilde ilet."
    )

    flags = state.get("flags", [])
    if "advice_seeking" in flags:
        system_prompt += "\nKULLANICI TAVSİYE İSTİYOR: Kesinlikle yönlendirici bir dil kullanma, sadece verileri objektif olarak sun."
    if "kismi_kapsam" in flags:
        system_prompt += "\nKISMİ KAPSAM: Kullanıcı kapsam dışı bir varlığı da sordu. Karşılaştırma yapmaktan kaçın."

    final_answer = ""
    try:
        async for chunk in llm.stream(combined_text, system=system_prompt):
            final_answer += chunk
            writer({"delta": chunk})
    except Exception as e:
        logger.error(f"[ORCHESTRATOR] Merge LLM hatası: {e}")

    # `stream` istisna atmadan HİÇ parça üretmezse final_answer boş kalır ve
    # writer hiç çağrılmazdı: SSE'de ne token ne error olayı gider, arayüzde
    # boş balon durur. Yukarıdaki `except` yalnızca istisnayı yakalıyordu,
    # boş çıktıyı değil — iki durumu da aynı düşüş kapatıyor.
    if not final_answer.strip():
        final_answer = "\n\n".join(successful)
        writer({"delta": final_answer})

    return {"final_answer": final_answer}


def _route_after_intent(state: OrchestratorState) -> list[str]:
    """Niyete göre ilgili ajanlara paralel dağıtım yapar veya kapsam dışı akışına yönlendirir."""
    early_exit_intents = {
        "OUT_OF_SCOPE",
        "UNAUTHORIZED_ACTION",
        "SYSTEM_INFO",
        "UNSUPPORTED_LANGUAGE",
        "INJECTION_ATTEMPT",
        "AMBIGUOUS",
        "SMALLTALK_META",
        "FUTURE_PREDICTION",
    }

    if state["intent"] in early_exit_intents:
        return ["handle_out_of_scope"]

    # Eski sürümde "both" tek etiketti; artık "portfolio+market" üretiliyor.
    intent = "portfolio+market" if state["intent"] == "both" else state["intent"]
    nodes = [AGENT_NODES[label] for label in intent.split("+") if label in AGENT_NODES]

    if not nodes:
        # Tanınmayan etiket. Eskiden burada koşulsuz ["portfolio_agent"] vardı;
        # niyet tespiti RISK üretemediği için risk soruları buraya düşüp
        # sessizce portföy özetiyle cevaplanıyordu — kullanıcı cevap aldığını
        # sanıyordu. Anlaşılmayan soru artık açıkça soruluyor (CLAUDE.md §4).
        logger.warning("[ORCHESTRATOR] Tanınmayan niyet etiketi: %r", state["intent"])
        return ["handle_out_of_scope"]

    return nodes


def _build_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("detect_intent", detect_intent)
    graph.add_node("handle_out_of_scope", handle_out_of_scope)
    graph.add_node("portfolio_agent", run_portfolio_agent)
    graph.add_node("market_agent", run_market_agent)
    graph.add_node("risk_agent", run_risk_agent)
    graph.add_node("web_research_agent", run_web_research_agent)
    graph.add_node("merge", merge_responses)

    graph.set_entry_point("detect_intent")

    graph.add_conditional_edges(
        "detect_intent",
        _route_after_intent,
        {
            "handle_out_of_scope": "handle_out_of_scope",
            "portfolio_agent": "portfolio_agent",
            "market_agent": "market_agent",
            "risk_agent": "risk_agent",
            "web_research_agent": "web_research_agent",
        },
    )

    graph.add_edge("handle_out_of_scope", END)
    graph.add_edge("portfolio_agent", "merge")
    graph.add_edge("market_agent", "merge")
    graph.add_edge("risk_agent", "merge")
    graph.add_edge("web_research_agent", "merge")
    graph.add_edge("merge", END)

    return graph.compile()


_compiled_graph = _build_graph()


def _initial_state(
    user_id: str, session_id: str, message: str, history: list[dict[str, str]]
) -> OrchestratorState:
    return {
        "user_id": user_id,
        "session_id": session_id,
        "message": message,
        "history": history,
        "intent": "",
        "flags": [],
        "agent_responses": [],
        "final_answer": "",
    }


async def run_orchestrator(
    user_id: str, session_id: str, message: str, history: list[dict[str, str]] | None = None
) -> OrchestratorState:
    """Stream gerektirmeyen çağırıcılar için (ör. testler): tek seferde tam sonucu döner."""
    return await _compiled_graph.ainvoke(
        _initial_state(user_id, session_id, message, history or [])
    )


async def stream_orchestrator(
    user_id: str, session_id: str, message: str, history: list[dict[str, str]] | None = None
) -> AsyncIterator[tuple[str, Any]]:
    """SSE endpoint'i için: ("custom", {"delta": ...}) token parçalarını ve en
    sonda ("values", OrchestratorState) tam durumu sırayla yield eder."""
    async for mode, chunk in _compiled_graph.astream(
        _initial_state(user_id, session_id, message, history or []),
        stream_mode=["custom", "values"],
    ):
        yield mode, chunk
