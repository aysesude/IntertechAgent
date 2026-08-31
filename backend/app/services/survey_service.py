"""Yatırımcı risk profili anketi: skorlama motoru.

`data/risk_survey_config.json` bu testin TEK DOĞRULUK KAYNAĞIDIR — sorular,
seçenekler, ağırlıklar ve profil bantları orada. Bu modül yalnızca o dosyayı
okur ve referans motoru (`skorlama.py`, ekip dışı teslim) birebir uygular.
Soru/ağırlık değişikliği burada değil, JSON'da yapılır.

PORT SADAKATİ ÖLÇÜLÜYOR: referans motorun beş persona vakası
`tests/test_survey_scoring.py` içinde beklenen değerleriyle birlikte duruyor.
Bir tanesi bile tutmuyorsa port eksiktir; ağırlık ya da bant değiştirildiğinde
o beklenen değerler de güncellenmek zorundadır (kasıtlı: değişikliğin etkisini
görmeden geçilemez).

ÜÇ TASARIM KARARI KORUNDU — hiçbiri "sadeleştirme" adına değiştirilmemeli:

1. **`nihai_skor = min(kapasite, tolerans)`, ORTALAMA DEĞİL.** Ortalanırsa
   parası olmayan ama cesur kullanıcı ile parası olan ama düşüşe dayanamayan
   kullanıcı aynı orta profile düşer; ikisi de yanlıştır. Düşük olan bağlayıcı
   kısıttır.
2. **Bilgi skoru tavan uygular.** Yeterince bilmeyen kullanıcı, parası ve
   iştahı olsa bile yüksek profile çıkamaz.
3. **Skorlama LLM'e YAPTIRILMAZ.** Deterministik ve denetlenebilir kalır; LLM
   yalnızca sonucu kişiselleştiren metin için kullanılır (bkz. `yorum_uret`).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Konteynerde `data/` kök dizine bağlanıyor (`./data:/data`, docker-compose),
# lokalde ise depo kökünün altında. `parents[3]` her iki durumda da doğru yeri
# gösterir: /app/app/services/x.py -> "/", backend/app/services/x.py -> depo kökü.
_CONFIG_PATH = Path(__file__).resolve().parents[3] / "data" / "risk_survey_config.json"

# Boyutların soru dağılımı. Referans motorla birebir aynı; ağırlıklar JSON'da.
_KAPASITE_SORULARI = ("B1", "B2", "B3", "B4", "B5", "C1")
_TOLERANS_SORULARI = ("C3", "D1", "D2", "D3")
_BILGI_SORULARI = ("E2", "E3", "E4")

# B6 puan vermez, kapasiteye TAVAN uygular (likidite ihtiyacı). Soru yanıtsızsa
# tavan yok demektir; 100 nötr üst sınırdır.
_TAVANSIZ = 100


class SurveyConfigError(RuntimeError):
    """Anket yapılandırması okunamadı ya da bozuk."""


@lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    """Anket yapılandırması. Süreç ömrü boyunca bir kez okunur.

    Dosya yoksa ya da bozuksa AÇIKÇA patlar — sessizce boş bir anket sunmak,
    kullanıcıya sorulmamış sorulardan profil üretmek olurdu.
    """
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SurveyConfigError(f"Anket yapılandırması okunamadı: {_CONFIG_PATH}") from exc


class SurveyAnswerError(ValueError):
    """Cevaplarda eksik ya da tanınmayan bir değer var."""


def _puan(kod: str, secim: str) -> int:
    """Seçilen seçeneğin puanı. Puansız seçenek 0 sayılır."""
    sorular = config()["sorular"]
    if kod not in sorular:
        raise SurveyAnswerError(f"Tanınmayan soru: {kod}")
    for secenek in sorular[kod]["o"]:
        if secenek[0] == secim:
            return secenek[2] if len(secenek) > 2 else 0
    raise SurveyAnswerError(f"{kod} için geçersiz seçenek: {secim!r}")


def _cevap(cevaplar: dict[str, Any], kod: str) -> str:
    deger = cevaplar.get(kod)
    if not isinstance(deger, str) or not deger:
        raise SurveyAnswerError(f"{kod} cevaplanmamış")
    return deger


def _matris_puani(e1: dict[str, Any]) -> int:
    """E1 ürün matrisi -> 0-70 puan.

    Her satır için `(bilgi + sıklık) × kategori_ağırlığı`. HACİM SÜTUNU
    PUANLANMAZ — yalnızca TK1 tutarlılık kontrolünde kullanılır (düşük risk
    beyan edip yüksek hacimli riskli işlem bildiren kullanıcıyı yakalar).
    """
    matris = config()["urun_matrisi"]
    bilgi_p = {o[0]: o[2] for o in matris["sutunlar"][0]["o"]}
    siklik_p = {o[0]: o[2] for o in matris["sutunlar"][1]["o"]}

    toplam = 0
    for satir in matris["satirlar"]:
        secim = e1.get(satir["k"]) or {}
        try:
            ham = bilgi_p[str(secim.get("bilgi", "0"))] + siklik_p[str(secim.get("siklik", "0"))]
        except KeyError as exc:
            raise SurveyAnswerError(f"E1/{satir['k']} için geçersiz değer: {exc}") from exc
        toplam += ham * satir["w"]
    return toplam


def _bant(skor: int) -> dict[str, Any]:
    """Skorun düştüğü profil bandı. Bantlar 0-100'ü boşluksuz kaplar."""
    for profil in config()["profiller"]:
        if profil["lo"] <= skor <= profil["hi"]:
            return profil
    raise SurveyConfigError(f"Profil bantları {skor} puanını kapsamıyor")


def _kurallar(
    cevaplar: dict[str, Any], kapasite: int, tolerans: int, bilgi: int, seviye: int
) -> list[dict[str, Any]]:
    """Tetiklenen tutarlılık kuralları.

    Metin JSON'da, KOŞUL burada: metinler çevrilebilir ve gözden geçirilebilir
    olmalı, koşullar test edilebilir olmalı (kılavuzun bilinçli ayrımı).

    TK1 REFERANS MOTORDAKİ HÂLİYLE DURUYOR: matrisin HERHANGİ bir satırındaki
    hacim ≥2, düşük risk beyanıyla çelişik sayılır. Bir ara yalnızca yüksek
    riskli satırlara daraltılmıştı; karar, TSPB şablonundan gelen kuralı
    kendi yorumumuzla değiştirmemek yönünde geri alındı. Bunun bilinen bedeli,
    yalnızca repo/tahvil işlemi olan muhafazakâr kullanıcının da reddedilmesi;
    telafisi, reddin gerekçesinin kullanıcıya CEVAPLARINA ATIFLA açıklanması
    (`_gerekceler`).
    """
    kural_metni = {k["kod"]: k for k in config()["kurallar"]}
    e1 = cevaplar.get("E1") or {}
    hacimler = [int(str((v or {}).get("hacim", "0")) or 0) for v in e1.values()]

    tetik = {
        "TK1": cevaplar.get("C3") in ("a", "b") and any(h >= 2 for h in hacimler),
        "TK2": tolerans - kapasite >= 30,
        "TK3": cevaplar.get("C1") == "a" and seviye >= 4,
        "TK4": bilgi < 26 and cevaplar.get("C3") in ("d", "e"),
        "TK5": cevaplar.get("B5") == "a" and seviye >= 5,
        "TK6": cevaplar.get("C2") == "a" and seviye >= 4,
        "TK7": seviye <= 2 and cevaplar.get("C2") == "b",
    }
    return [
        {
            "kod": kod,
            "durdurucu": kural_metni[kod]["durdurucu"],
            "mesaj": kural_metni[kod]["mesaj"],
        }
        for kod, tetiklendi in tetik.items()
        if tetiklendi
    ]


def _secenek_metni(kod: str, secim: str | None) -> str | None:
    """Kullanıcının seçtiği şıkkın METNİ. Ekranda gördüğü cümlenin aynısı."""
    soru = config()["sorular"].get(kod)
    if soru is None or secim is None:
        return None
    for secenek in soru["o"]:
        if secenek[0] == secim:
            return str(secenek[1])
    return None


def _azami_puan(kod: str) -> int:
    secenekler = config()["sorular"][kod]["o"]
    return max((s[2] if len(s) > 2 else 0) for s in secenekler)


def _hacim_beyanlari(e1: dict[str, Any]) -> list[tuple[str, str]]:
    """Hacim beyanı ≥2 olan matris satırları: `(satır adı, hacim etiketi)`.

    TK1'i tetikleyen tam olarak budur; kullanıcıya "hangi satır" diyebilmek
    için kuralın baktığı veriyi aynı yerden okuyoruz.
    """
    matris = config()["urun_matrisi"]
    hacim_etiketi = {o[0]: str(o[1]) for o in matris["sutunlar"][2]["o"]}
    bulunan: list[tuple[str, str]] = []
    for satir in matris["satirlar"]:
        secim = str((e1.get(satir["k"]) or {}).get("hacim", "0") or "0")
        if int(secim) >= 2:
            bulunan.append((str(satir["n"]), hacim_etiketi.get(secim, secim)))
    return bulunan


def _gerekceler(cevaplar: dict[str, Any], sonuc: dict[str, Any]) -> list[str]:
    """Sonucu kullanıcının KENDİ CEVAPLARINA bağlayan olgular.

    NEDEN LLM'E BIRAKILMIYOR: modele ham cevapları verip "neden böyle çıktı"
    diye sorsak, hangi cevabın belirleyici olduğunu TAHMİN ederdi. Anket
    sonucu bir uygunluk beyanıdır; gerekçesi de ölçülmüş olmak zorunda
    (CLAUDE.md "uydurmama"). Bu yüzden hangi cevabın neyi belirlediğini kod
    hesaplıyor, LLM yalnızca bu olguları cümleye döküyor.

    Metinler kullanıcının ekranda gördüğü şık cümleleriyle birebir aynı —
    "B3'te 15 puan aldınız" demek kimseye bir şey anlatmaz.
    """
    gerekceler: list[str] = []

    if not sonuc["sonuc_uretildi"]:
        c3 = _secenek_metni("C3", cevaplar.get("C3"))
        satirlar = _hacim_beyanlari(cevaplar.get("E1") or {})
        if c3:
            gerekceler.append(f"Risk tercihi olarak şunu seçtiniz: “{c3}”")
        for ad, hacim in satirlar:
            gerekceler.append(f"Ürün deneyiminde “{ad}” satırında {hacim} işlem hacmi bildirdiniz")
        gerekceler.append("Bu iki beyan bir arada tutarlı sayılmadığı için test sonuç üretmedi")
        return gerekceler

    # Hangi boyut bağlayıcı oldu? `nihai = min(kapasite, tolerans)`.
    if sonuc["kapasite"] <= sonuc["tolerans"]:
        baglayici, sorular = "mali kapasiteniz", _KAPASITE_SORULARI
    else:
        baglayici, sorular = "risk toleransınız", _TOLERANS_SORULARI
    gerekceler.append(
        f"Profilinizi {baglayici} belirledi; sonuç ikisinden düşük olana göre hesaplanır"
    )

    # O boyutta puanı en çok sınırlayan iki cevap.
    kayiplar = []
    for kod in sorular:
        secim = cevaplar.get(kod)
        if not isinstance(secim, str):
            continue
        kayip = _azami_puan(kod) - _puan(kod, secim)
        metin = _secenek_metni(kod, secim)
        if kayip > 0 and metin:
            kayiplar.append((kayip, config()["sorular"][kod]["t"], metin))
    for _, soru, secilen in sorted(kayiplar, reverse=True)[:2]:
        gerekceler.append(f"“{soru}” sorusunda “{secilen}” dediniz")

    if sonuc["likidite_tavani_uygulandi"]:
        b6 = _secenek_metni("B6", cevaplar.get("B6"))
        if b6:
            gerekceler.append(
                f"Parayı 12 ay içinde çekme ihtimaliniz için “{b6}” dediniz; "
                "bu, kapasitenize tavan uyguluyor"
            )

    if sonuc["bilgi_nedeniyle_kisitlandi"]:
        gerekceler.append(
            f"Ürün bilgi ve deneyim puanınız {sonuc['bilgi']}/100; "
            "profil bunun izin verdiği seviyeye çekildi"
        )

    return gerekceler


def skorla(cevaplar: dict[str, Any]) -> dict[str, Any]:
    """Anket cevaplarından profil üretir.

    `sonuc_uretildi` `False` ise (durdurucu bir tutarlılık kuralı tetiklendi)
    profil alanları `None` gelir. O durumda kullanıcıya profil GÖSTERİLMEZ,
    cevaplarını gözden geçirmesi istenir — çelişkili beyandan üretilmiş bir
    profil, üretilmemiş profilden kötüdür.
    """
    cfg = config()

    kapasite = sum(_puan(kod, _cevap(cevaplar, kod)) for kod in _KAPASITE_SORULARI)
    likidite_tavani = _puan("B6", _cevap(cevaplar, "B6")) if "B6" in cevaplar else _TAVANSIZ
    kapasite = min(kapasite, likidite_tavani)

    tolerans = sum(_puan(kod, _cevap(cevaplar, kod)) for kod in _TOLERANS_SORULARI)
    bilgi = _matris_puani(cevaplar.get("E1") or {}) + sum(
        _puan(kod, _cevap(cevaplar, kod)) for kod in _BILGI_SORULARI
    )

    # ORTALAMA DEĞİL: modül başlığındaki 1 numaralı karar.
    nihai = min(kapasite, tolerans)
    profil = _bant(nihai)

    azami_seviye = _bant(bilgi)["lv"]
    bilgi_kisiti = profil["lv"] > azami_seviye
    if bilgi_kisiti:
        profil = next(p for p in cfg["profiller"] if p["lv"] == azami_seviye)

    # C3 tercihinin kendi SPK kategori tavanı da bağlayabilir.
    urun_tavani = min(profil["cat"], cfg["c3_kategori_tavani"].get(cevaplar.get("C3"), 5))

    # Sınır bölgesi: bant genişliği ~14 puan, tek cevap bant değiştirebilir.
    # Uyarı atlanırsa aynı kişi testi iki hafta arayla çözdüğünde farklı sonuç
    # alır ve ürüne güveni sarsılır.
    esik = cfg["sinir_bolgesi_esigi"]
    sonsuz = 10**9
    alt = nihai - profil["lo"] if profil["lv"] > 1 else sonsuz
    ust = profil["hi"] - nihai if profil["lv"] < len(cfg["profiller"]) else sonsuz
    sinirda = min(alt, ust) <= esik and not bilgi_kisiti

    kurallar = _kurallar(cevaplar, kapasite, tolerans, bilgi, profil["lv"])
    durduruldu = any(k["durdurucu"] for k in kurallar)

    sonuc = {
        "kapasite": kapasite,
        "tolerans": tolerans,
        "bilgi": bilgi,
        "nihai_skor": nihai,
        "profil_seviyesi": None if durduruldu else profil["lv"],
        "profil_adi": "Belirlenemedi" if durduruldu else profil["ad"],
        "azami_fon_risk_degeri": None if durduruldu else profil["lv"],
        "azami_urun_risk_kategorisi": None if durduruldu else urun_tavani,
        "ornek_dagilim": None if durduruldu else profil["al"],
        "bilgi_nedeniyle_kisitlandi": bilgi_kisiti,
        "likidite_tavani_uygulandi": likidite_tavani < _TAVANSIZ,
        "sinir_bolgesinde": sinirda,
        "kurallar": kurallar,
        "sonuc_uretildi": not durduruldu,
    }
    # Gerekçe skorun TÜREVİ, girdisi değil: önce sonuç hesaplanır, sonra
    # hangi cevabın onu belirlediği okunur. Ters sırada yazılsaydı gerekçe
    # skoru etkileyebilir hâle gelirdi.
    sonuc["gerekceler"] = _gerekceler(cevaplar, sonuc)
    return sonuc


_YORUM_SISTEM_PROMPT = (
    "Sen bir bankanın yatırım profili asistanısın. Kullanıcının doldurduğu "
    "risk anketinin ÖLÇÜLMÜŞ sonucunu ona Türkçe, sade ve sıcak bir dille "
    "açıklayacaksın.\n"
    "\n"
    "SAYI ÜRETME: yalnızca sana verilen skorları kullan. Yeni bir oran, tutar "
    "veya yüzde uydurma.\n"
    "GEREKÇE UYDURMA: sonucun hangi cevaplardan çıktığını SANA VERİLEN "
    "'Belirleyici cevaplar' listesinden al. Listede olmayan bir cevabı "
    "belirleyici gibi gösterme, listedekini de değiştirme.\n"
    "TAVSİYE VERME: 'şunu al', 'şuna geç' deme. Ne ölçüldüğünü ve bunun ne "
    "anlama geldiğini anlat.\n"
    "KISITLARI SÖYLE: bilgi tavanı ya da likidite tavanı uygulandıysa bunu "
    "açıkça ama suçlayıcı olmayan bir dille aktar.\n"
    "SONUÇ ÜRETİLMEDİYSE: kullanıcıyı suçlama, hangi iki beyanın bir arada "
    "tutarlı sayılmadığını somut olarak söyle ve hangisini gözden "
    "geçirebileceğini belirt.\n"
    "En fazla 4 cümle. Madde işareti kullanma, düz paragraf yaz.\n"
    "Kullanıcıya 'siz' diye hitap et."
)


def _yedek_yorum(sonuc: dict[str, Any]) -> str:
    """LLM'e ulaşılamazsa gösterilecek metin.

    Sonuç ekranı boş kalamaz; kullanıcı anketi doldurdu ve bir karşılık
    bekliyor. Bu metin yalnızca ölçülmüş değerleri tekrar eder, yorum
    katmadan.

    Gerekçeler burada da kullanılıyor: LLM düştüğünde kullanıcının elinde
    "çelişki var" demekten fazlası kalsın. Gerekçeler deterministik üretildiği
    için sağlayıcıya bağlı değiller.
    """
    gerekceler = sonuc.get("gerekceler") or []

    if not sonuc["sonuc_uretildi"]:
        metin = (
            "Cevaplarınız arasında birbiriyle çelişen noktalar var, bu yüzden "
            "güvenilir bir profil üretemedik."
        )
        if gerekceler:
            metin += " " + ". ".join(gerekceler) + "."
        return metin + " Cevaplarınızı gözden geçirip anketi tekrar doldurabilirsiniz."

    metin = (
        f"Ölçülen yatırımcı profiliniz: {sonuc['profil_adi']}. "
        f"Risk kapasiteniz {sonuc['kapasite']}, risk toleransınız "
        f"{sonuc['tolerans']} puan; profiliniz ikisinden düşük olana göre "
        "belirlenir."
    )
    if sonuc["bilgi_nedeniyle_kisitlandi"]:
        metin += (
            " Ürün bilgi düzeyiniz bu profili sınırladı; deneyim arttıkça "
            "profil yeniden ölçülebilir."
        )
    if sonuc["likidite_tavani_uygulandi"]:
        metin += " Yakın vadeli nakit ihtiyacınız risk kapasitenizi sınırlıyor."
    return metin


async def yorum_uret(sonuc: dict[str, Any]) -> str:
    """Sonucu kişiselleştiren metni LLM'e yazdırır.

    SKORLAMA DEĞİL, YALNIZCA ANLATIM. Kılavuzun açık uyarısı: skorlama
    deterministik ve denetlenebilir kalmalı, LLM sonucu açıklamak için
    kullanılmalı. Bu yüzden modele yalnızca HESAPLANMIŞ değerler veriliyor ve
    yeni sayı üretmesi yasaklanıyor.

    LLM düşerse yedek metne düşülür — sonuç ekranı boş kalamaz.
    """
    from app.core.llm_client import get_llm_client

    girdi = (
        f"Profil: {sonuc['profil_adi']} (seviye {sonuc['profil_seviyesi']})\n"
        f"Kapasite: {sonuc['kapasite']}/100\n"
        f"Tolerans: {sonuc['tolerans']}/100\n"
        f"Bilgi ve deneyim: {sonuc['bilgi']}/100\n"
        f"Nihai skor: {sonuc['nihai_skor']}/100\n"
        f"Bilgi tavanı uygulandı: {'evet' if sonuc['bilgi_nedeniyle_kisitlandi'] else 'hayır'}\n"
        f"Likidite tavanı uygulandı: {'evet' if sonuc['likidite_tavani_uygulandi'] else 'hayır'}\n"
        f"Bant sınırında: {'evet' if sonuc['sinir_bolgesinde'] else 'hayır'}\n"
        f"Sonuç üretildi: {'evet' if sonuc['sonuc_uretildi'] else 'hayır'}\n"
        "Belirleyici cevaplar (ÖLÇÜLDÜ, değiştirme):\n"
        + "\n".join(f"- {g}" for g in sonuc.get("gerekceler") or ["(yok)"])
    )

    try:
        metin = await get_llm_client().generate(girdi, system=_YORUM_SISTEM_PROMPT)
    except Exception as exc:  # sağlayıcı/ağ hatalarının tümü
        logger.warning("survey_service: yorum uretilemedi, yedek metne dusuldu — %s", exc)
        return _yedek_yorum(sonuc)

    return metin.strip() or _yedek_yorum(sonuc)


def komsu_profil_adi(seviye: int) -> str | None:
    """Sınır bölgesinde gösterilecek komşu profilin adı.

    Skor bandın ÜST ucuna yakınsa bir üst, alt ucuna yakınsa bir alt profil
    kastedilir; burada yalnızca ad çözülüyor, hangi yön olduğunu çağıran
    taraf bilir.
    """
    for profil in config()["profiller"]:
        if profil["lv"] == seviye:
            return profil["ad"]
    return None
