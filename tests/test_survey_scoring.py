"""Anket skorlama motorunun referans porta sadakati.

Aşağıdaki beş persona ve beklenen değerleri UYDURMA DEĞİL: anket kitinin
referans motorundan (`skorlama.py`, ekip dışı teslim) olduğu gibi alındı ve
kitin kendi `demo.html` çıktısıyla birebir aynı olduğu belgelenmiş.

BU DOSYA PORTU KİLİTLER. Bir vaka bile tutmuyorsa port eksiktir. Ağırlık ya
da bant değiştirildiğinde beklenen değerler de güncellenmek zorundadır —
kasıtlı: değişikliğin etkisini görmeden geçilemez.
"""

import pytest

from app.services.survey_service import (
    SurveyAnswerError,
    _yuksek_riskli_satirlar,
    config,
    skorla,
)


def _bos_matris() -> dict[str, dict[str, str]]:
    return {
        satir["k"]: {"bilgi": "0", "siklik": "0", "hacim": "0"}
        for satir in config()["urun_matrisi"]["satirlar"]
    }


def _matris(**satirlar) -> dict[str, dict[str, str]]:
    d = _bos_matris()
    for anahtar, deger in satirlar.items():
        d[anahtar].update(deger)
    return d


# (cevaplar, beklenen (kapasite, tolerans, bilgi, nihai, profil_seviyesi))
VAKALAR = {
    "genc_calisan_tecrubesiz_iddiali": (
        dict(
            A1="a",
            A2="c",
            A3="Yazilim gelistirici, 3 yil",
            A4="a",
            B1="a",
            B2="a",
            B3="a",
            B4="b",
            B5="b",
            B6="c",
            C1="c",
            C2="d",
            C3="e",
            D1="d",
            D2="c",
            D3="d",
            E2="d",
            E3="d",
            E4="d",
            E1=_matris(r1={"bilgi": "1", "siklik": "1", "hacim": "1"}),
        ),
        (43, 100, 2, 43, 1),
    ),
    "emekli_koruma_odakli": (
        dict(
            A1="d",
            A2="b",
            A3="Ogretmen (emekli), 32 yil",
            A4="a",
            B1="a",
            B2="c",
            B3="b",
            B4="a",
            B5="d",
            B6="c",
            C1="b",
            C2="a",
            C3="a",
            D1="a",
            D2="a",
            D3="a",
            E2="d",
            E3="d",
            E4="d",
            E1=_matris(
                r1={"bilgi": "2", "siklik": "2", "hacim": "1"},
                r2={"bilgi": "2", "siklik": "1", "hacim": "1"},
            ),
        ),
        (62, 0, 10, 0, 1),
    ),
    "yuksek_varlikli_tecrubeli": (
        dict(
            A1="b",
            A2="c",
            A3="Portfoy yoneticisi, 12 yil",
            A4="b",
            B1="d",
            B2="d",
            B3="d",
            B4="a",
            B5="d",
            B6="d",
            C1="d",
            C2="d",
            C3="e",
            D1="d",
            D2="c",
            D3="d",
            E2="b",
            E3="b",
            E4="b",
            E1=_matris(
                r1={"bilgi": "2", "siklik": "3", "hacim": "3"},
                r2={"bilgi": "2", "siklik": "3", "hacim": "3"},
                r3={"bilgi": "2", "siklik": "3", "hacim": "3"},
                r4={"bilgi": "2", "siklik": "2", "hacim": "2"},
                r5={"bilgi": "2", "siklik": "2", "hacim": "2"},
            ),
        ),
        (100, 100, 92, 100, 7),
    ),
    "celiskili_beyan_tk1": (
        dict(
            A1="b",
            A2="c",
            A3="Isletmeci, 9 yil",
            A4="a",
            B1="c",
            B2="a",
            B3="c",
            B4="a",
            B5="c",
            B6="c",
            C1="c",
            C2="b",
            C3="a",
            D1="b",
            D2="a",
            D3="b",
            E2="b",
            E3="b",
            E4="b",
            E1=_matris(r4={"bilgi": "2", "siklik": "3", "hacim": "3"}),
        ),
        (82, 13, 50, 13, None),
    ),
    "kisa_vadeli_likidite_ihtiyaci": (
        dict(
            A1="b",
            A2="c",
            A3="Mimar, 15 yil",
            A4="a",
            B1="d",
            B2="d",
            B3="d",
            B4="a",
            B5="d",
            B6="a",
            C1="a",
            C2="e",
            C3="d",
            D1="c",
            D2="b",
            D3="c",
            E2="b",
            E3="b",
            E4="b",
            E1=_matris(r3={"bilgi": "2", "siklik": "2", "hacim": "2"}),
        ),
        (20, 68, 42, 20, 2),
    ),
}


@pytest.mark.parametrize("ad", list(VAKALAR))
def test_referans_vakalari_birebir_ayni_sonucu_verir(ad):
    cevaplar, beklenen = VAKALAR[ad]

    sonuc = skorla(cevaplar)
    alinan = (
        sonuc["kapasite"],
        sonuc["tolerans"],
        sonuc["bilgi"],
        sonuc["nihai_skor"],
        sonuc["profil_seviyesi"],
    )

    assert alinan == beklenen


def test_nihai_skor_ortalamalari_degil_dusuk_olani_alir():
    """En kritik tasarım kararı: `min(kapasite, tolerans)`.

    Ortalanırsa parası olmayan ama cesur kullanıcı ile parası olan ama düşüşe
    dayanamayan kullanıcı aynı orta profile düşer; ikisi de yanlıştır.
    "Genç çalışan" vakası tam bu ayrımı taşıyor: kapasite 43, tolerans 100.
    Ortalama 71 (Atak) olurdu; doğrusu 43.
    """
    cevaplar, _ = VAKALAR["genc_calisan_tecrubesiz_iddiali"]

    sonuc = skorla(cevaplar)

    assert sonuc["nihai_skor"] == min(sonuc["kapasite"], sonuc["tolerans"])
    assert sonuc["nihai_skor"] != (sonuc["kapasite"] + sonuc["tolerans"]) // 2


def test_bilgi_skoru_profile_tavan_uygular():
    """Parası ve iştahı olsa da yeterince bilmeyen kullanıcı yükselemez."""
    cevaplar, _ = VAKALAR["genc_calisan_tecrubesiz_iddiali"]

    sonuc = skorla(cevaplar)

    assert sonuc["bilgi_nedeniyle_kisitlandi"] is True
    assert sonuc["profil_seviyesi"] == 1


def test_durdurucu_kural_profil_uretmez():
    """Çelişkili beyanda profil ÜRETİLMEZ.

    Çelişkiden üretilmiş bir profil, üretilmemiş profilden kötüdür: kullanıcı
    onu doğru sanır ve ürün seçimi ona dayanır.
    """
    cevaplar, _ = VAKALAR["celiskili_beyan_tk1"]

    sonuc = skorla(cevaplar)

    assert sonuc["sonuc_uretildi"] is False
    assert sonuc["profil_seviyesi"] is None
    assert sonuc["ornek_dagilim"] is None
    assert any(k["kod"] == "TK1" and k["durdurucu"] for k in sonuc["kurallar"])


def test_likidite_tavani_kapasiteyi_kirpar():
    """B6 puan vermez, kapasiteye tavan uygular.

    "Kısa vadeli likidite ihtiyacı" vakasında kapasite soruları yüksek puan
    üretiyor ama parasına yakında ihtiyacı olan kullanıcı o kapasiteyi
    kullanamaz — tavan 20'ye kırpıyor.
    """
    cevaplar, _ = VAKALAR["kisa_vadeli_likidite_ihtiyaci"]

    sonuc = skorla(cevaplar)

    assert sonuc["likidite_tavani_uygulandi"] is True
    assert sonuc["kapasite"] == 20


def test_profil_seviyeleri_mevcut_anket_puani_araligina_oturur():
    """Motorun `profil_seviyesi` çıktısı doğrudan `users.risk_survey_score`
    olarak yazılıyor; veritabanı 1-7 aralığını CHECK ile kilitliyor."""
    seviyeler = {p["lv"] for p in config()["profiller"]}

    assert seviyeler == {1, 2, 3, 4, 5, 6, 7}


def test_eksik_cevap_sessizce_sifir_sayilmaz():
    """Cevaplanmamış soru 0 puan sayılsaydı, yarım bırakılmış bir anket
    "Korumacı" profil üretirdi ve kullanıcı bunu geçerli sanırdı."""
    cevaplar, _ = VAKALAR["yuksek_varlikli_tecrubeli"]
    eksik = {k: v for k, v in cevaplar.items() if k != "D1"}

    with pytest.raises(SurveyAnswerError):
        skorla(eksik)


def test_taninmayan_secenek_reddedilir():
    cevaplar, _ = VAKALAR["yuksek_varlikli_tecrubeli"]

    with pytest.raises(SurveyAnswerError):
        skorla({**cevaplar, "D1": "z"})


# ---------------------------------------------------------------------------
# TK1'in kapsamı: hangi işlem geçmişi düşük risk beyanıyla ÇELİŞİR?
# ---------------------------------------------------------------------------


def test_tk1_dusuk_riskli_urundeki_hacmi_celiski_saymaz():
    """Devlet tahvilinde işlem yapmış "riskten kaçınırım" beyanı ÇELİŞKİ DEĞİL.

    Kural önce matrisin herhangi bir satırındaki hacme bakıyordu ve tam da
    tutarlı davranan kullanıcıyı — parasını repo/BPP ve devlet tahvilinde
    tutan muhafazakâr yatırımcıyı — reddediyordu. Reddedilen kullanıcı
    kapatılamaz anket ekranında kalıyor, üstelik düzeltecek bir çelişkisi
    de yok.
    """
    cevaplar, _ = VAKALAR["emekli_koruma_odakli"]
    # Aynı emekli, ama düşük riskli ürünlerde EN YÜKSEK hacim beyanıyla.
    yogun_tahvil = {
        **cevaplar,
        "E1": _matris(
            r1={"bilgi": "2", "siklik": "3", "hacim": "3"},
            r2={"bilgi": "2", "siklik": "3", "hacim": "3"},
        ),
    }

    sonuc = skorla(yogun_tahvil)

    assert sonuc["sonuc_uretildi"] is True
    assert not any(k["kod"] == "TK1" for k in sonuc["kurallar"])
    # Daraltma profili riskli tarafa kaydırmıyor: tolerans hâlâ belirleyici.
    assert sonuc["profil_seviyesi"] == 1


def test_tk1_yuksek_riskli_urundeki_hacmi_hala_celiski_sayar():
    """Daraltma kuralı işlevsiz bırakmadı: türev/kaldıraçlı işlem geçmişi
    "riskten kaçınırım" beyanıyla bağdaşmaz ve reddedilmeye devam eder."""
    cevaplar, _ = VAKALAR["emekli_koruma_odakli"]
    viop = {**cevaplar, "E1": _matris(r4={"bilgi": "2", "siklik": "2", "hacim": "2"})}

    sonuc = skorla(viop)

    assert sonuc["sonuc_uretildi"] is False
    assert any(k["kod"] == "TK1" and k["durdurucu"] for k in sonuc["kurallar"])


def test_tk1_yalnizca_yuksek_riskli_urunlere_bakar():
    """Kuralın "yüksek riskli" yorumunu KİLİTLER.

    `_yuksek_riskli_satirlar` matrisin en yüksek ağırlıklı satırlarını
    seçiyor. Matris değişir de bu seçim orta riskli ürünleri kapsamaya
    başlarsa, kural sessizce genişler ve daraltma geri alınmış olur.
    """
    assert set(_yuksek_riskli_satirlar()) == {"r4", "r5"}
