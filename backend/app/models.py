from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    """The single admin account. Bootstrapped from env on first boot; there is
    no public registration. Kept as a table (not a constant) so password changes
    persist and the schema can grow to multiple users later."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Period(Base):
    """One calendar month of bookkeeping. Documents hang off a period. Closing a
    period locks it (no more uploads or deletes) so an archived month stays as
    filed."""

    __tablename__ = "periods"
    __table_args__ = (UniqueConstraint("year", "month", name="uq_period_year_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..12
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open | closed
    note: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    documents: Mapped[list["Document"]] = relationship(
        back_populates="period", cascade="all, delete-orphan"
    )
    lines: Mapped[list["StatementLine"]] = relationship(
        back_populates="period", cascade="all, delete-orphan"
    )


class StatementLine(Base):
    """One transaction parsed from the month's bank statement. Outgoing lines
    (negative amount) are what we expect a supporting invoice/bill for; an
    outgoing line with no linked document is "missing" — the core report.
    """

    __tablename__ = "statement_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("periods.id"), nullable=False, index=True
    )
    txn_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Signed: negative = money out (a payment we expect a document for).
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    payee: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    # The supporting document, once matched. Null = still missing (for outgoing).
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    period: Mapped["Period"] = relationship(back_populates="lines")
    document: Mapped["Document | None"] = relationship(back_populates="lines")


class Document(Base):
    """A file filed under a period. The bytes live on the mapped host folder at
    `stored_path` (relative to DOCUMENTS_DIR, e.g. "2026/06/statement.pdf"); this
    row is the metadata + index entry."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("periods.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # bank_statement | invoice | receipt | other
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    note: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    period: Mapped["Period"] = relationship(back_populates="documents")
    # Statement lines this document supports (set on match; cleared on delete).
    lines: Mapped[list["StatementLine"]] = relationship(back_populates="document")


class Setting(Base):
    """Persistent key-value configuration that can be changed from the UI without
    restarting the container. Env vars provide initial defaults; a saved Setting
    overrides them at runtime."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    """Append-only record of mutating actions. Captures who did what, when, and
    to which entity. Never updated or deleted in normal operation."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # create | update | delete
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. "document"
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    detail: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
