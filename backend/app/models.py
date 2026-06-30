from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
    false,
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
    # Custom documents subfolder (relative to the root). NULL = default YYYY/MM.
    folder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def folder_path(self) -> str:
        """Effective documents subfolder for this month (relative to the root)."""
        return self.folder or f"{self.year:04d}/{self.month:02d}"

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
    # Which account this line came from, e.g. "Bank account" or "Credit card".
    # A period can hold several statements, one per account.
    source: Mapped[str] = mapped_column(
        String(60), nullable=False, server_default="Bank account", default="Bank account"
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
    # Marked as not needing a document (e.g. a bank fee). When True the line is
    # excluded from the "missing" report and from auto-matching.
    no_doc_needed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false(), default=False
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
    # How amount/date were read off the file, if at all: "text" (embedded text
    # layer), "ocr" (Tesseract on a scan), or NULL (entered by hand / not read).
    extracted_via: Mapped[str | None] = mapped_column(String(16), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    period: Mapped["Period"] = relationship(back_populates="documents")
    # Statement lines this document supports (set on match; cleared on delete).
    lines: Mapped[list["StatementLine"]] = relationship(back_populates="document")


class Travel(Base):
    """One business trip (cestovný príkaz / vyúčtovanie) for a person in a month.

    The trip header holds traveller info, dates, purpose and overall times
    (used for per-diem duration fallback). Route stops are in TravelLeg rows."""

    __tablename__ = "travels"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), nullable=False, index=True)
    traveller_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    traveller_address: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    trip_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    period: Mapped["Period"] = relationship()
    legs: Mapped[list["TravelLeg"]] = relationship(
        back_populates="travel", cascade="all, delete-orphan",
        order_by="TravelLeg.order_idx",
    )


class TravelLeg(Base):
    """One leg of a business trip: a single from→to segment with its own transport,
    optional routing data, reimbursable expense, and per-diem (stravné) portion."""

    __tablename__ = "travel_legs"

    id: Mapped[int] = mapped_column(primary_key=True)
    travel_id: Mapped[int] = mapped_column(
        ForeignKey("travels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    from_place: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    to_place: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    transport: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    leg_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    depart_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    arrive_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expense: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    per_diem: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    travel: Mapped["Travel"] = relationship(back_populates="legs")


class Vehicle(Base):
    """A company car tracked in the logbook."""

    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    ecv: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    vin: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    manufacturer: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    car_model: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    fuel_type: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    consumption: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    fuel_price: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    ownership: Mapped[str] = mapped_column(String(30), nullable=False, default="Firemné")
    date_added: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    odometer_base: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    trips: Mapped[list["CarTrip"]] = relationship(back_populates="vehicle", cascade="all, delete-orphan")


class CarTrip(Base):
    """One journey entry in the logbook for a vehicle."""

    __tablename__ = "car_trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    journey_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_dt: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    route: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    driver_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    trip_type: Mapped[str] = mapped_column(String(30), nullable=False, default="Firemná")
    events: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fuel_price_override: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    travel_id: Mapped[int | None] = mapped_column(
        ForeignKey("travels.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    vehicle: Mapped["Vehicle"] = relationship(back_populates="trips")


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
