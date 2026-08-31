"""Şeker Yatırım "Tavsiye Listesi" sağlayıcısı — bkz. app/services/
target_price_ingest.py modül docstring'i (neden bu kaynak, neden RAG değil,
lisans notu).

Sayfa (`sekeryatirim.com.tr/Arastirma/TavsiyeListesi`) statik HTML, herkese
açık, kurumun KENDİ yayımladığı bir sayfa — abonelik gerektiren toplayıcı
sitelerden (Fintables/Finemar) farklı, kazıma yasağı yok. Yapı elle
doğrulandı (2026-08-28, gerçek sayfa fetch edilerek): üç sektör tablosu
(BANKA/HOLDİNG/SANAYİ), her biri aynı `tavsiyeListesi` sınıfını taşıyor,
satır başına 9 hücre (kod, tavsiye, kapanış, hedef, ...); sayfa üstünde tek
bir `rapor-tarih` etiketi var (hisse başına ayrı tarih YOK — kaynağın kendi
granülaritesi bu).

BeautifulSoup gibi yeni bir bağımlılık eklenmedi (lock dosyası/Docker imajı
yeniden derlemesi gerektirirdi); basit, elle doğrulanmış regex ile
ayrıştırılıyor. Sayfa yapısı değişirse (`_ROW_RE` eşleşmesi düşerse)
`ProviderError` fırlatılır — sessizce boş liste dönülmez, çağıran fark
etsin.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import requests

from app.providers.base import ProviderError, TargetPricePoint

_URL = "https://www.sekeryatirim.com.tr/Arastirma/TavsiyeListesi"
_INSTITUTION = "Şeker Yatırım"
_TIMEOUT_SECONDS = 15
_USER_AGENT = "Mozilla/5.0 (compatible; IntertechAgent/1.0; +demo)"

_DATE_RE = re.compile(r'<p class="rapor-tarih">\s*(\d{2}\.\d{2}\.\d{4})\s*</p>')
_TABLE_RE = re.compile(r"<table[^>]*tavsiyeListesi[^>]*>(.*?)</table>", re.S)
_TBODY_RE = re.compile(r"<tbody>(.*?)</tbody>", re.S)
_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# Sayfa 9 sütun veriyor (kod, tavsiye, kapanış, hedef, PD, hedef PD,
# kazandırma %, F/K, PD/DD); yalnızca ilk dördü kullanılıyor.
_MIN_CELLS = 4


def _hucre_metni(html: str) -> str:
    """Hücre içindeki iç içe etiketleri (ör. tavsiye `<div class="al-icon">`)
    söker, boşluk/satır sonlarını temizler."""
    return _TAG_RE.sub("", html).strip()


def _turkce_sayi(metin: str) -> Decimal | None:
    """ "378.820" (binlik nokta) / "72,85" (ondalık virgül) -> Decimal.
    Ayrıştırılamazsa None döner (uydurma yok, satır/alan atlanır)."""
    temiz = metin.replace(".", "").replace(",", ".").strip()
    if not temiz:
        return None
    try:
        return Decimal(temiz)
    except InvalidOperation:
        return None


def _rapor_tarihi(html: str) -> date:
    m = _DATE_RE.search(html)
    if not m:
        raise ProviderError("sekeryatirim", "-", "sayfa üstü rapor tarihi bulunamadı")
    return datetime.strptime(m.group(1), "%d.%m.%Y").date()


def fetch_target_prices() -> list[TargetPricePoint]:
    """Tavsiye listesindeki TÜM satırları çeker. Ayrıştırılamayan tek tek
    satırlar (beklenmeyen hücre sayısı, sayı ayrıştırma hatası) atlanır;
    sayfanın kendisi hiç erişilemezse ya da hiç tablo/satır bulunamazsa
    `ProviderError` fırlatılır — çağıran (ingest servisi) bunu loglar."""
    try:
        yanit = requests.get(_URL, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT_SECONDS)
        yanit.raise_for_status()
    except requests.RequestException as e:
        raise ProviderError("sekeryatirim", "-", f"sayfa alınamadı: {e}") from e

    html = yanit.text
    rapor_tarihi = _rapor_tarihi(html)

    sonuclar: list[TargetPricePoint] = []
    for tablo in _TABLE_RE.findall(html):
        tbody_match = _TBODY_RE.search(tablo)
        if not tbody_match:
            continue
        for satir in _ROW_RE.findall(tbody_match.group(1)):
            hucreler = [_hucre_metni(h) for h in _CELL_RE.findall(satir)]
            if len(hucreler) < _MIN_CELLS:
                continue
            sembol, tavsiye, kapanis_ham, hedef_ham = hucreler[:4]
            sembol = sembol.strip().upper()
            if not sembol or not tavsiye:
                continue
            hedef = _turkce_sayi(hedef_ham)
            if hedef is None:
                continue
            sonuclar.append(
                TargetPricePoint(
                    symbol=sembol,
                    institution=_INSTITUTION,
                    recommendation=tavsiye.strip().upper(),
                    target_price=hedef,
                    currency="TRY",
                    price_at_report=_turkce_sayi(kapanis_ham),
                    report_date=rapor_tarihi,
                    source_url=_URL,
                )
            )

    if not sonuclar:
        raise ProviderError("sekeryatirim", "-", "sayfa alındı ama hiç satır ayrıştırılamadı")
    return sonuclar
