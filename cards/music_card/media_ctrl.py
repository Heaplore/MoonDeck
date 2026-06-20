"""Media Control - 歌曲进度获取 v0.1

通过 Windows Global System Media Transport Controls (GMRTC) 获取:
- 当前歌曲标题
- 歌手/专辑
- 播放进度(当前位置/总时长)
- 播放状态

这是 Windows 10/11 内置 API，无需额外安装。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass
from typing import Optional

# 尝试通过 comtypes 访问 Windows Runtime
try:
    import comtypes
    import comtypes.client
    from comtypes import GUID

    # Windows.Media.Control GUID
    # IAsyncOperation GUIDs
    _HAS_COMTYPES = True
except ImportError:
    _HAS_COMTYPES = False


@dataclass
class MediaProgress:
    """播放进度信息"""
    title: str = ""
    artist: str = ""
    album: str = ""
    position_ms: int = 0     # 当前位置(毫秒)
    duration_ms: int = 0     # 总时长(毫秒)
    is_playing: bool = False

    @property
    def progress_pct(self) -> float:
        """进度百分比 (0.0 ~ 1.0)"""
        if self.duration_ms <= 0:
            return 0.0
        return max(0.0, min(1.0, self.position_ms / self.duration_ms))

    @property
    def position_str(self) -> str:
        """格式化位置 mm:ss"""
        s = self.position_ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    @property
    def duration_str(self) -> str:
        """格式化时长 mm:ss"""
        s = self.duration_ms // 1000
        return f"{s // 60}:{s % 60:02d}"


def _try_get_media_session():
    """尝试获取 GMRTC Session Manager (通过 PowerShell 桥接)"""
    try:
        import subprocess
        # PowerShell 调用 Windows.Media.Control API
        ps_script = """
        Add-Type -AssemblyName System.Runtime.WindowsRuntime
        [System.WindowsRuntimeAsyncHelpers, System.Runtime.WindowsRuntime] | Out-Null
        
        # 获取 Session Manager
        $manager = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync().GetAwaiter().GetResult()
        $session = $manager.GetCurrentSession()
        
        if ($session -eq $null) {
            Write-Output "NO_SESSION"
            exit
        }
        
        # 获取媒体信息
        $info = $session.TryGetMediaPropertiesAsync().GetAwaiter().GetResult()
        $timeline = $session.GetTimelineProperties()
        
        $position = $timeline.Position.TotalMilliseconds
        $duration = $timeline.EndTime.TotalMilliseconds
        $title = $info.Title
        $artist = $info.Artist
        $album = $info.AlbumTitle
        $playing = $session.PlaybackSession.PlaybackStatus -eq "Playing"
        
        Write-Output "$title|$artist|$album|$position|$duration|$playing"
        """
        
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            timeout=5,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        
        output = result.stdout.decode('utf-8', errors='ignore').strip()
        if output == "NO_SESSION" or not output:
            return None
        
        parts = output.split("|")
        if len(parts) >= 6:
            return MediaProgress(
                title=parts[0],
                artist=parts[1],
                album=parts[2],
                position_ms=int(float(parts[3])),
                duration_ms=int(float(parts[4])),
                is_playing=parts[5].lower() == "true",
            )
    except Exception:
        pass
    return None


# 缓存上次结果(PowerShell 调用慢,不能每次都调)
_cache: Optional[MediaProgress] = None
_cache_tick: int = 0


def get_media_progress() -> Optional[MediaProgress]:
    """获取当前播放进度(带缓存,每秒最多调用一次)"""
    global _cache, _cache_tick
    import time
    now = int(time.time())
    if now != _cache_tick:
        _cache_tick = now
        result = _try_get_media_session()
        if result is not None:
            _cache = result
    return _cache


def media_play_pause() -> None:
    """播放/暂停"""
    try:
        import subprocess
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$s = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync().GetAwaiter().GetResult().GetCurrentSession(); "
             "if ($s.PlaybackSession.PlaybackStatus -eq 'Playing') { $s.TryTogglePlayPauseAsync().GetAwaiter().GetResult() }"],
            capture_output=True, timeout=3, creationflags=0x08000000,
        )
    except Exception:
        pass


def media_next() -> None:
    """下一首"""
    try:
        import subprocess
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$s = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync().GetAwaiter().GetResult().GetCurrentSession(); "
             "$s.TrySkipNextAsync().GetAwaiter().GetResult()"],
            capture_output=True, timeout=3, creationflags=0x08000000,
        )
    except Exception:
        pass


def media_prev() -> None:
    """上一首"""
    try:
        import subprocess
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$s = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync().GetAwaiter().GetResult().GetCurrentSession(); "
             "$s.TrySkipPreviousAsync().GetAwaiter().GetResult()"],
            capture_output=True, timeout=3, creationflags=0x08000000,
        )
    except Exception:
        pass
