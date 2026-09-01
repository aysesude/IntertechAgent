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

2026-08-28 eki — Profil-uygunluk bilgilendirmesi: bu "risk analizi" DEĞİLDİR
(o `agents/risk_agent.py`'nin işi) — kullanıcının sorduğu şirketin, GÜNCEL
anket puanıyla tavsiye kapsamında olup olmadığının basit bir bildirimi (bkz.
`agents/portfolio_agent.py`'deki aynı gerekçe, aynı tarihli not). ANKET
DOLU OLDUĞU her şirket sorusunda çalışır — yalnızca kullanıcının o an ELİNDE
olan bir varlıkla sınırlı değil, çünkü burada soru "ne yapmalıyım" değil
sırf bir şirket hakkında bilgi; kullanıcı henüz sahip olmadığı ama tavsiye
kapsamı dışında kalan bir şirketi sorduğunda da bunu bilmesi gerekir (analist
onayı, `advice_eligibility` yorumu — bkz. tasarım notundaki "hangi kapasite"
sorusunun cevabı). Sınıf düzeyinde değil VARLIK düzeyinde kontrol edilir
(`advice_eligibility.is_asset_advice_allowed`) — `advice_eligibility.py`'nin
kendi notu, tek tek varlıkların (ör. fonlar) sınıf ortalamasından
ayrılabildiğini, bu yüzden varlık düzeyi fonksiyonlarının tercih edilmesi
gerektiğini söylüyor. `market_query.filtre_cikar`'ın döndürdüğü `sirket` alanı
gerçek bir şirket adı değil TICKER'dır (ör. "ASELS"); `SPEC_BY_SYMBOL`'de
karşılığı olmayan tickerlar için (yabancı hisse adı uyuşmazlığı vb., bkz.
evren eşleme notu) sınıf bilinmiyor demektir, uydurma yok, kontrol sessizce
atlanır. Bu davranış "her şirket sorusunda daha mantıklı" (kullanıcı kararı,
2026-08-28) gerekçesiyle bilinçli olarak geniş tutuldu; beğenilmezse
daraltılabilir.
"""

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from agents.base import AgentRequest, AgentResponse, BaseAgent
from agents.formatting import ASSET_CLASS_TR as _ASSET_CLASS_TR
from agents.formatting import tr_amount as _tr_amount
from agents.market_query import (
    filtre_cikar,
    genel_gundem_istegi_var_mi,
    guncellik_istegi_var_mi,
    sirket_sayisi,
)
from agents.price_query import (
    fiyat_niyeti,
    hedef_fiyat_niyeti,
    temel_oran_niyeti,
    uygunluk_niyeti,
)
from app.core.llm_client import get_llm_client
from app.providers.universe import SPEC_BY_SYMBOL
from app.services.advice_eligibility import asset_risk_level, is_asset_advice_allowed

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "market_agent.md").read_text(
    encoding="utf-8"
)

_KAYNAK_BASLIGI = "\n\nKaynaklar:\n"
_KAP_BASLIGI = "\n\nGüncel KAP Bildirimleri:\n"
_GUNDEM_BASLIGI = "\n\nGüncel Piyasa Başlıkları:\n"
_UYGUNLUK_BASLIGI = "\n\nRisk profili uyumu\n"


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


# "Belgelerde yok" cevabının kalıbı. Prompt tek bir cümle dayatıyor ama model
# onu soruya uyarlıyor: "Elimdeki belgelerde ASELSAN'ın sözleşme tutarı bilgisi
# yer almıyor.", "Elimdeki belgelerde S&P 500'ün mevcut durumuna ilişkin bilgi
# yer almıyor." Ortak çekirdek iki parça: "elimdeki belgelerde" + olumsuzlama.
_BULUNAMADI_RE = re.compile(
    r"elimdeki belgelerde.*(yer almiyor|bulunmuyor|bulunamadi|bilgi yok)", re.S
)

# Üstündeki metin bu uzunluğu aşıyorsa cevap artık "tek cümlelik yokluk
# bildirimi" değildir: model belgelerden bir şeyler aktarmış ve yalnızca BİR
# ayrıntının eksik olduğunu söylüyordur. O durumda kaynaklar gerçekten
# kullanılmıştır ve listelenmelidir.
_BULUNAMADI_MAX_UZUNLUK = 220

_TR_FOLD = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a"})


def _kaynak_kullanilmadi_mi(ozet: str) -> bool:
    """Özet "belgelerde yok" diyorsa kaynak listesi EKLENMEMELİ.

    Kaynak listesi koda gömülü olarak ekleniyor; model "bilgi yok" dediğinde
    cevap kendi kendisiyle çelişiyordu — üstte "veri yok", altta iki kaynak
    (ölçüldü 1 Eylül 2026: [27] S&P 500 cevabının kaynağı "Tofaş Şirket
    Profili", [71] olmayan bir şirketin kaynağı "Pegasus Şirket Profili").

    Bu, kod tabanında zaten var olan ilkenin aynısı: kullanılmayan bir
    kaynağı göstermek, kaynak göstermenin amacını tersine çevirir (bkz.
    gündem dalındaki aynı gerekçe).
    """
    sade = ozet.replace("İ", "i").lower().translate(_TR_FOLD).strip()
    return len(sade) <= _BULUNAMADI_MAX_UZUNLUK and bool(_BULUNAMADI_RE.search(sade))


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


def _sirket_varlik_sinifi_uygunluk_disi_mi(
    sirket: str, risk_survey_score: int | None
) -> str | None:
    """Sorulan `sirket` (bkz. modül docstring'i — bu bir TICKER'dır, şirket adı
    değil), kullanıcının GÜNCEL anket puanıyla tavsiye kapsamı dışındaysa
    Türkçe sınıf adını döner; kapsamdaysa ya da bilinmiyorsa `None`.

    VARLIK düzeyinde kontrol edilir (`is_asset_advice_allowed`), SINIF
    düzeyinde değil — bkz. `advice_eligibility.py`'nin kendi notu: tek tek
    varlıklar (özellikle fonlar) sınıflarının tipik seviyesinden ayrılabilir,
    bu yüzden sınıf fonksiyonları yerine varlık fonksiyonları tercih
    edilmeli.

    `risk_survey_score=None` (anket hiç doldurulmamış) ya da `sirket`
    `SPEC_BY_SYMBOL`'de bulunamıyorsa (bkz. evren eşleme notu, ~14/126
    ticker'ın karşılığı yok) uydurma yok — kontrol sessizce atlanır.
    """
    if risk_survey_score is None:
        return None
    spec = SPEC_BY_SYMBOL.get(sirket)
    if spec is None:
        return None
    if is_asset_advice_allowed(sirket, spec.asset_class, risk_survey_score):
        return None
    return _ASSET_CLASS_TR.get(spec.asset_class.value, spec.asset_class.value)


def _uygunluk_blogu(sinif_adi: str) -> str:
    """`sinif_adi` doluysa bilgilendirme metni döner — LLM'den geçmez,
    doğrudan eklenir (aynı ilke: `_kap_blogu`/`_gundem_blogu`).

    Uyarı dili KULLANILMAZ (bkz. agents/risk_agent.py Yol B ile aynı ilke):
    bu bir satış zorunluluğu ya da öneri değil, salt bilgilendirmedir.
    """
    return (
        _UYGUNLUK_BASLIGI + f"{sinif_adi} sınıfı, güncel risk profilinize göre şu anda tavsiye "
        "kapsamında değil. Bu bir öneri ya da uyarı değildir, yalnızca "
        "bilgilendirmedir."
    )


def _yanlis_sirket_sonuclarini_ele(
    results: list[dict[str, Any]], istenen_sirket: str
) -> list[dict[str, Any]]:
    """`execute()`'daki filtresiz yedek aramanın (bkz. orada) sonuçlarından,
    sorguda AÇIKÇA tanınan `istenen_sirket`ten FARKLI bir şirkete ait
    parçaları eler. `sirket` alanı boş (genel/makro) parçalar dokunulmadan
    kalır.

    NEDEN GEREKLİ (2026-08-27, analist test turu, ölçüldü): sorguda geçen
    bir şirket için filtreli arama boş dönerse (ör. RAG'de o şirkete ait
    yeterli doküman yok), `execute()` bir kez de FİLTRESİZ dener — dar bir
    filtre yüzünden geçerli bir cevabın kaybolmaması için bilinçli eklenmiş
    bir mekanizma. Ama filtre düşünce arama TÜM korpusa açılıyor ve
    `rag/retriever.py`'deki mesafe+kelime-örtüşme eşiği ŞİRKET KİMLİĞİNE
    değil LEKSİK örtüşmeye bakıyor: "İş Bankası'nın kurucusu kimdir" sorusu
    "kurucu" kelimesini paylaştığı için ASELSAN'ın kuruluş belgesini
    "ilgili" sayıp yanlış şirketi cevap diye sunmuştu. Sorgu belirli bir
    şirketi AÇIKÇA sorduysa, filtresiz sonuçtaki BAŞKA bir şirkete ait
    parçalar ASLA kullanılmaz: o şirket için kayıt yoktur denmesi, yanlış
    şirketin bilgisini güvenle sunmaktan iyidir (AK 5.5, "uydurmama").
    """
    return [r for r in results if (r.get("metadata") or {}).get("sirket") in (None, istenen_sirket)]


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


_HEDEF_FIYAT_YON_METNI = {
    "yukseltme": "yükseltildi",
    "dusurme": "düşürüldü",
    "koruma": "korundu",
}


# yfinance alan adı -> (Türkçe etiket, yüzdeye çevrilsin mi).
#
# SÖZLEŞME ÖLÇÜLDÜ (yfinance 1.6.0, 1 Eylül 2026): `profitMargins` ve
# `ebitdaMargins` KESİR döner (0,2949), `dividendYield` ise ZATEN YÜZDEDİR
# (3,06). İkisine de aynı işlemi uygulamak sayıyı yüz kat yanlış gösterirdi.
_TEMEL_ORAN_ETIKETLERI: tuple[tuple[str, str, bool], ...] = (
    ("trailingPE", "F/K", False),
    ("forwardPE", "İleri F/K", False),
    ("priceToBook", "PD/DD", False),
    ("ebitdaMargins", "FAVÖK marjı", True),
    ("profitMargins", "Kâr marjı", True),
    ("dividendYield", "Temettü verimi", False),
)


def _buyuk_tutar(deger: float) -> str:
    """Piyasa değeri gibi büyük tutarları okunur ölçekte yazar.

    Ham hâli "374.399.991.808,00" — bir insan bunu okuyup büyüklüğünü
    kavrayamaz ve modelin özetlerken yeniden yazması (dolayısıyla yanlış
    yazması) riskini artırır.
    """
    deger = float(deger)
    for esik, birim in ((1e12, "trilyon"), (1e9, "milyar"), (1e6, "milyon")):
        if abs(deger) >= esik:
            return f"{_tr_amount(deger / esik)} {birim}"
    return _tr_amount(deger)


def _render_temel_oranlar(sirket: str, data: dict[str, Any]) -> str:
    """Değerleme çarpanlarını LLM'den geçirmeden ham satırlar olarak döker.

    Sıfır ve `None` değerler YAZILMAZ: bankalarda `ebitdaMargins` 0 gelir
    (FAVÖK kavramı bankada tanımsızdır) ve "%0,00" basmak bir ÖLÇÜM iddiası
    olurdu — oysa o oranın o şirket için anlamı yok.
    """
    kayit = (data.get("records") or {}).get(sirket) or {}
    satirlar: list[str] = []
    for alan, etiket, yuzde_mi in _TEMEL_ORAN_ETIKETLERI:
        deger = kayit.get(alan)
        if deger in (None, 0):
            continue
        if yuzde_mi:
            satirlar.append(f"- {etiket}: %{_tr_amount(float(deger) * 100)}")
        else:
            birim = "%" if alan == "dividendYield" else ""
            satirlar.append(f"- {etiket}: {birim}{_tr_amount(deger)}")

    piyasa_degeri = kayit.get("marketCap")
    if piyasa_degeri:
        para = kayit.get("currency") or "TRY"
        satirlar.append(f"- Piyasa değeri: {_buyuk_tutar(piyasa_degeri)} {para}")

    if not satirlar:
        eksik = ", ".join(data.get("symbols_without_data") or [sirket])
        return f"Temel analiz oranları bulunamadı: {eksik}."

    baslik = f"{sirket} temel analiz oranları:"
    dipnot = ""
    if data.get("fetched_at"):
        # Tarih ve kaynak HER ZAMAN yazılır — diğer fiyat yollarındaki kural
        # (AK 5.3); tarihsiz bir oran, olmayan bir tazelik iddiasıdır.
        dipnot = (
            f"\n(Kaynak: {data.get('source', 'yfinance')}, "
            f"{_tarih_bicimle(data['fetched_at'])} itibarıyla)"
        )
    return baslik + "\n" + "\n".join(satirlar) + dipnot


def _render_hedef_fiyat(data: dict[str, Any]) -> str:
    """Hedef fiyat/analist tavsiyesi kayıtlarını LLM'den geçirmeden ham
    satırlar olarak döker — `_kap_blogu` ile aynı gerekçe: bu GEÇMİŞTE
    raporlanmış bir rakam, LLM'in yeniden yazması uydurma riski taşır
    (bkz. app/services/target_price_ingest.py docstring'i)."""
    satirlar: list[str] = []
    for k in data.get("records") or []:
        para = k.get("currency") or "TRY"
        satir = (
            f"{k.get('symbol')}: {k.get('institution')} — {k.get('recommendation')}, "
            f"hedef fiyat {_tr_amount(k.get('target_price'))} {para} "
            f"({_tarih_bicimle(k.get('report_date'))} tarihli rapor"
        )
        if k.get("price_at_report") is not None:
            satir += f", rapor anındaki fiyat {_tr_amount(k['price_at_report'])} {para}"
        satir += ")"
        yon = k.get("revision_direction")
        onceki = k.get("previous_target_price")
        if yon and onceki is not None:
            satir += (
                f" — önceki hedef {_tr_amount(onceki)} {para}'den "
                f"{_HEDEF_FIYAT_YON_METNI.get(yon, yon)}"
            )
        satirlar.append("- " + satir)

    eksik = list(data.get("unknown_symbols") or []) + list(data.get("symbols_without_data") or [])
    if eksik:
        satirlar.append("Hedef fiyatı bulunamayan: " + ", ".join(eksik))

    if not satirlar:
        return "Hedef fiyat: istenen varlık için kayıt yok."
    return "Hedef fiyat / analist tavsiyesi\n" + "\n".join(satirlar)


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

        # HEDEF FİYAT SORUSU RAG'E GİTMEZ, GÜNCEL FİYAT YOLUNA DA DÜŞMEZ.
        #
        # fiyat_niyeti() bu sorguları zaten kendi kapsamı dışında bırakıyor
        # (bkz. price_query.py _ICERIK_KELIMELERI_RE'deki "hedef fiyat"
        # bloğu) — burada AYRICA kontrol edilir çünkü bu, RAG dokümanlarında
        # DEĞİL, target_prices tablosunda yaşayan üçüncü bir veri sınıfı
        # (bkz. app/services/target_price_ingest.py docstring'i: neden RAG
        # değil).
        if (hedef_sirket := hedef_fiyat_niyeti(request.query)) is not None:
            return await self._hedef_fiyat_yaniti(hedef_sirket)

        # DEĞERLEME ÇARPANLARI DA RAG'E GİTMEZ — hedef fiyatla aynı gerekçe:
        # F/K, PD/DD, marjlar dokümanlarda değil `get_fundamentals`'ta
        # (yfinance) yaşıyor. Ölçüldü (1 Eylül 2026): doğrudan sorulduğunda
        # bu ajan "elimdeki belgelerde yer almıyor" diyor, aynı oturumda
        # Analist Ajanı aynı şirketin F/K'sını veriyordu.
        if (oran_sirketi := temel_oran_niyeti(request.query)) is not None:
            return await self._temel_oran_yaniti(oran_sirketi)

        # "BUNU ALABİLİR MİYİM?" SORUSU DA RAG'E GİTMEZ. Cevabı sistemin
        # kendi verisinde: varlığın uygunluk seviyesi + kullanıcının anket
        # puanı + `tradable` bayrağı. Ölçüldü (1 Eylül 2026): "Serbest fon
        # alabilir miyim?" ve "BIST 100 endeksinden alabilir miyim?"
        # Web Araştırma Ajanı'na düşüp ansiklopedik cevap aldı, oysa doğru
        # cevap elimizdeydi (puan 6, serbest fon seviye 7 — alamaz).
        if (uygunluk_sembolu := uygunluk_niyeti(request.query)) is not None:
            return await self._uygunluk_yaniti(uygunluk_sembolu, request.user_id)

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
        istenen_sirket = filtreler.get("sirket")
        if not tool_result.get("success") and filtreler:
            tool_result = await self.call_mcp_tool(
                "search_market_news", {"query": request.query, **ek_args}
            )

            # GÜVENLİK AĞI: filtresiz yedek deneme başka bir şirketin
            # dokümanını "ilgili" diye sunmasın (bkz. _yanlis_sirket_sonuclarini_ele).
            if istenen_sirket and tool_result.get("success"):
                ham_sonuclar = tool_result["data"].get("results") or []
                elenmis = _yanlis_sirket_sonuclarini_ele(ham_sonuclar, istenen_sirket)
                if not elenmis:
                    tool_result = {
                        "success": False,
                        "error": {"message": f"{istenen_sirket} için kayıt bulunamadı."},
                    }
                elif len(elenmis) != len(ham_sonuclar):
                    tool_result = {
                        **tool_result,
                        "data": {**tool_result["data"], "results": elenmis},
                    }

        if not tool_result.get("success"):
            error = tool_result.get("error", {})
            return self.error_response(error.get("message", "Piyasa verisi alınamadı"))

        data = tool_result["data"]
        results = data.get("results") or []
        summary_text = await self._summarize(request.query, results, on_token=on_token)

        # Profil-uygunluk bilgilendirmesi: ANKET DOLU OLDUĞU HER şirket
        # sorusunda çalışır (bkz. modül docstring'i "2026-08-28 eki") —
        # güncellik şartına bağlı değildir, KAP bloğundan bağımsız bir kontrol.
        uygunsuz_sinif: str | None = None
        if istenen_sirket:
            risk_survey_score = await self._fetch_risk_survey_score(request.user_id)
            uygunsuz_sinif = _sirket_varlik_sinifi_uygunluk_disi_mi(
                istenen_sirket, risk_survey_score
            )
            if uygunsuz_sinif is not None:
                uygunluk_blok = _uygunluk_blogu(uygunsuz_sinif)
                summary_text += uygunluk_blok
                if on_token is not None:
                    on_token(uygunluk_blok)

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
        if uygunsuz_sinif is not None:
            data = {**data, "uygunluk_disi_sinif": uygunsuz_sinif}

        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text=summary_text,
            data=data,
        )

    async def _fetch_risk_survey_score(self, user_id: str) -> int | None:
        """Profil-uygunluk kontrolü için anket puanını okur.

        `get_user_risk_survey` YAN ETKİSİZDİR (bkz. mcp_server/tools/
        risk_tools.py) — tekrar tekrar çağrılabilir, tüketen bir "olay" değil.
        Herhangi bir hata (tool başarısızlığı, bağlantı) ana akışı ASLA
        düşürmemeli: sessizce `None` döner, kontrol atlanır (bkz.
        agents/portfolio_agent.py::_fetch_risk_survey_score, aynı ilke).
        """
        try:
            sonuc = await self.call_mcp_tool("get_user_risk_survey", {"user_id": user_id})
        except Exception:
            return None
        if not sonuc.get("success"):
            return None
        return (sonuc.get("data") or {}).get("risk_survey_score")

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
            # SORULAN PENCERE TOOL'A GEÇER. Geçmiyordu: tool varsayılanı 3 ay
            # olduğu için "Dolar son bir yılda ne yaptı?" sorusu *"son bir
            # yıllık performansı bulunmuyor"* deyip 3 aylık veriyi veriyordu
            # (ölçüldü, 1 Eylül 2026) — bir yıllık seri veritabanında
            # dururken. Pencere anlaşılamadıysa geçilmez, tool kendi
            # varsayılanını kullanır; burada tahmin üretilmez.
            if niyet.get("window"):
                args["window"] = niyet["window"]
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

    async def _hedef_fiyat_yaniti(self, sirket: str) -> AgentResponse:
        """Hedef fiyat/analist tavsiyesi yanıtı — LLM DEVREDE DEĞİL (bkz.
        _fiyat_yaniti ile aynı gerekçe: ara bir LLM çağrısı rakamı yeniden
        yazma riski taşır)."""
        tool_result = await self.call_mcp_tool("get_target_prices", {"symbols": [sirket]})
        if not tool_result.get("success"):
            error = tool_result.get("error", {})
            return self.error_response(error.get("message", "Hedef fiyat verisi alınamadı"))

        data = tool_result["data"]
        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text=_render_hedef_fiyat(data),
            data=data,
        )

    async def _uygunluk_yaniti(self, sembol: str, user_id: str) -> AgentResponse:
        """ "Bunu alabilir miyim?" — LLM DEVREDE DEĞİL.

        Üç kaynak birleşiyor, üçü de deterministik: varlığın evren tanımı
        (`SPEC_BY_SYMBOL`), uygunluk seviyesi (`advice_eligibility`) ve
        kullanıcının anket puanı. Anket doldurulmamışsa puan uydurulmaz —
        durum dürüstçe söylenir (AK 5.5).
        """
        spec = SPEC_BY_SYMBOL.get(sembol)
        if spec is None:
            return self.error_response(f"{sembol} için varlık tanımı bulunamadı.")

        seviye = asset_risk_level(sembol, spec.asset_class)
        puan = await self._fetch_risk_survey_score(user_id)

        satirlar = [f"{spec.symbol} — {spec.name}"]

        # TUTULABİLİRLİK ÖNCE GELİR: uygunluk puanı ne olursa olsun
        # satın alınamayan bir varlıkta puan tartışması anlamsızdır.
        if not spec.tradable:
            satirlar.append(
                "Bu varlık satın alınamaz; fiyatı takip ediliyor ve "
                "karşılaştırma için kullanılıyor, ama portföye eklenemez."
            )
            return AgentResponse(
                agent_name=self.agent_name,
                success=True,
                summary_text="\n".join(satirlar),
                data={"symbol": sembol, "tradable": False, "uygunluk_seviyesi": seviye},
            )

        satirlar.append(f"Uygunluk seviyesi: {seviye}")
        if puan is None:
            satirlar.append(
                "Risk anketiniz henüz doldurulmadığı için uygunluk "
                "karşılaştırması yapılamıyor; anketi doldurduğunuzda bu soru "
                "kesin olarak cevaplanabilir."
            )
        else:
            satirlar.append(f"Sizin risk puanınız: {puan}")
            if is_asset_advice_allowed(sembol, spec.asset_class, puan):
                satirlar.append("Bu varlık risk puanınızın kapsamındadır.")
            else:
                satirlar.append(
                    f"Bu varlık risk puanınızın kapsamı dışında: seviyesi {seviye}, "
                    f"puanınız {puan}. Kapsam dışı varlıklar için öneri üretilmez."
                )

        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text="\n".join(satirlar),
            data={
                "symbol": sembol,
                "tradable": True,
                "uygunluk_seviyesi": seviye,
                "risk_survey_score": puan,
            },
        )

    async def _temel_oran_yaniti(self, sirket: str) -> AgentResponse:
        """Değerleme çarpanları yanıtı — LLM DEVREDE DEĞİL (`_hedef_fiyat_yaniti`
        ile aynı gerekçe: ara bir LLM çağrısı rakamı yeniden yazma riski
        taşır)."""
        tool_result = await self.call_mcp_tool("get_fundamentals", {"symbols": [sirket]})
        if not tool_result.get("success"):
            error = tool_result.get("error", {})
            return self.error_response(error.get("message", "Temel analiz verisi alınamadı"))

        data = tool_result["data"]
        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text=_render_temel_oranlar(sirket, data),
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
        #
        # AMA "belgelerde yok" cevabına kaynak eklenmez: o kaynaklar cevabı
        # DESTEKLEMİYOR, aksine cevapla çelişiyor (bkz. _kaynak_kullanilmadi_mi).
        if _kaynak_kullanilmadi_mi(full_text):
            return full_text

        kaynaklar = _kaynak_blogu(results)
        if kaynaklar:
            full_text += kaynaklar
            if on_token is not None:
                on_token(kaynaklar)

        return full_text
