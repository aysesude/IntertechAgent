import re
from pathlib import Path

import yaml

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


def _matches_word(query: str, phrase: str) -> bool:
    """Kelime sınırıyla eşleşme (alt dize DEĞİL).

    Alt dize araması sessizce yanlış eşleşiyordu: `bug` etiketi "**bug**ün"
    içinde, `al` fiili "**al**tın"/"an**al**iz" içinde. Sonuç, meşru soruların
    reddedilmesiydi — "bugün portföyüm ne durumda" müşteri hizmetlerine
    yönlendiriliyordu.

    ÖDÜNLEŞME: Türkçe çekim ekleri yakalanmaz (`destekten`, `alabilir`). Yön
    bilinçli — meşru bir soruyu reddetmek, kapsam dışı bir soruyu ajana
    göndermekten daha maliyetli (PR #40'ta alınan karar).

    KURAL: eşleşmesi kullanıcıyı REDDEDEN kontroller bunu kullanır. Yalnızca
    bayrak ekleyen kontroller (`tavsiye_bayragi`) alt dize aramasında kalır;
    orada çekim ekini yakalamak istenen davranıştır ve yanlış pozitifin
    bedeli yok.
    """
    return re.search(r"\b" + re.escape(phrase) + r"\b", query) is not None


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
            if any(_matches_word(query_lower, k) for k in liste):
                return {"intent": "INJECTION_ATTEMPT", "message": varsayilan_mesaj, "flags": flags}

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

    if not is_istisna:
        for fiil in fiiller:
            if _matches_word(query_lower, fiil):
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
    if any(t in query_lower for t in tavsiye_tetikleyiciler):
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

    if kapsam_disi_bulundu and not kapsam_ici_bulundu:
        return {
            "intent": "OUT_OF_SCOPE",
            "message": "Finansal danışmanınız olarak yalnızca desteklenen varlıklar (Hisse, Döviz, Altın vb.) hakkındaki sorularınızı yanıtlayabilirim.\nÖrnek: Portföyüm ne durumda?",
            "flags": flags,
        }

    if kapsam_disi_bulundu and kapsam_ici_bulundu:
        flags.append("kismi_kapsam")

    # Hiçbir kural motora takılmadıysa LLM'e devret
    return {"intent": "pass_to_llm", "flags": flags}
