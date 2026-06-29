from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import folders, storage
from ..database import get_db
from ..deps import get_current_user
from ..models import Setting, User
from ..schemas import StorageInfo, StorageUpdate

router = APIRouter(prefix="/api", tags=["settings"])


def _info(db: Session) -> StorageInfo:
    return StorageInfo(
        host_path=storage.DOCUMENTS_HOST_DIR or "(see DOCUMENTS_DIR_HOST in docker-compose)",
        container_path=str(storage.DOCUMENTS_DIR),
        layout=folders.get_layout(db),
        max_upload_mb=storage.MAX_UPLOAD_MB,
    )


@router.get("/storage", response_model=StorageInfo)
def get_storage_info(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Where uploaded documents are stored — shown on the Settings screen. The
    host path is fixed by the Docker volume mount; only the layout is editable."""
    return _info(db)


@router.patch("/storage", response_model=StorageInfo)
def update_storage_layout(
    body: StorageUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set the default-folder layout template (e.g. "{YYYY}/{MM}"). Validated by
    rendering it for a sample month; blank resets to the default. Affects where
    *new* uploads/sync go for months without an explicit folder — existing files
    stay where they are."""
    pattern = (body.layout or "").strip()
    if not pattern:
        pattern = folders.DEFAULT_LAYOUT
    try:
        rendered = folders.render_layout(pattern, 2026, 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid layout")
    if not rendered:
        raise HTTPException(status_code=400, detail="Layout must produce a folder path")

    row = db.query(Setting).filter(Setting.key == folders.LAYOUT_KEY).first()
    if row:
        row.value = pattern
    else:
        db.add(Setting(key=folders.LAYOUT_KEY, value=pattern))
    db.commit()
    return _info(db)
