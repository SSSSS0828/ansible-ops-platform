"""SQLite 任务和结构化事件仓储。"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TERMINAL_STATUSES = frozenset({"succeeded", "failed"})


def utc_now() -> str:
    # timezone.utc 在 Python 3.10 与 3.11 均可用，保持控制器镜像和开发环境一致。
    return datetime.now(timezone.utc).isoformat()


class JobRepository:
    """每次操作使用独立连接，适配后台任务线程和 SSE 读取。"""

    def __init__(self, database_path: str) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    playbook_id TEXT NOT NULL,
                    target_group TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    return_code INTEGER,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    host TEXT NOT NULL DEFAULT '',
                    task TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    changed INTEGER NOT NULL DEFAULT 0,
                    stdout TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(job_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_events_job_sequence
                    ON job_events(job_id, sequence);
                """
            )

    def create_job(self, job: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO jobs
                   (id, playbook_id, target_group, mode, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    job["id"],
                    job["playbook_id"],
                    job["target_group"],
                    job["mode"],
                    job["status"],
                    job["created_at"],
                ),
            )

    def mark_running(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
                (utc_now(), job_id),
            )

    def finish_job(
        self,
        job_id: str,
        *,
        status: str,
        return_code: int,
        summary: dict[str, Any],
        error: str = "",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE jobs
                   SET status = ?, finished_at = ?, return_code = ?, summary_json = ?, error = ?
                   WHERE id = ?""",
                (
                    status,
                    utc_now(),
                    return_code,
                    json.dumps(summary, ensure_ascii=False),
                    error,
                    job_id,
                ),
            )

    def add_event(
        self,
        job_id: str,
        *,
        event_type: str,
        host: str = "",
        task: str = "",
        status: str = "",
        changed: bool = False,
        stdout: str = "",
    ) -> dict[str, Any]:
        with self._connect() as connection:
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM job_events WHERE job_id = ?",
                (job_id,),
            ).fetchone()[0]
            created_at = utc_now()
            connection.execute(
                """INSERT INTO job_events
                   (job_id, sequence, event_type, host, task, status, changed, stdout, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    sequence,
                    event_type,
                    host,
                    task,
                    status,
                    int(changed),
                    stdout[:8_000],
                    created_at,
                ),
            )
        return {
            "sequence": sequence,
            "event_type": event_type,
            "host": host,
            "task": task,
            "status": status,
            "changed": changed,
            "stdout": stdout[:8_000],
            "created_at": created_at,
        }

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._job_from_row(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._job_from_row(row) for row in rows]

    def find_active_job(self, target_group: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM jobs
                   WHERE target_group = ? AND status IN ('queued', 'running')
                   ORDER BY created_at DESC LIMIT 1""",
                (target_group,),
            ).fetchone()
        return self._job_from_row(row) if row else None

    def list_events(self, job_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT sequence, event_type, host, task, status, changed, stdout, created_at
                   FROM job_events WHERE job_id = ? AND sequence > ? ORDER BY sequence""",
                (job_id, after),
            ).fetchall()
        return [
            {
                **dict(row),
                "changed": bool(row["changed"]),
            }
            for row in rows
        ]

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["summary"] = json.loads(item.pop("summary_json"))
        return item
