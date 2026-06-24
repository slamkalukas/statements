from fastapi import APIRouter, Depends

from .. import storage
from ..deps import get_current_user
from ..models import User
from ..schemas import StorageInfo

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/storage", response_model=StorageInfo)
def get_storage_info(user: User = Depends(get_current_user)):
    """Where uploaded documents are stored — shown on the Settings screen."""
    return StorageInfo(**storage.storage_info())
