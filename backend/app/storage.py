"""The file layer: documents live on the mapped host folder, not in the DB.

Layout is `<DOCUMENTS_DIR>/<YYYY>/<MM>/<filename>` (year/month nested, files flat
within a month). The DB stores the relative `stored_path`; everything here keeps
that path safe (no traversal outside the root) and tidy (collision-free names,
empty dirs pruned on delete).
"""
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

DOCUMENTS_DIR = Path(os.getenv("DOCUMENTS_DIR", "/data/documents")).resolve()
# The host folder this is bound to (informational — shown in Settings). The
# backend only ever touches DOCUMENTS_DIR inside the container; this is just the
# corresponding path on the host, passed through from compose for display.
DOCUMENTS_HOST_DIR = os.getenv("DOCUMENTS_DIR_HOST", "").strip()
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def storage_info() -> dict:
    """Where documents are stored, for display in Settings."""
    return {
        "host_path": DOCUMENTS_HOST_DIR or "(see DOCUMENTS_DIR_HOST in docker-compose)",
        "container_path": str(DOCUMENTS_DIR),
        "layout": "<root>/<YYYY>/<MM>/<file>",
        "max_upload_mb": MAX_UPLOAD_MB,
    }

# Stream copy chunk size.
_CHUNK = 1024 * 1024

# Characters we don't want in stored filenames (path separators, control chars,
# Windows-reserved punctuation). Everything else is preserved so names stay
# recognizable.
_UNSAFE = re.compile(r'[\\/\x00-\x1f<>:"|?*]')


class UploadTooLarge(Exception):
    """Raised when an upload exceeds MAX_UPLOAD_BYTES."""


def ensure_root() -> None:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str) -> str:
    """Reduce an arbitrary client filename to a safe basename.

    Strips any directory components and unsafe characters, collapses dots so a
    name can't become `..`, and falls back to a default if nothing survives.
    """
    # Keep only the basename — drop any path the client may have sent.
    name = name.replace("\\", "/").split("/")[-1]
    name = _UNSAFE.sub("_", name).strip().strip(".")
    name = re.sub(r"\.{2,}", ".", name)
    return name[:200] or "document"


def _unique_path(folder: Path, filename: str) -> Path:
    """First free path in `folder` for `filename`, suffixing ` (1)`, ` (2)` ..."""
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    i = 1
    while True:
        candidate = folder / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _assert_inside_root(path: Path) -> None:
    """Guard against path traversal: the resolved path must stay under the root."""
    root = str(DOCUMENTS_DIR)
    resolved = str(path.resolve())
    if resolved != root and not resolved.startswith(root + os.sep):
        raise ValueError("Resolved path escapes the documents directory")


def normalize_folder(rel: str) -> str:
    """Normalize a user-supplied relative subfolder to a safe posix path under
    the root. Returns "" for the root. Raises ValueError if it escapes the root."""
    raw = (rel or "").strip().replace("\\", "/").strip("/")
    parts = [sanitize_filename(p) for p in raw.split("/") if p not in ("", ".", "..")]
    folder = DOCUMENTS_DIR.joinpath(*parts).resolve() if parts else DOCUMENTS_DIR
    _assert_inside_root(folder)
    return "/".join(parts)


def resolve_folder(rel: str) -> Path:
    """Absolute path for a relative subfolder under the root, traversal-guarded."""
    norm = normalize_folder(rel)
    path = (DOCUMENTS_DIR / norm).resolve() if norm else DOCUMENTS_DIR
    _assert_inside_root(path)
    return path


def save_upload(folder: str, upload: UploadFile) -> tuple[str, int, str]:
    """Persist an upload under <root>/<folder>/, streaming with a size cap.

    Returns (relative_stored_path, size_bytes, original_filename). Raises
    UploadTooLarge if the stream exceeds the cap (the partial file is removed).
    """
    filename = sanitize_filename(upload.filename or "document")
    dest_folder = resolve_folder(folder)
    dest_folder.mkdir(parents=True, exist_ok=True)

    dest = _unique_path(dest_folder, filename)
    _assert_inside_root(dest)

    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = upload.file.read(_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise UploadTooLarge()
                out.write(chunk)
    except UploadTooLarge:
        dest.unlink(missing_ok=True)
        raise

    relative = dest.relative_to(DOCUMENTS_DIR).as_posix()
    return relative, size, (upload.filename or filename)


def save_upload_bytes(folder: str, filename: str, data: bytes) -> tuple[str, int, str]:
    """Persist already-read bytes under <root>/<folder>/. Same naming and
    traversal/size guards as save_upload. Returns (relative_path, size, name)."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadTooLarge()
    safe = sanitize_filename(filename or "document")
    dest_folder = resolve_folder(folder)
    dest_folder.mkdir(parents=True, exist_ok=True)
    dest = _unique_path(dest_folder, safe)
    _assert_inside_root(dest)
    dest.write_bytes(data)
    return dest.relative_to(DOCUMENTS_DIR).as_posix(), len(data), (filename or safe)


def resolve(stored_path: str) -> Path:
    """Absolute path for a stored document, re-checking containment."""
    path = (DOCUMENTS_DIR / stored_path).resolve()
    _assert_inside_root(path)
    return path


def list_dir(rel: str = "") -> dict:
    """List one folder inside the documents root for the in-app file browser.

    `rel` is a path relative to the root ("" = root). Returns the normalized
    path, its parent, and entries (folders first, then files), each with a
    root-relative path. Stays within the root (path-traversal guard).
    """
    rel = (rel or "").strip().strip("/")
    target = (DOCUMENTS_DIR / rel).resolve() if rel else DOCUMENTS_DIR
    _assert_inside_root(target)

    if not target.is_dir():
        if target == DOCUMENTS_DIR:
            # Root not created yet (nothing uploaded) — show it as empty.
            return {"path": "", "parent": "", "entries": []}
        raise FileNotFoundError(rel)

    dirs: list[dict] = []
    files: list[dict] = []
    for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        try:
            st = entry.stat()
        except OSError:
            continue
        rel_path = entry.relative_to(DOCUMENTS_DIR).as_posix()
        if entry.is_dir():
            try:
                child_count = sum(1 for _ in entry.iterdir())
            except OSError:
                child_count = 0
            dirs.append({"name": entry.name, "path": rel_path, "is_dir": True, "child_count": child_count})
        elif entry.is_file():
            files.append({
                "name": entry.name,
                "path": rel_path,
                "is_dir": False,
                "size_bytes": st.st_size,
                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            })

    parent = ""
    if rel:
        parent = Path(rel).parent.as_posix()
        if parent == ".":
            parent = ""
    return {"path": rel, "parent": parent, "entries": dirs + files}


def delete(stored_path: str) -> None:
    """Remove a stored file and prune now-empty month/year folders."""
    path = resolve(stored_path)
    path.unlink(missing_ok=True)
    # Prune empty parents up to (but not including) the root.
    folder = path.parent
    while folder != DOCUMENTS_DIR and folder.is_relative_to(DOCUMENTS_DIR):
        try:
            folder.rmdir()  # only succeeds when empty
        except OSError:
            break
        folder = folder.parent


def delete_tree(folder: str) -> None:
    """Remove a whole subfolder (used when deleting an empty period)."""
    path = resolve_folder(folder)
    if path != DOCUMENTS_DIR and path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
