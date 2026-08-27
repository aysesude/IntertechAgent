"""Logo servisi.

Ağa ÇIKMAZ: `requests.get` her testte değiştiriliyor. Gerçek sağlayıcıya
bağlı bir test, anahtarı olmayan geliştiricide ve CI'da kırılırdı.

Buradaki değişmezlerin çoğu "yanlış logo göstermeme" üzerine — eksik logo
görünür bir eksiklik, YANLIŞ logo ise fark edilmeyen bir hata.
"""

import pytest

from app.services import logo_service
from app.services.logo_service import get_logo_svg, temizle_onbellek

GERCEK_SVG = b'<svg data-source="logostream.dev" viewBox="0 0 60 60"><path d="M0,0"/></svg>'
YER_TUTUCU_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">'
    b'<rect width="400" height="400" fill="#1E1E1E"/><text>THY</text></svg>'
)


class SahteYanit:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code


@pytest.fixture(autouse=True)
def onbellek_temiz(monkeypatch):
    temizle_onbellek()
    monkeypatch.setattr(logo_service.settings, "logostream_api_key", "test-anahtari")
    yield
    temizle_onbellek()


def _sahte_get(sonuc, sayac: dict | None = None):
    def get(url, params=None, timeout=None):
        if sayac is not None:
            sayac["n"] = sayac.get("n", 0) + 1
        if isinstance(sonuc, Exception):
            raise sonuc
        return sonuc

    return get


def test_hisse_logosu_doner(monkeypatch):
    monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(GERCEK_SVG)))
    assert get_logo_svg("THYAO") == GERCEK_SVG


def test_yer_tutucu_LOGO_SAYILMAZ(monkeypatch):
    """Sağlayıcı logo bulamadığında 404 değil, 200 + koyu gri harf karesi
    döndürüyor.

    Ayırt edilmezse arayüz her eksik logo için o kareyi gösterir, bunun bir
    yer tutucu olduğu hiçbir yerde anlaşılmaz ve koyu kare açık temaya da
    uymaz.
    """
    monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(YER_TUTUCU_SVG)))
    assert get_logo_svg("THYAO") is None


class TestYalnizcaHisse:
    """Fon/döviz/maden SORGULANMAZ — yanlış şirket logosu riski.

    TEFAS fon kodları üç harfli ve başka borsalarda gerçek ticker: `IOO`
    için sağlayıcı gerçek bir logo döndürüyor ama o logo İş Portföy'ün
    değil. Bir fonun yanına başka şirketin logosunu koymak, hiç logo
    koymamaktan kötü.
    """

    @pytest.mark.parametrize("sembol", ["IOO", "AKE", "GTA", "AFT", "BHE"])
    def test_fon_sorgulanmaz(self, monkeypatch, sembol):
        sayac: dict = {}
        monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(GERCEK_SVG), sayac))

        assert get_logo_svg(sembol) is None
        assert sayac.get("n", 0) == 0, "fon için sağlayıcıya istek gitmemeli"

    @pytest.mark.parametrize("sembol", ["USDTRY", "EURTRY", "XAUTRY", "CEYREK"])
    def test_doviz_ve_maden_sorgulanmaz(self, monkeypatch, sembol):
        sayac: dict = {}
        monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(GERCEK_SVG), sayac))

        assert get_logo_svg(sembol) is None
        assert sayac.get("n", 0) == 0

    def test_evrende_olmayan_sembol_sorgulanmaz(self, monkeypatch):
        """Uç keyfi ticker'lar için genel bir logo proxy'sine dönüşmemeli —
        kotayı koruyan şey kümenin sonlu olması."""
        sayac: dict = {}
        monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(GERCEK_SVG), sayac))

        assert get_logo_svg("BILINMEYEN") is None
        assert sayac.get("n", 0) == 0


class TestOnbellek:
    def test_ikinci_cagri_aga_GITMEZ(self, monkeypatch):
        sayac: dict = {}
        monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(GERCEK_SVG), sayac))

        get_logo_svg("THYAO")
        get_logo_svg("THYAO")

        assert sayac["n"] == 1

    def test_LOGOSU_OLMAYAN_da_onbellege_girer(self, monkeypatch):
        # Olumsuz sonuç önbelleğe alınmazsa logosu olmayan her hisse için
        # her sayfa açılışında boşuna istek giderdi.
        sayac: dict = {}
        monkeypatch.setattr(
            logo_service.requests, "get", _sahte_get(SahteYanit(YER_TUTUCU_SVG), sayac)
        )

        get_logo_svg("THYAO")
        get_logo_svg("THYAO")

        assert sayac["n"] == 1

    def test_AG_HATASI_onbellege_girmez(self, monkeypatch):
        """Geçici bir kesinti yüzünden logo süreç ömrü boyunca kayıp
        kalmamalı."""
        import requests as requests_modulu

        sayac: dict = {}
        monkeypatch.setattr(
            logo_service.requests,
            "get",
            _sahte_get(requests_modulu.RequestException("kesinti"), sayac),
        )

        assert get_logo_svg("THYAO") is None
        assert get_logo_svg("THYAO") is None
        assert sayac["n"] == 2, "ağ hatası önbelleğe yazılmamalı"


def test_anahtar_yoksa_sessizce_devre_disi(monkeypatch):
    """Anahtarsız kurulumda demo çalışmaya devam etmeli; logo bir süs."""
    sayac: dict = {}
    monkeypatch.setattr(logo_service.settings, "logostream_api_key", None)
    monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(GERCEK_SVG), sayac))

    assert get_logo_svg("THYAO") is None
    assert sayac.get("n", 0) == 0


def test_saglayici_hatasi_logo_saymaz(monkeypatch):
    monkeypatch.setattr(
        logo_service.requests, "get", _sahte_get(SahteYanit(GERCEK_SVG, status_code=500))
    )
    assert get_logo_svg("THYAO") is None


def test_kucuk_harfli_sembol_de_calisir(monkeypatch):
    monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(GERCEK_SVG)))
    assert get_logo_svg("thyao") == GERCEK_SVG


class TestUc:
    def test_logo_yoksa_404(self, client_for, db_session, monkeypatch):
        """404, arayüzün `onError` ile rozete düşmesini sağlıyor. Boş görsel
        döndürmek eksik logoyu görünmez bir kusura çevirirdi."""
        monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(YER_TUTUCU_SVG)))

        yanit = client_for().get("/api/logos/THYAO")
        assert yanit.status_code == 404

    def test_logo_svg_olarak_doner(self, client_for, monkeypatch):
        monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(GERCEK_SVG)))

        yanit = client_for().get("/api/logos/THYAO")

        assert yanit.status_code == 200
        assert yanit.headers["content-type"].startswith("image/svg+xml")
        assert yanit.content == GERCEK_SVG

    def test_onbellek_basligi_var(self, client_for, monkeypatch):
        # Logolar değişmez; tarayıcı her sayfa açılışında yeniden sormasın.
        monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(GERCEK_SVG)))

        yanit = client_for().get("/api/logos/THYAO")
        assert "max-age" in yanit.headers.get("cache-control", "")

    def test_TOKEN_ISTEMEZ(self, client_for, monkeypatch):
        """`<img>` etiketi Authorization başlığı gönderemez.

        Token'lı bir uç için logoyu `fetch` ile alıp blob URL üretmek
        gerekirdi; tarayıcı önbelleği devre dışı kalırdı. Uç kullanıcıya
        özel hiçbir bilgi taşımıyor.
        """
        monkeypatch.setattr(logo_service.requests, "get", _sahte_get(SahteYanit(GERCEK_SVG)))

        # `client_for()` token GÖNDERMEZ.
        assert client_for().get("/api/logos/THYAO").status_code == 200
