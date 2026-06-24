from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Exact monetary type: validated to 2 decimal places, bounded magnitude.
Money = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]

# The kinds of document a month can hold.
DOCUMENT_KINDS = ("bank_statement", "invoice", "receipt", "other")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Auth / users ----
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(ORMModel):
    id: int
    email: EmailStr
    created_at: datetime | None = None


class TokenResponse(BaseModel):
    token: str
    user: UserOut


# ---- Periods ----
class PeriodCreate(BaseModel):
    year: int = Field(ge=1970, le=2200)
    month: int = Field(ge=1, le=12)
    note: str = Field(default="", max_length=512)


class PeriodOut(ORMModel):
    id: int
    year: int
    month: int
    status: str
    note: str
    created_at: datetime | None = None
    # Computed completeness/summary fields.
    document_count: int = 0
    has_statement: bool = False  # a statement has been imported (lines exist)
    total_size: int = 0
    outgoing_count: int = 0      # outgoing (payment) lines parsed from the statement
    missing_count: int = 0       # outgoing lines with no linked document — the report


# ---- Documents ----
class DocumentOut(ORMModel):
    id: int
    period_id: int
    kind: str
    original_filename: str
    content_type: str
    size_bytes: int
    doc_date: date | None = None
    amount: float | None = None
    note: str
    uploaded_at: datetime | None = None
    linked_line_count: int = 0  # how many statement lines this document supports


# ---- Statement lines / reconciliation ----
class StatementLineOut(BaseModel):
    id: int
    period_id: int
    txn_date: date
    amount: float          # signed; negative = outgoing payment
    description: str
    payee: str
    currency: str
    document_id: int | None = None
    document_filename: str | None = None


class StatementImportResult(BaseModel):
    format: str
    parsed: int
    imported: int
    duplicates: int
    outgoing: int


class LinkRequest(BaseModel):
    document_id: int


# ---- Storage info (Settings) ----
class StorageInfo(BaseModel):
    host_path: str        # the folder on the host where files are filed
    container_path: str   # where the backend writes inside the container
    layout: str           # how files are organized within the root
    max_upload_mb: int


class StorageUpdate(BaseModel):
    host_path: str = Field(max_length=512)


# ---- Dashboard ----
class DashboardSummary(BaseModel):
    periods_tracked: int
    open_periods: int
    total_documents: int
    total_size: int
    no_statement: int          # months with no statement imported yet
    months_with_missing: int   # months that have unmatched outgoing payments
    total_missing: int         # total unmatched outgoing payments across all months
    recent_periods: list[PeriodOut]
