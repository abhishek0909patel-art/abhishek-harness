"""Bookmarks API — create/list/delete/share."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api._common import api_error, ok
from src.db.models import BookmarkRow
from src.db.session import get_session
from src.domain.bookmark import BookmarkCreate, BookmarkOut

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


def _to_out(row: BookmarkRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "officer_id": row.officer_id,
        "query": row.query,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "shared": row.shared,
    }


@router.post("/")
def create_bookmark(payload: BookmarkCreate, session: Session = Depends(get_session)) -> dict[str, Any]:
    row = BookmarkRow(officer_id=payload.officer_id, query=payload.query or "", shared=False)
    session.add(row)
    session.flush()
    return ok(_to_out(row))


@router.get("/")
def list_bookmarks(officer_id: str | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    stmt = select(BookmarkRow).order_by(BookmarkRow.created_at.desc())
    if officer_id:
        stmt = stmt.where(BookmarkRow.officer_id == officer_id)
    rows = session.execute(stmt).scalars().all()
    return ok([_to_out(r) for r in rows])


@router.delete("/{bookmark_id}")
def delete_bookmark(bookmark_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    row = session.get(BookmarkRow, bookmark_id)
    if row is None:
        raise api_error("NOT_FOUND", "Bookmark not found", status_code=404)
    session.delete(row)
    return ok({"deleted": bookmark_id})


@router.patch("/{bookmark_id}/share")
def share_bookmark(bookmark_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    row = session.get(BookmarkRow, bookmark_id)
    if row is None:
        raise api_error("NOT_FOUND", "Bookmark not found", status_code=404)
    row.shared = True
    session.add(row)
    session.flush()
    return ok(_to_out(row))
