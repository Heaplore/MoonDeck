"""Music Service - 检测系统音乐播放器 v0.1

检测方式:
1. 扫描已知音乐播放器进程
2. 获取窗口标题(通常包含 "歌名 - 歌手" 格式)
3. 返回播放器名称 + 歌曲信息

支持的播放器:
- Spotify
- 网易云音乐 (CloudMusic / Netease)
- QQ音乐 (QQMusic)
- Soda Music
- foobar2000
- AIMP
- MusicBee
- VLC (播放状态)
- Windows Media Player
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass, field
from typing import Optional, List

# Win32 API
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

EnumWindows = _user32.EnumWindows
GetWindowTextW = _user32.GetWindowTextW
GetWindowTextLengthW = _user32.GetWindowTextLengthW
IsWindowVisible = _user32.IsWindowVisible
GetWindowThreadProcessId = _user32.GetWindowThreadProcessId

OpenProcess = _kernel32.OpenProcess
QueryFullProcessImageNameW = _kernel32.QueryFullProcessImageNameW
CloseHandle = _kernel32.CloseHandle

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

# 已知音乐播放器: (进程名(小写), 显示名, 图标)
KNOWN_PLAYERS = [
    ("spotify", "Spotify", "🎧"),
    ("cloudmusic", "网易云音乐", "🎵"),
    ("netease", "网易云音乐", "🎵"),
    ("qqmusic", "QQ音乐", "🎶"),
    ("sodamusic", "汽水音乐", "🎵"),
    ("soda", "汽水音乐", "🎵"),
    ("foobar2000", "foobar2000", "🎛️"),
    ("aimp", "AIMP", "🎵"),
    ("musicbee", "MusicBee", "🐝"),
    ("vlc", "VLC", "🎬"),
    ("wmplayer", "Windows Media Player", "📀"),
    ("musicanim", "Music Animation", "🎵"),
]


@dataclass
class MusicInfo:
    """当前播放信息"""
    player_name: str = ""
    player_icon: str = "🎵"
    song_title: str = ""
    song_artist: str = ""
    is_playing: bool = False
    window_title: str = ""
    pid: int = 0


def _get_window_title(hwnd: int) -> str:
    """获取窗口标题"""
    length = GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_process_path(pid: int) -> str:
    """获取进程可执行文件路径"""
    try:
        handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not handle:
            return ""
        buf = ctypes.create_unicode_buffer(512)
        size = ctypes.c_ulong(512)
        if QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            CloseHandle(handle)
            return buf.value.lower()
        CloseHandle(handle)
    except Exception:
        pass
    return ""


def _parse_window_title(title: str) -> tuple[str, str]:
    """尝试从窗口标题解析 歌名 - 歌手
    
    常见格式:
    - "歌名 - 歌手 - 播放器名"
    - "歌名 - 歌手"
    - "播放器名"
    """
    if not title:
        return "", ""
    
    # 去掉常见播放器后缀
    clean = title
    for suffix in [" - Spotify", " - 网易云音乐", " - QQ音乐", " - Soda Music",
                    " - foobar2000", " - AIMP", " - MusicBee", " - VLC media player",
                    " - Windows Media Player"]:
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)].strip()
    
    # 尝试按 " - " 分割(歌名 - 歌手)
    parts = clean.split(" - ", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    
    return clean.strip(), ""


def detect_music() -> List[MusicInfo]:
    """检测当前运行的音乐播放器,返回列表"""
    results: List[MusicInfo] = []
    
    # 收集所有窗口
    windows: list[tuple[int, str]] = []
    
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def enum_callback(hwnd, _lparam):
        if IsWindowVisible(hwnd):
            title = _get_window_title(hwnd)
            if title:
                pid = ctypes.c_ulong()
                GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                windows.append((hwnd, title, pid.value))
        return True
    
    EnumWindows(enum_callback, 0)
    
    # 匹配已知播放器
    seen_pids = set()
    for hwnd, title, pid in windows:
        if pid in seen_pids:
            continue
        
        # 获取进程路径
        proc_path = _get_process_path(pid)
        
        for proc_name, display_name, icon in KNOWN_PLAYERS:
            if proc_name in proc_path:
                seen_pids.add(pid)
                song, artist = _parse_window_title(title)
                
                info = MusicInfo(
                    player_name=display_name,
                    player_icon=icon,
                    song_title=song if song != display_name else "",
                    song_artist=artist,
                    is_playing=True,  # 能检测到窗口就假定在播放
                    window_title=title,
                    pid=pid,
                )
                results.append(info)
                break
    
    return results


def detect_music_simple() -> Optional[MusicInfo]:
    """检测单个播放器(返回第一个)"""
    players = detect_music()
    return players[0] if players else None


# ── 媒体控制 ─────────────────────────────────────────
# 通过模拟系统媒体键控制播放(所有播放器都响应)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2


def _send_media_key(vk_code: int) -> None:
    """发送一个媒体按键"""
    try:
        import ctypes.wintypes as wt

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wt.WORD),
                ("wScan", wt.WORD),
                ("dwFlags", wt.DWORD),
                ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wt.DWORD), ("ki", KEYBDINPUT)]

        ii_ = INPUT()
        ii_.type = INPUT_KEYBOARD
        ii_.ki.wVk = vk_code
        ii_.ki.dwFlags = 0

        ii_up = INPUT()
        ii_up.type = INPUT_KEYBOARD
        ii_up.ki.wVk = vk_code
        ii_up.ki.dwFlags = KEYEVENTF_KEYUP

        SendInput = ctypes.windll.user32.SendInput
        SendInput(2, ctypes.byref(ii_), ctypes.sizeof(INPUT))
    except Exception:
        pass


def media_play_pause() -> None:
    """播放/暂停"""
    _send_media_key(VK_MEDIA_PLAY_PAUSE)


def media_next() -> None:
    """下一首"""
    _send_media_key(VK_MEDIA_NEXT_TRACK)


def media_prev() -> None:
    """上一首"""
    _send_media_key(VK_MEDIA_PREV_TRACK)


def media_stop() -> None:
    """停止"""
    _send_media_key(VK_MEDIA_STOP)
