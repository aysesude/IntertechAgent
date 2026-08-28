"""Hedef fiyat OKUMA servisi — target_prices'ı yazan taraf
`target_price_ingest.py`'den ayrı (price_history/price_service ayrımıyla
aynı desen).

target_prices'ta zaten yalnızca kurum başına TEK (en güncel) satır var —
bkz. target_price_ingest.py docstring'i — bu yüzden burada ekstra bir
"en son satırı bul" sorgusu gerekmiyor.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models import Asset, TargetPrice


def get_target_prices(db: Session, symbols: list[str]) -> dict:
    """Sembollerin bilinen tüm kurum hedef fiyatlarını döndürür.

    "GARAN'ın hedef fiyatı ne?", "ASELS için analist tavsiyesi ne?" gibi
    sorular buradan cevaplanır — LLM'e YENİDEN YAZDIRILMADAN, ham blok
    olarak sunulur (bkz. agents/market_agent.py::_hedef_fiyat_yaniti).

    Kısmi sonuç hata değildir; tanınmayan ve hedef fiyatı olmayan
    semboller ayrı ayrı raporlanır (AK 5.5).

    Raises:
        ValidationAppError: sembol listesi boş.
        NotFoundError: hiçbir sembol varlık evreninde tanınmadı.
    """
    if not symbols:
        raise ValidationAppError("symbols boş olamaz")

    istenen = [s.strip().upper() for s in symbols if s and s.strip()]
    if not istenen:
        raise ValidationAppError("symbols boş olamaz")

    assets = {
        a.symbol: a
        for a in db.execute(select(Asset).where(Asset.symbol.in_(istenen))).scalars().all()
    }
    taninmayan = [s for s in istenen if s not in assets]
    if not assets:
        raise NotFoundError(f"Tanınmayan sembol(ler): {', '.join(taninmayan)}")

    kayitlar: list[dict] = []
    hedefsiz: list[str] = []
    for sembol in istenen:
        asset = assets.get(sembol)
        if asset is None:
            continue
        satirlar = (
            db.execute(select(TargetPrice).where(TargetPrice.asset_id == asset.id)).scalars().all()
        )
        if not satirlar:
            hedefsiz.append(sembol)
            continue
        for satir in satirlar:
            kayitlar.append(
                {
                    "symbol": asset.symbol,
                    "institution": satir.institution,
                    "recommendation": satir.recommendation,
                    "target_price": float(satir.target_price),
                    "currency": satir.currency,
                    "price_at_report": (
                        float(satir.price_at_report) if satir.price_at_report is not None else None
                    ),
                    "previous_target_price": (
                        float(satir.previous_target_price)
                        if satir.previous_target_price is not None
                        else None
                    ),
                    "revision_direction": satir.revision_direction,
                    "horizon_months": satir.horizon_months,
                    "report_date": satir.report_date.isoformat(),
                    "source_url": satir.source_url,
                }
            )

    return {
        "records": kayitlar,
        "unknown_symbols": taninmayan,
        "symbols_without_data": hedefsiz,
    }
