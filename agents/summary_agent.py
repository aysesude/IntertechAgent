"""Özet Ajanı: "Hızlı Özet" panelinin dört kartını üretir.

KENDİ SAYISI OLMAYAN AJAN. Bu, ajanın tanımıdır ve kodla garanti edilir:

- Hiçbir hesap yapmaz. Diğer ajanların kullandığı AYNI MCP tool'larını çağırır
  ve dönen değerleri olduğu gibi taşır.
- LLM yalnızca CÜMLEYİ kurar. Ürettiği metindeki her sayı, kendisine verilen
  deterministik bloğun içinde birebir geçmek ZORUNDADIR; geçmiyorsa o kart
  LLM metnini değil deterministik özeti gösterir (`_sayilari_dogrula`).

NEDEN BU KADAR SIKI. 1 Eylül 2026 sohbet turunun en pahalı bulgusu (K3) şuydu:
aynı soruya iki ajan iki farklı cevap veriyordu — biri "F/K belgelerde yok"
derken diğeri sayıyı veriyordu. Özet kartları sohbetteki ajanlarla AYNI
portföy hakkında konuşacak; kart ile sohbet farklı sayı söylerse aynı hata
ürün düzeyinde geri gelir. Sayı doğrulaması bunu prompt'a güvenerek değil,
YAPISAL olarak engelliyor.

ORCHESTRATOR'A BAĞLI DEĞİL. Tetikleyici deterministik (kullanıcı düğmeye
basar), dolayısıyla niyet sınıflandırmasına gerek yok. Sohbet grafiğine
eklenmemesi bilinçli: panelin üretimi sohbet geçmişini kirletmemeli.

DÖRT KART, DÖRT İŞ BÖLÜMÜ (prompt'ta da yazılı):
    genel   ZAMAN     ne değişti            get_portfolio_summary + performance
    portfoy YAPI      neye sahipsin         get_holdings
    piyasa  DIŞARISI  hangi gelişme var     get_portfolio_news
    risk    ÖLÇÜ      profille aran nasıl   get_risk_assessment

DÖRT AYRI LLM ÇAĞRISI, PARALEL. Panelin bütün maliyeti LLM'de: ölçüm (test
sunucusu, 2 Eylül 2026) tool'lar 0,3 sn, LLM 29,5 sn. Tek çağrıda dört kartın
metni arka arkaya yazılıyordu; bölününce süre en uzun tek karta iniyor ve
kartlar ek süre maliyeti olmadan uzayabiliyor. Ayrıntı: `_llm_metinleri`.
"""

import asyncio
import logging
import re
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

from agents.base import BaseAgent
from agents.formatting import ASSET_CLASS_TR as _ASSET_CLASS_TR
from agents.formatting import tr_amount as _tr_amount
from agents.formatting import tr_date as _tr_date
from agents.formatting import tr_percent as _tr_percent
from app.core.llm_client import get_llm_client

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "summary_agent.md").read_text(
    encoding="utf-8"
)

# Model düz metin yazmalı ama bazen çıktıyı kod çitine alıyor; savunma
# amaçlı temizleniyor.
_KOD_CITI = re.compile(r"^```(?:json|markdown)?|```$", re.MULTILINE)

# Metinden sayı çıkarma. Türkçe biçimde binlik nokta, ondalık virgül:
# "1.583.703,56" tek bir sayıdır, "1", "583" ve "703" değil.
#
# Sayının ÖLÇÜM mü yoksa dilin parçası mı olduğu ayırt ediliyor: başında "%"
# ya da sonunda para birimi varsa o bir ölçümdür ve muafiyeti yoktur.
_SAYI_RE = re.compile(r"(%\s*)?(\d[\d.,]*)\s*(TL|₺)?")

# Muafiyet YALNIZCA ölçüm olmayan küçük TAM sayılara. "üç varlık", "2. çeyrek",
# "ilk 3 pozisyon" gibi ifadeler neredeyse her metinde geçiyor ve bunları
# blokta birebir aramak doğrulamayı gereksiz yere sertleştirirdi.
#
# ONDALIKLI SAYI ASLA MUAF DEĞİL: ölçümler ondalık taşır. İlk sürümde eşik
# ondalıklara da uygulanıyordu ve uydurma bir "%4,10" doğrulamadan geçti
# (kendi testinde yakalandı) — yüzdeler tam da korunması gereken değerler.
_MUAFIYET_ESIGI = 10

KART_SIRASI = ("genel", "portfoy", "piyasa", "risk")

KART_BASLIKLARI = {
    "genel": "Genel Durum",
    "portfoy": "Portföyünüz",
    "piyasa": "Piyasa",
    "risk": "Risk",
}

# Her kartın GÖREVİ. Kartlar artık AYRI çağrılarda yazıldığı için hiçbiri
# diğerinin metnini göremiyor; tekrarı engelleyen tek şey bu tablonun her
# prompt'a "seninki bu, diğerleri şunlar" diye yazılması.
KART_GOREVLERI = {
    "genel": "ZAMAN. Ne oldu, ne değişti, dönem içinde nereye geldi.",
    "portfoy": "YAPI. Neye sahip, dağılım nasıl, ağırlık nerede toplanmış.",
    "piyasa": "DIŞARISI. Elindeki varlıklarla ilgili hangi gelişme var, "
    "kaynak belgeler ne söylüyor.",
    "risk": "ÖLÇÜ. Risk seviyesi, profiliyle arasındaki fark ve sebebi.",
}


def _normalize_sayi(ham: str) -> str:
    """Karşılaştırma biçimden bağımsız olmalı: blokta "1.583.703,56" yazarken
    modelin "1583703,56" yazması bir uydurma değil, biçim farkıdır. Binlik
    ayraçları atılıyor ve sondaki sıfırlar kırpılıyor ("26,70" = "26,7")."""
    sade = ham.strip(".,").replace(".", "")
    if "," in sade:
        tam, _, kesir = sade.partition(",")
        kesir = kesir.rstrip("0")
        sade = f"{tam},{kesir}" if kesir else tam
    return sade


def _sayilari_cikar(metin: str) -> set[str]:
    """Metindeki tüm sayılar (ölçüm olsun olmasın), normalleştirilmiş."""
    return {sade for _, ham, _ in _SAYI_RE.findall(metin) if (sade := _normalize_sayi(ham))}


def _sayilari_dogrula(cikti: str, girdi: str) -> bool:
    """Çıktıdaki her sayı girdide geçiyor mu?

    Bu fonksiyon ajanın SÖZLEŞMESİDİR (bkz. modül docstring'i): "kendi sayısı
    olmayan ajan" vaadi prompt'a güvenilerek değil burada denetleniyor.

    Muafiyet yalnızca ÖLÇÜM OLMAYAN küçük tam sayılara (bkz.
    `_MUAFIYET_ESIGI`): "%" ya da para birimi taşıyan bir sayı her boyutta
    doğrulanır.
    """
    izinli = _sayilari_cikar(girdi)
    for yuzde, ham, birim in _SAYI_RE.findall(cikti):
        sade = _normalize_sayi(ham)
        if not sade or sade in izinli:
            continue

        olcum = bool(yuzde or birim or "," in sade)
        if not olcum:
            try:
                if abs(float(sade)) < _MUAFIYET_ESIGI:
                    continue
            except ValueError:
                pass

        logger.warning("[AJAN] summary: veride olmayan sayı üretildi: %s", ham)
        return False
    return True


def _satir(
    etiket: str,
    deger: Any,
    bicim: Callable[[Any], str] = str,
    *,
    son_ek: str = "",
) -> str | None:
    """Değer yoksa satır HİÇ üretilmez.

    HAM DEĞER ALIR, biçimlenmiş metin DEĞİL. İlk sürüm biçimlenmiş metni
    alıyordu ve `tr_amount(None)` boş dize değil `"—"` döndürdüğü için satır
    "Toplam değer: — TL" olarak üretiliyordu; boş bir portföyde risk kartı
    "Profil bandı içinde mi: hayır" diyordu — ölçülmemiş bir şeyi ölçülmüş
    gibi sunmak (kendi testinde yakalandı). Kontrol ham değerde yapılmalı.
    """
    if deger is None or deger == "":
        return None
    return f"{etiket}: {bicim(deger)}{son_ek}"


def _imzali_yuzde(deger: Any) -> str:
    return _tr_percent(deger, signed=True)


def _blok_genel(veri: dict[str, Any]) -> list[str]:
    ozet = veri.get("summary") or {}
    perf = veri.get("performance") or {}
    perf_ozet = perf.get("summary") or {}
    degisimler = perf_ozet.get("changes") or {}
    kz = ozet.get("total_gain_loss") or {}

    satirlar = [
        _satir("Toplam değer", ozet.get("total_value"), _tr_amount, son_ek=" TL"),
        _satir("Fiyat tarihi", ozet.get("as_of"), _tr_date),
        _satir("Yatırılan tutar", ozet.get("net_invested"), _tr_amount, son_ek=" TL"),
        _satir("Serbest nakit", ozet.get("cash_try"), _tr_amount, son_ek=" TL"),
        _satir("Dönem getirisi", perf_ozet.get("change_percent"), _imzali_yuzde),
        _satir("Günlük değişim", degisimler.get("daily"), _imzali_yuzde),
        _satir("Haftalık değişim", degisimler.get("weekly"), _imzali_yuzde),
    ]

    # İki değerli satırlar: ikisi de varsa yazılır, biri eksikse yarım bir
    # ifade ("333.703,56 TL (—)") üretilmez.
    if kz.get("amount") is not None and kz.get("percent") is not None:
        satirlar.append(
            f"Toplam kâr/zarar: {_tr_amount(kz['amount'])} TL ({_imzali_yuzde(kz['percent'])})"
        )
    if perf.get("series_start") and perf.get("as_of"):
        satirlar.append(f"Dönem: {_tr_date(perf['series_start'])} – {_tr_date(perf['as_of'])}")

    return [s for s in satirlar if s]


def _blok_portfoy(veri: dict[str, Any]) -> list[str]:
    holdings = veri.get("holdings") or {}
    satirlar: list[str] = []

    # En büyük üç pozisyon: servis zaten büyükten küçüğe sıralı döndürüyor,
    # burada yeniden sıralama YAPILMIYOR (sıralama bir yargıdır ve serviste
    # verildi).
    for row in (holdings.get("holdings") or [])[:3]:
        if row.get("price_missing"):
            continue
        satirlar.append(
            f"{row.get('symbol')} ({_ASSET_CLASS_TR.get(row.get('asset_class'), '—')}): "
            f"ağırlık {_tr_percent(row.get('weight_percent'))}, "
            f"K/Z {_tr_percent(row.get('unrealized_pnl_percent'), signed=True)}"
        )

    nakit = _satir("Serbest nakit ağırlığı", holdings.get("cash_weight_percent"), _tr_percent)
    if nakit:
        satirlar.append(nakit)

    for etiket, anahtar in (
        ("En çok kazandıran", "best_performer"),
        ("En çok kaybettiren", "worst_performer"),
    ):
        item = holdings.get(anahtar)
        if item:
            satirlar.append(
                f"{etiket}: {item.get('symbol')} "
                f"{_tr_percent(item.get('unrealized_pnl_percent'), signed=True)}"
            )

    haric = holdings.get("excluded_symbols") or []
    if haric:
        satirlar.append("Fiyatı alınamayan: " + ", ".join(haric))
    return satirlar


# Doküman metninden alınacak en fazla karakter. Kart "haber yorumu yok, sadece
# başlık sıralıyor" diye bildirildi (sahada ölçüldü, 2 Eylül 2026) — sebebi
# modelin yetersizliği değil, BLOĞUN İÇERİK TAŞIMAMASIYDI: LLM'e yalnızca
# başlık/kaynak/tarih veriliyor, yorumlayacağı metin hiç verilmiyordu.
#
# Sınır var çünkü tam metinler uzun ve kartın işi belgeyi aktarmak değil.
# Kesme CÜMLE SONUNDA yapılıyor: yarım kalan bir cümle modeli, olmayan bir
# devamı tamamlamaya davet eder.
_DOKUMAN_METIN_SINIRI = 320
_PIYASA_VARLIK_SAYISI = 4
_PIYASA_DOKUMAN_SAYISI = 2


def _metin_kirp(metin: Any) -> str:
    """Sınıra kadar kırpar, son tam cümlede biter."""
    if not isinstance(metin, str):
        return ""
    duz = " ".join(metin.split())
    if len(duz) <= _DOKUMAN_METIN_SINIRI:
        return duz
    kesik = duz[:_DOKUMAN_METIN_SINIRI]
    son = max(kesik.rfind(". "), kesik.rfind("! "), kesik.rfind("? "))
    # Cümle sonu çok başta kaldıysa kırpma metnin neredeyse tamamını atardı;
    # o durumda kelime sınırında kesip açıkça devamı olduğunu belirtiyoruz.
    if son > _DOKUMAN_METIN_SINIRI // 2:
        return kesik[: son + 1]
    return kesik.rsplit(" ", 1)[0] + "…"


def _blok_piyasa(veri: dict[str, Any]) -> list[str]:
    haberler = veri.get("news") or {}
    satirlar: list[str] = []
    for varlik in (haberler.get("assets") or [])[:_PIYASA_VARLIK_SAYISI]:
        for dokuman in (varlik.get("documents") or [])[:_PIYASA_DOKUMAN_SAYISI]:
            baslik = (
                f"{varlik.get('symbol')} [{dokuman.get('tur') or 'belge'}]: "
                f"{dokuman.get('baslik')} "
                f"({dokuman.get('kaynak')}, {_tr_date(dokuman.get('tarih'))})"
            )
            icerik = _metin_kirp(dokuman.get("content"))
            # İçerikteki sayılar KAYNAKLIDIR: belgeden geliyor, uydurma değil.
            # Bloğa girdikleri için sayı doğrulaması da onlara izin verir ve
            # kart bir bilanço rakamını gerekçe göstererek konuşabilir.
            satirlar.append(f"{baslik}\n  {icerik}" if icerik else baslik)

    kapsanan = haberler.get("covered_weight_percent")
    if kapsanan is not None:
        satirlar.append(f"Belgesi olan varlıkların portföydeki payı: {_tr_percent(kapsanan)}")
    # `confidence: low` portföyün büyük kısmı için kaynak OLMADIĞI anlamına
    # geliyor ve tool sözleşmesi bunun kullanıcıya söylenmesini istiyor.
    if haberler.get("confidence") == "low":
        satirlar.append("Uyarı: portföyün büyük kısmı için kaynak doküman yok.")
    return satirlar


def _blok_risk(veri: dict[str, Any]) -> list[str]:
    risk = veri.get("risk") or {}
    metrikler = risk.get("metrics") or {}
    satirlar = [
        _satir("Risk seviyesi", risk.get("risk_level")),
        _satir("Risk profili", risk.get("risk_profile")),
        _satir(
            "Yıllık volatilite",
            metrikler.get("annualized_volatility_percent"),
            _tr_percent,
        ),
        _satir("VaR", metrikler.get("value_at_risk_try"), _tr_amount, son_ek=" TL"),
        _satir("En büyük pozisyon", metrikler.get("max_asset_symbol")),
        _satir(
            "En büyük pozisyonun ağırlığı",
            metrikler.get("max_asset_weight_percent"),
            _tr_percent,
        ),
    ]

    # ÜÇ DURUMLU alan: True/False/None. `None` "hesaplanamadı" demek ve
    # "hayır"a çevrilemez — ölçülmemiş bir uyumsuzluk iddiası olurdu.
    if risk.get("is_within_profile") is not None:
        satirlar.append(
            "Profil bandı içinde mi: " + ("evet" if risk["is_within_profile"] else "hayır")
        )
    uyumsuz = risk.get("mismatched_holdings") or []
    if uyumsuz:
        satirlar.append(
            "Profiline uymayan varlıklar: " + ", ".join(str(k.get("symbol") or k) for k in uyumsuz)
        )
    return [s for s in satirlar if s]


_BLOK_URETICILERI = {
    "genel": _blok_genel,
    "portfoy": _blok_portfoy,
    "piyasa": _blok_piyasa,
    "risk": _blok_risk,
}

_VERI_YOK = "Bu kart için yeterli veri alınamadı."


def _diger_kartlar(kart_id: str) -> str:
    """Bir kartın prompt'una diğer üçünün konusunu yazar — tekrarı engelleyen
    tek mekanizma bu (kartlar ayrı çağrılarda yazılıyor, birbirlerini
    göremiyorlar)."""
    return "\n".join(
        f"- {KART_BASLIKLARI[k]}: {KART_GOREVLERI[k]}" for k in KART_SIRASI if k != kart_id
    )


class SummaryAgent(BaseAgent):
    """Bkz. modül docstring'i. `execute` YOK: bu ajan sohbet grafiğinde değil,
    kendi ucundan (`/api/insight`) çağrılıyor ve `AgentResponse` değil kart
    listesi üretiyor."""

    agent_name = "summary"

    async def execute(self, request, *, on_token=None):
        """Bu ajan sohbet grafiğinde DEĞİL; giriş noktası `kartlari_uret`.

        `BaseAgent.execute` soyut olduğu için burada tanımlanmak zorunda ama
        anlamlı bir karşılığı yok: ajanın çıktısı tek bir `AgentResponse`
        değil, dört karttan oluşan bir liste ve tetikleyicisi bir sohbet
        mesajı değil bir düğme. Sessizce boş yanıt döndürmek yerine açıkça
        patlıyor — biri onu grafiğe eklemeye kalkarsa hemen görsün.
        """
        raise NotImplementedError(
            "SummaryAgent sohbet akışında kullanılmaz; `kartlari_uret` çağırın."
        )

    async def kartlari_uret(self, user_id: str) -> list[dict[str, Any]]:
        """Dört kartı üretir. Hiçbir koşulda boş liste dönmez."""
        # AŞAMA SÜRELERİ ÖLÇÜLÜYOR. "Özet alınamadı" bildirildiğinde sebebin
        # tool'lar mı yoksa LLM mi olduğunu tahmin etmek yerine log'dan
        # okuyabilmek için (2 Eylül 2026).
        t0 = perf_counter()
        bloklar = await self._deterministik_bloklar(user_id)
        t1 = perf_counter()
        metinler = await self._llm_metinleri(bloklar)
        logger.info("[AJAN] summary: tool'lar %.1f sn, LLM %.1f sn", t1 - t0, perf_counter() - t1)

        kartlar: list[dict[str, Any]] = []
        for kart_id in KART_SIRASI:
            satirlar = bloklar.get(kart_id) or []
            metin = metinler.get(kart_id)
            # Blok boşsa LLM metnine güvenilemez: dayanacağı veri yok.
            if metin and satirlar:
                kartlar.append(
                    {
                        "id": kart_id,
                        "title": KART_BASLIKLARI[kart_id],
                        "body": metin,
                        "degraded": False,
                    }
                )
            else:
                kartlar.append(
                    {
                        "id": kart_id,
                        "title": KART_BASLIKLARI[kart_id],
                        "body": "\n".join(satirlar) if satirlar else _VERI_YOK,
                        "degraded": True,
                    }
                )
        return kartlar

    async def _deterministik_bloklar(self, user_id: str) -> dict[str, list[str]]:
        """Beş tool paralel çağrılır; biri düşerse yalnızca kendi kartı
        etkilenir (zarif düşüş)."""
        cagrilar = {
            "summary": ("get_portfolio_summary", {"user_id": user_id}),
            "performance": ("get_portfolio_performance", {"user_id": user_id, "window": "1m"}),
            "holdings": ("get_holdings", {"user_id": user_id}),
            "risk": ("get_risk_assessment", {"user_id": user_id}),
            "news": (
                "get_portfolio_news",
                {"user_id": user_id, "per_asset": _PIYASA_DOKUMAN_SAYISI},
            ),
        }
        sonuclar = await asyncio.gather(
            *(self.call_mcp_tool(ad, arg) for ad, arg in cagrilar.values()),
            return_exceptions=True,
        )

        veri: dict[str, Any] = {}
        for anahtar, sonuc in zip(cagrilar, sonuclar):
            if isinstance(sonuc, Exception):
                logger.warning("[AJAN] summary: %s düştü — %s", anahtar, sonuc)
                continue
            if isinstance(sonuc, dict) and sonuc.get("success"):
                veri[anahtar] = sonuc.get("data")

        return {kart: uretici(veri) for kart, uretici in _BLOK_URETICILERI.items()}

    async def _llm_metinleri(self, bloklar: dict[str, list[str]]) -> dict[str, str]:
        """Kart metinlerini alır. KART BAŞINA BİR ÇAĞRI, DÖRDÜ PARALEL.

        NEDEN TEK ÇAĞRI DEĞİL — bu bir hız düzeltmesi. Ölçüm (test sunucusu,
        2 Eylül 2026): tool'lar 0,3 sn, LLM 29,5 sn. Yani panelin bütün
        maliyeti tek bir üretimde ve orada süreyi belirleyen, ÜRETİLEN TOKEN
        SAYISIDIR. Dört kartın metnini tek çağrıda arka arkaya yazdırmak,
        dördünü sırayla beklemek demekti.

        Bölündüğünde LLM aşaması dört kartın toplamı yerine EN UZUN TEK KARTA
        iner. Üç yan faydası var: (1) kartlar uzayabiliyor, çünkü ek metin
        artık toplam süreye eklenmiyor; (2) her çağrı yalnızca kendi bloğunu
        taşıdığı için piyasa kartının uzun belge alıntıları diğer üç çağrıyı
        şişirmiyor; (3) JSON ayrıştırma kırılganlığı ortadan kalkıyor —
        model artık düz metin yazıyor.

        Bedeli TEKRAR RİSKİ: kartlar birbirinin metnini göremiyor. Prompt her
        çağrıda "senin işin bu, diğerlerininki şu" diyerek bunu kapatıyor
        (`KART_GOREVLERI`).

        Bir kartın çağrısı düşerse yalnızca o kart deterministik özete iner;
        `return_exceptions=True` bunun için.
        """
        dolu = {k: v for k, v in bloklar.items() if v}
        if not dolu:
            return {}

        istemci = get_llm_client()
        sonuclar = await asyncio.gather(
            *(self._tek_kart(istemci, k, v) for k, v in dolu.items()),
            return_exceptions=True,
        )

        gecerli: dict[str, str] = {}
        for kart_id, sonuc in zip(dolu, sonuclar):
            if isinstance(sonuc, Exception):
                logger.warning("[AJAN] summary: %s kartı yazılamadı — %s", kart_id, sonuc)
                continue
            if sonuc:
                gecerli[kart_id] = sonuc
        return gecerli

    async def _tek_kart(self, istemci: Any, kart_id: str, satirlar: list[str]) -> str | None:
        """Bir kartın metnini üretir; doğrulamadan geçmezse `None`."""
        prompt = (
            _PROMPT_TEMPLATE.replace("{{kart_basligi}}", KART_BASLIKLARI[kart_id])
            .replace("{{kart_gorevi}}", KART_GOREVLERI[kart_id])
            .replace("{{diger_kartlar}}", _diger_kartlar(kart_id))
            .replace("{{veriler}}", "\n".join(satirlar))
        )

        ham = await istemci.generate("Kartı yaz.", system=prompt)
        metin = _KOD_CITI.sub("", (ham or "").strip()).strip()
        if not metin:
            return None

        # SAYI DOĞRULAMASI KART BAZINDA. Bir kartta uydurma sayı varsa yalnızca
        # o kart düşer; diğer üçü cezalandırılmaz.
        if not _sayilari_dogrula(metin, "\n".join(satirlar)):
            return None
        return metin
