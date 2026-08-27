"""Tüm modeller burada import edilir ki Base.metadata (ve dolayısıyla Alembic
autogenerate) hepsini görsün."""

from app.models.asset import Asset
from app.models.base import Base
from app.models.chat_session import ChatSession
from app.models.data_ingest_log import DataIngestLog
from app.models.holding import Holding
from app.models.macro_news_snapshot import MacroNewsSnapshot
from app.models.message import Message, MessageRole, MessageStatus
from app.models.portfolio import Portfolio
from app.models.price_history import PriceHistory
from app.models.transaction import Transaction, TransactionType
from app.models.user import User

__all__ = [
    "Asset",
    "Base",
    "ChatSession",
    "DataIngestLog",
    "Holding",
    "MacroNewsSnapshot",
    "Message",
    "MessageRole",
    "MessageStatus",
    "Portfolio",
    "PriceHistory",
    "Transaction",
    "TransactionType",
    "User",
]
