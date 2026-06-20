"""MoonDeck 存储管理器(SQLite)

职责:
- 布局/主题/便签等持久化数据
- 单例连接(避免到处开连接)
- 读写加锁(线程安全)

表结构:
- layout(card_id TEXT PRIMARY KEY, x INT, y INT, w INT, h INT, visible INT, updated_at TEXT)
- kv(key TEXT PRIMARY KEY, value TEXT)  -- 通用键值(主题/快捷键覆盖等)
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class StorageManager:
    """SQLite 存储(单例)"""

    _instance: "StorageManager | None" = None
    _lock = threading.Lock()

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._write_lock = threading.Lock()
        self._init_schema()

    @classmethod
    def instance(cls) -> "StorageManager":
        if cls._instance is None:
            raise RuntimeError("StorageManager 尚未初始化,请先调用 init_instance(db_path)")
        return cls._instance

    @classmethod
    def init_instance(cls, db_path: Path) -> "StorageManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(db_path)
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance._conn.close()
                except Exception:
                    pass
                cls._instance = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,  # 多线程安全由 _write_lock 保护
            )
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_schema(self) -> None:
        conn = self._connect()
        with self._write_lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS layout (
                    card_id   TEXT PRIMARY KEY,
                    x         INTEGER NOT NULL,
                    y         INTEGER NOT NULL,
                    w         INTEGER NOT NULL,
                    h         INTEGER NOT NULL,
                    visible   INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kv (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            conn.commit()

    # ---- 布局 ----

    def save_layout(self, card_id: str, x: int, y: int, w: int, h: int, visible: bool = True) -> None:
        """保存单卡片位置/尺寸"""
        conn = self._connect()
        with self._write_lock:
            conn.execute(
                """
                INSERT INTO layout (card_id, x, y, w, h, visible, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(card_id) DO UPDATE SET
                    x=excluded.x, y=excluded.y, w=excluded.w, h=excluded.h,
                    visible=excluded.visible, updated_at=excluded.updated_at
                """,
                (card_id, int(x), int(y), int(w), int(h), int(bool(visible)), datetime.now().isoformat()),
            )
            conn.commit()

    def load_layout(self, card_id: str) -> Optional[Dict[str, Any]]:
        """读取单卡片布局;不存在返回 None"""
        conn = self._connect()
        cur = conn.execute("SELECT * FROM layout WHERE card_id = ?", (card_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "card_id": row["card_id"],
            "x": row["x"],
            "y": row["y"],
            "w": row["w"],
            "h": row["h"],
            "visible": bool(row["visible"]),
            "updated_at": row["updated_at"],
        }

    def load_all_layouts(self) -> List[Dict[str, Any]]:
        """读取所有卡片布局"""
        conn = self._connect()
        cur = conn.execute("SELECT * FROM layout ORDER BY card_id")
        return [
            {
                "card_id": r["card_id"],
                "x": r["x"],
                "y": r["y"],
                "w": r["w"],
                "h": r["h"],
                "visible": bool(r["visible"]),
                "updated_at": r["updated_at"],
            }
            for r in cur.fetchall()
        ]

    def delete_layout(self, card_id: str) -> None:
        """删除单卡片布局"""
        conn = self._connect()
        with self._write_lock:
            conn.execute("DELETE FROM layout WHERE card_id = ?", (card_id,))
            conn.commit()

    # ---- 通用 KV ----

    def set_kv(self, key: str, value: Any) -> None:
        """存任意可序列化值"""
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        conn = self._connect()
        with self._write_lock:
            conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            conn.commit()

    def get_kv(self, key: str, default: Any = None) -> Any:
        """读 KV,自动 json 反序列化"""
        conn = self._connect()
        cur = conn.execute("SELECT value FROM kv WHERE key = ?", (key,))
        row = cur.fetchone()
        if row is None:
            return default
        raw = row["value"]
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    def close(self) -> None:
        """关闭连接(测试/退出用)"""
        with self._write_lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
