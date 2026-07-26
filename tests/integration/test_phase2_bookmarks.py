"""Phase 2 integration gate — bookmarks API (service-layer, no router mount changes)."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from src.api.bookmarks import create_bookmark, list_bookmarks, delete_bookmark, share_bookmark
from src.api._common import api_error
from src.db.session import create_db_session
from src.db.models import Base, BookmarkRow
from sqlalchemy import text


@pytest.fixture()
def _clean_bookmarks():
    with create_db_session() as session:
        session.execute(text("DELETE FROM bookmarks"))
        session.commit()
    yield
    with create_db_session() as session:
        session.execute(text("DELETE FROM bookmarks"))
        session.commit()


def test_bookmarks_roundtrip(_clean_bookmarks):
    with create_db_session() as session:
        Base.metadata.create_all(bind=session.get_bind())

        res = create_bookmark({"officer_id": "off-1", "query": "show counts"}, session=session)
        data = res["data"]
        assert data["query"] == "show counts"
        bookmark_id = data["id"]

        rows = list_bookmarks(officer_id="off-1", session=session)["data"]
        assert any(item["id"] == bookmark_id for item in rows)

        shared = share_bookmark(bookmark_id, session=session)["data"]
        assert shared["shared"] is True

        deleted = delete_bookmark(bookmark_id, session=session)["data"]
        assert deleted["deleted"] == bookmark_id


def test_list_empty_is_empty(_clean_bookmarks):
    with create_db_session() as session:
        rows = list_bookmarks(officer_id="does-not-exist", session=session)["data"]
        assert rows == []


def test_delete_missing_returns_404():
    with create_db_session() as session:
        with pytest.raises(HTTPException) as exc_info:
            delete_bookmark("missing", session=session)
        assert exc_info.value.status_code == 404


def test_share_missing_returns_404():
    with create_db_session() as session:
        with pytest.raises(HTTPException) as exc_info:
            share_bookmark("missing", session=session)
        assert exc_info.value.status_code == 404
