"""Bookmark request/response models."""
from __future__ import annotations

from pydantic import BaseModel


class BookmarkCreate(BaseModel):
    officer_id: str | None = None
    query: str


class BookmarkOut(BaseModel):
    id: str
    officer_id: str | None
    query: str
    created_at: str | None
    shared: bool
