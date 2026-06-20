"""Lyrics Loader - 歌词获取 v0.3 (Phase 3)

策略: 3 层降级
  1. 网易云 API (music.163.com) - 老 PyQt5 标杆版主力
  2. LrcAPI 公共聚合 (api.lrc.cx/lyrics) - 网易云拿不到的兜底
  3. 失败 -> 返回空列表

辅助:
  - 内存缓存 (避免重复请求)
  - 繁体转简体 (zhconv)
  - LRC 解析 (沿用 PyQt5 标杆版正则)

接口 (与 v0.2 兼容):
  - LyricLine dataclass: time_sec, text
  - parse_lrc(text) -> List[LyricLine]
  - get_lyrics(title, artist) -> List[LyricLine]

新增:
  - clear_cache() - 清空缓存
  - get_lyrics_with_source(title, artist) -> tuple[List[LyricLine], str] - 返回 (歌词, 来源标签)
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List, Optional, Tuple

import requests

try:
    import zhconv
    _HAS_ZHCONV = True
except ImportError:
    _HAS_ZHCONV = False

log = logging.getLogger("lyrics_loader")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class LyricLine:
    """单行歌词"""
    time_sec: float
    text: str


# ---------------------------------------------------------------------------
# LRC 解析 (PyQt5 标杆版同款正则)
# ---------------------------------------------------------------------------
def parse_lrc(lrc_text: str) -> List[LyricLine]:
    """解析 LRC 格式歌词"""
    lines: List[LyricLine] = []
    if not lrc_text:
        return lines
    for line in lrc_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 匹配 [mm:ss.xx] 或 [mm:ss.xxx] 或 [mm:ss]
        matches = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", line)
        text = re.sub(r"\[\d+:\d+(?:\.\d+)?\]", "", line).strip()
        if not matches or not text:
            continue
        for m in matches:
            minutes = int(m[0])
            seconds = float(m[1])
            time_sec = minutes * 60 + seconds
            lines.append(LyricLine(time_sec, text))
    lines.sort(key=lambda x: x.time_sec)
    return lines


def to_simplified(text: str) -> str:
    """繁体转简体 (zhconv 不可用时跳过)"""
    if not text or not _HAS_ZHCONV:
        return text
    try:
        return zhconv.convert(text, "zh-cn")
    except Exception:
        return text


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------
_cache: dict[str, List[LyricLine]] = {}
_cache_meta: dict[str, str] = {}  # key -> source label


def _cache_key(title: str, artist: str) -> str:
    return f"{title.strip().lower()}|{artist.strip().lower()}"


def clear_cache() -> None:
    """清空内存缓存"""
    global _cache, _cache_meta
    _cache.clear()
    _cache_meta.clear()


# ---------------------------------------------------------------------------
# Level 1: 网易云 API
# ---------------------------------------------------------------------------
_NETEASE_SEARCH = "http://music.163.com/api/search/get"
_NETEASE_LYRIC = "http://music.163.com/api/song/lyric"
_NETEASE_HEADERS = {
    "Referer": "http://music.163.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _search_netease(title: str, artist: str) -> Optional[int]:
    """搜网易云, 返回最匹配 song_id"""
    q = f"{title} {artist}".strip() if artist else title.strip()
    try:
        r = requests.get(
            _NETEASE_SEARCH,
            params={"s": q, "type": 1, "limit": 5},
            headers=_NETEASE_HEADERS,
            timeout=5,
        )
        songs = r.json().get("result", {}).get("songs", [])
        if not songs:
            return None
        # 简单匹配: title + artist 都匹配
        title_l = title.strip().lower()
        artist_l = artist.strip().lower()
        for s in songs:
            if (s.get("name", "").lower() == title_l or
                    title_l in s.get("name", "").lower()):
                if not artist_l or artist_l in s["artists"][0]["name"].lower():
                    return s["id"]
        # 退化: 用第一个
        return songs[0]["id"]
    except Exception as e:
        log.debug(f"网易云搜索失败: {e}")
        return None


def _fetch_netease_lyric(song_id: int) -> Optional[str]:
    """拉网易云歌词 LRC 文本"""
    try:
        r = requests.get(
            _NETEASE_LYRIC,
            params={"id": song_id, "lv": 1, "tv": -1},
            headers=_NETEASE_HEADERS,
            timeout=5,
        )
        lrc = r.json().get("lrc", {}).get("lyric", "")
        return lrc if lrc else None
    except Exception as e:
        log.debug(f"网易云歌词拉取失败: {e}")
        return None


def fetch_netease(title: str, artist: str) -> Optional[List[LyricLine]]:
    """网易云获取歌词 (返回 None 表示没拿到)"""
    sid = _search_netease(title, artist)
    if not sid:
        return None
    lrc = _fetch_netease_lyric(sid)
    if not lrc:
        return None
    lines = parse_lrc(lrc)
    return lines if lines else None


# ---------------------------------------------------------------------------
# Level 2: LrcAPI 公共聚合 (api.lrc.cx/lyrics)
# ---------------------------------------------------------------------------
_LRCAPI_URL = "https://api.lrc.cx/lyrics"


def fetch_lrcapi(title: str, artist: str) -> Optional[List[LyricLine]]:
    """LrcAPI 公共聚合获取歌词 (返回 None 表示没拿到)"""
    try:
        r = requests.get(
            _LRCAPI_URL,
            params={"title": title, "artist": artist},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        lrc_text = r.text
        if not lrc_text or not lrc_text.strip():
            return None
        # LrcAPI 直接返回 LRC 文本 (含时间戳), 不需要二次解析
        # 但有时返回 JSON, 看 Content-Type
        ct = r.headers.get("content-type", "")
        if "json" in ct.lower():
            # 解析 JSON 拿 lrc 字段
            try:
                data = r.json()
                # LrcAPI JSON 格式: 数组里含 lrc_ttml / lrc 字段
                if isinstance(data, list) and data:
                    item = data[0]
                    lrc_text = item.get("lrc") or item.get("lrc_ttml") or ""
                elif isinstance(data, dict):
                    lrc_text = data.get("lrc") or data.get("lyric") or ""
            except Exception:
                return None
            if not lrc_text:
                return None
        # 简体化
        lrc_text = to_simplified(lrc_text)
        lines = parse_lrc(lrc_text)
        return lines if lines else None
    except Exception as e:
        log.debug(f"LrcAPI 失败: {e}")
        return None


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------
def get_lyrics(title: str, artist: str) -> List[LyricLine]:
    """获取歌词 (3 层降级: 网易云 → LrcAPI → 失败)

    Returns:
        List[LyricLine] - 解析后的歌词 (空列表表示没拿到)
    """
    if not title:
        return []
    key = _cache_key(title, artist)
    if key in _cache:
        return _cache[key]

    # Level 1: 网易云
    log.info(f"歌词查询: {title} - {artist}")
    lines = fetch_netease(title, artist)
    if lines:
        log.info(f"  ✅ 网易云命中 ({len(lines)} 行)")
        _cache[key] = lines
        _cache_meta[key] = "netease"
        return lines
    log.info(f"  ⚠️ 网易云未命中, 试 LrcAPI ...")

    # Level 2: LrcAPI
    lines = fetch_lrcapi(title, artist)
    if lines:
        log.info(f"  ✅ LrcAPI 命中 ({len(lines)} 行)")
        _cache[key] = lines
        _cache_meta[key] = "lrcapi"
        return lines
    log.info(f"  ❌ 全部失败, 返回空")

    _cache[key] = []
    _cache_meta[key] = "none"
    return []


def get_lyrics_with_source(title: str, artist: str) -> Tuple[List[LyricLine], str]:
    """获取歌词 + 返回来源标签 (netease / lrcapi / none)"""
    lines = get_lyrics(title, artist)
    key = _cache_key(title, artist)
    return lines, _cache_meta.get(key, "none")


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

    tests = [
        ("爱殇", "小时姑娘"),
        ("晴天", "周杰伦"),
        ("稻香", "周杰伦"),
        ("起风了", "买辣椒也用券"),
        ("孤勇者", "陈奕迅"),
        ("漠河舞厅", "柳爽"),
        ("海底", "一支榴莲"),
        ("平凡之路", "朴树"),
        ("七里香", "周杰伦"),
        ("慢慢喜欢你", "莫文蔚"),
    ]

    print()
    print("=" * 60)
    print(f"📝 歌词命中率测试 ({len(tests)} 首)")
    print("=" * 60)

    stats = {"netease": 0, "lrcapi": 0, "none": 0}
    for title, artist in tests:
        lines, source = get_lyrics_with_source(title, artist)
        stats[source] = stats.get(source, 0) + 1
        if lines:
            print(f"  ✅ [{source:7s}] {title} - {artist}  ({len(lines)} 行)")
            print(f"     头 3 行:")
            for ln in lines[:3]:
                print(f"       [{int(ln.time_sec//60):02d}:{ln.time_sec%60:05.2f}] {ln.text}")
        else:
            print(f"  ❌ [{source:7s}] {title} - {artist}")

    print()
    print("=" * 60)
    print("📊 统计")
    print("=" * 60)
    total = len(tests)
    netease_n = stats["netease"]
    lrcapi_n = stats["lrcapi"]
    none_n = stats["none"]
    hit = netease_n + lrcapi_n
    print(f"  网易云命中:   {netease_n}/{total} ({netease_n/total*100:.0f}%)")
    print(f"  LrcAPI 命中:  {lrcapi_n}/{total} ({lrcapi_n/total*100:.0f}%)")
    print(f"  总命中率:     {hit}/{total} ({hit/total*100:.0f}%)")
    print(f"  失败:         {none_n}/{total}")
