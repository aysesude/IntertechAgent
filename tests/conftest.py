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

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(f"sqlite:///{_TEST_DB_PATH}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
    _TEST_DB_PATH.unlink(missing_ok=True)


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
