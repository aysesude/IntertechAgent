"""Al/Sat servisi — projedeki ilk para hareket ettiren yol.

Muhasebenin kendisi `ledger_service` içinde ve orada zaten test edilmiş
durumda; buradaki testler bu katmanın kendi kararlarını kilitliyor:
uygunluk kuralı, yuvarlama yönü, kur dondurma, fiyatın sunucudan gelmesi.

Senaryolar elle hesaplanabilecek kadar küçük tutuldu.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import PriceSource, RiskProfile
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models import Asset, Portfolio, PriceHistory, Transaction, TransactionType, User
from app.schemas.trade import TradeSide
from app.services.ledger_service import LedgerError, cash_balance_as_of, record_transaction
from app.services.trade_service import (
    deposit_cash,
    execute_trade,
    get_tradable_assets,
    preview_trade,
)


@pytest.fixture()
def kullanici(db_session):
    """Puanı 5 (Büyüme) olan, 100.000 TL nakdi bulunan kullanıcı.

    Puan 5 bilerek: yerli hisseyi açar ama ABD hissesini (6) ve serbest fonu
    (7) açmaz — uygunluk kuralının iki yönü de aynı kullanıcıyla sınanabilir.
    """
    user = User(
        email="trader@test.local",
        full_name="Test Trader",
        risk_profile=RiskProfile.GROWTH,
        risk_survey_score=5,
    )
    db_session.add(user)
    db_session.flush()
    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    from data.seed_assets import seed_assets

    seed_assets(db_session)

    # Fiyatlar: yerli hisse, ABD hissesi ve kur. Elle hesaplanabilir değerler.
    bugun = datetime.now(timezone.utc).date()
    for sembol, fiyat in [("THYAO", "100"), ("AAPL", "200"), ("USDTRY", "40")]:
        asset = db_session.execute(select(Asset).where(Asset.symbol == sembol)).scalar_one()
        db_session.add(
            PriceHistory(
                asset_id=asset.id,
                price_date=bugun,
                close_price=Decimal(fiyat),
                source=PriceSource.YFINANCE,
            )
        )
    record_transaction(
        db_session,
        portfolio.id,
        TransactionType.DEPOSIT,
        transaction_date=datetime.now(timezone.utc),
        cash_amount_try=Decimal("100000"),
        note="test fonlama",
    )
    db_session.commit()
    return user


def _varlik(db_session, sembol: str) -> Asset:
    return db_session.execute(select(Asset).where(Asset.symbol == sembol)).scalar_one()


class TestUygunluk:
    def test_puanin_ustundeki_varlik_ALINAMAZ(self, db_session, kullanici):
        # AAPL seviye 6, kullanıcının puanı 5.
        with pytest.raises(ValidationAppError) as hata:
            preview_trade(db_session, kullanici.id, "AAPL", TradeSide.BUY, Decimal(1))

        # Sebep kullanıcıya SÖYLENMELİ; "işlem yapılamaz" tek başına
        # kullanıcıyı hatayı kendinde aramaya iter.
        assert "6" in str(hata.value) and "5" in str(hata.value)

    def test_puana_uyan_varlik_ALINIR(self, db_session, kullanici):
        onizleme = preview_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal(10))
        assert onizleme.gross_try == Decimal("1000.0000")

    def test_uyumsuz_varlik_SATILABILIR(self, db_session, kullanici):
        """Elindeki uyumsuz varlıktan çıkışın tek yolu satmak.

        Satışı da engellemek kullanıcıyı uyumsuz pozisyonda kilitler — kural
        yalnızca ALIMA uygulanır.
        """
        portfolio = db_session.execute(
            select(Portfolio).where(Portfolio.user_id == kullanici.id)
        ).scalar_one()
        aapl = _varlik(db_session, "AAPL")
        # Puanı yetmese de elinde AAPL var (ör. puanını sonradan düşürmüş).
        record_transaction(
            db_session,
            portfolio.id,
            TransactionType.BUY,
            transaction_date=datetime.now(timezone.utc),
            asset_id=aapl.id,
            quantity=Decimal(2),
            price=Decimal("200"),
            currency="USD",
            fx_rate_to_try=Decimal("40"),
        )
        db_session.commit()

        onizleme = preview_trade(db_session, kullanici.id, "AAPL", TradeSide.SELL, Decimal(1))
        assert onizleme.quantity == Decimal(1)

    def test_anketi_doldurmamis_kullanici_alim_yapamaz(self, db_session, kullanici):
        kullanici.risk_survey_score = None
        db_session.commit()

        with pytest.raises(ValidationAppError, match="anket"):
            preview_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal(1))


class TestHesap:
    def test_kur_ISLEM_ANINDA_donuyor(self, db_session, kullanici):
        """USD varlığın TRY maliyeti deftere dondurularak yazılmalı.

        Sonradan hesaplansaydı geçmiş bir alımın maliyeti bugünkü kura göre
        değişir ve kâr/zarar oynardı.
        """
        kullanici.risk_survey_score = 6
        db_session.commit()

        sonuc = execute_trade(db_session, kullanici.id, "AAPL", TradeSide.BUY, Decimal(1))

        islem = db_session.get(Transaction, sonuc.transaction_id)
        assert islem.fx_rate_to_try == Decimal("40")
        assert islem.price == Decimal("200")
        # 1 × 200 USD × 40 = 8.000 TL
        assert islem.cash_amount_try == Decimal("-8000.0000")

    def test_miktar_ASAGI_yuvarlanir(self, db_session, kullanici):
        """Hisse tam sayı; 3,7 adet emri 3'e iner.

        Yukarı yuvarlamak kullanıcının istemediği kadar alım yaptırır ve
        bakiyesini hak etmediği kadar düşürür.
        """
        onizleme = preview_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal("3.7"))
        assert onizleme.quantity == Decimal(3)

    def test_yuvarlama_sifira_dusurduyse_HATA(self, db_session, kullanici):
        # Sessizce sıfır adet almak, kullanıcıya "işlem yapıldı" demek olurdu.
        with pytest.raises(ValidationAppError, match="en küçük işlem miktarı"):
            preview_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal("0.4"))

    def test_komisyon_yok(self, db_session, kullanici):
        onizleme = preview_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal(10))
        assert onizleme.fee_try == Decimal(0)
        assert onizleme.cash_delta_try == -onizleme.gross_try

    def test_onizleme_defteri_DEGISTIRMEZ(self, db_session, kullanici):
        portfolio = db_session.execute(
            select(Portfolio).where(Portfolio.user_id == kullanici.id)
        ).scalar_one()
        once = cash_balance_as_of(db_session, portfolio.id)

        preview_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal(10))

        assert cash_balance_as_of(db_session, portfolio.id) == once


class TestDefterKurallari:
    def test_yetersiz_bakiye_reddedilir(self, db_session, kullanici):
        # 100.000 TL var; 2.000 adet × 100 TL = 200.000 TL istiyor.
        with pytest.raises(ValidationAppError, match="Yetersiz bakiye"):
            preview_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal(2000))

    def test_eldekinden_fazla_satis_reddedilir(self, db_session, kullanici):
        execute_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal(5))

        with pytest.raises(ValidationAppError, match="satılamaz"):
            preview_trade(db_session, kullanici.id, "THYAO", TradeSide.SELL, Decimal(6))

    def test_hic_sahip_olunmayan_varlik_satilamaz(self, db_session, kullanici):
        with pytest.raises(ValidationAppError, match="satılamaz"):
            preview_trade(db_session, kullanici.id, "THYAO", TradeSide.SELL, Decimal(1))

    def test_fiyati_olmayan_varlik_islem_gormez(self, db_session, kullanici):
        # Fiyat uydurmak yerine açıkça reddet (AK 5.5).
        with pytest.raises(ValidationAppError, match="kayıtlı fiyat yok"):
            preview_trade(db_session, kullanici.id, "AKBNK", TradeSide.BUY, Decimal(1))

    def test_taninmayan_sembol(self, db_session, kullanici):
        with pytest.raises(NotFoundError):
            preview_trade(db_session, kullanici.id, "YOKBOYLE", TradeSide.BUY, Decimal(1))


class TestGerceklesme:
    def test_alim_defteri_ve_holdingsi_gunceller(self, db_session, kullanici):
        """`holdings` defterden TÜRETİLEN önbellek; yeniden kurulmazsa portföy
        ekranı işlemi hiç olmamış gibi gösterir."""
        from app.models import Holding

        sonuc = execute_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal(10))

        assert sonuc.preview.cash_after == Decimal("99000.0000")
        portfolio = db_session.execute(
            select(Portfolio).where(Portfolio.user_id == kullanici.id)
        ).scalar_one()
        holding = db_session.execute(
            select(Holding).where(Holding.portfolio_id == portfolio.id)
        ).scalar_one()
        assert holding.quantity == Decimal(10)

    def test_satis_nakdi_geri_getirir(self, db_session, kullanici):
        execute_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal(10))
        sonuc = execute_trade(db_session, kullanici.id, "THYAO", TradeSide.SELL, Decimal(4))

        # 100.000 - 1.000 + 400
        assert sonuc.preview.cash_after == Decimal("99400.0000")

    def test_islem_tarihi_BUGUN(self, db_session, kullanici):
        # Ürün kararı: işlemler güncel tarihli, güncel fiyat üzerinden.
        sonuc = execute_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal(1))
        assert sonuc.executed_at.date() == datetime.now(timezone.utc).date()


class TestNakitYatirma:
    def test_bakiye_artar(self, db_session, kullanici):
        yeni = deposit_cash(db_session, kullanici.id, Decimal("50000"))
        assert yeni == Decimal("150000.0000")

    def test_sifir_veya_negatif_reddedilir(self, db_session, kullanici):
        with pytest.raises(ValidationAppError):
            deposit_cash(db_session, kullanici.id, Decimal(0))


class TestListe:
    def test_uygun_olmayan_varlik_LISTEDEN_DUSMEZ(self, db_session, kullanici):
        """Sessizce elemek, kullanıcının o varlığın var olduğunu bile
        görmemesi demek olurdu."""
        liste = get_tradable_assets(db_session, kullanici.id)
        aapl = next(a for a in liste.assets if a.symbol == "AAPL")

        assert aapl.can_buy is False
        assert aapl.block_reason is not None
        assert "6" in aapl.block_reason

    def test_fiyat_TARIHIYLE_birlikte_doner(self, db_session, kullanici):
        # Arayüz tarihi göstermek zorunda, yoksa kullanıcı canlı fiyat sanır.
        liste = get_tradable_assets(db_session, kullanici.id)
        thyao = next(a for a in liste.assets if a.symbol == "THYAO")

        assert thyao.price == Decimal("100.0000")
        assert thyao.price_date == datetime.now(timezone.utc).date()
        assert thyao.price_stale is False

    def test_eldeki_miktar_listede(self, db_session, kullanici):
        execute_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal(7))

        liste = get_tradable_assets(db_session, kullanici.id)
        thyao = next(a for a in liste.assets if a.symbol == "THYAO")
        assert thyao.held_quantity == Decimal(7)

    def test_nakit_bakiyesi_listede(self, db_session, kullanici):
        assert get_tradable_assets(db_session, kullanici.id).cash_balance == Decimal("100000.0000")


def test_defter_kurali_ihlali_LedgerError_olarak_yukselir(db_session, kullanici):
    """Servis kendi kontrollerini geçse bile defter son sözü söyler.

    İki kapı da açık kalmalı: servis kullanıcıya anlaşılır mesaj veriyor,
    defter ise muhasebeyi koruyor. Servis kontrolü ileride yanlışlıkla
    gevşetilirse defter yine de tutar.
    """
    portfolio = db_session.execute(
        select(Portfolio).where(Portfolio.user_id == kullanici.id)
    ).scalar_one()

    with pytest.raises(LedgerError, match="Yetersiz nakit"):
        record_transaction(
            db_session,
            portfolio.id,
            TransactionType.WITHDRAW,
            transaction_date=datetime.now(timezone.utc),
            cash_amount_try=Decimal("-999999"),
        )


def test_gecmis_fiyat_degil_SON_fiyat_kullanilir(db_session, kullanici):
    """Bugünün fiyatı varken dünkü fiyattan işlem yapılmamalı."""
    thyao = _varlik(db_session, "THYAO")
    db_session.add(
        PriceHistory(
            asset_id=thyao.id,
            price_date=date(2020, 1, 1),
            close_price=Decimal("5"),
            source=PriceSource.YFINANCE,
        )
    )
    db_session.commit()

    onizleme = preview_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal(1))
    assert onizleme.price == Decimal("100.0000")


def test_sinif_hassasiyeti_madende_kesirli(db_session, kullanici):
    """Gram altın 0,01 ile alınabilir; hisse tam sayı."""
    xau = _varlik(db_session, "XAUTRY")
    db_session.add(
        PriceHistory(
            asset_id=xau.id,
            price_date=datetime.now(timezone.utc).date(),
            close_price=Decimal("3000"),
            source=PriceSource.YFINANCE,
        )
    )
    db_session.commit()

    onizleme = preview_trade(db_session, kullanici.id, "XAUTRY", TradeSide.BUY, Decimal("2.55"))
    assert onizleme.quantity == Decimal("2.55")

    # Aynı kesir hissede AŞAĞI yuvarlanır — hassasiyet sınıfa bağlı.
    hisse = preview_trade(db_session, kullanici.id, "THYAO", TradeSide.BUY, Decimal("2.55"))
    assert hisse.quantity == Decimal(2)
