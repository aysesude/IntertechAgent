"""Tavsiye uygunluğu testleri — sınıf tablosu VE varlık düzeyi istisnaları.

Kural ("seviye puandan büyükse tavsiye alamaz") iş analisti şartnamesinden;
tablo 26 Ağustos 2026'da yeniden kalibre edildi (NAKIT 1, TAHVIL 2, DOVIZ 3,
MADEN 4, HISSE 5) çünkü eski hâli yedi puandan yalnızca dört farklı sonuç
üretiyordu. Gerekçe ve sapma notları `core/config.py` içinde.

Beklenen değerler tabloya bakılarak ELLE yazıldı, koddan türetilmedi — tablo
yanlışlıkla değiştirilirse test bunu yakalamalı, sessizce uyum sağlamamalı.
"""

import pytest
from sqlalchemy import select

from app.core.config import AssetClass
from app.services.advice_eligibility import (
    allowed_asset_classes,
    asset_risk_level,
    blocked_asset_classes,
    is_advice_allowed,
    is_asset_advice_allowed,
    validate_survey_score,
)

_NAKIT = AssetClass.CASH
_TAHVIL = AssetClass.BOND
_DOVIZ = AssetClass.CURRENCY
_MADEN = AssetClass.PRECIOUS_METAL

# Puan -> tavsiye edilebilecek sınıflar. Tablodan elle çıkarıldı.
_BEKLENEN = {
    1: {_NAKIT},
    2: {_NAKIT, _TAHVIL},
    3: {_NAKIT, _TAHVIL, _DOVIZ},
    4: {_NAKIT, _TAHVIL, _DOVIZ, _MADEN},
    5: set(AssetClass),
    6: set(AssetClass),
    7: set(AssetClass),
}


@pytest.mark.parametrize("puan,beklenen", sorted(_BEKLENEN.items()))
def test_allowed_asset_classes_matches_specification(puan, beklenen):
    assert allowed_asset_classes(puan) == beklenen


@pytest.mark.parametrize("puan,beklenen", sorted(_BEKLENEN.items()))
def test_blocked_is_the_complement_of_allowed(puan, beklenen):
    assert blocked_asset_classes(puan) == set(AssetClass) - beklenen


def test_stock_advice_requires_score_five():
    """Hisse SINIFI seviyesi 5: 4 ve altı puanlar hisse tavsiyesi alamaz.

    Yabancı hissenin ayrıca 6 istediğine dikkat — o kısıt varlık düzeyinde
    kilitleniyor (bkz. `TestVarlikDuzeyi`), sınıf düzeyinde değil.
    """
    assert not is_advice_allowed(AssetClass.STOCK, 4)
    assert is_advice_allowed(AssetClass.STOCK, 5)
    assert is_advice_allowed(AssetClass.STOCK, 7)


def test_equal_level_is_allowed_not_blocked():
    """Kural "BÜYÜKSE alamaz" diyor; eşitlik serbesttir.

    Sınır hatası burada yön değiştirir: `<` yazılsaydı tahvil seviyesi (2)
    olan bir kullanıcı tahvil tavsiyesi alamazdı — şartnamenin tam tersi.
    """
    assert is_advice_allowed(AssetClass.BOND, 2)
    assert is_advice_allowed(AssetClass.CURRENCY, 3)
    assert is_advice_allowed(AssetClass.PRECIOUS_METAL, 4)


def test_cash_is_allowed_at_every_score():
    """Nakit seviyesi 1: en düşük puanda bile serbest kalmalı."""
    for puan in range(1, 8):
        assert is_advice_allowed(AssetClass.CASH, puan), puan


def test_allowed_set_grows_monotonically_with_score():
    """Puan arttıkça izin kümesi daralamaz.

    Ayrı bir değişmez: tablo elle düzenlenirken bir sınıfın seviyesi yanlış
    girilirse (ör. nakit 5 yapılırsa) küme büyümesi bozulur ve bu test
    tekil eşleşme testlerinden bağımsız olarak uyarır.
    """
    for puan in range(1, 7):
        assert allowed_asset_classes(puan) <= allowed_asset_classes(puan + 1)


@pytest.mark.parametrize("gecersiz", [0, -1, 8, 100])
def test_out_of_range_score_raises(gecersiz):
    """Aralık dışı puan sessizce sınıra çekilmez, hata verir.

    Clamp edilseydi 9 puanlık bozuk bir girdi 7 sayılıp kullanıcıya hak
    etmediği genişlikte tavsiye üretilirdi.
    """
    with pytest.raises(ValueError):
        validate_survey_score(gecersiz)
    with pytest.raises(ValueError):
        allowed_asset_classes(gecersiz)
    with pytest.raises(ValueError):
        is_advice_allowed(AssetClass.CASH, gecersiz)


def test_specification_table_covers_every_asset_class():
    """Yeni bir varlık sınıfı eklenirse tablo da güncellenmeli.

    config.py açılışta bunu zaten doğruluyor; burada ikinci kez kontrol
    edilmesinin sebebi, o doğrulamanın yanlışlıkla kaldırılması durumunda
    testin sessiz kalmaması.
    """
    assert set(allowed_asset_classes(7)) == set(AssetClass)


class TestVarlikDuzeyi:
    """Varlık, sınıfının seviyesinden AYRILABİLİR — iki yöne de.

    Sınıf tablosu tipik varlığı tarif eder. Kullanıcının kararı "fonlar kendi
    risklerini taşısın" idi: bir fonun uygunluğu kabuğundan (BOND/STOCK)
    değil içeriğinden çıkar. Bu testler o istisnaları kilitliyor; semboller
    elle yazılı, çünkü asıl risk istisnanın SESSİZCE KAYBOLMASI.
    """

    def test_para_piyasasi_fonu_sinifinin_ALTINDA(self):
        """IOO: sınıfı BOND (=2) ama nakit eşdeğeri, seviyesi 1.

        Bu istisna olmasaydı 1 puanlık kullanıcıya önerilebilecek HİÇBİR
        varlık kalmıyordu — nakit sınıfında varlık yok, serbest bakiye
        satın alınabilir bir şey değil.
        """
        assert asset_risk_level("IOO", AssetClass.BOND) == 1
        assert is_asset_advice_allowed("IOO", AssetClass.BOND, 1)
        # Sınıf sürümü aynı puanda HAYIR der; ayrım kasıtlı.
        assert not is_advice_allowed(AssetClass.BOND, 1)

    def test_eurobond_fonu_sinifinin_USTUNDE(self):
        """AKE: sınıfı BOND (=2) ama döviz ürünü, seviyesi 3."""
        assert asset_risk_level("AKE", AssetClass.BOND) == 3
        assert not is_asset_advice_allowed("AKE", AssetClass.BOND, 2)
        assert is_asset_advice_allowed("AKE", AssetClass.BOND, 3)

    def test_yabanci_hisse_yerlinin_bir_ustunde(self):
        """ABD hissesi 6, BIST hissesi 5.

        Gerekçe volatilite DEĞİL — ölçüm tersini söylüyor (ABD %28,8, BIST
        %38,6) — erişim ve karmaşıklık: kur, saklama, yerel yatırımcı
        korumasının bulunmaması, vergi.
        """
        assert asset_risk_level("THYAO", AssetClass.STOCK) == 5
        assert asset_risk_level("AAPL", AssetClass.STOCK) == 6
        assert is_asset_advice_allowed("THYAO", AssetClass.STOCK, 5)
        assert not is_asset_advice_allowed("AAPL", AssetClass.STOCK, 5)

    def test_yabanci_hisse_FONU_da_alti_sayilir(self):
        """AFT yurt dışı hisse fonu; TI2/TCD yerli. Kabuk aynı, içerik farklı."""
        assert asset_risk_level("AFT", AssetClass.STOCK) == 6
        assert asset_risk_level("TI2", AssetClass.STOCK) == 5
        assert asset_risk_level("TCD", AssetClass.STOCK) == 5

    def test_gumus_ve_platin_altindan_bir_kademe_yukarida(self):
        """Kıymetli maden sınıfı 4 ama sınıf içi dağılım geniş.

        Ölçüldü (365 gün): gram altın %28,6, gümüş %65,9, platin %55,3.
        İkincisi ve üçüncüsü YERLİ HİSSENİN (%38,6, seviye 5) üstünde
        oynuyor, dolayısıyla ondan düşük bir kademede duramazlar.
        """
        assert asset_risk_level("XAUTRY", AssetClass.PRECIOUS_METAL) == 4
        assert asset_risk_level("XAGTRY", AssetClass.PRECIOUS_METAL) == 5
        assert asset_risk_level("XPTTRY", AssetClass.PRECIOUS_METAL) == 5
        # Sikkeler gram ALTINDAN türetilir, onunla aynı kademede kalır.
        assert asset_risk_level("CEYREK", AssetClass.PRECIOUS_METAL) == 4

    def test_evrende_olmayan_sembol_sinif_varsayilanina_duser(self):
        """Elle eklenmiş bir DB kaydı uygunluk kontrolünü çökertmemeli."""
        assert asset_risk_level("YOKBOYLE", AssetClass.STOCK) == 5

    def test_gecersiz_puan_varlik_surumunde_de_hata_verir(self):
        with pytest.raises(ValueError):
            is_asset_advice_allowed("IOO", AssetClass.BOND, 0)


def _izinli_semboller(puan):
    from app.providers.universe import ASSET_UNIVERSE

    return frozenset(
        a.symbol
        for a in ASSET_UNIVERSE
        if a.tradable and is_asset_advice_allowed(a.symbol, a.asset_class, puan)
    )


def test_yedinci_seviye_yalnizca_serbest_fonu_acar():
    """7'nin tek sakini serbest fondur (SPK III-52.1).

    Ölçüt yapı, volatilite değil: serbest fon nitelikli yatırımcıya satılır,
    portföy sınırlamalarının çoğundan muaftır ve kaldıraç/açığa satış
    kullanabilir. BHE'nin ölçülen oynaklığı (%22,8) 6'daki ABD hisseleriyle
    aynı bantta — yani bu kademeyi kazandıran sayı değil.

    700 TEFAS fonu tarandığında kaldıraçlı/ters/girişim sermayesi fonu
    çıkmadı; 7'nin ilk tanımının ("türev ürün") karşılığı yoktu.
    """
    from app.providers.universe import ASSET_UNIVERSE

    yedide_acilan = _izinli_semboller(7) - _izinli_semboller(6)
    assert yedide_acilan == {"BHE"}

    bhe = next(a for a in ASSET_UNIVERSE if a.symbol == "BHE")
    assert bhe.risk_level == 7


def test_her_puan_bir_oncekinden_farkli_kume_acar():
    """Asıl ölçüt: yedi puanın YEDİSİNİN de somut bir karşılığı olmalı.

    Eski tablo yedi puandan yalnızca DÖRT farklı sonuç üretiyordu (2, 5 ve 7
    bir öncekine hiçbir şey eklemiyordu), yani anketin ayırt ettiği kademe
    sayısı vaat edilenin yarısıydı. Yeniden kalibrasyonun sebebi buydu.
    """
    kumeler = [_izinli_semboller(puan) for puan in range(1, 8)]

    assert len(set(kumeler)) == 7, "yedi puan yedi farkli varlik kumesi acmali"
    for onceki, sonraki in zip(kumeler, kumeler[1:]):
        assert onceki < sonraki, "puan arttikca kume GERCEKTEN buyumeli"


def _migration_yolu(dosya_adi: str):
    """Migration dosyasının yolunu bulur — HEM lokal koşumda (`backend/` ve
    `tests/` repo kökünde kardeş klasör) HEM `docker compose exec -w / api
    pytest /tests -q` ile koşulduğunda (compose `./backend:/app` mount eder;
    container'da `/backend` diye bir yol YOKTUR, `backend/` içeriği doğrudan
    `/app` altındadır) doğru sonucu verir.

    2026-08-28: bu iki koşum biçimi arasındaki fark fark edilmeden bu testler
    docker'da FileNotFoundError ile düşüyordu — merge/kod değişikliğiyle
    ilgisi yoktu, salt yol varsayımı tekti.
    """
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    for aday_kok in (
        kok / "backend" / "alembic" / "versions",
        kok / "app" / "alembic" / "versions",
    ):
        aday = aday_kok / dosya_adi
        if aday.exists():
            return aday
    raise FileNotFoundError(
        f"{dosya_adi}: ne backend/alembic/versions ne app/alembic/versions altında bulundu "
        f"(aranan kök: {kok})"
    )


class TestVeritabaninaYazilmasi:
    """`assets.risk_level` — kodun DB'deki TÜREV kopyası.

    Seviye uzun süre yalnızca kodda yaşadı ve bunun bedeli SQL'den
    görünmemesiydi: `assets` tablosuna bakan biri alanın varlığını bile
    anlamıyor, "puanının üstünde varlık tutanlar" sorgusu SQL ile
    yazılamıyordu. Alım/satım engeli ve risk ajanı bu bilgiye DB üzerinden
    bakacağı için sütun eklendi.

    Tanım noktası hâlâ `universe.py`; bu testler kopyanın ondan
    AYRIŞMADIĞINI koruyor.
    """

    def test_seed_her_aktif_varliga_seviye_yazar(self, db_session):
        from app.models import Asset
        from data.seed_assets import seed_assets

        seed_assets(db_session)

        bos = [
            a.symbol
            for a in db_session.execute(select(Asset).where(Asset.is_active)).scalars()
            if a.risk_level is None
        ]
        assert not bos, f"seviyesi boş aktif varlık: {bos[:10]}"

    def test_db_degeri_kodla_BIREBIR_ayni(self, db_session):
        """Ayrışma sessizdir: sorgular eski seviyeye göre filtreler ve kimse
        fark etmez. Bu yüzden 141 varlığın tamamı tek tek karşılaştırılıyor."""
        from app.models import Asset
        from data.seed_assets import seed_assets

        seed_assets(db_session)

        ayrisan = [
            f"{a.symbol}: DB {a.risk_level} != kod {asset_risk_level(a.symbol, a.asset_class)}"
            for a in db_session.execute(select(Asset).where(Asset.is_active)).scalars()
            if a.risk_level != asset_risk_level(a.symbol, a.asset_class)
        ]
        assert not ayrisan, ayrisan[:10]

    def test_seed_TEKRAR_kosunca_elle_yazilan_deger_duzeltilir(self, db_session):
        """Sütun türev; tek yazma kapısı `seed_assets`.

        Elle yazılan bir değer kalıcı olsaydı DB ile kod kalıcı olarak
        ayrışır ve `universe.py`'nin "tek tanım noktası" sözleşmesi bozulurdu.
        """
        from app.models import Asset
        from data.seed_assets import seed_assets

        seed_assets(db_session)
        ioo = db_session.execute(select(Asset).where(Asset.symbol == "IOO")).scalar_one()
        assert ioo.risk_level == 1
        ioo.risk_level = 7
        db_session.flush()

        seed_assets(db_session)

        db_session.refresh(ioo)
        assert ioo.risk_level == 1

    def test_aralik_disi_seviye_veritabani_duzeyinde_reddedilir(self, db_session):
        from sqlalchemy.exc import IntegrityError

        from app.models import Asset
        from data.seed_assets import seed_assets

        seed_assets(db_session)
        with pytest.raises(IntegrityError):
            db_session.execute(
                Asset.__table__.update().where(Asset.symbol == "IOO").values(risk_level=9)
            )
            db_session.flush()

    def test_migration_ve_model_ayni_kisiti_tasiyor(self):
        """`docs/DATA.md` §8: testler migration koşmaz, dolayısıyla kısıt iki
        yere de yazılmalı; ayrıştıklarında kimse fark etmez."""
        from app.models import Asset

        migration = _migration_yolu("a3d75e1c9f04_asset_risk_level.py").read_text(encoding="utf-8")

        kisit = next(
            c for c in Asset.__table__.constraints if c.name == "ck_assets_risk_level_range"
        )
        assert kisit.name in migration
        assert str(kisit.sqltext) in migration

    def test_migrationdaki_degerler_kodla_ayni(self):
        """Migration bir anlık görüntüdür ve değerleri SABİT yazılıdır.

        Kod ile o an ayrışırsa deploy sonrası DB yanlış seviyelerle dolar ve
        `seed_assets` çalışana kadar öyle kalır. Bu test migration YAZILDIĞI
        andaki tabloyu kilitler; kod ileride değişirse migration
        güncellenmez, yeni bir migration da gerekmez — beklenen davranış
        `seed_assets`'in üzerine yazmasıdır. O yüzden burada yalnızca
        migration'ın KENDİ İÇİNDE tutarlı olduğu doğrulanıyor.
        """
        import importlib.util

        yol = _migration_yolu("a3d75e1c9f04_asset_risk_level.py")
        spec = importlib.util.spec_from_file_location("mig_risk_level", yol)
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)

        tum_seviyeler = set(modul._SINIF_SEVIYELERI.values()) | set(modul._VARLIK_ISTISNALARI)
        assert tum_seviyeler <= set(range(1, 8)), "migration aralık dışı seviye içeriyor"

        # Aynı sembol iki farklı seviyeye yazılmamalı — son UPDATE kazanırdı
        # ve hangisi olduğu sözlük sırasına bağlı kalırdı.
        semboller = [s for liste in modul._VARLIK_ISTISNALARI.values() for s in liste]
        assert len(semboller) == len(set(semboller)), "migration'da tekrarlanan sembol var"
