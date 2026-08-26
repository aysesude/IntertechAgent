"""Test ortamı: gerçek Postgres yerine geçici bir SQLite dosyası kullanılır.
Modeller dialect-agnostic tiplerle yazıldığı için (bkz. app/models/base.py)
aynı kod Postgres'te de doğru çalışır — bkz. backend/alembic/versions/.

DATABASE_URL, app.core.config henüz import edilmeden (bu dosyanın en üstünde)
ayarlanmalı; aksi halde `Settings` gerçek Postgres URL'sini önbelleğe alır.
"""

import os
import tempfile
import uuid
from pathlib import Path

_TEST_DB_PATH = Path(tempfile.gettempdir()) / f"finans_danismani_test_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"

# `Settings.jwt_secret_key` bilerek varsayilansiz (bkz. config.py) — .env
# olmadan calisan testler icin burada sabitleniyor. Testte gercek bir sirra
# ihtiyac yok, sadece imzalanan token'in ayni anahtarla cozulebilmesi yeterli.
os.environ.setdefault("JWT_SECRET_KEY", "test-anahtari-yalnizca-testler-icin")

# Ankraj testlerde SABITLENIR. Uretimde varsayilan olarak bos birakilir ve
# seed onu gercek fiyat verisinin bittigi gune baglar (bkz. data/anchor.py) —
# ama testler icin bu yanlis olurdu: uretilen defterin tarihleri fixture'daki
# fiyatlara, dolayisiyla testin kostugu GUNE bagli hale gelirdi. Sabit tarih,
# `ANCHOR_DATE` override yolunun da her kosuda sinanmasini sagliyor.
os.environ.setdefault("ANCHOR_DATE", "2026-08-01")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import create_access_token
from app.models import Base, User


def auth_headers(user: User) -> dict[str, str]:
    """Kullanıcı adına geçerli bir Bearer başlığı üretir.

    Testler token'ı `/api/auth/login` üzerinden almıyor: giriş akışının kendisi
    ayrıca test ediliyor (test_auth_api.py), diğer testlerin ona bağımlı olması
    giriş bozulduğunda ilgisiz onlarca testi birden kırardı.
    """
    token, _ = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client_for():
    """Bir kullanıcı adına kimlik doğrulanmış TestClient üreten fabrika.

    `client_for(user)` o kullanıcının token'ını taşır; `client_for()` hiç token
    göndermez (401/403 yollarını sınamak için).
    """

    def _make(user: User | None = None) -> TestClient:
        from app.main import app  # geç import: DATABASE_URL yukarıda ayarlanmış olmalı

        if user is None:
            return TestClient(app)
        return TestClient(app, headers=auth_headers(user))

    return _make


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(f"sqlite:///{_TEST_DB_PATH}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
    try:
        _TEST_DB_PATH.unlink(missing_ok=True)
    except PermissionError:
        # Windows: bağlantı havuzu dosyayı geç bırakabiliyor; geçici dizindeki
        # artık dosya zararsızdır, test sonucunu etkilememeli.
        pass


@pytest.fixture()
def db_session(engine):
    session_factory = sessionmaker(bind=engine)
    session: Session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()
