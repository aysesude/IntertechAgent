"""assets: uygunluk risk seviyesi (risk_level, 1-7)

Seviye şimdiye kadar YALNIZCA kodda yaşıyordu: sınıf varsayılanı
`config.ASSET_CLASS_ADVICE_RISK_LEVEL`, varlık istisnası
`providers/universe.AssetSpec.risk_level`, ikisini birleştiren okuma noktası
`services/advice_eligibility.asset_risk_level`.

Bunun bedeli, alanın SQL'den GÖRÜNMEMESİ oldu: `assets` tablosuna bakan biri
seviyenin var olduğunu bile anlamıyor, "puanının üstünde varlık tutan
kullanıcılar" gibi bir sorgu SQL ile yazılamıyor, JOIN yapılamıyordu.
İleride alım/satım engeli ve risk ajanı bu bilgiye ihtiyaç duyacak; ikisi de
veriye DB üzerinden bakıyor.

TÜREV KOPYA, ikinci bir gerçek değil. Tanım noktası hâlâ `universe.py`;
`seed_assets` her koşuda bu sütunu koddan yeniden yazar (backfill ve
daily_update başlangıçta onu çağırdığı için sütun kendiliğinden tazelenir).
Kod ile DB ayrışırsa `scripts/data_doctor` bunu bildirir.

DOLDURMA MIGRATION İÇİNDE. Deploy `alembic upgrade head` çalıştırıyor ama
seed çalıştırmıyor; sütun boş kalsaydı bir sonraki cron koşusuna kadar
(en fazla bir gün) NULL kalır ve o aralıkta seviyeye bakan her sorgu sessizce
"seviye yok" görürdü. Değerler burada SABİT yazılı — migration bir anlık
görüntüdür, canlı koda referans vermemelidir; kod değişince yeni migration
değil, `seed_assets` günceller.

NULLABLE bırakıldı: mevcut satırların üzerine ekleniyor ve evrende olmayan
(pasife çekilmiş) eski semboller için anlamlı bir seviye yok. Aktif varlıkta
NULL olmaması bir DEĞİŞMEZDİR ve testle korunur, kısıtla değil — pasif
satırlar aynı sütunu paylaşıyor.

Revision ID: a3d75e1c9f04
Revises: f18c4a2e7b90
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3d75e1c9f04"
down_revision: str | None = "f18c4a2e7b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK_NAME = "ck_assets_risk_level_range"

# Sınıf varsayılanları — `config.ASSET_CLASS_ADVICE_RISK_LEVEL` ile aynı,
# migration anındaki hâliyle dondurulmuş.
_SINIF_SEVIYELERI = {
    "cash": 1,
    "bond": 2,
    "currency": 3,
    "precious_metal": 4,
    "stock": 5,
}

# Sınıfından ayrılan varlıklar — `AssetSpec.risk_level` ile aynı.
_VARLIK_ISTISNALARI = {
    1: ["IOO"],
    3: ["AKE"],
    5: ["XAGTRY", "XPTTRY"],
    6: [
        "AAPL", "AFT", "AMD", "AMZN", "BRK-B", "CAT", "GOOGL", "JNJ", "JPM",
        "KO", "LLY", "MA", "MCD", "META", "MSFT", "NVDA", "PG", "TSLA",
        "UNH", "V", "WMT", "XOM",
    ],
    7: ["BHE"],
}


def upgrade() -> None:
    op.add_column("assets", sa.Column("risk_level", sa.Integer(), nullable=True))
    op.create_check_constraint(
        _CHECK_NAME,
        "assets",
        "risk_level IS NULL OR (risk_level BETWEEN 1 AND 7)",
        )

    baglanti = op.get_bind()

    # Önce sınıf varsayılanı, sonra istisnalar — istisnalar varsayılanı EZER.
    for sinif, seviye in _SINIF_SEVIYELERI.items():
        baglanti.execute(
            sa.text("UPDATE assets SET risk_level = :seviye WHERE asset_class = :sinif"),
            {"seviye": seviye, "sinif": sinif},
        )

    for seviye, semboller in _VARLIK_ISTISNALARI.items():
        baglanti.execute(
            sa.text("UPDATE assets SET risk_level = :seviye WHERE symbol IN :semboller").bindparams(
                sa.bindparam("semboller", expanding=True)
            ),
            {"seviye": seviye, "semboller": semboller},
        )


def downgrade() -> None:
    op.drop_constraint(_CHECK_NAME, "assets", type_="check")
    op.drop_column("assets", "risk_level")
