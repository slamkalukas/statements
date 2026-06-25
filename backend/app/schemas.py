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
    missing_count: int = 0       # outgoing lines still needing a document — the report
    no_doc_count: int = 0        # outgoing lines marked as not needing a document (e.g. fees)


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
    extracted_via: str | None = None  # "text" | "ocr" | None — how amount/date were read


# ---- Statement lines / reconciliation ----
class StatementLineOut(BaseModel):
    id: int
    period_id: int
    source: str = "Bank account"
    txn_date: date
    amount: float          # signed; negative = outgoing payment
    description: str
    payee: str
    currency: str
    document_id: int | None = None
    document_filename: str | None = None
    no_doc_needed: bool = False  # marked as not needing a document (e.g. a fee)


class StatementImportResult(BaseModel):
    format: str
    source: str
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


# ---- File browser (navigate the documents root) ----
class FileEntry(BaseModel):
    name: str
    path: str          # path relative to the documents root
    is_dir: bool
    size_bytes: int = 0
    child_count: int = 0
    modified: str | None = None


class DirListing(BaseModel):
    path: str           # current folder, relative to the root ("" = root)
    parent: str         # parent folder, relative to the root
    entries: list[FileEntry]


# ---- Auto-match (scan documents, pair to transactions) ----
class AutoMatchRequest(BaseModel):
    rescan: bool = False  # re-read every document, even ones that already have an amount


class AutoMatchResult(BaseModel):
    scanned: int      # documents read for an amount this run
    ocr: int          # of those, how many needed OCR (scanned/image-only)
    matched: int      # transactions newly paired to a document
    ambiguous: int    # amounts where several docs/payments collide (left for you)
    still_missing: int  # outgoing payments still without a document


# ---- Folder sync ----
class SyncResult(BaseModel):
    scanned: int    # total files found on disk
    imported: int   # newly registered in the DB
    skipped: int    # already tracked, left alone
    ocr: int = 0     # of the imported files, how many needed OCR
    matched: int = 0  # payments auto-paired to the imported files


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
