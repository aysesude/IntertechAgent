"""Backfill ve günlük iş, varlık kataloğunu KENDİSİ hizalar.

Fiyat yazabilmek için varlığın DB kaydı gerekiyor. Kayıt yoksa `price_ingest`
sembolü sessizce atlıyordu ("varlık DB'de yok — önce seed_assets
çalıştırılmalı"). Sunucuda tam bu yaşandı: evrene yeni bir fon (IOO) eklendi,
`make backfill` onu atladı ve belgelenen sıra ("önce backfill, sonra seed")
yeni varlıklarda geçersiz hâle geldi — doğrusu seed → backfill → seed
oluyordu, yani prosedür varlığın yaşına göre değişiyordu.

CLI'lar artık `seed_assets` çağırıyor; sıra her durumda aynı.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.core.config import PriceSource
from app.models import Asset
from app.providers.base import PricePoint
from app.providers.universe import ASSET_UNIVERSE
from data.seed_assets import seed_assets


def test_bos_veritabaninda_katalog_kurulur(db_session):
    """`seed_assets` tek başına tüm evreni oluşturabilmeli.

    Backfill'in düzeltmesi bu değişmeze dayanıyor: CLI önce bunu çağırıyor,
    sonra fiyat yazıyor.
    """
    assert db_session.execute(select(func.count()).select_from(Asset)).scalar_one() == 0

    seed_assets(db_session)

    kayitli = {s for s in db_session.execute(select(Asset.symbol)).scalars()}
    beklenen = {spec.symbol for spec in ASSET_UNIVERSE}
    assert beklenen <= kayitli, f"katalogda eksik: {beklenen - kayitli}"


def test_katalog_hizalamasi_fiyatlara_dokunmaz(db_session):
    """`seed_assets` YALNIZCA katalog tablosuna dokunmalı.

    CLI'ların başında çağrılıyor; fiyatları ya da defteri etkileseydi
    backfill her koşuda veri bozardı.
    """
    from app.models import PriceHistory
    from app.services.price_ingest import upsert_prices

    seed_assets(db_session)
    asset_id = db_session.execute(select(Asset.id).where(Asset.symbol == "THYAO")).scalar_one()
    upsert_prices(
        db_session,
        asset_id,
        [PricePoint(date(2026, 8, 20), Decimal("123.45"), PriceSource.YFINANCE)],
    )
    db_session.flush()

    onceki = db_session.execute(select(func.count()).select_from(PriceHistory)).scalar_one()

    seed_assets(db_session)  # ikinci kez — idempotent olmalı

    sonraki = db_session.execute(select(func.count()).select_from(PriceHistory)).scalar_one()
    assert sonraki == onceki, "katalog hizalaması fiyat satırlarına dokundu"


def test_cli_katalogu_once_hizaliyor():
    """Düzeltmenin kendisi: her iki CLI de `seed_assets` çağırmalı.

    Kaynak metnine bakmak kaba ama alternatifi tüm CLI'ı sahte sağlayıcıyla
    koşturmak; buradaki asıl risk çağrının SESSİZCE KAYBOLMASI ve tuzağın
    fark edilmeden geri gelmesi.
    """
    import inspect

    import data.backfill as backfill
    import data.daily_update as daily

    for modul in (backfill, daily):
        kaynak = inspect.getsource(modul.main)
        assert "seed_assets(session)" in kaynak, f"{modul.__name__}: katalog hizalaması yok"
