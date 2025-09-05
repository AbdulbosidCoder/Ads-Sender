# db.py
from __future__ import annotations
import sqlite3
from typing import Optional, Sequence

class Database:
    def __init__(self, path_to_db: str = "main.db"):
        self.path_to_db = path_to_db
        self._init_db()

    # ---------------- Core connection ----------------
    @property
    def connection(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path_to_db)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON;")
        return con

    def execute(
        self,
        sql: str,
        params: Sequence | tuple = (),
        *,
        fetchone: bool = False,
        fetchall: bool = False,
        commit: bool = False,
    ):
        """
        Execute a SQL statement with optional fetch / commit controls.
        Returns:
          - dict when fetchone=True (or None)
          - list[dict] when fetchall=True (or [])
          - None otherwise
        """
        with self.connection as connection:
            cur = connection.cursor()
            cur.execute(sql, params)
            if commit:
                connection.commit()
            if fetchone:
                row = cur.fetchone()
                return dict(row) if row else None
            if fetchall:
                rows = cur.fetchall()
                return [dict(r) for r in rows]
            return None

    @staticmethod
    def _format_update(fields: dict) -> tuple[str, tuple]:
        if not fields:
            raise ValueError("No fields provided to update.")
        assignments = ", ".join([f"{k}=?" for k in fields.keys()])
        values = tuple(fields.values())
        return assignments, values

    # ---------------- Schema & migrations ----------------
    def _init_db(self) -> None:
        # Users (role has DEFAULT 'user')
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS Users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone_number TEXT,
                role TEXT DEFAULT 'user'
            );
            """,
            commit=True,
        )
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS FullTexts (
                hash TEXT PRIMARY KEY,
                full_text TEXT NOT NULL
            );
            """,
            commit=True,
        )

        # (ixtiyoriy) indeks — PRIMARY KEY(hash) yetarli, lekin xohlasangiz:
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_fulltexts_hash ON FullTexts(hash);",
            commit=True,
        )
        # Groups
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS Groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                name TEXT,
                user_id INTEGER,
                CONSTRAINT fk_groups_user
                    FOREIGN KEY (user_id)
                    REFERENCES Users(id)
                    ON DELETE SET NULL
                    ON UPDATE CASCADE
            );
            """,
            commit=True,
        )

        # Topics (with is_general)
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS Topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                name TEXT,
                group_id INTEGER NOT NULL,
                is_general INTEGER NOT NULL DEFAULT 0,
                CONSTRAINT fk_topics_group
                    FOREIGN KEY (group_id)
                    REFERENCES Groups(id)
                    ON DELETE CASCADE
                    ON UPDATE CASCADE
            );
            """,
            commit=True,
        )

        # MessageRouteCache
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS MessageRouteCache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_hash TEXT NOT NULL,
                src_group_tid INTEGER NOT NULL,
                dst_group_id INTEGER NOT NULL,
                dst_topic_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            commit=True,
        )

        # Indexes
        self.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON Users(telegram_id);", commit=True)
        self.execute("CREATE INDEX IF NOT EXISTS idx_groups_telegram_id ON Groups(telegram_id);", commit=True)
        self.execute("CREATE INDEX IF NOT EXISTS idx_topics_group_id ON Topics(group_id);", commit=True)
        self.execute("CREATE INDEX IF NOT EXISTS idx_topics_is_general ON Topics(is_general);", commit=True)
        self.execute("CREATE INDEX IF NOT EXISTS idx_msg_cache_hash ON MessageRouteCache(message_hash);", commit=True)
        self.execute("CREATE INDEX IF NOT EXISTS idx_msg_cache_src ON MessageRouteCache(src_group_tid);", commit=True)

        # Lightweight migrations / ensure columns exist
        self._ensure_column_exists("Topics", "is_general", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column_exists("Users", "role", "TEXT DEFAULT 'user'")

        # Backfill NULL roles to 'user' for older rows
        self.execute("UPDATE Users SET role = COALESCE(role, 'user') WHERE role IS NULL;", commit=True)

    def _ensure_column_exists(self, table: str, column: str, coldef: str) -> None:
        info = self.execute(f"PRAGMA table_info({table});", fetchall=True) or []
        cols = {row["name"] for row in info}
        if column not in cols:
            self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef};", commit=True)

    # ---------------- Users CRUD ----------------
    def create_user(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        phone_number: str | None = None,
        role: str | None = "user",
    ) -> int:
        self.execute(
            """
            INSERT INTO Users (telegram_id, username, first_name, last_name, phone_number, role)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (telegram_id, username, first_name, last_name, phone_number, role),
            commit=True,
        )
        row = self.execute("SELECT id FROM Users WHERE telegram_id = ?;", (telegram_id,), fetchone=True)
        return int(row["id"])

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        return self.execute("SELECT * FROM Users WHERE id = ?;", (user_id,), fetchone=True)

    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[dict]:
        return self.execute("SELECT * FROM Users WHERE telegram_id = ?;", (telegram_id,), fetchone=True)

    def list_users(self, limit: int = 100, offset: int = 0) -> list[dict]:
        return self.execute(
            "SELECT * FROM Users ORDER BY id DESC LIMIT ? OFFSET ?;",
            (limit, offset),
            fetchall=True,
        )

    def update_user(self, user_id: int, **fields):
        set_clause, values = self._format_update(fields)
        self.execute(
            f"UPDATE Users SET {set_clause} WHERE id = ?;",
            (*values, user_id),
            commit=True,
        )

    def delete_user(self, user_id: int) -> None:
        self.execute("DELETE FROM Users WHERE id = ?;", (user_id,), commit=True)

    # --- Role helpers ---
    def set_user_role(self, user_id: int, role: str) -> None:
        self.update_user(user_id, role=role)

    def get_role_by_telegram_id(self, telegram_id: int) -> Optional[str]:
        row = self.get_user_by_telegram_id(telegram_id)
        return row.get("role") if row else None

    # ---------------- Groups CRUD ----------------
    def create_group(self, telegram_id: int, name: str, user_id: int | None = None) -> int:
        """
        Insert a new group and return its primary key.
        Avoids last_insert_rowid() scope issues by re-selecting via unique telegram_id.
        """
        self.execute(
            """
            INSERT OR IGNORE INTO Groups (telegram_id, name, user_id)
            VALUES (?, ?, ?);
            """,
            (telegram_id, name, user_id),
            commit=True,
        )
        # Update the name/user_id if already existed (optional)
        self.execute(
            "UPDATE Groups SET name = COALESCE(?, name), user_id = COALESCE(?, user_id) WHERE telegram_id = ?;",
            (name, user_id, telegram_id),
            commit=True,
        )
        row = self.execute("SELECT id FROM Groups WHERE telegram_id = ?;", (telegram_id,), fetchone=True)
        return int(row["id"])

    def get_group_by_id(self, group_id: int) -> Optional[dict]:
        return self.execute("SELECT * FROM Groups WHERE id = ?;", (group_id,), fetchone=True)

    def get_group_by_telegram_id(self, telegram_id: int) -> Optional[dict]:
        return self.execute("SELECT * FROM Groups WHERE telegram_id = ?;", (telegram_id,), fetchone=True)

    def get_group_by_name(self, name: str) -> Optional[dict]:
        return self.execute("SELECT * FROM Groups WHERE name = ?;", (name,), fetchone=True)

    def list_groups(self, limit: int = 100, offset: int = 0) -> list[dict]:
        return self.execute(
            "SELECT * FROM Groups ORDER BY id DESC LIMIT ? OFFSET ?;",
            (limit, offset),
            fetchall=True,
        )

    def list_groups_by_user(self, user_id: int, limit: int = 100, offset: int = 0) -> list[dict]:
        return self.execute(
            """
            SELECT * FROM Groups
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?;
            """,
            (user_id, limit, offset),
            fetchall=True,
        )

    def update_group(self, group_id: int, **fields):
        set_clause, values = self._format_update(fields)
        self.execute(
            f"UPDATE Groups SET {set_clause} WHERE id = ?;",
            (*values, group_id),
            commit=True,
        )

    def delete_group(self, group_id: int) -> None:
        self.execute("DELETE FROM Groups WHERE id = ?;", (group_id,), commit=True)

    # ---------------- Topics CRUD ----------------
    def create_topic(self, telegram_id: int, name: str, group_id: int, is_general: int = 0) -> int:
        """
        Insert a new topic (forum thread) for a group and return its primary key.
        Avoid last_insert_rowid scope by re-selecting via (telegram_id, group_id).
        """
        self.execute(
            """
            INSERT INTO Topics (telegram_id, name, group_id, is_general)
            VALUES (?, ?, ?, ?);
            """,
            (telegram_id, name, group_id, is_general),
            commit=True,
        )
        row = self.execute(
            "SELECT id FROM Topics WHERE telegram_id = ? AND group_id = ? ORDER BY id DESC LIMIT 1;",
            (telegram_id, group_id),
            fetchone=True,
        )
        return int(row["id"])

    def get_topic_by_id(self, topic_id: int) -> Optional[dict]:
        return self.execute("SELECT * FROM Topics WHERE id = ?;", (topic_id,), fetchone=True)

    def list_topics(self, limit: int = 100, offset: int = 0) -> list[dict]:
        return self.execute(
            "SELECT * FROM Topics ORDER BY id DESC LIMIT ? OFFSET ?;",
            (limit, offset),
            fetchall=True,
        )

    def list_topics_by_group(self, group_id: int, limit: int = 100, offset: int = 0) -> list[dict]:
        return self.execute(
            """
            SELECT * FROM Topics
            WHERE group_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?;
            """,
            (group_id, limit, offset),
            fetchall=True,
        )

    def update_topic(self, topic_id: int, **fields):
        set_clause, values = self._format_update(fields)
        self.execute(
            f"UPDATE Topics SET {set_clause} WHERE id = ?;",
            (*values, topic_id),
            commit=True,
        )

    def delete_topic(self, topic_id: int) -> None:
        self.execute("DELETE FROM Topics WHERE id = ?;", (topic_id,), commit=True)

    # ---------------- Convenience / Joins ----------------
    def list_groups_with_user(self, limit: int = 100, offset: int = 0) -> list[dict]:
        return self.execute(
            """
            SELECT g.*, u.username AS user_username, u.telegram_id AS user_telegram_id
            FROM Groups g
            LEFT JOIN Users u ON u.id = g.user_id
            ORDER BY g.id DESC
            LIMIT ? OFFSET ?;
            """,
            (limit, offset),
            fetchall=True,
        )

    def list_topics_with_group(self, group_id: int | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
        params: list = []
        where = ""
        if group_id is not None:
            where = "WHERE t.group_id = ?"
            params.append(group_id)
        params.extend([limit, offset])
        return self.execute(
            f"""
            SELECT t.*, g.name AS group_name, g.telegram_id AS group_telegram_id
            FROM Topics t
            JOIN Groups g ON g.id = t.group_id
            {where}
            ORDER BY t.id DESC
            LIMIT ? OFFSET ?;
            """,
            tuple(params),
            fetchall=True,
        )

    # ---------------- MessageRouteCache ----------------
    def create_message_route_cache(
        self,
        *,
        message_hash: str,
        src_group_tid: int,
        dst_group_id: int,
        dst_topic_id: int,
    ) -> int:
        self.execute(
            """
            INSERT INTO MessageRouteCache (message_hash, src_group_tid, dst_group_id, dst_topic_id)
            VALUES (?, ?, ?, ?);
            """,
            (message_hash, src_group_tid, dst_group_id, dst_topic_id),
            commit=True,
        )
        row = self.execute("SELECT last_insert_rowid() AS id;", fetchone=True)
        return int(row["id"])

    def get_route_by_hash(self, *, message_hash: str, src_group_tid: int) -> Optional[dict]:
        return self.execute(
            """
            SELECT * FROM MessageRouteCache
            WHERE message_hash = ? AND src_group_tid = ?
            ORDER BY id DESC
            LIMIT 1;
            """,
            (message_hash, src_group_tid),
            fetchone=True,
        )

    def clear_old_cache(self, days: int = 7) -> None:
        self.execute(
            "DELETE FROM MessageRouteCache WHERE created_at < datetime('now', ?);",
            (f"-{days} days",),
            commit=True,
        )

    # ---------------- Full text cache (hash -> full_text) ----------------
    def save_full_by_hash(self, h: str, full_text: str) -> None:
        """
        Full matnni hash bo‘yicha saqlash (upsert).
        'general_reader.py' bundan foydalanadi.
        """
        self.execute(
            """
            INSERT INTO FullTexts (hash, full_text)
            VALUES (?, ?)
            ON CONFLICT(hash) DO UPDATE SET full_text=excluded.full_text;
            """,
            (h, full_text),
            commit=True,
        )

    def get_full_by_hash(self, h: str) -> Optional[str]:
        row = self.execute(
            "SELECT full_text FROM FullTexts WHERE hash = ?;",
            (h,),
            fetchone=True,
        )
        return row["full_text"] if row else None
