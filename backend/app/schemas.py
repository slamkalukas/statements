from datetime import date, datetime, time
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


class PeriodFolderUpdate(BaseModel):
    # Relative subfolder under the documents root; blank resets to the default YYYY/MM.
    folder: str = Field(default="", max_length=255)


class PeriodOut(ORMModel):
    id: int
    year: int
    month: int
    status: str
    note: str
    folder: str = ""        # effective documents subfolder (relative to the root)
    created_at: datetime | None = None
    # Computed completeness/summary fields.
    document_count: int = 0
    has_statement: bool = False  # a statement has been imported (lines exist)
    total_size: int = 0
    outgoing_count: int = 0      # outgoing (payment) lines parsed from the statement
    missing_count: int = 0       # outgoing lines still needing a document — the report
    no_doc_count: int = 0        # outgoing lines marked as not needing a document (e.g. fees)
    travel_count: int = 0        # travel trips in this month
    car_trip_count: int = 0      # logbook drives (with km) in this month


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


class MoveLineRequest(BaseModel):
    # Target accounting month for the line (the period is created if absent).
    year: int = Field(ge=1970, le=2200)
    month: int = Field(ge=1, le=12)


# ---- Storage info (Settings) ----
class StorageInfo(BaseModel):
    host_path: str        # the folder on the host where files are filed
    container_path: str   # where the backend writes inside the container
    layout: str           # how files are organized within the root
    max_upload_mb: int


class StorageUpdate(BaseModel):
    # The default-folder layout template, e.g. "{YYYY}/{MM}" or "#{YYYY}/Vydavky".
    layout: str = Field(max_length=255)


# ---- Travel report (cestovné) ----

class TravelLegBase(BaseModel):
    from_place: str = Field(default="", max_length=120)
    to_place: str = Field(default="", max_length=120)
    transport: str = Field(default="", max_length=60)
    leg_date: date | None = None      # explicit date for this leg (None = same as trip_date)
    depart_time: time | None = None   # when you leave from_place
    arrive_time: time | None = None   # when you arrive at to_place
    expense: float | None = None      # reimbursable cost (ticket, taxi receipt, etc.)
    per_diem: float | None = None     # stravné for this leg (None = not set)


class TravelLegCreate(TravelLegBase):
    order_idx: int = 0


class TravelLegUpdate(BaseModel):
    from_place: str | None = Field(default=None, max_length=120)
    to_place: str | None = Field(default=None, max_length=120)
    transport: str | None = Field(default=None, max_length=60)
    leg_date: date | None = None
    depart_time: time | None = None
    arrive_time: time | None = None
    expense: float | None = None
    per_diem: float | None = None
    order_idx: int | None = None


class TravelLegOut(TravelLegBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    travel_id: int
    order_idx: int
    distance_km: float | None = None
    duration_min: int | None = None  # one-way drive time rounded to 20 min (ORS)


class TravelBase(BaseModel):
    traveller_name: str = Field(default="", max_length=120)
    traveller_address: str = Field(default="", max_length=255)
    trip_date: date
    end_date: date | None = None
    purpose: str = Field(default="", max_length=255)
    vehicle_id: int | None = None


class TravelCreate(TravelBase):
    legs: list[TravelLegCreate] = Field(default_factory=list)


class BulkTravelCreate(TravelBase):
    dates: list[date] = Field(min_length=1, max_length=200)
    legs: list[TravelLegCreate] = Field(default_factory=list)


class TravelUpdate(BaseModel):
    traveller_name: str | None = Field(default=None, max_length=120)
    traveller_address: str | None = Field(default=None, max_length=255)
    trip_date: date | None = None
    end_date: date | None = None
    purpose: str | None = Field(default=None, max_length=255)
    vehicle_id: int | None = None


class TravelOut(TravelBase):
    id: int
    period_id: int
    per_diem: float          # effective: sum of leg per_diems, or duration-based fallback
    per_diem_computed: float
    duration_hours: float | None = None  # derived from first leg depart → last leg arrive
    total_km: float | None = None        # sum of all leg distance_km
    legs: list[TravelLegOut] = []


class PerDiemRates(BaseModel):
    band1: float = Field(ge=0)  # 5–12 h
    band2: float = Field(ge=0)  # 12–18 h
    band3: float = Field(ge=0)  # over 18 h


# ---- Logbook (Kniha jázd) ----

class VehicleBase(BaseModel):
    ecv: str = Field(max_length=20)
    vin: str = Field(default="", max_length=20)
    manufacturer: str = Field(default="", max_length=60)
    car_model: str = Field(default="", max_length=60)
    fuel_type: str = Field(default="", max_length=30)
    consumption: float | None = None
    fuel_price: float | None = None
    ownership: str = Field(default="Firemné", max_length=30)
    date_added: date | None = None
    active: bool = True
    odometer_base: int | None = None


class VehicleCreate(VehicleBase):
    pass


class VehicleUpdate(BaseModel):
    ecv: str | None = Field(default=None, max_length=20)
    vin: str | None = Field(default=None, max_length=20)
    manufacturer: str | None = Field(default=None, max_length=60)
    car_model: str | None = Field(default=None, max_length=60)
    fuel_type: str | None = Field(default=None, max_length=30)
    consumption: float | None = None
    fuel_price: float | None = None
    ownership: str | None = Field(default=None, max_length=30)
    date_added: date | None = None
    active: bool | None = None
    odometer_base: int | None = None


class VehicleOut(VehicleBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None
    km_total: int | None = None
    km_ytd: int | None = None


class CarTripBase(BaseModel):
    start_dt: datetime
    end_dt: datetime | None = None
    purpose: str = Field(default="", max_length=255)
    route: str = Field(default="", max_length=1000)
    km: int | None = None
    driver_name: str = Field(default="", max_length=120)
    trip_type: str = Field(default="Firemná", max_length=30)
    events: str | None = Field(default=None, max_length=255)
    fuel_price_override: float | None = None


class CarTripCreate(CarTripBase):
    travel_id: int | None = None


class CarTripUpdate(BaseModel):
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    purpose: str | None = Field(default=None, max_length=255)
    route: str | None = Field(default=None, max_length=1000)
    km: int | None = None
    driver_name: str | None = Field(default=None, max_length=120)
    trip_type: str | None = Field(default=None, max_length=30)
    events: str | None = None
    fuel_price_override: float | None = None
    travel_id: int | None = None


class CarTripOut(CarTripBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vehicle_id: int
    journey_number: int
    cost: float | None = None
    travel_id: int | None = None
    created_at: datetime | None = None


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
    total_travels: int = 0     # travel trips across all months
    total_car_trips: int = 0   # logbook drives (with km) across all months
    recent_periods: list[PeriodOut]
