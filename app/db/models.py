from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, Index, MetaData, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names keep Alembic autogenerate diffs stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    rubrics: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_documents_created_date", "created_date"),)
