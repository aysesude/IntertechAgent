"""risk_profile_enum: 'growth' (Büyüme) değeri eklenir

Risk/Strateji Ajanı senaryo motoru (config.py: RISK_MAX_ASSET_WEIGHT,
RISK_MAX_CATEGORY_WEIGHT, RISK_DEFENSE_FLOOR, RISK_TARGET_VOLATILITY_BAND,
RISK_RECEIVER_PREFERENCE_ORDER) artık 4 risk profili kullanıyor: Korumacı,
Dengeli, Büyüme, Agresif. Bu migration yalnızca veritabanı enum tipine yeni
değeri ekler; mevcut kullanıcı satırları değişmez, varsayılan profil
(balanced) aynı kalır.

Revision ID: b26e8dab6ef9
Revises: 6a92d4c8e0f1
Create Date: 2026-08-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b26e8dab6ef9"
down_revision: str | None = "6a92d4c8e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADD VALUE transaction içinde çalışır (bkz. 9c31e7a0d2b4); kısıt yalnızca
    # yeni değerin AYNI transaction'da KULLANILAMAMASIDIR — bu migration
    # 'growth' değerini kullanmaz, yalnızca ekler. AFTER ile Python
    # tarafındaki RiskProfile enum sırasıyla (conservative, balanced, growth,
    # aggressive) aynı sırada tutuluyor.
    op.execute("ALTER TYPE risk_profile_enum ADD VALUE IF NOT EXISTS 'growth' AFTER 'balanced'")


def downgrade() -> None:
    # PG enum'dan tek bir değer silinemez; tip yeniden yaratılır. Yeni tipte
    # 'growth' bulunmadığı için o değeri taşıyan satırlar önce başka bir
    # profile alınmalı — aksi halde aşağıdaki USING cast'i hata verir
    # (bkz. 9c31e7a0d2b4'teki aynı desen).
    #
    # Bu dosya yazıldığında "hiçbir kullanıcı growth değil" varsayılıyordu.
    # Seed artık 'growth' kullanıcıları üretiyor (data/seed_ledger.py:
    # ARCHETYPE_RISK_PROFILE), yani bu satırların VAR OLMASI beklenen durum;
    # varsayımla çalışmak downgrade'i ham bir cast hatasıyla düşürürdü.
    #
    # Hedef olarak 'balanced' seçildi: downgrade bilgi kaybı olmadan yapılamaz,
    # ama risk toleransını olduğundan DÜŞÜK varsaymak finansal üründe güvenli
    # yöndür — 'aggressive'e taşımak kullanıcıya hak etmediği agresiflikte
    # öneri ürettirirdi. GERİ ALINAMAZ: upgrade tekrar çalıştırıldığında bu
    # kullanıcılar 'growth' değil 'balanced' olarak kalır.
    op.execute("UPDATE users SET risk_profile = 'balanced' WHERE risk_profile = 'growth'")
    op.execute("ALTER TYPE risk_profile_enum RENAME TO risk_profile_enum_old")
    op.execute("CREATE TYPE risk_profile_enum AS ENUM ('conservative', 'balanced', 'aggressive')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN risk_profile TYPE risk_profile_enum "
        "USING risk_profile::text::risk_profile_enum"
    )
    op.execute("DROP TYPE risk_profile_enum_old")
