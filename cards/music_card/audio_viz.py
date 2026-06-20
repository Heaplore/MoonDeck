"""Audio Visualizer - WASAPI loopback FFT v0.7 (Phase 2)

基于 PyQt5 标杆版 (E:\\OH-workspace\\Widgets\\music-card\\music_card.py) 移植到 PyQt6。

接口保持向后兼容 (与 v0.2 旧版一致):
- start(): 启动后台采样线程
- get_peak() -> float
- get_levels(bands: int = 5) -> List[float]
- get_spectrum() -> np.ndarray  (新增, 给 widget 用)
- has_real_audio() -> bool  (新增)

特性:
- 48 bands 真实 FFT (覆盖 30Hz-18kHz 对数分桶)
- 平滑: 上升 0.6 / 下降 0.12
- peak_hold: 每帧 max × 0.95 衰减
- simulate() fallback (无音频设备时)
- pyaudiowpatch WASAPI loopback
"""
from __future__ import annotations

import threading
import time
from typing import List

import numpy as np

try:
    import pyaudiowpatch as pyaudio
    _HAS_PYAUDIOWPATCH = True
except ImportError:
    _HAS_PYAUDIOWPATCH = False

# ---------------------------------------------------------------------------
# 共享状态 (后台线程写, UI 线程读, 用锁保护)
# ---------------------------------------------------------------------------
_BANDS = 48
_spectrum = np.zeros(_BANDS, dtype=np.float32)
_peak_hold = np.zeros(_BANDS, dtype=np.float32)
_lock = threading.Lock()
_running = False
_has_real_audio = False
_audio_thread: threading.Thread | None = None
_sim_thread: threading.Thread | None = None


# ---------------------------------------------------------------------------
# FFT 频谱核心
# ---------------------------------------------------------------------------
def _process_fft(data: np.ndarray, frame_count: int, sample_rate: int) -> np.ndarray:
    """对一段音频做 FFT + 对数分桶, 返回 _BANDS 长度电平数组 [0, 1]"""
    fft_data = np.abs(np.fft.rfft(data))[: frame_count // 2]
    freqs = np.fft.rfftfreq(frame_count, 1.0 / sample_rate)[: frame_count // 2]

    edges = np.logspace(np.log10(30), np.log10(18000), _BANDS + 1)
    vals = np.zeros(_BANDS, dtype=np.float32)
    for i in range(_BANDS):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if np.any(mask):
            vals[i] = np.max(fft_data[mask])

    mx = float(np.max(vals))
    if mx > 0:
        vals /= mx
    return vals


def _smooth_update(raw: np.ndarray) -> None:
    """平滑 + peak_hold 更新"""
    with _lock:
        for i in range(_BANDS):
            a = 0.6 if raw[i] > _spectrum[i] else 0.12
            _spectrum[i] += (raw[i] - _spectrum[i]) * a
            _peak_hold[i] = max(_peak_hold[i], _spectrum[i])
            _peak_hold[i] *= 0.95


def _audio_callback(in_data, frame_count, time_info, status):
    """pyaudio 流式回调 - 在后台线程跑"""
    try:
        data = np.frombuffer(in_data, dtype=np.float32)
        # 立体声转单声道
        if len(data) >= frame_count * 2:
            data = data.reshape(-1, 2).mean(axis=1)

        # 用固定 sample_rate 44100 (与设备无关)
        raw = _process_fft(data, len(data), 44100)
        _smooth_update(raw)
    except Exception:
        pass
    return (None, pyaudio.paContinue)


def _find_loopback_device(pa) -> dict | None:
    """找默认输出设备的 loopback"""
    try:
        default = pa.get_default_output_device_info()
        default_name = default["name"]

        # 优先级 1: 名字完全匹配 default 的 loopback
        for i in range(pa.get_device_count()):
            dev = pa.get_device_info_by_index(i)
            if "[Loopback]" in dev["name"]:
                base = dev["name"].replace(" [Loopback]", "").strip()
                if base == default_name:
                    return dev

        # 优先级 2: 关键字匹配
        keyword = default_name.split("(")[0].strip()
        for i in range(pa.get_device_count()):
            dev = pa.get_device_info_by_index(i)
            if "[Loopback]" in dev["name"] and keyword in dev["name"]:
                return dev

        # 优先级 3: 任意 loopback
        for i in range(pa.get_device_count()):
            dev = pa.get_device_info_by_index(i)
            if "[Loopback]" in dev["name"]:
                return dev
    except Exception:
        pass
    return None


def _audio_loop() -> None:
    """后台线程: WASAPI loopback 流式采样"""
    global _has_real_audio
    if not _HAS_PYAUDIOWPATCH:
        return

    pa = None
    stream = None
    try:
        pa = pyaudio.PyAudio()
        loopback = _find_loopback_device(pa)
        if not loopback:
            return

        rate = int(loopback["defaultSampleRate"])
        channels = loopback["maxInputChannels"]

        stream = pa.open(
            format=pyaudio.paFloat32,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=loopback["index"],
            frames_per_buffer=1024,
            stream_callback=_audio_callback,
        )
        stream.start_stream()
        _has_real_audio = True
        log_msg(f"✅ WASAPI loopback 启动成功 (rate={rate}, ch={channels}, dev='{loopback['name']}')")

        # 保持线程存活
        while _running:
            time.sleep(0.1)
            if not stream.is_active():
                break

    except Exception as e:
        log_msg(f"❌ WASAPI loopback 启动失败: {e}")
    finally:
        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        if pa:
            try:
                pa.terminate()
            except Exception:
                pass
        _has_real_audio = False


def simulate() -> None:
    """无音频设备时模拟律动 (PyQt5 标杆版同款算法)"""
    t = time.time() * 2
    with _lock:
        for i in range(_BANDS):
            v = 0.3 + 0.15 * np.sin(t * 2.5 + i * 0.15)
            v += 0.6 * max(0, np.sin(t * 4.2)) * (1 if i < 10 else 0)
            v += 0.4 * max(0, np.sin(t * 3.1 + 0.8)) * (1 if 10 <= i < 28 else 0)
            v += 0.25 * max(0, np.sin(t * 5.5 + 1.5)) * (1 if i >= 28 else 0)
            v = float(np.clip(v, 0, 1))
            a = 0.6 if v > _spectrum[i] else 0.12
            _spectrum[i] += (v - _spectrum[i]) * a
            _peak_hold[i] = max(_peak_hold[i], _spectrum[i])
            _peak_hold[i] *= 0.95


def _sim_ticker() -> None:
    """simulate 模式 ticker: 没真音频时持续模拟律动"""
    while _running:
        if not _has_real_audio:
            simulate()
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# 公开 API (向后兼容)
# ---------------------------------------------------------------------------
def start() -> None:
    """启动后台音频采样线程"""
    global _running, _audio_thread, _sim_thread
    if _audio_thread and _audio_thread.is_alive():
        return
    _running = True
    _audio_thread = threading.Thread(target=_audio_loop, daemon=True, name="AudioFFT")
    _audio_thread.start()
    _sim_thread = threading.Thread(target=_sim_ticker, daemon=True, name="AudioSim")
    _sim_thread.start()


def stop() -> None:
    """停止采样"""
    global _running
    _running = False


def get_peak() -> float:
    """获取当前系统音频峰值 [0.0, 1.0+], 兼容旧 API"""
    with _lock:
        return float(np.max(_spectrum))


def get_levels(bands: int = 5) -> List[float]:
    """获取 N 段电平 (旧 API 兼容)"""
    with _lock:
        sp = _spectrum.copy()

    if bands <= 0:
        return []
    if bands == 1:
        return [float(np.mean(sp))]

    if len(sp) == bands:
        return [float(x) for x in sp]

    # 聚合到 bands 段 (取均值)
    out: List[float] = []
    chunk = len(sp) / bands
    for i in range(bands):
        s = int(i * chunk)
        e = int((i + 1) * chunk)
        seg = sp[s:e] if e > s else sp[s:s + 1]
        out.append(float(np.mean(seg)) if len(seg) > 0 else 0.0)
    return out


def get_spectrum() -> np.ndarray:
    """获取完整 48 band 频谱 (新 API, 给 widget 用)"""
    with _lock:
        return _spectrum.copy()


def get_peaks() -> np.ndarray:
    """获取 peak_hold 线 (新 API, 给 widget 用)"""
    with _lock:
        return _peak_hold.copy()


def has_real_audio() -> bool:
    """是否在用真音频 (新 API)"""
    return _has_real_audio


# ---------------------------------------------------------------------------
# NowPlayingState 共享状态 (内联 now_playing.py 避免 PyInstaller 遗漏)
# ---------------------------------------------------------------------------
from dataclasses import dataclass, field
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .lyrics_loader import LyricLine

@dataclass
class _NowPlayingState:
    lyrics: List = field(default_factory=list)
    lyric_idx: int = -1
    position_sec: float = 0.0
    duration_sec: float = 0.0
    is_playing: bool = False
    song_title: str = ""
    song_artist: str = ""


_np_state = _NowPlayingState()


def get_now_playing() -> _NowPlayingState:
    return _np_state


def set_now_playing(
    lyrics: List,
    lyric_idx: int,
    position_sec: float,
    duration_sec: float,
    is_playing: bool,
    song_title: str = "",
    song_artist: str = "",
) -> None:
    _np_state.lyrics = lyrics
    _np_state.lyric_idx = lyric_idx
    _np_state.position_sec = position_sec
    _np_state.duration_sec = duration_sec
    _np_state.is_playing = is_playing
    _np_state.song_title = song_title
    _np_state.song_artist = song_artist


# ---------------------------------------------------------------------------
# 日志 (避免 widget 还没 import 时出错)
# ---------------------------------------------------------------------------
def log_msg(msg: str) -> None:
    import logging
    log = logging.getLogger("audio_viz")
    if not log.handlers:
        log.addHandler(logging.NullHandler())
    log.info(msg)
