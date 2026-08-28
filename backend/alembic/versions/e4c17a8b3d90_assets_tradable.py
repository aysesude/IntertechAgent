"""assets: tutulabilirlik bayrağı (tradable)

`AssetSpec.tradable` Ağustos'tan beri evrende tanımlıydı ve XU100'de `False`
duruyordu, ama VERİTABANINA HİÇ YAZILMIYORDU: bayrağı okuyan tek yer
`data/seed_ledger` idi (endeks kullanıcılara dağıtılmasın diye). Al/Sat listesi
ise `is_active` dışında süzgeç uygulamıyordu — sonuç olarak **BIST 100 endeksi
satın alınabilir bir varlık gibi listeleniyordu**; sınıfı hisse, uygunluk
seviyesi 5, yani anket puanı 5 ve üzeri olan herkes "endeks alabiliyordu".

Aynı yoldan iki gösterge daha geliyor (BRENT, SPX): fiyatlanır ve saklanırlar
çünkü piyasa şeridi onlara dayanıyor, ama portföye giremezler. Bayrak DB'ye
taşınmadan bu iki satır da Al/Sat listesine düşerdi.

`is_active` ile karıştırılmamalı: pasif varlık artık FİYATLANMAZ (evrenden
çıkmıştır), tutulamayan varlık fiyatlanır ama alınamaz.

NOT NULL + server_default true: mevcut satırların tamamı tutulabilirdi, tek
istisna XU100 ve o aşağıda tek tek kapatılıyor. Varsayılanın `true` olması
yeni bir varlığın yanlışlıkla listeden düşmesindense yanlışlıkla listede
kalmasını seçiyor — ikincisi görünür, ilki sessiz.

Revision ID: e4c17a8b3d90
Revises: e8e6807ad5c4
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4c17a8b3d90"
down_revision: str | None = "e8e6807ad5c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Bu migration çalıştığında evrende tutulamayan tek varlık XU100'dür; BRENT ve
# SPX'in satırları henüz yok (ilk `seed_assets` koşusunda doğru bayrakla
# yaratılacaklar). Liste yine de sembol bazlı yazıldı: `seed_assets`
# çalıştırılmadan da şema tutarlı kalsın.
_TUTULAMAYANLAR = ("XU100", "BRENT", "SPX")


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("tradable", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(
        "UPDATE assets SET tradable = false WHERE symbol IN "
        f"({', '.join(repr(s) for s in _TUTULAMAYANLAR)})"
    )


def downgrade() -> None:
    op.drop_column("assets", "tradable")
