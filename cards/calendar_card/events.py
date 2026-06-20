"""CalendarEventStore - 事件存储

事件存储到 JSON 文件: cache/calendar_events.json
格式:
{
    "2026-06-12": ["韩立生日", "项目周会"],
    "2026-06-15": ["端午节 加班"],
    ...
}

支持:
- get_events(date) / get_events_in_range(start, end)
- add_event(date, text)
- remove_event(date, text)
- 加载 / 保存 JSON
- 未来扩展:同步 lark-calendar(预留接口)
"""
from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional


class CalendarEventStore:
    """线程安全的事件存储"""

    def __init__(self, db_path: Path):
        self._path = db_path
        self._lock = threading.Lock()
        self._events: Dict[str, List[str]] = {}
        self._loaded = False
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._events = {}
            self._loaded = True
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._events = {k: list(v) for k, v in data.items() if isinstance(v, list)}
                else:
                    self._events = {}
        except (json.JSONDecodeError, OSError):
            self._events = {}
        self._loaded = True

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._events, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # 静默失败

    @staticmethod
    def _key(d: date) -> str:
        return d.isoformat()

    def get_events(self, d: date) -> List[str]:
        with self._lock:
            return list(self._events.get(self._key(d), []))

    def get_events_in_range(self, start: date, end: date) -> Dict[date, List[str]]:
        """获取 [start, end] 区间内的事件,左闭右闭"""
        result: Dict[date, List[str]] = {}
        with self._lock:
            cur = start
            while cur <= end:
                key = self._key(cur)
                if key in self._events:
                    result[cur] = list(self._events[key])
                cur += timedelta(days=1)
        return result

    def get_events_map_for_month(self, year: int, month: int) -> Dict[date, List[str]]:
        """获取整月事件(含邻月填充)"""
        # 找到当月第一天所在周的周一
        from .lunar import get_days_in_month
        first = date(year, month, 1)
        last = date(year, month, get_days_in_month(year, month))
        # 向左找周一
        start = first - timedelta(days=first.weekday())
        # 向右找周日(42 天刚好 6 周)
        end = start + timedelta(days=41)
        return self.get_events_in_range(start, end)

    def add_event(self, d: date, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        with self._lock:
            key = self._key(d)
            lst = self._events.setdefault(key, [])
            if text in lst:
                return False
            lst.append(text)
            self._save()
            return True

    def remove_event(self, d: date, text: str) -> bool:
        with self._lock:
            key = self._key(d)
            lst = self._events.get(key, [])
            if text in lst:
                lst.remove(text)
                if not lst:
                    del self._events[key]
                self._save()
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._events = {}
            self._save()

    def all_events(self) -> Dict[date, List[str]]:
        """全量返回(给管理界面用)"""
        with self._lock:
            return {date.fromisoformat(k): list(v) for k, v in self._events.items()}

    # === 未来扩展:同步 lark-calendar ===
    # 预留:fetch_from_lark(self, lark_cli) -> None
