"""BloombergHT ayrıştırıcısının regresyon testleri.

Aşağıdaki HTML kesiti UYDURMA DEĞİL: 24 Ağustos 2026'da
https://www.bloomberght.com/sondakika adresinden konteyner içinden çekilen
gerçek sayfadan alındı (sınıf adları, boşluklar ve `&#039;` kaçışı dahil
aynen korundu). Ayrıştırıcı bu kesite göre yazıldı; site yapısı değişip
testler kırıldığında kesitin kendisi de yenilenmelidir.

Sınıf adlarına BAĞLANMAMA kararı burada da test ediliyor: `test_sinif_adlari_
degisse_de_ayristirir`, aynı yapıyı bambaşka sınıf adlarıyla verir.
"""

from datetime import datetime

from app.providers.bloomberg_ht_p import basliklari_ayristir

# Gerçek sayfadan alınan tek bir madde (figure/figcaption yapısı).
_GERCEK_MADDE = """
<figure class="relative"> <figcaption> <div class="flex mb-2">
<div class="bg-[#BD1B2E] h-10 w-2"></div>
<div class="inline-block bg-red-100 py-1 px-3">
<span class="text-[#BD1B2E] font-bold text-2xl">14:38</span> </div> </div>
<div class="text-xs text-gray-400">24 Ağustos 2026, Pazartesi</div>
<div class="font-unna font-bold text-xl leading-6"> TCMB: REEL SEKTÖRÜN NET
DÖVİZ POZİSYONU AÇIĞI HAZİRAN&#039;DA 205,8 MİLYAR DOLAR OLDU; ÖNCEKİ 204,4
MİLYAR DOLAR </div> </figcaption> </figure>
"""

_IKINCI_MADDE = """
<figure class="relative"> <figcaption> <div class="flex mb-2">
<div class="inline-block bg-red-100 py-1 px-3">
<span class="text-[#BD1B2E] font-bold text-2xl">11:03</span> </div> </div>
<div class="text-xs text-gray-400">24 Ağustos 2026, Pazartesi</div>
<div class="font-unna font-bold text-xl leading-6"> TCMB, YÜZDE 37 FAİZ
ORANIYLA 1 MİLYAR TL TUTARINDA BİR HAFTALIK REPO İHALESİ AÇTI </div>
</figcaption> </figure>
"""


def test_ak_5_1_gercek_madde_dogru_ayristirilir():
    basliklar = basliklari_ayristir(_GERCEK_MADDE)

    assert len(basliklar) == 1
    b = basliklar[0]
    assert b.baslik.startswith("TCMB: REEL SEKTÖRÜN NET DÖVİZ POZİSYONU")
    assert "205,8 MİLYAR DOLAR" in b.baslik
    # HTML kaçışı çözülmeli: `HAZİRAN&#039;DA` -> `HAZİRAN'DA`
    assert "HAZİRAN'DA" in b.baslik
    assert b.tarih == datetime(2026, 8, 24, 14, 38)
    assert b.kaynak_url == "https://www.bloomberght.com/sondakika"


def test_birden_fazla_madde_sirayla_okunur():
    basliklar = basliklari_ayristir(_GERCEK_MADDE + _IKINCI_MADDE)

    assert len(basliklar) == 2
    assert basliklar[1].tarih == datetime(2026, 8, 24, 11, 3)


def test_tarih_kutusu_baslik_sanilmaz():
    """Tarih kutusu ("24 Ağustos 2026, Pazartesi") başlık adaylarından
    elenmeli — aksi hâlde başlıksız bir maddede tarih, başlık diye geçer."""
    basliklar = basliklari_ayristir(_GERCEK_MADDE)

    assert "Pazartesi" not in basliklar[0].baslik


def test_sinif_adlari_degisse_de_ayristirir():
    """Ayrıştırıcı Tailwind sınıflarına bağlı olmamalı: bir tema
    güncellemesi sessizce tüm gündemi düşürmemeli."""
    degistirilmis = _GERCEK_MADDE.replace("font-unna font-bold text-xl leading-6", "x1").replace(
        "text-xs text-gray-400", "x2"
    )

    basliklar = basliklari_ayristir(degistirilmis)

    assert len(basliklar) == 1
    assert basliklar[0].baslik.startswith("TCMB:")


def test_saati_olmayan_madde_gun_basi_kabul_edilir():
    saatsiz = _GERCEK_MADDE.replace(
        '<span class="text-[#BD1B2E] font-bold text-2xl">14:38</span>', ""
    )

    basliklar = basliklari_ayristir(saatsiz)

    assert basliklar[0].tarih == datetime(2026, 8, 24, 0, 0)


def test_tarihi_olmayan_madde_listeden_dusurulmez():
    """Tarih ayrıştırılamazsa başlık yine gösterilir, yalnızca tarihi
    yazılmaz — eksik bir alan yüzünden bilgi atılmaz."""
    tarihsiz = _GERCEK_MADDE.replace("24 Ağustos 2026, Pazartesi", "")

    basliklar = basliklari_ayristir(tarihsiz)

    assert len(basliklar) == 1
    assert basliklar[0].tarih is None
    assert basliklar[0].baslik.startswith("TCMB:")


def test_taninmayan_ay_adi_tarihi_none_yapar():
    bozuk = _GERCEK_MADDE.replace("24 Ağustos 2026", "24 Foobar 2026")

    basliklar = basliklari_ayristir(bozuk)

    assert basliklar[0].tarih is None


def test_bos_ya_da_alakasiz_html_bos_liste_doner():
    assert basliklari_ayristir("") == []
    assert basliklari_ayristir("<html><body><p>hiçbir şey</p></body></html>") == []
