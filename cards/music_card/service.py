"""Music Service - SMTC 元数据 + 媒体控制 v0.7 (Phase 2)

基于 PyQt5 标杆版 MediaInfoThread 移植到 PyQt6 + winrt。
接口向后兼容 (与 v0.2 旧版一致):
- MusicInfo dataclass
- detect_music_simple() -> Optional[MusicInfo]
- media_play_pause() / media_next() / media_prev()

新特性:
- SMTC (GlobalSystemMediaTransportControlsSessionManager) 拿真实元数据
- 后台 QThread + asyncio 异步轮询
- 同步函数返回最新缓存 (零延迟)
- 自动识别播放器 (汽水/QQ/网易云/Spotify/foobar2000 等)
"""
from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes as wt
import logging
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger("music_service")


# ---------------------------------------------------------------------------
# 媒体信息数据结构 (向后兼容 v0.2 接口)
# ---------------------------------------------------------------------------
@dataclass
class MusicInfo:
    """当前播放信息"""
    player_name: str = ""
    player_icon: str = "🎵"
    song_title: str = ""
    song_artist: str = ""
    album: str = ""
    is_playing: bool = False
    window_title: str = ""
    pid: int = 0
    position_sec: float = 0.0   # 新增: 播放位置 (秒)
    duration_sec: float = 0.0   # 新增: 总时长 (秒)
    source: str = ""            # 新增: SMTC source app id


# ---------------------------------------------------------------------------
# 播放器识别 (从 SMTC source app user model id 推断)
# ---------------------------------------------------------------------------
_PLAYER_REGISTRY = [
    # (匹配关键字, 显示名, 图标)  - 按优先级匹配
    ("SodaMusic",       "汽水音乐",       "🥤"),
    ("QQMusic",        "QQ音乐",         "🎶"),
    ("CloudMusic",     "网易云音乐",     "🎵"),
    ("163Music",       "网易云音乐",     "🎵"),
    ("NetEase",        "网易云音乐",     "🎵"),
    ("Spotify",        "Spotify",        "🎧"),
    ("MusicBee",       "MusicBee",       "🐝"),
    ("foobar2000",     "foobar2000",     "🎛️"),
    ("AIMP",           "AIMP",           "🎵"),
    ("vlc",            "VLC",            "🎬"),
    ("wmplayer",       "Windows Media",  "📀"),
    ("iTunes",         "iTunes",         "🎵"),
]


def _identify_player(source: str) -> tuple[str, str]:
    """从 SMTC source id 推断播放器名 + 图标"""
    src_lower = source.lower()
    for keyword, name, icon in _PLAYER_REGISTRY:
        if keyword.lower() in src_lower:
            return name, icon
    return (source or "未知播放器", "🎵")


# ---------------------------------------------------------------------------
# SMTC 后台轮询线程
# ---------------------------------------------------------------------------
def _ts_to_sec(ts) -> float:
    """winrt TimeSpan / datetime.timedelta / int -> 秒 (float)

    PyInstaller 打包后 winrt TimeSpan 可能 fallback 到 datetime.timedelta,
    timedelta 不支持 / 10_000_000,需要 total_seconds().
    """
    if ts is None:
        return 0.0
    # datetime.timedelta 优先
    if hasattr(ts, "total_seconds"):
        try:
            return float(ts.total_seconds())
        except Exception:
            pass
    # winrt TimeSpan / int (100ns units) / float
    try:
        return float(int(ts)) / 10_000_000
    except (TypeError, ValueError):
        return 0.0


class _SMTCThread(QThread):
    """后台 SMTC 轮询线程, 通过 signal 把元数据推给 UI"""
    info_ready = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._running = True

    def run(self) -> None:
        """在线程内跑独立 asyncio 循环"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._poll_forever())
        except Exception as e:
            log.warning(f"SMTC 线程异常: {e}")
        finally:
            loop.close()

    async def _poll_forever(self) -> None:
        try:
            import winrt.windows.media.control as wmc
            log.info("请求 SMTC Manager ...")
            manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
            log.info("✅ SMTC Manager 拿到")
        except Exception as e:
            log.error(f"❌ SMTC Manager 请求失败: {e}")
            return

        empty_payload = {
            "title": "", "artist": "", "album": "",
            "is_playing": False, "position": 0.0, "duration": 0.0,
            "source": "",
        }

        while self._running:
            try:
                session = manager.get_current_session()
                if not session:
                    self.info_ready.emit(dict(empty_payload))
                else:
                    mp = await session.try_get_media_properties_async()
                    pi = session.get_playback_info()
                    tl = session.get_timeline_properties()

                    # 播放状态码: 4=playing, 5=paused
                    is_playing = bool(pi and pi.playback_status == 4)

                    # timeline 时间单位是 100ns (PyInstaller 打包后可能变 timedelta, 要 robust 转换)
                    pos_sec = _ts_to_sec(tl.position) if tl else 0.0
                    dur_sec = _ts_to_sec(tl.end_time) if tl else 0.0

                    self.info_ready.emit({
                        "title": mp.title or "",
                        "artist": mp.artist or "",
                        "album": mp.album_title or "",
                        "is_playing": is_playing,
                        "position": pos_sec,
                        "duration": dur_sec,
                        "source": session.source_app_user_model_id or "",
                    })
            except Exception as e:
                log.debug(f"SMTC 轮询异常: {e}")
                self.info_ready.emit(dict(empty_payload))

            await asyncio.sleep(0.3)

    def stop(self) -> None:
        self._running = False
        self.wait(3000)


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_smtc_thread: Optional[_SMTCThread] = None
_latest_info = MusicInfo()


def _on_info(payload: dict) -> None:
    """SMTC signal 回调: 更新全局缓存"""
    global _latest_info

    source = payload.get("source", "")
    name, icon = _identify_player(source)

    _latest_info = MusicInfo(
        player_name=name,
        player_icon=icon,
        song_title=payload.get("title", ""),
        song_artist=payload.get("artist", ""),
        album=payload.get("album", ""),
        is_playing=payload.get("is_playing", False),
        window_title=f"{payload.get('title', '')} - {payload.get('artist', '')}".strip(" -"),
        pid=0,
        position_sec=payload.get("position", 0.0),
        duration_sec=payload.get("duration", 0.0),
        source=source,
    )
    log.info(f"_on_info 触发: title={_latest_info.song_title!r} artist={_latest_info.song_artist!r} source={source!r}")


def _ensure_smtc_started() -> None:
    """惰性启动 SMTC 后台线程"""
    global _smtc_thread
    if _smtc_thread is not None and _smtc_thread.isRunning():
        return
    _smtc_thread = _SMTCThread()
    _smtc_thread.info_ready.connect(_on_info)
    _smtc_thread.start()
    log.info("SMTC 后台线程已启动")


# ---------------------------------------------------------------------------
# 同步 API (向后兼容)
# ---------------------------------------------------------------------------
def detect_music_simple() -> Optional[MusicInfo]:
    """同步返回当前 MusicInfo (从 SMTC 缓存读)"""
    _ensure_smtc_started()
    if not _latest_info.player_name and not _latest_info.song_title:
        return None
    return _latest_info


def detect_music() -> list:
    """兼容旧 API, 返回单元素列表"""
    info = detect_music_simple()
    return [info] if info else []


# ---------------------------------------------------------------------------
# 媒体控制 (SMTC 官方接口)
# ---------------------------------------------------------------------------
async def _smtc_action_async(action: str) -> None:
    try:
        import winrt.windows.media.control as wmc
        mgr = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
        s = mgr.get_current_session()
        if not s:
            return
        if action == "next":
            await s.try_skip_next_async()
        elif action == "prev":
            await s.try_skip_previous_async()
        elif action == "toggle":
            pi = s.get_playback_info()
            if pi and pi.playback_status == 4:  # playing
                await s.try_pause_async()
            else:
                await s.try_play_async()
        elif action == "stop":
            await s.try_stop_async()
        elif action.startswith("seek:"):
            pos_ms = int(action.split(":")[1])
            from datetime import timedelta
            target = timedelta(milliseconds=pos_ms)
            try:
                result = await s.try_change_playback_position_async(target)
                log.info(f"SMTC seek 结果: {result} (目标 {pos_ms}ms)")
                if not result:
                    log.warning(f"SMTC seek 返回 False - 播放器不支持 seek")
            except Exception as e:
                log.warning(f"SMTC seek 失败: {e}")
    except Exception as e:
        log.warning(f"SMTC action '{action}' 失败: {e}")


def media_play_pause() -> None:
    """播放/暂停切换"""
    asyncio.run(_smtc_action_async("toggle"))


def media_next() -> None:
    """下一首"""
    asyncio.run(_smtc_action_async("next"))


def media_prev() -> None:
    """上一首"""
    asyncio.run(_smtc_action_async("prev"))


def media_stop() -> None:
    """停止"""
    asyncio.run(_smtc_action_async("stop"))


def media_seek(position_sec: float) -> None:
    """跳转到指定位置 (秒) - 键盘模拟 seek (左右箭头)"""
    _keyboard_seek(position_sec)


def _keyboard_seek(target_sec: float) -> None:
    """SendInput 方式: 先激活播放器窗口, 再发箭头键, 最后切回"""
    try:
        import ctypes
        import time as _t

        user32 = ctypes.windll.user32

        # 找播放器窗口
        _found_hwnd = [None]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _enum_cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.lower()
            for kw in ["sodamusic", "汽水", "qqmusic", "qq音乐", "netease", "cloudmusic", "网易云", "spotify"]:
                if kw in title:
                    _found_hwnd[0] = hwnd
                    log.info(f"键盘 seek: 找到播放器窗口 hwnd={hwnd} title={buf.value}")
                    return False
            return True

        user32.EnumWindows(_enum_cb, 0)
        player_hwnd = _found_hwnd[0]

        if not player_hwnd:
            log.warning("键盘 seek: 找不到播放器窗口")
            return

        # 获取当前播放位置
        info = detect_music_simple()
        current_sec = info.position_sec if info else 0
        diff = target_sec - current_sec
        if abs(diff) < 1:
            return

        # 激活播放器窗口
        SW_RESTORE = 9
        user32.ShowWindow(player_hwnd, SW_RESTORE)
        user32.SetForegroundWindow(player_hwnd)
        _t.sleep(0.1)

        # 计算步数
        steps = min(int(abs(diff) / 5) + 1, 60)
        direction = "right" if diff > 0 else "left"

        # SendInput 方式
        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002
        VK_LEFT = 0x25
        VK_RIGHT = 0x27

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                       ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                       ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("ki", KEYBDINPUT)]

        def send_key(vk):
            ii = INPUT()
            ii.type = INPUT_KEYBOARD
            ii.ki.wVk = vk
            ii_up = INPUT()
            ii_up.type = INPUT_KEYBOARD
            ii_up.ki.wVk = vk
            ii_up.ki.dwFlags = KEYEVENTF_KEYUP
            user32.SendInput(2, ctypes.byref(ii), ctypes.sizeof(INPUT))

        vk = VK_RIGHT if direction == "right" else VK_LEFT
        for i in range(steps):
            send_key(vk)
            _t.sleep(0.05)

        log.info(f"键盘 seek: {direction} {steps}次, 目标 {target_sec:.0f}s")

    except Exception as e:
        log.warning(f"键盘 seek 失败: {e}")


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
    print("=== music_service 自检 ===")
    print("启动 SMTC 后台线程 ...")
    _ensure_smtc_started()
    import time
    time.sleep(2.0)  # 等第一轮轮询完成

    info = detect_music_simple()
    if info:
        print(f"\n当前音乐:")
        print(f"  播放器: {info.player_icon} {info.player_name}")
        print(f"  歌曲:   {info.song_title}")
        print(f"  歌手:   {info.song_artist}")
        print(f"  状态:   {'▶️ 播放中' if info.is_playing else '⏸ 暂停'}")
        print(f"  进度:   {info.position_sec:.1f}s / {info.duration_sec:.1f}s")
        print(f"  Source: {info.source}")
    else:
        print("\n⚠️  没有音乐在播放 (或 SMTC 未拿到元数据)")
