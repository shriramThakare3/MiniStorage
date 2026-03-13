"""
db/models.py
------------
SQLAlchemy ORM models.

Tables
------
* files    — metadata for every uploaded file
* folders  — optional virtual folder hierarchy

`Base.metadata.create_all(engine)` is called at API startup so the
schema is bootstrapped automatically — no Alembic required for dev.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, BigInteger, DateTime,
    ForeignKey, Text, func, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Folder ────────────────────────────────────────────────────────────────────
class Folder(Base):
    """
    Virtual folder — stored only as metadata.
    Supports nested folders via self-referential parent_id.
    """
    __tablename__ = "folders"

    id        = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name      = Column(String(255), nullable=False)
    parent_id = Column(String(36), ForeignKey("folders.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    children = relationship("Folder", backref="parent",    foreign_keys=[parent_id], lazy="select")
    files    = relationship("File",   back_populates="folder", cascade="all, delete-orphan")

    __table_args__ = (
        # Fast lookup of top-level folders and children
        Index("ix_folders_parent_id", "parent_id"),
    )

    def __repr__(self) -> str:
        return f"<Folder id={self.id} name={self.name!r}>"


# ── File ──────────────────────────────────────────────────────────────────────
class File(Base):
    """
    Metadata for a file stored on disk.
    The actual bytes live at `path` on the container filesystem.
    """
    __tablename__ = "files"

    id           = Column(String(36),  primary_key=True, default=lambda: str(uuid.uuid4()))
    filename     = Column(String(255), nullable=False)                 # original name shown to users
    stored_name  = Column(String(255), nullable=False, unique=True)    # UUID-based name on disk
    path         = Column(Text,        nullable=False)                 # absolute path on disk
    size         = Column(BigInteger,  nullable=False, default=0)      # bytes
    content_type = Column(String(128), nullable=True)                  # MIME type
    folder_id    = Column(String(36),  ForeignKey("folders.id", ondelete="SET NULL"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at   = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    folder = relationship("Folder", back_populates="files")

    __table_args__ = (
        Index("ix_files_filename",  "filename"),   # search by name
        Index("ix_files_folder_id", "folder_id"),  # list by folder
        Index("ix_files_created",   "created_at"), # sort by date
    )

    def __repr__(self) -> str:
        return f"<File id={self.id} filename={self.filename!r} size={self.size}>"
