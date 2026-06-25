from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from .. import storage
from ..deps import get_current_user
from ..models import User
from ..schemas import DirListing

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("", response_model=DirListing)
def list_files(
    path: str = Query("", max_length=512),
    user: User = Depends(get_current_user),
):
    """List a folder inside the documents root (for the in-app file browser)."""
    try:
        return DirListing(**storage.list_dir(path))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")


@router.get("/download")
def download_file(
    path: str = Query(..., max_length=512),
    user: User = Depends(get_current_user),
):
    """Download any file inside the documents root by its relative path."""
    try:
        p = storage.resolve(path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(p, filename=p.name)
