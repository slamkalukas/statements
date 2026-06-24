from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import storage
from ..database import get_db
from ..deps import get_current_user
from ..models import Setting, User
from ..schemas import StorageInfo, StorageUpdate

router = APIRouter(prefix="/api", tags=["settings"])

_HOST_PATH_KEY = "documents_host_path"


def _get_host_path(db: Session) -> str:
    """Return the saved host path override, or the env-var default."""
    row = db.query(Setting).filter(Setting.key == _HOST_PATH_KEY).first()
    if row and row.value:
        return row.value
    return storage.DOCUMENTS_HOST_DIR or "(see DOCUMENTS_DIR_HOST in docker-compose)"


@router.get("/storage", response_model=StorageInfo)
def get_storage_info(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Where uploaded documents are stored — shown on the Settings screen."""
    info = storage.storage_info()
    info["host_path"] = _get_host_path(db)
    return StorageInfo(**info)


@router.patch("/storage", response_model=StorageInfo)
def update_storage_info(
    body: StorageUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist the host folder label. This only updates the displayed path — the
    actual Docker volume mount is controlled by DOCUMENTS_DIR_HOST in docker-compose."""
    row = db.query(Setting).filter(Setting.key == _HOST_PATH_KEY).first()
    if row:
        row.value = body.host_path
    else:
        db.add(Setting(key=_HOST_PATH_KEY, value=body.host_path))
    db.commit()

    info = storage.storage_info()
    info["host_path"] = body.host_path
    return StorageInfo(**info)
