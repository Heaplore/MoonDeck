"""cards/music_card/now_playing.py

全局当前播放状态 (歌词 + 进度 + 当前行)
供 MusicAreaWidget (写入) 和 DesktopBackground 视觉化器 (读取) 共享
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .lyrics_loader import LyricLine


@dataclass
class _NowPlayingState:
    lyrics: List[LyricLine] = field(default_factory=list)
    lyric_idx: int = -1
    position_sec: float = 0.0
    duration_sec: float = 0.0
    is_playing: bool = False
    song_title: str = ""
    song_artist: str = ""


_state = _NowPlayingState()


def get_now_playing() -> _NowPlayingState:
    return _state


def set_now_playing(
    lyrics: List[LyricLine],
    lyric_idx: int,
    position_sec: float,
    duration_sec: float,
    is_playing: bool,
    song_title: str = "",
    song_artist: str = "",
) -> None:
    _state.lyrics = lyrics
    _state.lyric_idx = lyric_idx
    _state.position_sec = position_sec
    _state.duration_sec = duration_sec
    _state.is_playing = is_playing
    _state.song_title = song_title
    _state.song_artist = song_artist
