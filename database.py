import sqlite3
import logging
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id      INTEGER PRIMARY KEY,
                    username     TEXT,
                    created_date TEXT
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id        INTEGER NOT NULL,
                    text           TEXT NOT NULL,
                    completed      INTEGER DEFAULT 0,
                    created_date   TEXT NOT NULL,
                    completed_date TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)
        logger.info("База данных инициализирована")

    def register_user(self, user_id: int, username: str | None):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, username, created_date) VALUES (?, ?, ?)",
                (user_id, username, datetime.now().isoformat()),
            )

    def add_task(self, user_id: int, text: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO tasks (user_id, text, created_date) VALUES (?, ?, ?)",
                (user_id, text, datetime.now().isoformat()),
            )
            task_id = cursor.lastrowid
        logger.info("Пользователь %s добавил задачу #%s: %s", user_id, task_id, text)
        return task_id

    def get_tasks(self, user_id: int, filter: str | None = None) -> list[dict]:
        query = "SELECT * FROM tasks WHERE user_id = ?"
        params: list = [user_id]
        if filter == "active":
            query += " AND completed = 0"
        elif filter == "completed":
            query += " AND completed = 1"
        query += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_task(self, task_id: int, user_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ? AND user_id = ?",
                (task_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def toggle_task(self, task_id: int, user_id: int) -> bool:
        task = self.get_task(task_id, user_id)
        if not task:
            return False
        new_status = 0 if task["completed"] else 1
        completed_date = datetime.now().isoformat() if new_status else None
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET completed = ?, completed_date = ? WHERE id = ? AND user_id = ?",
                (new_status, completed_date, task_id, user_id),
            )
        logger.info("Пользователь %s изменил статус задачи #%s → %s", user_id, task_id, new_status)
        return True

    def delete_task(self, task_id: int, user_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE id = ? AND user_id = ?",
                (task_id, user_id),
            )
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Пользователь %s удалил задачу #%s", user_id, task_id)
        return deleted

    def edit_task(self, task_id: int, user_id: int, new_text: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET text = ? WHERE id = ? AND user_id = ?",
                (new_text, task_id, user_id),
            )
        edited = cursor.rowcount > 0
        if edited:
            logger.info("Пользователь %s отредактировал задачу #%s", user_id, task_id)
        return edited

    def clear_tasks(self, user_id: int) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE user_id = ?",
                (user_id,),
            )
        count = cursor.rowcount
        logger.info("Пользователь %s очистил все задачи (%s шт.)", user_id, count)
        return count

    def get_stats(self, user_id: int) -> dict:
        tasks = self.get_tasks(user_id)
        total = len(tasks)
        completed = sum(1 for t in tasks if t["completed"])
        active = total - completed
        percent = round(completed / total * 100) if total else 0
        return {"total": total, "active": active, "completed": completed, "percent": percent}
