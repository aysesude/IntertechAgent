import re
from pathlib import Path

import yaml

from agents.market_query import sirket_gecer_mi

# Config yolunu dinamik al
CONFIG_PATH = Path(__file__).parent / "scope.yaml"


def load_scope_config():
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


scope_config = load_scope_config()

# Türkçe büyük "İ" ayrı ele alınır: "İ".lower() birleşen noktalı bir "i̇"
# üretir ve "i" ile eşleşmez ("İş Bankası" -> "i̇ş bankası").
_UPPER_DOTTED_I = str.maketrans({"İ": "i"})


def _normalize(text: str) -> str:
    return text.translate(_UPPER_DOTTED_I).lower().strip()


_SUFFIX_SAFE_MIN = 5  # bu uzunluktan itibaren sonek toleransı güvenli


def _matches_word(query: str, phrase: str, *, exact: bool = False) -> bool:
    """Kelime sınırıyla eşleşme (alt dize DEĞİL).
    ...
    """
    if exact:
        # Sonek toleransının zararlı olduğu fiiller için: "yatır" ile
        # "yatırım" ayrı kelimelerdir, ilki emir kipi ikincisi isim.
        return re.search(r"\b" + re.escape(phrase) + r"\b", query) is not None
    if len(phrase) >= _SUFFIX_SAFE_MIN:
        # "transfer" → "transferi", "kaldıraç" → "kaldıraçlı"
        pattern = r"\b" + re.escape(phrase) + r"[a-zçğıöşü]{0,6}\b"
    else:
        # "al", "sat", "aç", "çek", "öde" → tam eşleşme kalır
        pattern = r"\b" + re.escape(phrase) + r"\b"
    return re.search(pattern, query) is not None


def check_scope(query: str) -> dict:
    """
    Kullanıcı girdisini scope.yaml kurallarına göre değerlendirir.
    Dönen sözlükte:
      - 'intent': Kesin bir niyet veya durum kodu (örn. 'UNAUTHORIZED_ACTION', 'OUT_OF_SCOPE', 'pass_to_llm')
      - 'message': Eğer kapsam dışıysa kullanıcıya gösterilecek yanıt
      - 'flags': 'advice_seeking' vb. gibi ek davranış bayrakları
    Eğer kural motoru karar veremezse {"intent": "pass_to_llm"} döner.
    """
    if not scope_config:
        return {"intent": "pass_to_llm", "flags": []}

    query_lower = _normalize(query)
    words = query_lower.split()
    flags = []

    # 1. Boş Mesaj Kontrolü
    if not query_lower:
        return {
            "intent": "OUT_OF_SCOPE",
            "message": "Lütfen bir soru veya komut girin.",
            "flags": flags,
        }

    # 2. Dil Kontrolü (Basit heuristik)
    dil_config = scope_config.get("dil_kontrolu", {})
    if dil_config.get("aktif") and len(words) >= dil_config.get("min_kelime", 4):
        # Gerçek dil tespiti olmadan basit bir engelleme şimdilik yapmıyoruz (TODO)
        pass

    # 2.1 Enjeksiyon Kontrolü
    enjeksiyon = scope_config.get("enjeksiyon_kontrolu", {})
    if enjeksiyon.get("aktif"):
        varyantlar = enjeksiyon.get("varyantlar", {})
        mesajlar = scope_config.get("mesajlar", {})
        varsayilan_mesaj = mesajlar.get("out_of_scope", {}).get(
            "varsayilan",
            "Finansal danışmanınız olarak yalnızca desteklenen varlıklar hakkındaki sorularınızı yanıtlayabilirim.",
        )
        if isinstance(varsayilan_mesaj, dict):
            varsayilan_mesaj = varsayilan_mesaj.get(
                "varsayilan",
                "Finansal danışmanınız olarak yalnızca desteklenen varlıklar hakkındaki sorularınızı yanıtlayabilirim.",
            )

        for kategori, liste in varyantlar.items():
            for k in liste:
                parts = [re.escape(w) for w in k.split()]
                pattern = r".{0,30}".join(parts)
                if re.search(pattern, query_lower):
                    return {
                        "intent": "INJECTION_ATTEMPT",
                        "message": varsayilan_mesaj,
                        "flags": flags,
                    }

    # 2.2 Destek Talebi
    destek = scope_config.get("destek_talebi", {})
    if any(_matches_word(query_lower, k) for k in destek.get("etiketler", [])):
        mesajlar = scope_config.get("mesajlar", {})
        destek_mesaji = mesajlar.get("out_of_scope", {}).get(
            "destek", "Destek talepleri için Müşteri Hizmetleri ile iletişime geçebilirsiniz."
        )
        if isinstance(destek_mesaji, dict):
            destek_mesaji = destek_mesaji.get(
                "destek", "Destek talepleri için Müşteri Hizmetleri ile iletişime geçebilirsiniz."
            )
        return {"intent": "OUT_OF_SCOPE", "message": destek_mesaji, "flags": flags}

    # 3. İşlem Talebi (UNAUTHORIZED_ACTION)
    islem_talebi = scope_config.get("islem_talebi", {})
    fiiller = islem_talebi.get("fiiller", [])
    istisnalar = islem_talebi.get("istisna_kaliplari", [])

    # İstisnalar çok kelimeli kalıplar ("alayım mı") ve REDDETMEYİ ENGELLİYOR;
    # geniş eşleşme burada güvenli yönde hata yapar, alt dize kalıyor.
    is_istisna = any(istisna in query_lower for istisna in istisnalar)

    # Sonek toleransı bazı fiiller için zararlı: bkz. scope.yaml
    # `tam_eslesme_fiiller` — "yatır" toleransla "yatırım"ı yutuyordu.
    tam_eslesme = {_normalize(f) for f in islem_talebi.get("tam_eslesme_fiiller", [])}

    if not is_istisna:
        for fiil in fiiller:
            if _matches_word(query_lower, fiil, exact=_normalize(fiil) in tam_eslesme):
                return {
                    "intent": "UNAUTHORIZED_ACTION",
                    "message": "Bu işlemi gerçekleştirmeye yetkim bulunmuyor. Yalnızca portföy durumunuzu ve piyasa haberlerini analiz edebilirim.",
                    "flags": flags,
                }

    # 4. Tavsiye Bayrağı (advice_seeking)
    # Alt dize bilerek: bu kontrol REDDETMİYOR, yalnızca bayrak ekliyor.
    # Çekim ekli biçimleri ("önerin", "tavsiyeniz") yakalamak istenen davranış.
    tavsiye_config = scope_config.get("tavsiye_bayragi", {})
    tavsiye_tetikleyiciler = tavsiye_config.get("tetikleyiciler", [])

    karisik_config = scope_config.get("karisik_varlik", {})
    karsilastirma_kaliplari = karisik_config.get("karsilastirma_kaliplari", [])

    tum_tavsiye_tetikleyiciler = tavsiye_tetikleyiciler + karsilastirma_kaliplari

    if any(t in query_lower for t in tum_tavsiye_tetikleyiciler):
        flags.append("advice_seeking")

    # 5. Varlık Ekseni (Kapsam Dışı Varlık)
    varlik_siniflari = scope_config.get("varlik_siniflari", {})
    kapsam_disi_varliklar = varlik_siniflari.get("kapsam_disi", [])

    kapsam_disi_bulundu = any(
        _matches_word(query_lower, _normalize(etiket))
        for v_sinif in kapsam_disi_varliklar
        for etiket in v_sinif.get("etiketler", [])
    )

    # Eğer kapsam dışı bir varlık bulunduysa (Örn. kripto, emlak) ve kapsam içi varlık yoksa reddedelim.
    kapsam_ici_varliklar = varlik_siniflari.get("kapsam_ici", [])
    kapsam_ici_bulundu = any(
        _matches_word(query_lower, _normalize(etiket))
        for v_sinif in kapsam_ici_varliklar
        for etiket in v_sinif.get("etiketler", [])
    )

    # Bazı BIST şirketlerinin ADI, tamamen alakasız bir kapsam-dışı varlık
    # sınıfının etiketiyle kelime düzeyinde çakışıyor: "Emlak Konut" ->
    # gayrimenkul sınıfındaki "konut", "Yapı Kredi" -> bankacılık ürünleri
    # sınıfındaki "kredi". Kullanıcı "hisse"/"BIST" demeden direkt şirket
    # adını yazınca kapsam_ici hiç eşleşmiyor ve sorgu KESİN olarak (rastgele
    # değil — ölçümle doğrulandı, check_scope() deterministik) yanlışlıkla
    # reddediliyordu: "Emlak Konut'un temettü ödemesi ne zaman?" ve "Yapı
    # Kredi'nin 2026 temettüsü ne kadar?" ikisi de OUT_OF_SCOPE dönüyordu,
    # oysa RAG'de bu şirketlerin verisi doğru ve eksiksiz duruyor.
    #
    # `market_query.sirket_gecer_mi` zaten test edilmiş, deterministik bir
    # fonksiyon (RAG'in kendi filtre çıkarımı da aynı modülü kullanıyor) —
    # burada yeni bir eşleme listesi yazmak yerine o kullanılır. Sorguda
    # bilinen bir BIST şirketi tespit edilirse, sanki `bist_hisse` etiketi
    # eşleşmiş gibi kapsam içi sayılır. "konut kredisi ne kadar" gibi GERÇEK
    # kapsam-dışı sorular etkilenmez: bunlarda hiçbir şirket adı geçmiyor.
    #
    # BİLEREK `sirket_tespit_et` (tek/None) DEĞİL `sirket_gecer_mi`
    # (en az bir tane mi) kullanılıyor: "Akbank, İş Bankası ve Yapı Kredi'nin
    # ... karşılaştır" gibi 3 şirketli bir sorguda `sirket_tespit_et`
    # belirsizlik yüzünden None dönüyor (bkz. o fonksiyonun docstring'i) ve
    # "Yapı Kredi" bankacılık-ürünleri sınıfındaki "kredi" etiketiyle
    # çakışıp sorguyu yanlışlıkla OUT_OF_SCOPE'a düşürüyordu (ölçüldü,
    # 2026-08-26, analist canlı test turu).
    if not kapsam_ici_bulundu:
        kapsam_ici_bulundu = sirket_gecer_mi(query)

    if kapsam_disi_bulundu and not kapsam_ici_bulundu:
        return {
            "intent": "OUT_OF_SCOPE",
            "message": "Finansal danışmanınız olarak yalnızca desteklenen varlıklar (Hisse, Döviz, Altın vb.) hakkındaki sorularınızı yanıtlayabilirim.\nÖrnek: Portföyüm ne durumda?",
            "flags": flags,
        }

    if kapsam_disi_bulundu and kapsam_ici_bulundu:
        flags.append("kismi_kapsam")

    # 6. Smalltalk / Selamlaşma
    smalltalk = scope_config.get("mesajlar", {}).get("smalltalk_meta", {})
    smalltalk_etiketler = smalltalk.get("etiketler", [])
    if any(_matches_word(query_lower, etiket) for etiket in smalltalk_etiketler):
        return {
            "intent": "SMALLTALK_META",
            "message": smalltalk.get(
                "varsayilan",
                "Merhaba! Portföyünüz ve piyasalar hakkındaki sorularınızı yanıtlayabilirim.",
            ),
            "flags": flags,
        }

    # Hiçbir kural motora takılmadıysa LLM'e devret
    return {"intent": "pass_to_llm", "flags": flags}
