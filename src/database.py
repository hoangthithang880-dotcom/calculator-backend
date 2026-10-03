"""每个请求使用独立连接；历史记录持久存储于 SQLite。"""

import csv
import io
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .calculator import ExpressionError


class HistoryRepository:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
            )

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, expression, result, request_id=None):
        with self.connect() as connection:
            # 串行化“查重 + 插入”，避免网络重试产生重复记录。
            connection.execute("BEGIN IMMEDIATE")
            if request_id:
                existing = connection.execute(
                    "SELECT * FROM calculation_history WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if existing:
                    if existing["expression"] != expression:
                        raise ExpressionError("同一请求编号不能用于不同算式", "REQUEST_CONFLICT")
                    return self.record(existing), False
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            cursor = connection.execute(
                "INSERT INTO calculation_history (expression, result, created_at, request_id) VALUES (?, ?, ?, ?)",
                (expression, result, created_at, request_id),
            )
            return {
                "id": cursor.lastrowid,
                "expression": expression,
                "result": result,
                "created_at": created_at,
            }, True

    @staticmethod
    def record(row):
        return {key: row[key] for key in ("id", "expression", "result", "created_at")}

    def list(self, query="", page=1, page_size=8):
        # 转义 LIKE 通配符；关键词只匹配文字，不会被当成 SQL。
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        where = "WHERE expression LIKE ? ESCAPE '\\' OR result LIKE ? ESCAPE '\\'"
        with self.connect() as connection:
            connection.execute("BEGIN")
            total = connection.execute(
                f"SELECT COUNT(*) FROM calculation_history {where}",
                (pattern, pattern),
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM calculation_history {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                (pattern, pattern, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [self.record(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def delete(self, record_id):
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM calculation_history WHERE id = ?",
                (record_id,),
            )
            return cursor.rowcount > 0

    def export(self):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, expression, result, created_at FROM calculation_history ORDER BY id DESC"
            ).fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(("id", "expression", "result", "created_at"))
        for row in rows:
            # CSV 导出到电子表格时，将表达式保留为文字而非公式。
            values = [str(value) for value in row]
            values = [
                "'" + value if value.startswith(("=", "+", "-", "@")) else value for value in values
            ]
            writer.writerow(values)
        return "\ufeff" + output.getvalue()
