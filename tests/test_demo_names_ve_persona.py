"""Demo kullanıcılarının adı/e-postası + elle kurulmuş demo personası.

İkisi de arayüzde GÖRÜNEN veriyi belirliyor: ad her sayfada üst çubukta,
persona ise demo videolarında girilecek hesap. Bu yüzden "çalışıyor mu"
değil, "ekranda doğru mu görünüyor" sorusunu sınıyorlar.

    AK 5.4  — kullanıcıya özel veri (persona kendi portföyünü görür)
    AK 2.6  — farklı portföy yapıları farklı sonuç üretebilmeli
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import AssetClass, RiskProfile, risk_profile_for_survey_score
from app.models import Portfolio, Transaction, TransactionType, User
from app.services.advice_eligibility import mismatched_holdings
from app.services.portfolio_service import get_holdings_valuation
from data.generate_dummy import main as generate_dummy_main
from data.names import ADLAR, SOYADLAR, ad_soyad, eposta
from data.seed_ledger import (
    DEMO_PERSONA_INDEX,
    DEMO_PERSONA_SEPET,
    DEMO_PERSONA_SURVEY_SCORE,
    TOPLAM_KULLANICI,
    _user_id,
)

# Faker'ın tr_TR sağlayıcısının ürettiği ünvanlar. Havuza elle bir ad
# eklenirken yanlışlıkla geri gelmesin diye burada kilitli.
UNVANLAR = ("Uz.", "Dr.", "Prof.", "Av.", "Öğr.", "Doç.", "Müh.")


# ---------------------------------------------------------------------------
# İsim havuzu — DB gerektirmez
# ---------------------------------------------------------------------------


def test_isimler_UNVANSIZ_ve_iki_kelime():
    """Ünvan ve üç-dört parçalı adlar geri gelmesin.

    Faker çıktısı böyleydi: "Uz. Zamir Aşıkel Tarhan", "Nazende Şehreban
    Eraslan Sezgin". Baş harf rozeti (`AuthContext.initialsOf`) ilk iki
    kelimeyi alıyor; ünvanlı bir adda rozet "UZ" yazardı.
    """
    for index in range(TOPLAM_KULLANICI):
        isim = ad_soyad(index)
        parcalar = isim.split()
        assert len(parcalar) == 2, f"{isim!r} iki kelime değil"
        assert not any(isim.startswith(u) for u in UNVANLAR), f"{isim!r} ünvanlı"


def test_isim_ve_eposta_BENZERSIZ_ve_birbirini_tutar():
    """E-posta addan türetilir; ikisi ekranda yan yana görünüyor.

    Eskiden bağımsızdılar ve tutmuyorlardı:
    `yildirimsatrettin@example.org` ↔ "Uz. Zamir Aşıkel Tarhan".
    """
    isimler = [ad_soyad(i) for i in range(TOPLAM_KULLANICI)]
    epostalar = [eposta(i) for i in isimler]

    assert len(set(isimler)) == TOPLAM_KULLANICI, "ad tekrarı"
    assert len(set(epostalar)) == TOPLAM_KULLANICI, "e-posta tekrarı"
    assert eposta("Zeynep Yılmaz") == "zeynep.yilmaz@ornek.com"
    # Türkçe harfler ASCII'ye çevrilmeli: adres kutusuna yazılabilir olmalı.
    assert eposta("Şeyma Çakır") == "seyma.cakir@ornek.com"
    assert all(e.isascii() for e in epostalar)


def test_havuz_kullanici_sayisindan_UZUN():
    """Ad havuzu tükenirse aynı ad iki kullanıcıya düşer.

    `ad_soyad` indeksi ada birebir eşliyor; havuz kısalırsa benzersizlik
    sessizce kaybolur ve iki demo hesabı aynı isimle görünür.
    """
    assert len(ADLAR) > TOPLAM_KULLANICI
    assert len(SOYADLAR) > 0


# ---------------------------------------------------------------------------
# Demo personası — tam seed gerektirir
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seeded(engine):
    """Tam seed bir kez koşar; `db_session` KULLANILMAZ — o fixture her testin
    sonunda bütün tabloları boşaltıyor (bkz. conftest), seed'i de silerdi."""
    generate_dummy_main()
    return engine


def test_persona_DORT_VARLIK_SINIFINI_da_tutar(seeded):
    """Demoda çeşitliliği gösteren hesap bu; dört sınıf da ekranda olmalı.

    Ölçülen kısıt: uygunluk merdiveni hisseyi ancak 5. puanda açıyor, yani
    dengeli bir persona (puan 3-4) HİÇ hisse tutamaz ve tanıtım dosyasındaki
    haber senaryosu çalışmaz. Bu yüzden persona agresif bantta.
    """
    with Session(seeded) as session:
        hv = get_holdings_valuation(session, _user_id(DEMO_PERSONA_INDEX))
        siniflar = {h.asset_class for h in hv.holdings}

        assert siniflar == {
            AssetClass.STOCK,
            AssetClass.PRECIOUS_METAL,
            AssetClass.CURRENCY,
            AssetClass.BOND,
        }
        assert hv.excluded_symbols == [], "personanın fiyatsız varlığı olmamalı"


def test_persona_profiline_UYGUN(seeded):
    """Ürün Sahibi kararı: dummy veri gerçekçi ve tutarlı olmalı; kasıtlı
    uyumsuz kombinasyon üretilmez (bkz. seed_ledger'daki PO notu)."""
    with Session(seeded) as session:
        persona = session.get(User, _user_id(DEMO_PERSONA_INDEX))

        assert persona.risk_survey_score == DEMO_PERSONA_SURVEY_SCORE
        assert persona.risk_profile is risk_profile_for_survey_score(DEMO_PERSONA_SURVEY_SCORE)
        assert persona.risk_profile is RiskProfile.AGGRESSIVE

        hv = get_holdings_valuation(session, persona.id)
        uyumsuz = mismatched_holdings(
            [(h.symbol, h.asset_class) for h in hv.holdings], persona.risk_survey_score
        )
        assert uyumsuz == []


def test_persona_SERBEST_NAKIT_tutar(seeded):
    """Sepet payları %90; kalan %10 harcanmadan nakit kalır.

    Nakit dilimi olmayan bir portföyde pasta grafiğinde nakit hiç görünmez ve
    "yatırıma dönüşmemiş paranız" anlatısı demoda kurulamaz.
    """
    with Session(seeded) as session:
        hv = get_holdings_valuation(session, _user_id(DEMO_PERSONA_INDEX))
        varlik_agirligi = sum(Decimal(h.weight_percent) for h in hv.holdings)

    assert varlik_agirligi < Decimal("95"), "serbest nakit görünmüyor"


def test_persona_GECMIS_SATISI_var(seeded):
    """Satış olmadan gerçekleşmiş K/Z üretilmiyor ve işlem geçmişi 'hep alım'
    gibi görünüyor."""
    with Session(seeded) as session:
        portfolio = session.execute(
            select(Portfolio).where(Portfolio.user_id == _user_id(DEMO_PERSONA_INDEX))
        ).scalar_one()
        sayim = dict(
            session.execute(
                select(Transaction.transaction_type, func.count())
                .where(Transaction.portfolio_id == portfolio.id)
                .group_by(Transaction.transaction_type)
            ).all()
        )

    assert sayim.get(TransactionType.SELL, 0) >= 1
    assert sayim.get(TransactionType.BUY, 0) >= len(DEMO_PERSONA_SEPET)
    assert sayim.get(TransactionType.DEPOSIT, 0) == 1


def test_persona_mevcut_50_kullaniciyi_KAYDIRMAZ(seeded):
    """Persona sona eklenir; 0-49 arasındaki kimlikler yerinde kalmalı.

    Mevcut kullanıcılardan biri elle şekillendirilseydi arketip/puan dağılımı
    kayar, ekibin elindeki test kimlikleri ölürdü.
    """
    with Session(seeded) as session:
        kayitli = set(session.execute(select(User.id)).scalars())

    assert kayitli == {_user_id(i) for i in range(TOPLAM_KULLANICI)}
    assert _user_id(DEMO_PERSONA_INDEX) in kayitli
