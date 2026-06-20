"""MiMo Token Plan 用量查询服务 v4

通过浏览器 CDP act evaluate 在 JS 上下文 fetch API（复用已有 Cookie）。
比 snapshot 快得多，不需要解析 DOM。
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

logger = logging.getLogger(__name__)

_BROWSER_SCRIPT = Path(r"D:\Program Files (x86)\easyclaw\resources\cfmind\skills\browser-tool\scripts\run-browser.py")
_API_URL = "https://platform.xiaomimimo.com/api/v1/tokenPlan/usage"

# JS 代码：直接 fetch API 并返回 JSON
_FETCH_JS = f"""
(async () => {{
    try {{
        const resp = await fetch('{_API_URL}', {{credentials: 'include'}});
        const data = await resp.json();
        return JSON.stringify(data);
    }} catch(e) {{
        return JSON.stringify({{code: -1, message: e.toString()}});
    }}
}})()
"""


@dataclass
class MiMoUsage:
    """MiMo Token Plan 用量数据"""
    used: int = 0
    limit: int = 0
    percent: float = 0.0
    remaining_pct: float = 0.0
    error: str = ""

    @property
    def success(self) -> bool:
        return not self.error and self.limit > 0

    def used_display(self) -> str:
        if self.used >= 1_0000_0000:
            return f"{self.used / 1_0000_0000:.2f}亿"
        elif self.used >= 1_0000:
            return f"{self.used / 1_0000:.0f}万"
        return str(self.used)

    def limit_display(self) -> str:
        if self.limit >= 1_0000_0000:
            return f"{self.limit / 1_0000_0000:.0f}亿"
        elif self.limit >= 1_0000:
            return f"{self.limit / 1_0000:.0f}万"
        return str(self.limit)


class MiMoService(QObject):
    """MiMo Token Plan 数据采集服务 v4

    通过浏览器 CDP act evaluate 在 JS 上下文 fetch API。
    """
    data_ready = pyqtSignal(object)

    def __init__(self, interval_ms: int = 5 * 60 * 1000, parent=None):
        super().__init__(parent)
        self._interval_ms = interval_ms
        self._timer: Optional[QTimer] = None
        self._last: Optional[MiMoUsage] = None
        self._tab_id: Optional[str] = None
        self._initialized = False

    def start(self):
        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self._fetch)
        self._timer.start()
        # 首次延迟 3s（等浏览器就绪）
        QTimer.singleShot(3000, self._fetch)

    def _fetch(self):
        try:
            usage = self._fetch_via_js()
            self._last = usage
            self.data_ready.emit(usage)
        except Exception as e:
            logger.warning(f"MiMo 用量采集失败: {e}")
            self.data_ready.emit(MiMoUsage(error=str(e)))

    def _ensure_tab(self) -> Optional[str]:
        """确保有一个打开的 tab"""
        if self._tab_id:
            return self._tab_id
        try:
            cmd = [
                sys.executable, str(_BROWSER_SCRIPT),
                "open", _API_URL
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                self._tab_id = data.get("targetId")
                return self._tab_id
        except Exception as e:
            logger.debug(f"browser open 失败: {e}")
        return None

    def _fetch_via_js(self) -> MiMoUsage:
        """在浏览器 JS 上下文直接 fetch API"""
        target_id = self._ensure_tab()
        if not target_id:
            return MiMoUsage(error="无法打开浏览器 tab")

        cmd = [
            sys.executable, str(_BROWSER_SCRIPT),
            "act", "evaluate", _FETCH_JS,
            "--target-id", target_id
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode != 0:
            # tab 可能已关闭，重置
            self._tab_id = None
            return MiMoUsage(error=f"JS evaluate 失败: {result.stderr[:200]}")

        return self._parse_output(result.stdout)

    def _parse_output(self, output: str) -> MiMoUsage:
        """从输出中提取 JSON"""
        # act evaluate 输出格式：结果在 output 中
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith('{') and '"code"' in line:
                try:
                    return self._parse_api_response(json.loads(line))
                except json.JSONDecodeError:
                    pass

        # 尝试整个输出
        start = output.find('{')
        end = output.rfind('}') + 1
        if start >= 0 and end > start:
            try:
                return self._parse_api_response(json.loads(output[start:end]))
            except json.JSONDecodeError:
                pass

        return MiMoUsage(error=f"无法解析: {output[:200]}")

    def _parse_api_response(self, data: dict) -> MiMoUsage:
        if data.get("code") != 0:
            return MiMoUsage(error=f"API: {data.get('message', '未知')}")

        items = data.get("data", {}).get("usage", {}).get("items", [])
        for item in items:
            if item.get("name") == "plan_total_token":
                used = item.get("used", 0)
                limit = item.get("limit", 0)
                percent = item.get("percent", 0)
                return MiMoUsage(
                    used=used, limit=limit,
                    percent=percent,
                    remaining_pct=round((1.0 - percent) * 100, 1),
                )

        return MiMoUsage(error="无 plan_total_token")

    @property
    def last(self) -> Optional[MiMoUsage]:
        return self._last
