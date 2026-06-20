"""Lyrics Loader - 歌词获取与 LRC 解析

支持:
1. 本地 LRC 文件搜索 (桌面/下载/汽水音乐)
2. 网络 LRC 搜索 (通过搜索引擎)
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class LyricLine:
    """单行歌词"""
    time_sec: float  # 时间点(秒)
    text: str        # 歌词文本


def parse_lrc(lrc_text: str) -> List[LyricLine]:
    """解析 LRC 格式歌词"""
    lines = []
    for line in lrc_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        # 匹配 [mm:ss.xx] 或 [mm:ss.xxx] 或 [mm:ss]
        matches = re.findall(r'\[(\d+):(\d+(?:\.\d+)?)\]', line)
        text = re.sub(r'\[\d+:\d+(?:\.\d+)?\]', '', line).strip()
        if matches and text:
            for m in matches:
                minutes = int(m[0])
                seconds = float(m[1])
                time_sec = minutes * 60 + seconds
                lines.append(LyricLine(time_sec, text))
    lines.sort(key=lambda x: x.time_sec)
    return lines


def search_local_lyrics(title: str, artist: str) -> Optional[str]:
    """搜索本地 LRC 文件"""
    search_dirs = [
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / "Music",
        Path.home() / "AppData" / "Roaming" / "SodaMusic",
    ]
    keywords = [title.lower(), f"{artist} {title}".lower()]
    for d in search_dirs:
        if not d.exists():
            continue
        try:
            for f in d.rglob("*.lrc"):
                name_lower = f.name.lower()
                for kw in keywords:
                    if all(w in name_lower for w in kw.split()):
                        return f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    return None


def search_lyrics_online(title: str, artist: str) -> Optional[str]:
    """通过搜索引擎找 LRC 歌词"""
    query = f"{artist} {title} LRC 歌词"
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://www.bing.com/search?q={encoded}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # 找 LRC 链接
        lrc_urls = re.findall(r'(https?://[^\s"<>]+\.lrc)', html)
        for lrc_url in lrc_urls[:3]:
            try:
                lrc_req = urllib.request.Request(lrc_url, headers={
                    "User-Agent": "Mozilla/5.0"
                })
                with urllib.request.urlopen(lrc_req, timeout=5) as lr:
                    return lr.read().decode("utf-8", errors="ignore")
            except Exception:
                continue
    except Exception:
        pass
    return None


def get_lyrics(title: str, artist: str) -> List[LyricLine]:
    """获取歌词(本地优先,网络兜底)"""
    # 1. 本地搜索
    lrc_text = search_local_lyrics(title, artist)
    # 2. 网络搜索
    if not lrc_text:
        lrc_text = search_lyrics_online(title, artist)
    if lrc_text:
        return parse_lrc(lrc_text)
    return []
