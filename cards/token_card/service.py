"""Token 鍗＄墖鏁版嵁閲囬泦灞?v1.3.0 鐦﹁韩鍚?

v1.3.0 (2026-06-13) 閲嶅ぇ鐦﹁韩:
- 鐮嶆帀 history_importer / 4 瀹牸 / trend_7d / today_24h
- 鍙繚鐣?mmx-cli 瀹炴椂涓ゆ潯杩涘害鏉℃暟鎹?5h 绐楀彛 + 鍛ㄧ獥鍙?
- 鑰佸ぇ鍙嶉:娌＄簿鍔涘ぉ澶╁鏁版嵁,鍘嗗彶鏁版嵁涓嶈浜?
v1.1.0 (2026-06-12) 閲嶅ぇ淇:瀵归綈 mmx-cli 鐪熷疄杈撳嚭鏍煎紡
- 鐪熷疄缁撴瀯:model_remains[] 鏁扮粍,姣忛」鍚?current_interval_remaining_percent / current_weekly_remaining_percent
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """鍗曟棰濆害蹇収(v1.3.0 鐦﹁韩鍚?鍙墿涓ゆ潯杩涘害鏉?+ 鍏冧俊鎭?
    v0.3 (2026-06-13): 鍔?m3 / m27 / weekly_used 涓変釜 UI 瀛楁(閰嶅悎 v0.3 澶ф暟瀛?+ 3 杩涘害)
    """
    # ---- 5h 绐楀彛(鎬?5h 绐楀彛)----
    interval_remaining_pct: float = 0.0  # 5h 鍓╀綑 %
    interval_used_pct: float = 0.0  # 5h 宸茬敤 %
    interval_end_time: int = 0  # 5h 绐楀彛缁撴潫鏃堕棿鎴?姣)

    # ---- 鏈懆鐢ㄩ噺(鎬?----
    weekly_remaining_pct: float = 0.0  # 鍛ㄥ墿浣?%
    weekly_used_pct: float = 0.0  # 鍛ㄥ凡鐢?%
    weekly_end_time: int = 0  # 鏈懆缁撴潫鏃堕棿鎴?姣)
    weekly_boost_permille: int = 0  # 鍛ㄥ姞璧?鍗冨垎姣?1500 = 150%)

    # ---- v0.3 鏂板:M3 / M2.7 妯″瀷鍒嗚建 ----
    m3_used_pct: float = 0.0  # M3 妯″瀷宸茬敤 %
    m27_used_pct: float = 0.0  # M2.7 妯″瀷宸茬敤 %
    weekly_used: int = 0  # 鍛ㄧ疮璁＄敤 token 鏁?缁欏ぇ鏁板瓧灞曠ず)

    # ---- 鍏冧俊鎭?----
    fetched_at: str = ""
    source: str = ""  # mmx_cli / mock / error
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class TokenService:
    """Token 鏁版嵁閲囬泦鏈嶅姟

    v1.3.0:鍙噰 mmx 瀹炴椂涓ゆ潯杩涘害鏉℃暟鎹?    """

    def __init__(self, mmx_path: str = "mmx.cmd", timeout: int = 10):
        self.mmx_path = mmx_path
        self.timeout = timeout
        self._last_usage: Optional[TokenUsage] = None

    def fetch(self) -> TokenUsage:
        """鑾峰彇鏈€鏂伴搴︽暟鎹?鍙噰涓ゆ潯杩涘害鏉?"""
        try:
            raw = self._call_mmx_quota()
            usage = self._parse_mmx_output(raw)
            usage.fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            usage.source = "mmx_cli"
            self._last_usage = usage
            return usage
        except subprocess.TimeoutExpired:
            return self._error_result(f"mmx-cli 瓒呮椂(>{self.timeout}s)")
        except FileNotFoundError:
            return self._error_result(f"鎵句笉鍒?mmx-cli:{self.mmx_path}")
        except json.JSONDecodeError as e:
            return self._error_result(f"mmx-cli 杈撳嚭涓嶆槸鍚堟硶 JSON:{e}")
        except Exception as e:
            return self._error_result(f"鏈煡閿欒:{type(e).__name__}:{e}")

    def fetch_mock(self) -> TokenUsage:
        """鐢熸垚 mock 鏁版嵁(UI 鍗犱綅 + 娴嬭瘯)"""
        usage = TokenUsage(
            interval_remaining_pct=66.0,
            interval_used_pct=34.0,
            interval_end_time=1781316000000,
            weekly_remaining_pct=64.0,
            weekly_used_pct=36.0,
            weekly_end_time=1781452800000,
            weekly_boost_permille=1500,
            m3_used_pct=11.0,       # M3 鐢ㄤ簡 11%
            m27_used_pct=21.0,      # M2.7 鐢ㄤ簡 21%
            weekly_used=5720,        # 绱 5,720
            fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            source="mock",
        )
        self._last_usage = usage
        return usage

    def _call_mmx_quota(self) -> dict:
        """璋?mmx quota show -f json"""
        import sys as _sys
        from pathlib import Path
        import os as _os
        _dbg = _os.path.join(_os.environ.get("TEMP", "."), "tokencard_debug.log")
        with open(_dbg, "a") as _df: _df.write(f"mmx_path={self.mmx_path}\n")

        # Windows: .cmd/.bat 鏂囦欢鍗充娇 shell=False 涔熶細琚?CreateProcess 鑷姩濂?cmd.exe 鈫?寮圭獥
        # 瑙ｅ喅鏂规:濡傛灉 mmx_path 鏄?.cmd/.bat,缁曡繃瀹冪洿鎺ョ敤 node.exe 璋冨簳灞?.mjs
        if _sys.platform == "win32" and self.mmx_path.lower().endswith((".cmd", ".bat")):
            mmx_dir = Path(self.mmx_path).parent
            node_exe = mmx_dir / "node.exe"
            mjs_file = mmx_dir / "node_modules" / "mmx-cli" / "dist" / "mmx.mjs"
            if node_exe.exists() and mjs_file.exists():
                cmd = [str(node_exe), str(mjs_file), "quota", "show", "-f", "json"]
            else:
                # fallback: 鐩存帴鐢?mmx_path + CREATE_NO_WINDOW
                cmd = [self.mmx_path, "quota", "show", "-f", "json"]
        else:
            cmd = [self.mmx_path, "quota", "show", "-f", "json"]

        # 鍏滃簳:濡傛灉杩樻槸璋?.cmd,鍔?CREATE_NO_WINDOW
        creation_flags = 0
        if _sys.platform == "win32" and cmd[0].lower().endswith((".cmd", ".bat")):
            creation_flags = 0x08000000  # CREATE_NO_WINDOW

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            shell=False,
            **({"creationflags": creation_flags} if creation_flags else {}),
        )
        if result.returncode != 0:
            raise RuntimeError(f"mmx-cli 閫€鍑虹爜 {result.returncode}:{result.stderr[:200]}")
        return json.loads(result.stdout)

    def _parse_mmx_output(self, raw: dict) -> TokenUsage:
        """鎶?mmx-cli 鐪熷疄杈撳嚭杞垚 TokenUsage

        鐪熷疄缁撴瀯(2026-06-13 楠岃瘉):
        {
          "model_remains": [
            {"model_name": "general", ...},
            {"model_name": "M3", ...},
            {"model_name": "M2.7", ...}
          ]
        }

        v0.3 鍔?M3 / M2.7 鍒嗚建杩涘害鏉?鍒嗗埆鎸?model_name 鎷夊悇鑷殑 remaining %)
        """
        model_remains_raw = raw.get("model_remains", [])

        def _get(name: str) -> dict:
            return next((m for m in model_remains_raw if m.get("model_name") == name), {})

        # 鎬婚搴?general)
        general = _get("general") or (model_remains_raw[0] if model_remains_raw else {})
        # M3 / M2.7 鍒嗚建(濡傛灉 mmx 杈撳嚭閲屾湁)
        m3 = _get("M3") or _get("m3")
        m27 = _get("M2.7") or _get("m2.7") or _get("M27") or _get("m27")

        interval_rem = float(general.get("current_interval_remaining_percent", 0))
        weekly_rem = float(general.get("current_weekly_remaining_percent", 0))

        # M3 / M2.7 宸茬敤%
        def _used_pct(m: dict) -> float:
            if not m:
                return 0.0
            rem = float(m.get("current_interval_remaining_percent", 0) or 0)
            return round(100.0 - rem, 2)

        m3_used = _used_pct(m3)
        m27_used = _used_pct(m27)

        # weekly_used 绱(浠?weekly_used_tokens 瀛楁,娌℃湁灏?0)
        weekly_used_tokens = int(general.get("weekly_used_tokens", 0) or 0)

        return TokenUsage(
            interval_remaining_pct=interval_rem,
            interval_used_pct=round(100.0 - interval_rem, 2),
            interval_end_time=int(general.get("end_time", 0)),
            weekly_remaining_pct=weekly_rem,
            weekly_used_pct=round(100.0 - weekly_rem, 2),
            weekly_end_time=int(general.get("weekly_end_time", 0)),
            weekly_boost_permille=int(general.get("weekly_boost_permille", 0)),
            m3_used_pct=m3_used,
            m27_used_pct=m27_used,
            weekly_used=weekly_used_tokens,
        )

    def _error_result(self, msg: str) -> TokenUsage:
        return TokenUsage(
            fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            source="error",
            error=msg,
        )

    @property
    def last(self) -> Optional[TokenUsage]:
        return self._last_usage

    @property
    def last(self) -> Optional[TokenUsage]:
        return self._last_usage


# 鐙珛娴嬭瘯鍏ュ彛
if __name__ == "__main__":
    import sys
    s = TokenService()
    if "--mock" in sys.argv:
        u = s.fetch_mock()
    else:
        u = s.fetch()
    print(json.dumps(u.to_dict(), ensure_ascii=False, indent=2))

