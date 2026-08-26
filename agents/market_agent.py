"""Piyasa Araştırma Ajanı: `search_market_news` MCP tool'unu çağırır, dönen
doküman parçalarını LLM ile doğal dile döker ve altına kaynak listesi ekler.

RAG vektör deposuna doğrudan erişmez — tüm veri erişimi MCP Server üzerinden
geçer. Tool saf DB tabanlı RAG'dır (LLM yok, canlı internet yok); LLM yalnızca
bu ajanda, yalnızca tool'dan gelen metni yeniden ifade etmek için devreye girer.
Sayısal hiçbir değer LLM tarafından üretilmez.

İki savunma katmanı var:
  1. Deterministik filtre — sorgudaki şirket/dönem tespit edilip tool'a
     geçirilir, arama uzayı benzerlik hesaplanmadan önce daralır.
  2. Etiketli parçalar — her parça `[n] Başlık (Kaynak, tarih)` başlığıyla
     LLM'e verilir. Eskiden parçalar etiketsiz birleştiriliyordu; model iki
     ayrı şirketin rakamlarını tek cümlede harmanlayabiliyordu.

Ayrıca: sorgu bir şirkete işaret ediyor VE güncellik istiyorsa (bkz.
`market_query.guncellik_istegi_var_mi`), `get_live_kap_disclosures` ile canlı
bir KAP bildirim listesi de eklenir. Bu blok LLM'e ASLA verilmez — RAG
özetiyle aynı cümlede eritilirse hangi bilginin arşivden hangisinin şu an
KAP'tan geldiği bulanıklaşır (2026-08-24 kararı: "RAG değişmeyecek bilgiler
içindir, güncel bildirim listesi ayrı ve etiketli kalır"). KAP'a
ulaşılamazsa bu blok sessizce atlanır — RAG özeti kendi başına geçerli bir
cevaptır, canlı ek bir "varsa iyi" katmandır.

Sorgu bir şirkete işaret ETMİYOR ama hem gündem hem güncellik istiyorsa
("son piyasa haberleri neler"), soru RAG'e HİÇ gitmez: yanıt yalnızca
`get_live_market_headlines`'tan gelen BloombergHT başlıklarıdır. Arşivde
haber yok; yine de aramaya gidildiğinde en yakın belge dönüp kaynak
listesine yazılıyor, cevapta hiç geçmeyen bir doküman sanki cevabı
destekliyormuş gibi görünüyordu (ölçüldü, 24 Ağustos).

İki canlı yol birbirini dışlar: şirket sorulduğunda genel gündem alakasız
gürültüdür, şirket sorulmadığında KAP'a hangi şirketi soracağımız belirsizdir.
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from agents.base import AgentRequest, AgentResponse, BaseAgent
from agents.formatting import tr_amount as _tr_amount
from agents.market_query import (
    filtre_cikar,
    genel_gundem_istegi_var_mi,
    guncellik_istegi_var_mi,
    sirket_sayisi,
)
from agents.price_query import fiyat_niyeti
from app.core.llm_client import get_llm_client

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "market_agent.md").read_text(
    encoding="utf-8"
)

_KAYNAK_BASLIGI = "\n\nKaynaklar:\n"
_KAP_BASLIGI = "\n\nGüncel KAP Bildirimleri:\n"
_GUNDEM_BASLIGI = "\n\nGüncel Piyasa Başlıkları:\n"


def _tarih_bicimle(ham: Any) -> str:
    """`2026-07-28` → `28.07.2026`. Ayrıştırılamayan değer olduğu gibi döner —
    tarih biçimi yüzünden cevabın tamamını kaybetmek istemiyoruz."""
    metin = str(ham or "").strip()
    try:
        return date.fromisoformat(metin[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return metin


def _parca_etiketi(metadata: dict[str, Any]) -> str:
    """`ASELSAN 2026 2. Çeyrek Finansal Sonuçları (KAP, 28.07.2026)`"""
    baslik = str(metadata.get("baslik") or metadata.get("dosya") or "Başlıksız belge")
    parcalar = [str(metadata.get(alan)) for alan in ("kaynak", "tarih") if metadata.get(alan)]
    if not parcalar:
        return baslik
    if metadata.get("tarih"):
        parcalar[-1] = _tarih_bicimle(metadata["tarih"])
    return f"{baslik} ({', '.join(parcalar)})"


def _dokuman_blogu(results: list[dict[str, Any]]) -> str:
    """LLM'e verilecek metin. Numaralandırma ve kaynak başlığı, modelin iki
    farklı belgeyi tek bir anlatıya karıştırmasını zorlaştırır."""
    return "\n\n".join(
        f"[{i}] {_parca_etiketi(r.get('metadata') or {})}\n{r.get('content', '')}"
        for i, r in enumerate(results, start=1)
    )


def _kaynak_blogu(results: list[dict[str, Any]]) -> str:
    """Kullanıcıya gösterilecek kaynak listesi. Aynı belgeden birden çok parça
    gelebilir; tekrar edenler ilk görülme sırası korunarak teklenir."""
    gorulen: list[str] = []
    for r in results:
        etiket = _parca_etiketi(r.get("metadata") or {})
        if etiket not in gorulen:
            gorulen.append(etiket)
    if not gorulen:
        return ""
    return _KAYNAK_BASLIGI + "\n".join(f"- {etiket}" for etiket in gorulen)


def _kap_blogu(disclosures: list[dict[str, Any]]) -> str:
    """`- Finansal Rapor (6 Aylık) — 04.08.2026 (https://...)` biçiminde,
    LLM'den geçmeden doğrudan KAP'ın kendi ifadeleriyle listelenir."""
    if not disclosures:
        return ""
    satirlar = []
    for d in disclosures:
        satir = f"- {d.get('baslik') or 'Başlıksız bildirim'}"
        if tarih := d.get("tarih"):
            satir += f" — {tarih}"
        if url := d.get("url"):
            satir += f" ({url})"
        satirlar.append(satir)
    return _KAP_BASLIGI + "\n".join(satirlar)


def _gundem_blogu(headlines: list[dict[str, Any]], kaynak_url: str | None) -> str:
    """`- TCMB: ... — 24.08.2026 14:38` biçiminde, LLM'den geçmeden doğrudan
    sitenin kendi başlıklarıyla listelenir.

    Madde başına bağlantı YOK: BloombergHT son dakika maddelerinin ayrı bir
    adresi bulunmuyor (ölçüldü), bu yüzden kaynak listenin sonunda bir kez
    verilir. Olmayan bir permalink üretmek uydurma olurdu.
    """
    if not headlines:
        return ""
    satirlar = []
    for h in headlines:
        satir = f"- {h.get('baslik') or 'Başlıksız haber'}"
        if tarih := h.get("tarih"):
            satir += f" — {tarih}"
        satirlar.append(satir)
    blok = _GUNDEM_BASLIGI + "\n".join(satirlar)
    if kaynak_url:
        # BOŞ SATIR ŞART: tek satır sonu markdown'da listeyi bitirmiyor,
        # kaynak satırı son maddenin devamı gibi render ediliyordu (ölçüldü,
        # 24 Ağustos). Boş satır listeyi kapatıp ayrı bir paragraf açar.
        blok += f"\n\nKaynak: BloombergHT ({kaynak_url})"
    return blok


def _render_guncel_fiyat(data: dict[str, Any]) -> str:
    """Güncel fiyatları etiketli satırlara döker.

    TARİH HER SATIRDA yazılır. Fiyat "bugünün" fiyatı olmak zorunda değil —
    piyasa hafta sonu ve tatilde kapalı — ve tarihi söylemeden vermek, olmayan
    bir tazelik iddia etmek olurdu. `source` de yazılır: kullanıcı rakamın
    resmî bir kaynaktan mı yoksa üretilmiş veriden mi geldiğini görebilmeli
    (AK 5.1).
    """
    satirlar: list[str] = []
    for p in data.get("prices") or []:
        satir = (
            f"{p.get('name')} ({p.get('symbol')}): "
            f"{_tr_amount(p.get('price'))} TL — {_tarih_bicimle(p.get('price_date'))} "
            f"kapanışı, kaynak: {p.get('source')}"
        )
        if p.get("stale"):
            # Eski fiyat GİZLENMEZ, eskiliği söylenir (zarif düşüş).
            satir += f" [DİKKAT: {p.get('age_days')} gün önceki fiyat, güncel olmayabilir]"
        satirlar.append(satir)

    eksik = list(data.get("unknown_symbols") or []) + list(data.get("symbols_without_data") or [])
    if eksik:
        satirlar.append("Fiyatı bulunamayan: " + ", ".join(eksik))

    if not satirlar:
        return "Güncel fiyat: istenen varlık için kayıt yok."
    return "Güncel fiyatlar\n" + "\n".join(satirlar)


def _render_fiyat_gecmisi(data: dict[str, Any]) -> str:
    """Seriyi uç noktalara indirger: başlangıç, bitiş, değişim.

    Tam seri (60-120 nokta) anlatıya girmez; hem ücretli token hem de modelin
    yanlış değer okuma kaynağı. Yüzde değişim burada hesaplanıyor — LLM'in
    seriden çıkarması istenmiyor.
    """
    series = data.get("series") or {}
    satirlar: list[str] = []

    for sembol, noktalar in sorted(series.items()):
        if not noktalar:
            continue
        ilk, son = noktalar[0], noktalar[-1]
        ilk_fiyat = float(ilk.get("close") or 0)
        son_fiyat = float(son.get("close") or 0)
        degisim = ((son_fiyat / ilk_fiyat - 1) * 100) if ilk_fiyat else None
        satir = (
            f"{sembol}: {_tarih_bicimle(ilk.get('date'))} {_tr_amount(ilk_fiyat)} TL → "
            f"{_tarih_bicimle(son.get('date'))} {_tr_amount(son_fiyat)} TL"
        )
        if degisim is not None:
            isaret = "+" if degisim >= 0 else "-"
            satir += f" ({isaret}%{_tr_amount(abs(degisim))})"
        satirlar.append(satir)

    eksik = list(data.get("unknown_symbols") or []) + list(data.get("symbols_without_data") or [])
    if eksik:
        satirlar.append("Veri bulunamayan: " + ", ".join(eksik))

    if not satirlar:
        return "Fiyat geçmişi: istenen varlık için kayıt yok."
    return f"Fiyat geçmişi ({data.get('window', '—')})\n" + "\n".join(satirlar)


class MarketAgent(BaseAgent):
    agent_name = "market_agent"

    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        # FİYAT SORUSU RAG'E GİTMEZ.
        #
        # Kur ve fiyat dokümanlarda değil `price_history` tablosunda yaşıyor.
        # Bu dal olmadan "dolar ne kadar?" sorusu belge aramasına düşüyor ve
        # "veritabanımızda bu sorguyla ilgili doğrulanmış bir bilgi bulunamadı"
        # dönüyordu (ölçüldü, 23 Ağustos test turu) — elde güncel kur dururken.
        fiyat = fiyat_niyeti(request.query)
        if fiyat is not None:
            return await self._fiyat_yaniti(fiyat)

        filtreler = filtre_cikar(request.query)

        # SAF GÜNDEM SORUSU RAG'E GİTMEZ.
        #
        # "Son piyasa haberleri neler" sorusunun arşivde karşılığı YOK —
        # RAG haber tutmuyor. Yine de aramaya gidildiğinde en yakın belge
        # dönüyor ve kaynak listesine yazılıyordu: cevapta hiç geçmeyen
        # "Doğuş Otomotiv 2. Çeyrek Sonuçları" sanki cevabı destekleyen bir
        # kaynakmış gibi görünüyordu (ölçüldü, 24 Ağustos). Kullanılmayan
        # bir kaynağı listelemek, kaynak göstermenin amacını tersine çevirir.
        #
        # Koşul İKİ kelimeyi birden arar: gündem kelimesi TEK BAŞINA yetmez,
        # yoksa "piyasa değeri ne demek" gibi bir kavram sorusu da bu dala
        # düşüp arşive hiç bakmazdı. Güncellik şartı ikisini ayırıyor.
        if (
            not filtreler.get("sirket")
            and genel_gundem_istegi_var_mi(request.query)
            and guncellik_istegi_var_mi(request.query)
        ):
            gundem_yaniti = await self._gundem_yaniti(on_token=on_token)
            if gundem_yaniti is not None:
                return gundem_yaniti
            # Canlı kaynağa ulaşılamadı: aşağıdaki RAG yoluna düşülür. Boş
            # cevap vermektense arşivde ne varsa onu göstermek daha iyi.

        # Çoklu şirketli sorgularda (karşılaştırma vb.) sabit top_k=5
        # yetersiz kalıyordu: korpus büyüdükçe her şirketin kendi ilgili
        # chunk'ı için rekabet arttı, 3 şirketten biri üst-5'in dışına
        # düşüp cevaptan tamamen kayboluyordu (ölçüldü, 2026-08-26 — "Akbank,
        # İş Bankası ve Yapı Kredi'nin ... karşılaştır" sorgusunda Yapı
        # Kredi'nin net kâr chunk'ı düşmüştü). Tek şirketli/şirketsiz
        # sorgularda davranış DEĞİŞMİYOR (top_k=5 kalıyor).
        ek_args: dict[str, Any] = {}
        if (n := sirket_sayisi(request.query)) > 1:
            ek_args["top_k"] = min(5 * n, 20)

        tool_result = await self.call_mcp_tool(
            "search_market_news", {"query": request.query, **filtreler, **ek_args}
        )

        # Yedek deneme: filtre tespiti yanılmış olabilir (ör. sorguda geçen
        # şirket adı belgelerde farklı kodla etiketlenmiştir). Filtreli arama
        # boş dönerse bir kez de filtresiz denenir — filtre bir hızlandırma ve
        # doğruluk aracıdır, cevabı büsbütün engellememeli.
        if not tool_result.get("success") and filtreler:
            tool_result = await self.call_mcp_tool(
                "search_market_news", {"query": request.query, **ek_args}
            )

        if not tool_result.get("success"):
            error = tool_result.get("error", {})
            return self.error_response(error.get("message", "Piyasa verisi alınamadı"))

        data = tool_result["data"]
        results = data.get("results") or []
        summary_text = await self._summarize(request.query, results, on_token=on_token)

        # Güncellik istenen, şirketi belirlenmiş sorularda RAG'a ek olarak
        # canlı KAP bildirimleri de eklenir. Şirket tespit edilemediyse
        # ("piyasa nasıl gidiyor" gibi genel bir soru) hangi şirketin
        # bildirimi isteneceği belirsiz, bu adım tamamen atlanır.
        canli_bildirimler: list[dict[str, Any]] = []
        if (sirket := filtreler.get("sirket")) and guncellik_istegi_var_mi(request.query):
            canli_bildirimler = await self._canli_kap_bildirimleri(sirket, on_token=on_token)
            summary_text += _kap_blogu(canli_bildirimler)

        if canli_bildirimler:
            data = {**data, "canli_kap_bildirimleri": canli_bildirimler}

        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text=summary_text,
            data=data,
        )

    async def _fiyat_yaniti(self, niyet: dict) -> AgentResponse:
        """Güncel fiyat veya fiyat geçmişi yanıtı — LLM DEVREDE DEĞİL.

        Sayılar tool'dan geliyor ve buradan olduğu gibi geçiyor; cümleyi
        orchestrator'ın merge adımı kuruyor (ajanların ortak sözleşmesi).
        Ara bir LLM çağrısı hem gecikme ekler hem de rakamı yeniden yazma
        riski taşır.
        """
        semboller = niyet["symbols"]
        if niyet["history"]:
            tool_adi = "get_asset_price_history"
            args: dict[str, Any] = {"symbols": semboller}
        else:
            tool_adi = "get_current_prices"
            args = {"symbols": semboller}

        tool_result = await self.call_mcp_tool(tool_adi, args)
        if not tool_result.get("success"):
            error = tool_result.get("error", {})
            return self.error_response(error.get("message", "Fiyat verisi alınamadı"))

        data = tool_result["data"]
        metin = _render_fiyat_gecmisi(data) if niyet["history"] else _render_guncel_fiyat(data)
        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text=metin,
            data=data,
        )

    async def _canli_kap_bildirimleri(
        self, sirket: str, *, on_token: Callable[[str], None] | None = None
    ) -> list[dict[str, Any]]:
        """KAP'a ulaşılamazsa (ağ, zaman aşımı, pykap kurulu değil vb.) ana
        cevabı bozmadan sessizce boş liste döner — RAG özeti kendi başına
        geçerli bir cevaptır, bu yalnızca "varsa iyi" bir ek katmandır."""
        tool_result = await self.call_mcp_tool("get_live_kap_disclosures", {"sirket": sirket})
        if not tool_result.get("success"):
            return []

        disclosures = tool_result.get("data", {}).get("disclosures") or []
        if disclosures and on_token is not None:
            on_token(_kap_blogu(disclosures))
        return disclosures

    async def _gundem_yaniti(
        self, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse | None:
        """Yalnızca canlı gündem bloğundan oluşan yanıt — LLM DEVREDE DEĞİL.

        Başlıklar sitenin kendi ifadeleriyle geçer; özetleyecek bir arşiv
        metni yok, cümleyi orchestrator'ın merge adımı kuruyor.

        Canlı kaynağa ulaşılamazsa `None` döner ve çağıran taraf RAG yoluna
        düşer — bu dal bir kestirme, çıkmaz sokak değil.
        """
        gundem = await self._canli_piyasa_gundemi(on_token=on_token)
        headlines = gundem.get("headlines") or []
        if not headlines:
            return None

        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text=_gundem_blogu(headlines, gundem.get("kaynak_url")),
            data={"canli_piyasa_gundemi": headlines},
        )

    async def _canli_piyasa_gundemi(
        self, *, on_token: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        """BloombergHT'ye ulaşılamazsa boş sözlük döner; gerekçesi
        `_canli_kap_bildirimleri` ile aynı — canlı katman ana cevabı
        düşürmez."""
        tool_result = await self.call_mcp_tool("get_live_market_headlines", {})
        if not tool_result.get("success"):
            return {}

        data = tool_result.get("data") or {}
        headlines = data.get("headlines") or []
        if headlines and on_token is not None:
            on_token(_gundem_blogu(headlines, data.get("kaynak_url")))
        return data

    async def _summarize(
        self,
        query: str,
        results: list[dict[str, Any]],
        *,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        prompt = _PROMPT_TEMPLATE.format(query=query, documents=_dokuman_blogu(results))

        llm = get_llm_client()
        full_text = ""
        async for chunk in llm.stream(prompt):
            full_text += chunk
            if on_token is not None:
                on_token(chunk)

        # Kaynak listesi LLM'e bırakılmaz (uydurulmuş kaynak riski) — metadata'dan
        # üretilip akışın sonuna eklenir, kullanıcı da akarken görsün diye
        # on_token'dan geçirilir.
        kaynaklar = _kaynak_blogu(results)
        if kaynaklar:
            full_text += kaynaklar
            if on_token is not None:
                on_token(kaynaklar)

        return full_text
