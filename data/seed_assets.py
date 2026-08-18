"""Varlık evrenini (providers/universe.py) DB'ye yazar.

Upsert mantığı: sembole göre eşleşen varlık güncellenir, olmayan eklenir,
HİÇBİRİ SİLİNMEZ (fiyat geçmişi ve işlem FK'ları var; varlık kapatılacaksa
is_active=False yapılır). Evrenden çıkarılan semboller pasife çekilir.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset
from app.providers.universe import ASSET_UNIVERSE, SPEC_BY_SYMBOL


def seed_assets(session: Session) -> dict[str, Asset]:
    """Evreni upsert eder; sembol -> Asset eşlemesi döndürür."""
    existing = {asset.symbol: asset for asset in session.execute(select(Asset)).scalars().all()}

    def upsert(spec) -> Asset:
        asset = existing.get(spec.symbol)
        if asset is None:
            asset = Asset(symbol=spec.symbol)
            session.add(asset)
        asset.name = spec.name
        asset.asset_class = spec.asset_class
        asset.currency = spec.currency
        asset.sub_type = spec.sub_type.value if spec.sub_type else None
        asset.is_active = True
        asset.data_source = spec.data_source
        asset.provider_symbol = spec.provider_symbol
        asset.derived_factor = spec.derived_factor
        return asset

    by_symbol: dict[str, Asset] = {}

    # 1. geçiş: kaynak (türetilmemiş) varlıklar — id alsınlar diye önce flush.
    for spec in ASSET_UNIVERSE:
        if spec.derived_from is None:
            by_symbol[spec.symbol] = upsert(spec)
    session.flush()

    # 2. geçiş: türetilmişler. FK, flush'tan ÖNCE atanmalı; aksi halde
    # ck_assets_derived_consistency kısıtı ('derived' <-> kaynak dolu) patlar.
    for spec in ASSET_UNIVERSE:
        if spec.derived_from is not None:
            asset = upsert(spec)
            asset.derived_from_asset_id = by_symbol[spec.derived_from].id
            by_symbol[spec.symbol] = asset

    # Evrende artık olmayan varlıklar silinmez, kapatılır.
    for symbol, asset in existing.items():
        if symbol not in SPEC_BY_SYMBOL:
            asset.is_active = False

    session.flush()
    return by_symbol
