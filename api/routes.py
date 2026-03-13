"""
api/routes.py
-------------
All HTTP route handlers for the Mini Cloud Storage API.

Endpoints
---------
Files
  POST   /files/upload          Upload a file (multipart/form-data)
  GET    /files                  List files — paginated, searchable, folder-scoped
  GET    /files/{id}             Download a file
  DELETE /files/{id}             Delete a file + its bytes on disk
  PATCH  /files/{id}/rename      Rename a file (metadata only)

Folders
  POST   /folders                Create a folder
  GET    /folders                List folders (optionally by parent)

System
  GET    /health                 Liveness + DB check
"""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, Query,
    UploadFile, File as FastAPIFile, status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from core.config import settings
from db.models import File, Folder
from db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic schemas
# ═══════════════════════════════════════════════════════════════════════════════

class FileResponse_(BaseModel):
    id:           str
    filename:     str
    size:         int
    content_type: Optional[str]
    folder_id:    Optional[str]
    created_at:   str
    updated_at:   str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, obj: File) -> "FileResponse_":
        return cls(
            id=obj.id,
            filename=obj.filename,
            size=obj.size,
            content_type=obj.content_type,
            folder_id=obj.folder_id,
            created_at=obj.created_at.isoformat(),
            updated_at=obj.updated_at.isoformat(),
        )


class FileListResponse(BaseModel):
    total:  int
    page:   int
    limit:  int
    files:  list[FileResponse_]


class RenameRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)


class FolderCreate(BaseModel):
    name:      str           = Field(..., min_length=1, max_length=255)
    parent_id: Optional[str] = None


class FolderResponse(BaseModel):
    id:        str
    name:      str
    parent_id: Optional[str]
    created_at: str

    @classmethod
    def from_orm(cls, obj: Folder) -> "FolderResponse":
        return cls(
            id=obj.id,
            name=obj.name,
            parent_id=obj.parent_id,
            created_at=obj.created_at.isoformat(),
        )


class HealthResponse(BaseModel):
    status:  str
    db:      str
    version: str = "1.0.0"


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_storage_dir(folder_id: Optional[str] = None) -> str:
    """
    Return (and create if needed) the directory where a file will be saved.
    If folder_id is given, files go into storage/<folder_id>/.
    Otherwise they go into storage/root/.
    """
    sub = folder_id if folder_id else "root"
    path = os.path.join(settings.STORAGE_ROOT, sub)
    os.makedirs(path, exist_ok=True)
    return path


def _get_file_or_404(file_id: str, db: Session) -> File:
    """Fetch a File record by id or raise 404."""
    file = db.get(File, file_id)
    if not file:
        raise HTTPException(status_code=404, detail=f"File '{file_id}' not found")
    return file


# ═══════════════════════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/health", response_model=HealthResponse, tags=["system"])
def health_check(db: Session = Depends(get_db)):
    """Liveness + DB connectivity check."""
    try:
        db.execute(select(func.now()))
        db_status = "ok"
    except Exception as exc:
        logger.error("Health DB error: %s", exc)
        db_status = "error"
    return HealthResponse(status="ok", db=db_status)


# ═══════════════════════════════════════════════════════════════════════════════
# Files
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/files/upload",
    response_model=FileResponse_,
    status_code=status.HTTP_201_CREATED,
    tags=["files"],
    summary="Upload a file",
)
async def upload_file(
    file:      UploadFile = FastAPIFile(...),
    folder_id: Optional[str] = Query(None, description="Target folder id (optional)"),
    db:        Session = Depends(get_db),
):
    """
    Upload a file via multipart/form-data.

    - File size is checked against `MAX_UPLOAD_SIZE_MB` (default 100 MB).
    - The file is stored on disk under `storage/<folder_id>/` or `storage/root/`.
    - Metadata (filename, path, size, MIME type) is saved in PostgreSQL.
    """
    # ── Validate folder exists ────────────────────────────────────────────────
    if folder_id:
        folder = db.get(Folder, folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail=f"Folder '{folder_id}' not found")

    # ── Read file bytes (enforce size limit) ──────────────────────────────────
    contents = await file.read()
    size = len(contents)

    if size > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large: {size / 1024 / 1024:.1f} MB. "
                f"Limit is {settings.MAX_UPLOAD_SIZE_MB} MB."
            ),
        )
    if size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # ── Build unique on-disk filename ─────────────────────────────────────────
    ext         = os.path.splitext(file.filename or "")[1].lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    save_dir    = _ensure_storage_dir(folder_id)
    save_path   = os.path.join(save_dir, stored_name)

    # ── Write to disk ─────────────────────────────────────────────────────────
    try:
        with open(save_path, "wb") as f_out:
            f_out.write(contents)
    except OSError as exc:
        logger.error("Disk write failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save file to disk.")

    # ── Save metadata to DB ───────────────────────────────────────────────────
    record = File(
        id=str(uuid.uuid4()),
        filename=file.filename or stored_name,
        stored_name=stored_name,
        path=save_path,
        size=size,
        content_type=file.content_type,
        folder_id=folder_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    logger.info("Uploaded: %s (%d bytes) → %s", record.filename, size, save_path)
    return FileResponse_.from_orm(record)


@router.get(
    "/files",
    response_model=FileListResponse,
    tags=["files"],
    summary="List files — paginated, searchable",
)
def list_files(
    search:    Optional[str] = Query(None,  description="Substring search on filename"),
    folder_id: Optional[str] = Query(None,  description="Filter by folder (omit for root)"),
    page:      int           = Query(1,     ge=1),
    limit:     int           = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    db:        Session = Depends(get_db),
):
    """
    Return a paginated list of files.

    - `search` does a case-insensitive substring match on `filename`.
    - `folder_id=none` returns root-level files (no folder).
    - `folder_id=<id>` returns files inside that folder.
    - Omitting `folder_id` returns ALL files.
    """
    query = select(File)

    if search:
        pattern = f"%{search.lower()}%"
        query = query.where(File.filename.ilike(pattern))

    if folder_id == "none":
        query = query.where(File.folder_id.is_(None))
    elif folder_id:
        query = query.where(File.folder_id == folder_id)

    total: int = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar_one()

    offset = (page - 1) * limit
    files  = db.execute(
        query.order_by(File.created_at.desc()).offset(offset).limit(limit)
    ).scalars().all()

    return FileListResponse(
        total=total,
        page=page,
        limit=limit,
        files=[FileResponse_.from_orm(f) for f in files],
    )


@router.get(
    "/files/{file_id}",
    tags=["files"],
    summary="Download a file",
    response_class=FileResponse,
)
def download_file(file_id: str, db: Session = Depends(get_db)):
    """
    Stream the file bytes back to the client.
    Sets `Content-Disposition: attachment` so browsers download it.
    """
    record = _get_file_or_404(file_id, db)

    if not os.path.exists(record.path):
        logger.error("File on disk missing: %s (db id=%s)", record.path, file_id)
        raise HTTPException(status_code=410, detail="File data not found on disk.")

    return FileResponse(
        path=record.path,
        filename=record.filename,
        media_type=record.content_type or "application/octet-stream",
    )


@router.delete(
    "/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["files"],
    summary="Delete a file",
)
def delete_file(file_id: str, db: Session = Depends(get_db)):
    """
    Delete the file record from PostgreSQL **and** remove bytes from disk.
    Returns 204 on success, 404 if not found.
    """
    record = _get_file_or_404(file_id, db)

    # Remove from disk first (best-effort — don't fail if already gone)
    if os.path.exists(record.path):
        try:
            os.remove(record.path)
            logger.info("Deleted from disk: %s", record.path)
        except OSError as exc:
            logger.warning("Could not delete file from disk: %s", exc)

    db.delete(record)
    db.commit()
    logger.info("Deleted file record: %s (%s)", file_id, record.filename)


@router.patch(
    "/files/{file_id}/rename",
    response_model=FileResponse_,
    tags=["files"],
    summary="Rename a file (metadata only — disk file is untouched)",
)
def rename_file(
    file_id: str,
    body:    RenameRequest,
    db:      Session = Depends(get_db),
):
    """
    Update `filename` in PostgreSQL.
    The on-disk stored name is UUID-based and never changes.
    """
    record = _get_file_or_404(file_id, db)
    old_name = record.filename
    record.filename = body.filename
    db.commit()
    db.refresh(record)
    logger.info("Renamed %s: %r → %r", file_id, old_name, body.filename)
    return FileResponse_.from_orm(record)


# ═══════════════════════════════════════════════════════════════════════════════
# Folders
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/folders",
    response_model=FolderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["folders"],
    summary="Create a folder",
)
def create_folder(body: FolderCreate, db: Session = Depends(get_db)):
    """
    Create a virtual folder.
    Set `parent_id` to nest inside an existing folder.
    """
    if body.parent_id:
        parent = db.get(Folder, body.parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail=f"Parent folder '{body.parent_id}' not found")

    folder = Folder(
        id=str(uuid.uuid4()),
        name=body.name,
        parent_id=body.parent_id,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    logger.info("Created folder: %s (%s)", folder.name, folder.id)
    return FolderResponse.from_orm(folder)


@router.get(
    "/folders",
    response_model=list[FolderResponse],
    tags=["folders"],
    summary="List folders",
)
def list_folders(
    parent_id: Optional[str] = Query(None, description="Filter by parent (omit = top-level only)"),
    db:        Session = Depends(get_db),
):
    """
    List folders.
    - Omit `parent_id` → returns top-level folders (parent_id IS NULL).
    - Pass `parent_id=<id>` → returns children of that folder.
    - Pass `parent_id=all` → returns every folder.
    """
    query = select(Folder)
    if parent_id == "all":
        pass  # no filter — return everything
    elif parent_id:
        query = query.where(Folder.parent_id == parent_id)
    else:
        query = query.where(Folder.parent_id.is_(None))

    folders = db.execute(query.order_by(Folder.name)).scalars().all()
    return [FolderResponse.from_orm(f) for f in folders]
