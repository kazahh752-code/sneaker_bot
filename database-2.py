import sqlite3
from config import DB_PATH, DEFAULT_MAX_PRICE


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                subscribed INTEGER DEFAULT 0,
                max_price INTEGER DEFAULT 4000,
                sizes TEXT DEFAULT '44.5,45,45.5',
                custom_query TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS seen_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                seen_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, item_id)
            );
        """)
        self.conn.commit()

    def add_user(self, user_id: int, username: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)",
            (user_id, username)
        )
        self.conn.commit()

    def get_user(self, user_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def set_subscribed(self, user_id: int, state: bool):
        self.conn.execute("UPDATE users SET subscribed=? WHERE id=?", (1 if state else 0, user_id))
        self.conn.commit()

    def is_subscribed(self, user_id: int) -> bool:
        row = self.conn.execute("SELECT subscribed FROM users WHERE id=?", (user_id,)).fetchone()
        return bool(row["subscribed"]) if row else False

    def get_all_subscribers(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM users WHERE subscribed=1").fetchall()
        return [dict(r) for r in rows]

    def get_user_max_price(self, user_id: int) -> int:
        row = self.conn.execute("SELECT max_price FROM users WHERE id=?", (user_id,)).fetchone()
        return row["max_price"] if row else DEFAULT_MAX_PRICE

    def set_user_max_price(self, user_id: int, price: int):
        self.conn.execute("UPDATE users SET max_price=? WHERE id=?", (price, user_id))
        self.conn.commit()

    def get_custom_query(self, user_id: int) -> str:
        row = self.conn.execute("SELECT custom_query FROM users WHERE id=?", (user_id,)).fetchone()
        return (row["custom_query"] or "") if row else ""

    def set_custom_query(self, user_id: int, query: str):
        self.conn.execute("UPDATE users SET custom_query=? WHERE id=?", (query, user_id))
        self.conn.commit()

    def is_seen(self, user_id: int, item_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_items WHERE user_id=? AND item_id=?", (user_id, item_id)
        ).fetchone()
        return row is not None

    def mark_seen(self, user_id: int, item_id: str):
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO seen_items (user_id, item_id) VALUES (?, ?)",
                (user_id, item_id)
            )
            self.conn.commit()
        except Exception:
            pass

    def cleanup_old(self, days=14):
        self.conn.execute(
            "DELETE FROM seen_items WHERE seen_at < datetime('now', ?)", (f"-{days} days",)
        )
        self.conn.commit()
