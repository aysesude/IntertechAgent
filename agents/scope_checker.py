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

    query_lower = query.lower().strip()
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
            if any(k in query_lower for k in liste):
                return {"intent": "INJECTION_ATTEMPT", "message": varsayilan_mesaj, "flags": flags}

    # 2.2 Destek Talebi
    destek = scope_config.get("destek_talebi", {})
    if any(k in query_lower for k in destek.get("etiketler", [])):
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
    # Hata düzeltmesi: Alt dize yerine kelime sınırı (\b) ile kontrol
    islem_talebi = scope_config.get("islem_talebi", {})
    fiiller = islem_talebi.get("fiiller", [])
    istisnalar = islem_talebi.get("istisna_kaliplari", [])

    # Önce istisnaları kontrol et (örn. "alayım mı")
    is_istisna = any(istisna in query_lower for istisna in istisnalar)

    if not is_istisna:
        # Fiilleri kelime sınırlarıyla ara
        for fiil in fiiller:
            pattern = r"\b" + re.escape(fiil) + r"\b"
            if re.search(pattern, query_lower):
                return {
                    "intent": "UNAUTHORIZED_ACTION",
                    "message": "Bu işlemi gerçekleştirmeye yetkim bulunmuyor. Yalnızca portföy durumunuzu ve piyasa haberlerini analiz edebilirim.",
                    "flags": flags,
                }

    # 4. Tavsiye Bayrağı (advice_seeking)
    tavsiye_config = scope_config.get("tavsiye_bayragi", {})
    tavsiye_tetikleyiciler = tavsiye_config.get("tetikleyiciler", [])
    if any(t in query_lower for t in tavsiye_tetikleyiciler):
        flags.append("advice_seeking")

    # 5. Varlık Ekseni (Kapsam Dışı Varlık)
    varlik_siniflari = scope_config.get("varlik_siniflari", {})
    kapsam_disi_varliklar = varlik_siniflari.get("kapsam_disi", [])

    kapsam_disi_bulundu = False
    for v_sinif in kapsam_disi_varliklar:
        etiketler = v_sinif.get("etiketler", [])
        for etiket in etiketler:
            pattern = r"\b" + re.escape(etiket.lower()) + r"\b"
            if re.search(pattern, query_lower):
                kapsam_disi_bulundu = True
                break
        if kapsam_disi_bulundu:
            break

    # Eğer kapsam dışı bir varlık bulunduysa (Örn. kripto, emlak) ve kapsam içi varlık yoksa reddedelim.
    kapsam_ici_varliklar = varlik_siniflari.get("kapsam_ici", [])
    kapsam_ici_bulundu = False
    for v_sinif in kapsam_ici_varliklar:
        etiketler = v_sinif.get("etiketler", [])
        for etiket in etiketler:
            pattern = r"\b" + re.escape(etiket.lower()) + r"\b"
            if re.search(pattern, query_lower):
                kapsam_ici_bulundu = True
                break
        if kapsam_ici_bulundu:
            break

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
