"""Where a period's documents live: a configurable default layout (a template
with {YYYY}/{MM} placeholders) plus any explicit per-month override.

The layout is stored in the Settings table and editable from the Settings page,
so the user can match their real on-disk structure (e.g. "#{YYYY}/Vydavky") once
instead of setting every month's folder by hand.
"""
from . import storage
from .models import Period, Setting

DEFAULT_LAYOUT = "{YYYY}/{MM}"
LAYOUT_KEY = "documents_layout"


def get_layout(db) -> str:
    """The current default-folder layout template (falls back to {YYYY}/{MM})."""
    row = db.query(Setting).filter(Setting.key == LAYOUT_KEY).first()
    return row.value if (row and row.value) else DEFAULT_LAYOUT


def render_layout(pattern: str, year: int, month: int) -> str:
    """Fill a layout template for a given month and normalize it to a safe
    relative subfolder. Supports {YYYY} {YY} {MM} {M} placeholders."""
    s = pattern or DEFAULT_LAYOUT
    s = (s.replace("{YYYY}", f"{year:04d}")
          .replace("{YY}", f"{year % 100:02d}")
          .replace("{MM}", f"{month:02d}")
          .replace("{M}", str(month)))
    return storage.normalize_folder(s)


def default_folder(db, year: int, month: int) -> str:
    """The default (layout-derived) folder for a month, ignoring any override."""
    return render_layout(get_layout(db), year, month)


def effective_folder(db, period: Period) -> str:
    """The folder a period's documents actually use: its explicit override if set,
    otherwise the layout-derived default."""
    if period.folder:
        return period.folder
    return default_folder(db, period.year, period.month)
