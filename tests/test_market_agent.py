"""agents/market_agent.py: filtresiz yedek aramanın çapraz-şirket güvenlik ağı.

`_yanlis_sirket_sonuclarini_ele` deterministik ve saf bir fonksiyon — LLM
yok, tamamen kural tabanlı (bkz. market_query.py'nin modül başlığındaki
"yanlış bir çıkarım sessiz bir hataya dönüşür" ilkesiyle aynı gerekçe).

2026-08-27, analist test turunda ölçülen bir hatayı önlüyor: "İş Bankası'nın
kurucusu kimdir" sorusu, RAG'de İş Bankası için yeterli doküman olmadığından
`execute()`'un filtresiz yedek aramasına düşmüş ve retriever'ın mesafe+
kelime-örtüşme eşiği (LEKSİK, şirket kimliğine değil) "kurucu" kelimesini
paylaştığı için ASELSAN'ın kuruluş belgesini yanlışlıkla "ilgili" sayıp
cevap diye sunmuştu (bkz. _yanlis_sirket_sonuclarini_ele docstring'i,
agents/market_agent.py).
"""

from agents.market_agent import _yanlis_sirket_sonuclarini_ele


def _parca(sirket: str | None, baslik: str = "belge") -> dict:
    return {"content": "...", "metadata": {"sirket": sirket, "baslik": baslik}}


def test_dogru_sirketin_sonuclari_dokunulmadan_kalir():
    sonuclar = [_parca("ASELS"), _parca("ASELS")]
    assert _yanlis_sirket_sonuclarini_ele(sonuclar, "ASELS") == sonuclar


def test_baska_sirketin_sonucu_elenir():
    """Regresyon: "İş Bankası'nın kurucusu kimdir" sorusu ASELSAN'ın kuruluş
    belgesini döndürmüştü (ölçüldü, 2026-08-27)."""
    sonuclar = [_parca("ASELS", "ASELSAN Kuruluş Bilgisi")]
    assert _yanlis_sirket_sonuclarini_ele(sonuclar, "ISCTR") == []


def test_sirketsiz_genel_belgeler_dokunulmadan_kalir():
    """`sirket` alanı boş (makro/genel) parçalar başka bir şirketin dokümanı
    DEĞİLDİR, elenmemeli — yalnızca FARKLI bir şirkete ait parçalar elenir."""
    genel = _parca(None, "Enflasyon Raporu")
    assert _yanlis_sirket_sonuclarini_ele([genel], "ISCTR") == [genel]


def test_karisik_sonuclarda_yalnizca_yanlis_sirket_elenir():
    dogru = _parca("ISCTR", "İş Bankası Şirket Profili")
    yanlis = _parca("ASELS", "ASELSAN Kuruluş Bilgisi")
    genel = _parca(None, "BIST 100 Genel Görünüm")
    assert _yanlis_sirket_sonuclarini_ele([dogru, yanlis, genel], "ISCTR") == [dogru, genel]


def test_bos_liste_bos_doner():
    assert _yanlis_sirket_sonuclarini_ele([], "ISCTR") == []
