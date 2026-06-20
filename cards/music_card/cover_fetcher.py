"""Cover Fetcher - 从网易云/LrcAPI 获取专辑封面, 本地缓存

数据源优先级:
1. 本地缓存 (cache/covers/{slug}.jpg)
2. 网易云搜索 API (返回 album.picUrl)
3. LrcAPI (返回 cover 字段)
4. fallback: None (用 emoji 占位)

缓存策略:
- 文件名: slugify("{title} - {artist}.jpg")
- 路径: cache/covers/
- 永久缓存 (不主动清理)
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

# 缓存根目录
_CACHE_DIR = Path(__file__).parent.parent.parent / "cache" / "covers"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(text: str) -> str:
    """生成文件名安全的 slug (替换非法字符)"""
    # 保留中文 + 英文 + 数字 + 空格 + - _ . ( )
    safe = re.sub(r'[<>:"/\\|?*]', '', text)
    # 空格变下划线
    safe = re.sub(r'\s+', '_', safe.strip())
    # 截断
    if len(safe) > 100:
        safe = safe[:100]
    return safe or "unknown"


def _cache_path(title: str, artist: str) -> Path:
    return _CACHE_DIR / f"{_slugify(f'{title} - {artist}')}.jpg"


def _search_netease_cover(title: str, artist: str) -> Optional[str]:
    """从网易云搜索 API 获取 cover URL"""
    try:
        q = f"{title} {artist}".strip() if artist else title.strip()
        r = requests.get(
            "http://music.163.com/api/search/get",
            params={"s": q, "type": 1, "limit": 3},
            headers={"Referer": "http://music.163.com", "User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        songs = r.json().get("result", {}).get("songs", [])
        for s in songs:
            name = s.get("name", "")
            artists = s.get("artists", [])
            ar_name = artists[0]["name"] if artists else ""
            # 名字匹配 (放宽: title 在 name 里)
            if (title and (title == name or title in name or name in title)) and \
               (not artist or artist in ar_name or ar_name in artist):
                pic = s.get("album", {}).get("picUrl")
                if pic:
                    # 网易云 picUrl 强制缩小到 300x300 (够用 + 省流量)
                    return pic.replace("http://", "https://").rstrip() + "?param=300y300"
    except Exception as e:
        log.debug(f"网易云封面搜索失败: {e}")
    return None


def _search_lrcapi_cover(title: str, artist: str) -> Optional[str]:
    """从 LrcAPI 获取 cover URL"""
    try:
        r = requests.get(
            "https://api.lrc.cx/lyrics",
            params={"title": title, "artist": artist},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        if r.status_code != 200:
            return None
        ct = r.headers.get("content-type", "")
        if "json" in ct.lower():
            data = r.json()
            if isinstance(data, list) and data:
                item = data[0]
                return item.get("cover")
            elif isinstance(data, dict):
                return data.get("cover")
        # 文本响应不是 JSON, 没 cover 字段
    except Exception as e:
        log.debug(f"LrcAPI 封面搜索失败: {e}")
    return None


def fetch_cover(title: str, artist: str) -> Optional[Path]:
    """获取封面, 返回本地缓存路径 (None 表示失败)

    流程:
    1. 本地缓存命中 → 直接返回
    2. 网易云搜索 → 下载 → 缓存 → 返回
    3. LrcAPI 搜索 → 下载 → 缓存 → 返回
    4. 全部失败 → 返回 None
    """
    if not title:
        return None

    # 1. 本地缓存
    cache_p = _cache_path(title, artist)
    if cache_p.exists() and cache_p.stat().st_size > 100:
        return cache_p

    # 2. 网易云
    cover_url = _search_netease_cover(title, artist)
    if not cover_url:
        # 3. LrcAPI
        cover_url = _search_lrcapi_cover(title, artist)

    if not cover_url:
        return None

    # 下载
    try:
        r = requests.get(cover_url, timeout=10)
        r.raise_for_status()
        # 至少 1KB 算有效图片
        if len(r.content) < 1024:
            return None
        cache_p.write_bytes(r.content)
        log.info(f"封面已缓存: {title} - {artist} → {cache_p.name}")
        return cache_p
    except Exception as e:
        log.debug(f"封面下载失败: {e}")
        return None
