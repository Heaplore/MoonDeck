"""Weather Card - 数据源服务

wttr.in (WorldWeatherOnline 公益前端,免 key 免注册)
- 实况 + 3 天预报:一次调用 /?format=j1&lang=zh 全返回
- 城市:支持 ?q=Shenzhen 中文/英文,自动 IP 定位兜底
- 缓存:30 分钟(避免浪费免费额度)
- 失败 fallback:返回 last_known 数据,UI 显示 stale 标记
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

_LOG = logging.getLogger("moondeck.weather")

# 全局天气数据缓存（供桌宠台词生成使用）
_current_weather: Optional[Dict] = None

# ============== 配置 ==============
_HOST = "https://wttr.in"
_CITY = "Shenzhen"  # 硬编码深圳(老大位置),后续支持 IP 自动定位
_TIMEOUT_S = 8  # wttr.in 偶尔慢(公益服务),多给点时间
_CACHE_FILE = Path(__file__).parent.parent.parent / "cache" / "weather_cache.json"


# ============== WWO 天气代码 → emoji + 文案 ==============
# WorldWeatherOnline weatherCode (wttr.in 后端数据源)
# https://developer.worldweatheronline.com/docs/weather-icons
_ICON_MAP: Dict[int, tuple] = {
    113: ("☀️", "晴"),
    116: ("⛅", "多云"),
    119: ("☁️", "阴"),
    122: ("☁️", "阴"),
    143: ("🌫️", "雾"),
    176: ("🌦️", "阵雨"),
    179: ("🌨️", "阵雪"),
    182: ("🌨️", "阵雪"),
    185: ("🌨️", "阵雪"),
    200: ("⛈️", "雷雨"),
    227: ("❄️", "雪"),
    230: ("❄️", "雪"),
    248: ("🌫️", "雾"),
    260: ("🌫️", "浓雾"),
    263: ("🌧️", "小雨"),
    266: ("🌧️", "小雨"),
    281: ("🌧️", "冻雨"),
    284: ("🌧️", "冻雨"),
    293: ("🌧️", "阵雨"),
    296: ("🌧️", "小雨"),
    299: ("🌧️", "阵雨"),
    302: ("🌧️", "中雨"),
    305: ("🌧️", "小雨"),
    308: ("🌧️", "暴雨"),
    311: ("🌧️", "冻雨"),
    314: ("🌧️", "冻雨"),
    317: ("🌧️", "冻雨"),
    320: ("🌨️", "小雪"),
    323: ("🌨️", "小雪"),
    326: ("🌨️", "阵雪"),
    329: ("❄️", "中雪"),
    332: ("❄️", "中雪"),
    335: ("❄️", "阵雪"),
    338: ("❄️", "大雪"),
    350: ("❄️", "冰雹"),
    353: ("🌦️", "阵雨"),
    356: ("🌧️", "中雨"),
    359: ("🌧️", "暴雨"),
    362: ("🌦️", "阵雨"),
    365: ("🌧️", "中雨"),
    368: ("🌨️", "阵雪"),
    371: ("🌨️", "阵雪"),
    374: ("🌨️", "冰雹"),
    377: ("🌨️", "中雪"),
    386: ("⛈️", "雷阵雨"),
    389: ("⛈️", "强雷阵雨"),
    392: ("🌨️", "阵雪"),
    395: ("❄️", "中雪"),
}


def _icon(code) -> str:
    try:
        return _ICON_MAP.get(int(code), ("❓", "未知"))[0]
    except (ValueError, TypeError):
        return "❓"


def _text(code) -> str:
    try:
        return _ICON_MAP.get(int(code), ("❓", "未知"))[1]
    except (ValueError, TypeError):
        return "未知"


# ============== WeatherData ==============


class WeatherData:
    """UI 友好的扁平数据结构"""

    def __init__(self):
        self.success: bool = False
        self.error: Optional[str] = None

        # 实况
        self.now_temp: str = "--"
        self.now_feels: str = "--"
        self.now_text: str = "加载中"
        self.now_icon: str = "❓"
        self.now_humidity: str = "--"
        self.now_wind: str = "--"
        self.now_wind_scale: str = "--"
        self.now_uv: str = "--"
        self.now_pressure: str = "--"
        self.now_visibility: str = "--"
        self.now_obs_time: str = "--:--"
        # v0.3 新增:PM2.5(wttr.in 不提供,设占位)
        self.now_pm25: str = "--"

        # 城市
        self.city: str = "深圳"

        # 3-5 天预报(从 today + next 4)
        self.daily: list = []  # [{fxDate, icon, iconDay, text, tempMin, tempMax}, ...]
        # icon = emoji 字符, iconDay = 原始文字类型(widget 按文字判断绘制什么)

        # 缓存时间
        self.fetched_at: str = ""

        # 缓存命中标记(新 fetch 才会是 False)
        self.is_stale: bool = False


# ============== WeatherService ==============


class WeatherService(QObject):
    """天气数据源服务(单 widget 绑定)

    30 分钟拉一次(可配),失败 fallback 到磁盘缓存 + UI 显示 stale 标记。
    """

    data_ready = pyqtSignal(object)  # 携带 WeatherData

    def __init__(self, widget=None, interval_ms: int = 30 * 60 * 1000):
        super().__init__()
        self._widget = widget
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._refresh)
        self._data = WeatherData()

    def start(self):
        """启动定时刷新 + 立即拉一次"""
        self._timer.start()
        self._refresh()

    def stop(self):
        self._timer.stop()

    def _refresh(self):
        """拉数据(同步,简单可靠)"""
        try:
            payload = self._fetch_all()
            data = self._parse(payload)
            # 写磁盘缓存
            self._save_cache(data)
            self._data = data
            # 更新全局缓存（供桌宠使用）
            global _current_weather
            _current_weather = {
                "condition": data.now_text,
                "temperature": data.now_temp,
            }
        except Exception as e:
            _LOG.warning(f"wttr.in 拉取失败: {e},回退到磁盘缓存")
            cached = self._load_cache()
            if cached is not None:
                self._data = cached
                self._data.is_stale = True
            else:
                d = WeatherData()
                d.error = str(e)
                d.now_text = "无数据"
                self._data = d
        # 通知 widget
        self.data_ready.emit(self._data)

    # ============== HTTP ==============

    def _http_get_json(self, url: str) -> Dict[str, Any]:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "curl/7.88.1")  # wttr.in 对 curl UA 更友好
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
            raw = r.read().decode("utf-8")
        return json.loads(raw)

    def _fetch_all(self) -> Dict[str, Any]:
        """一次拿实况 + 3 天预报"""
        url = f"{_HOST}/{_CITY}?format=j1&lang=zh"
        return self._http_get_json(url)

    # ============== 解析 ==============

    def _parse(self, payload: Dict[str, Any]) -> WeatherData:
        d = WeatherData()
        d.success = True
        d.fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        d.city = "深圳"  # wttr.in nearest_area 可能不准,先固定

        # 实况
        cur_list = payload.get("current_condition", [])
        if cur_list:
            cur = cur_list[0]
            d.now_temp = cur.get("temp_C", "--")
            d.now_feels = cur.get("FeelsLikeC", "--")
            code = cur.get("weatherCode", "999")
            d.now_icon = _icon(code)
            d.now_text = _text(code)
            d.now_humidity = cur.get("humidity", "--")
            d.now_wind = cur.get("winddir16Point", "--")
            d.now_wind_scale = cur.get("windspeedKmph", "--")
            d.now_uv = cur.get("uvIndex", "--")
            d.now_pressure = cur.get("pressure", "--")
            d.now_visibility = cur.get("visibility", "--")
            d.now_obs_time = (cur.get("observation_time", "") or "")[:5] or "--:--"

        # 5 天预报(weather[0..4] = 今天 + 后 4 天)
        daily_list = payload.get("weather", [])
        for day in daily_list[:5]:
            mid_hour = day.get("hourly", [{}])[4] if len(day.get("hourly", [])) > 4 else {}
            wcode = mid_hour.get("weatherCode", "999")
            d.daily.append({
                "fxDate": day.get("date", ""),
                "icon": _icon(wcode),
                "iconDay": _text(wcode),  # 文字类型(widget 用来判断绘制什么)
                "text": _text(wcode),
                "tempMin": day.get("mintempC", "--"),
                "tempMax": day.get("maxtempC", "--"),
            })

        return d

    # ============== 磁盘缓存 ==============

    def _save_cache(self, data: WeatherData):
        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            obj = {
                "success": data.success,
                "now_temp": data.now_temp,
                "now_feels": data.now_feels,
                "now_text": data.now_text,
                "now_icon": data.now_icon,
                "now_humidity": data.now_humidity,
                "now_wind": data.now_wind,
                "now_wind_scale": data.now_wind_scale,
                "now_uv": data.now_uv,
                "now_pressure": data.now_pressure,
                "now_visibility": data.now_visibility,
                "now_obs_time": data.now_obs_time,
                "now_pm25": getattr(data, "now_pm25", "--"),
                "city": data.city,
                "daily": data.daily,
                "fetched_at": data.fetched_at,
            }
            _CACHE_FILE.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            _LOG.debug(f"写天气缓存失败: {e}")

    def _load_cache(self) -> Optional[WeatherData]:
        if not _CACHE_FILE.exists():
            return None
        try:
            obj = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            d = WeatherData()
            for k, v in obj.items():
                if hasattr(d, k):
                    setattr(d, k, v)
            d.success = True  # 缓存视为成功(只标 stale)
            return d
        except Exception as e:
            _LOG.debug(f"读天气缓存失败: {e}")
            return None
