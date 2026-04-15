from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Any

from config import VALID_STATUSES, settings


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with closing(get_connection()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_name TEXT NOT NULL,
                song_title TEXT NOT NULL,
                artist TEXT,
                note TEXT,
                claimed_tip_amount REAL,
                status TEXT NOT NULL DEFAULT 'New',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS gallery_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "requester_name": row["requester_name"],
        "song_title": row["song_title"],
        "artist": row["artist"] or "",
        "note": row["note"] or "",
        "claimed_tip_amount": row["claimed_tip_amount"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


def gallery_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "original_name": row["original_name"],
        "created_at": row["created_at"],
    }


def insert_request(
    requester_name: str,
    song_title: str,
    artist: str = "",
    note: str = "",
    claimed_tip_amount: float | None = None,
) -> dict[str, Any]:
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO requests (
                requester_name,
                song_title,
                artist,
                note,
                claimed_tip_amount,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 'New', ?)
            """,
            (
                requester_name,
                song_title,
                artist,
                note,
                claimed_tip_amount,
                created_at,
            ),
        )
        connection.commit()
        request_id = cursor.lastrowid

    return get_request_by_id(request_id)


def get_request_by_id(request_id: int) -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    if row is None:
        return None

    return row_to_dict(row)


def list_requests(status: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM requests"
    params: tuple[Any, ...] = ()

    if status and status in VALID_STATUSES:
        query += " WHERE status = ?"
        params = (status,)

    query += " ORDER BY created_at DESC, id DESC"

    with closing(get_connection()) as connection:
        rows = connection.execute(query, params).fetchall()

    return [row_to_dict(row) for row in rows]


def update_request_status(request_id: int, status: str) -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            "UPDATE requests SET status = ? WHERE id = ?",
            (status, request_id),
        )
        connection.commit()

        if cursor.rowcount == 0:
            return None

    return get_request_by_id(request_id)


def delete_request(request_id: int) -> dict[str, Any] | None:
    request_item = get_request_by_id(request_id)
    if request_item is None:
        return None

    with closing(get_connection()) as connection:
        connection.execute("DELETE FROM requests WHERE id = ?", (request_id,))
        connection.commit()

    return request_item


def clear_requests() -> int:
    with closing(get_connection()) as connection:
        count = connection.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        connection.execute("DELETE FROM requests")
        connection.commit()

    return int(count)


def get_stats() -> dict[str, Any]:
    with closing(get_connection()) as connection:
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total_requests,
                COALESCE(SUM(claimed_tip_amount), 0) AS total_claimed_tips
            FROM requests
            """
        ).fetchone()

        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM requests
            GROUP BY status
            """
        ).fetchall()

    counts = {row["status"]: row["total"] for row in rows}

    return {
        "total_requests": totals["total_requests"],
        "total_claimed_tips": round(float(totals["total_claimed_tips"] or 0), 2),
        "counts": {
            "New": counts.get("New", 0),
            "Queued": counts.get("Queued", 0),
            "Played": counts.get("Played", 0),
            "Skipped": counts.get("Skipped", 0),
        },
    }


def insert_gallery_image(filename: str, original_name: str) -> dict[str, Any]:
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO gallery_images (filename, original_name, created_at)
            VALUES (?, ?, ?)
            """,
            (filename, original_name, created_at),
        )
        connection.commit()
        image_id = cursor.lastrowid

    return get_gallery_image_by_id(image_id)


def get_gallery_image_by_id(image_id: int) -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM gallery_images WHERE id = ?",
            (image_id,),
        ).fetchone()

    if row is None:
        return None

    return gallery_row_to_dict(row)


def list_gallery_images(limit: int | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM gallery_images ORDER BY created_at DESC, id DESC"
    params: tuple[Any, ...] = ()

    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)

    with closing(get_connection()) as connection:
        rows = connection.execute(query, params).fetchall()

    return [gallery_row_to_dict(row) for row in rows]


def delete_gallery_image(image_id: int) -> dict[str, Any] | None:
    image = get_gallery_image_by_id(image_id)
    if image is None:
        return None

    with closing(get_connection()) as connection:
        connection.execute("DELETE FROM gallery_images WHERE id = ?", (image_id,))
        connection.commit()

    return image
