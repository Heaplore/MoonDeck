"""Audio Visualizer - 系统音频峰值检测 v0.7

后台线程独立采样 WASAPI 峰值，UI 主线程只读共享变量。
避免每帧调用 COM 导致卡顿。
"""
from __future__ import annotations

import comtypes
from comtypes import POINTER, cast
from ctypes import c_float
import math
import random
import threading
import time
from typing import List

_peak_value: float = 0.0
_peak_lock = threading.Lock()
_running = False
_audio_thread: threading.Thread | None = None


def _audio_loop():
    """后台线程：每 30ms 采样一次系统音频峰值"""
    global _peak_value, _running
    try:
        from pycaw.constants import CLSID_MMDeviceEnumerator
        from pycaw.pycaw import IAudioMeterInformation, IMMDeviceEnumerator, EDataFlow, ERole

        comtypes.CoInitialize()
        enumerator = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator,
            IMMDeviceEnumerator,
            comtypes.CLSCTX_INPROC_SERVER,
        )
        speakers = enumerator.GetDefaultAudioEndpoint(
            EDataFlow.eRender.value, ERole.eMultimedia.value
        )
        raw_meter = speakers.Activate(
            IAudioMeterInformation._iid_,
            comtypes.CLSCTX_ALL,
            None,
        )
        meter = cast(raw_meter, POINTER(IAudioMeterInformation))

        _running = True
        while _running:
            try:
                raw = float(meter.GetPeakValue())
                peak = max(0.0, min(1.0, raw))
                amplified = peak * 2.5
                with _peak_lock:
                    _peak_value = min(1.0, amplified)
            except Exception:
                with _peak_lock:
                    _peak_value = 0.0
                # 重建连接
                try:
                    enumerator2 = comtypes.CoCreateInstance(
                        CLSID_MMDeviceEnumerator,
                        IMMDeviceEnumerator,
                        comtypes.CLSCTX_INPROC_SERVER,
                    )
                    speakers2 = enumerator2.GetDefaultAudioEndpoint(
                        EDataFlow.eRender.value, ERole.eMultimedia.value
                    )
                    raw_meter2 = speakers2.Activate(
                        IAudioMeterInformation._iid_,
                        comtypes.CLSCTX_ALL,
                        None,
                    )
                    meter = cast(raw_meter2, POINTER(IAudioMeterInformation))
                except Exception:
                    pass
            time.sleep(0.03)  # ~33fps
    except Exception:
        _running = False


def start():
    """启动音频采样线程"""
    global _audio_thread, _running
    if _audio_thread and _audio_thread.is_alive():
        return
    _running = False
    _audio_thread = threading.Thread(target=_audio_loop, daemon=True)
    _audio_thread.start()


def stop():
    """停止采样"""
    global _running
    _running = False


def get_peak() -> float:
    """获取当前系统音频峰值 (0.0 ~ 1.5)，非阻塞"""
    with _peak_lock:
        return _peak_value


def get_levels(bands: int = 5) -> List[float]:
    """获取多频段电平（基于峰值模拟频谱分布）"""
    peak = get_peak()
    if peak < 0.01:
        return [0.0] * bands
    levels = []
    for i in range(bands):
        ratio = i / max(1, bands - 1)
        center_dist = (ratio - 0.5) * 2
        gaussian = math.exp(-center_dist ** 2 * 0.8)
        noise = random.uniform(0.9, 1.1)
        level = peak * gaussian * noise
        levels.append(max(0.0, min(1.0, level)))
    return levels
