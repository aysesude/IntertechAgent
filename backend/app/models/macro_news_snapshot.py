"""Canlı makro/piyasa haberi önbelleği ("riskk" 2026-08-24 eki + 2026-08-25
canlı veri genişlemesi — bkz. agents/risk_agent.py modül docstring'i).

Neden ayrı bir tablo, RAG değil: `data/documents/README.md` (2026-08-20)
RAG'ı yalnızca statik/uzun ömürlü içeriğe (bilanço, şirket profili, referans)
sınırladı; "makro" türü dokümanlara artık yeni ekleme yapılmıyor. Bu tablo o
politikaya dokunmaz — RAG'ın ve `rag.ingest`'in tamamen dışında, ayrı bir
mekanizmadır.

Neden istek anında değil, batch: `price_service.py`'deki aynı ilke —  canlı
çağrı sohbet anında yapılırsa sağlayıcı kesintisi sohbet kesintisi olur (10 sn
MCP tool zaman aşımı riski). Bu yüzden `data/macro_news_update.py`
(`data/daily_update.py` ile aynı kalıp) periyodik/elle çalışır, sonucu buraya
yazar; istek anında yalnızca bu tablo okunur (`get_macro_news` MCP tool'u).

Kapsam: yalnızca yfinance'te GERÇEK bir ticker'ı olan sınıflar — Kıymetli
Maden (GC=F/SI=F/PL=F) ve Döviz (USDTRY=X vb.), bkz.
app/providers/universe.py:yfinance_news_ticker. Tahvil ve Nakit'in (TEFAS
fonları, mevduat) Yahoo'da karşılığı yok; onlar için mevcut RAG makro
dokümanları (donmuş ama var olan) kaynak olmaya devam eder.
"""

from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import AssetClass
from app.models.base import Base, CreatedAtMixin, UUIDMixin


class MacroNewsSnapshot(UUIDMixin, CreatedAtMixin, Base):
    """Bir "haber anahtarı" (bkz. universe.py:macro_news_key — ör. XAUTRY,
    USDTRY) için çekilmiş tek bir canlı haber başlığı.

    `symbol`, portföydeki varlık sembolüyle BİREBİR eşleşmeyebilir: türetilmiş
    varlıklar (CEYREK, YARIM, ...) tabanlarının sembolü altında saklanır.
    Sorgulayan taraf (risk_agent) aynı `macro_news_key` eşlemesini kullanarak
    held sembolü bu anahtara çevirir.

    `created_at` (mixin) bu SATIRIN DB'ye ne zaman yazıldığını tutar;
    `fetched_at` batch çalışmasının ne zaman yapıldığını (birden fazla satır
    aynı `fetched_at`'i paylaşabilir, bkz. macro_news_ingest.upsert_news);
    `published_at` ise haberin KENDİ yayın tarihidir (sağlayıcıdan gelir).
    Üçü ayrı anlam taşıdığı için tek bir alana indirgenmez."""

    __tablename__ = "macro_news_snapshot"
    __table_args__ = (
        UniqueConstraint("symbol", "url", name="uq_macro_news_snapshot_symbol_url"),
        Index("ix_macro_news_snapshot_symbol_published_at", "symbol", "published_at"),
    )

    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(
        Enum(
            AssetClass,
            name="asset_class_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
