from typing import Any

from app.db.database import connect


def _rows_to_dicts(rows: list) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def insert_todo(
    title: str,
    notes: str | None = None,
    due_date: str | None = None,
    google_task_id: str | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO todos (title, notes, due_date, google_task_id)
            VALUES (?, ?, ?, ?)
            RETURNING id, title, notes, due_date, google_task_id, created_at
            """,
            (title, notes, due_date, google_task_id),
        )
        row = cursor.fetchone()
        conn.commit()
        return dict(row)


def list_todos() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title, notes, due_date, google_task_id, created_at
            FROM todos
            ORDER BY id DESC
            """
        ).fetchall()
    return _rows_to_dicts(rows)


def insert_idea(title: str, description: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO ideas (title, description)
            VALUES (?, ?)
            RETURNING id, title, description, created_at
            """,
            (title, description),
        )
        row = cursor.fetchone()
        conn.commit()
        return dict(row)


def list_ideas() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, description, created_at FROM ideas ORDER BY id DESC"
        ).fetchall()
    return _rows_to_dicts(rows)


def insert_project(title: str, description: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO projects (title, description)
            VALUES (?, ?)
            RETURNING id, title, description, created_at
            """,
            (title, description),
        )
        row = cursor.fetchone()
        conn.commit()
        return dict(row)


def list_projects() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, description, created_at FROM projects ORDER BY id DESC"
        ).fetchall()
    return _rows_to_dicts(rows)


def insert_calendar_event(title: str, date: str) -> dict[str, Any]:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO calendar_events (title, date)
            VALUES (?, ?)
            RETURNING id, title, date, created_at
            """,
            (title, date),
        )
        row = cursor.fetchone()
        conn.commit()
        return dict(row)


def list_calendar_events() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, date, created_at FROM calendar_events ORDER BY id DESC"
        ).fetchall()
    return _rows_to_dicts(rows)


def insert_trello_card(
    title: str,
    notes: str | None = None,
    due_date: str | None = None,
    trello_card_id: str | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO trello_cards (title, notes, due_date, trello_card_id)
            VALUES (?, ?, ?, ?)
            RETURNING id, title, notes, due_date, trello_card_id, created_at
            """,
            (title, notes, due_date, trello_card_id),
        )
        row = cursor.fetchone()
        conn.commit()
        return dict(row)
