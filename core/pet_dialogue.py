"""桌宠气泡台词 - AI 实时生成

根据当前上下文（时间、天气、音乐状态、节日、心情）动态生成台词。
优先使用 Agnes API 生成，失败时回退到规则引擎。

使用方式：
    from core.pet_dialogue import generate_dialogue
    bubble_text = generate_dialogue(weather_data, music_state)

配置：
    设置环境变量 MOONDECK_PET_API_KEY 即可启用 Agnes AI 生成台词
    不设置则自动回退到规则引擎（基于时间/天气/节日的智能选词）
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import random
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 没有 python-dotenv 就只用环境变量

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 内置台词池（AI 失败时的回退）
# ---------------------------------------------------------------------------
_FALLBACK_LINES = {
    "greeting": [
        "主人好呀", "嗨~", "我在呢", "今天也是元气满满的一天！",
    ],
    "encouragement": [
        "加油~", "你已经很棒了！", "再坚持一下下！",
    ],
    "care": [
        "别忘了喝水", "再忙也要休息", "吃点东西吧",
        "记得活动一下肩膀哦", "多喝热水！",
    ],
    "casual": [
        "月色真美", "...", "你在忙什么呀？", "想听什么歌？",
        "今天天气不错呢", "深圳好热啊", "好无聊~", "嘻嘻",
    ],
}


# ---------------------------------------------------------------------------
# 上下文收集器
# ---------------------------------------------------------------------------
def collect_context() -> Dict[str, Any]:
    """收集当前上下文信息"""
    now = datetime.datetime.now()

    # 时间信息
    hour = now.hour
    weekday = now.weekday()  # 0=周一
    context = {
        "time": now.strftime("%H:%M"),
        "hour": hour,
        "weekday": weekday,
        "date": now.strftime("%Y-%m-%d"),
        "season": _get_season(now.month),
        "is_weekend": weekday >= 5,
        "festival": _get_festival(now),
    }

    # 时间段语义
    if 6 <= hour < 9:
        context["period"] = "morning_rush"
        context["period_desc"] = "早高峰"
    elif 9 <= hour < 12:
        context["period"] = "morning_work"
        context["period_desc"] = "上午工作"
    elif 12 <= hour < 14:
        context["period"] = "lunch"
        context["period_desc"] = "午休时间"
    elif 14 <= hour < 18:
        context["period"] = "afternoon_work"
        context["period_desc"] = "下午工作"
    elif 18 <= hour < 20:
        context["period"] = "evening"
        context["period_desc"] = "傍晚"
    elif 20 <= hour < 23:
        context["period"] = "night"
        context["period_desc"] = "夜晚"
    else:
        context["period"] = "late_night"
        context["period_desc"] = "深夜"

    return context


def _get_season(month: int) -> str:
    if month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    elif month in (9, 10, 11):
        return "autumn"
    else:
        return "winter"


def _get_festival(now: datetime.datetime) -> Optional[str]:
    """检查是否是特殊节日"""
    month_day = now.strftime("%m-%d")
    festivals = {
        "01-01": "元旦",
        "02-14": "情人节",
        "03-08": "妇女节",
        "04-01": "愚人节",
        "05-01": "劳动节",
        "06-01": "儿童节",
        "09-10": "教师节",
        "10-31": "万圣节",
        "11-11": "光棍节",
        "12-25": "圣诞节",
    }
    return festivals.get(month_day)


# ---------------------------------------------------------------------------
# 天气 + 音乐状态（调用方传入）
# ---------------------------------------------------------------------------
def _build_prompt(context: Dict[str, Any],
                  weather: Optional[Dict] = None,
                  music: Optional[Dict] = None) -> str:
    """构建 AI 提示词"""
    parts = [
        "你是小紫，一个可爱的桌面桌宠。你现在要生成一句气泡台词，语气轻松可爱，像朋友聊天一样。",
        f"当前时间：{context['time']}（{context['period_desc']}）",
        f"今天是{['周一', '周二', '周三', '周四', '周五', '周六', '周日'][context['weekday']]}，{context['season']}天",
    ]

    if context.get("festival"):
        parts.append(f"今天是{context['festival']}")

    if weather:
        w = weather.get("condition", "")
        t = weather.get("temperature", "")
        if t:
            parts.append(f"气温 {t}°C")
        if w:
            parts.append(f"天气 {w}")

    if music:
        if music.get("playing"):
            parts.append(f"正在播放：{music.get('title', '')} - {music.get('artist', '')}")
        else:
            parts.append("当前没有播放音乐")

    parts.append("\n要求：")
    parts.append("- 只生成一句台词，不超过 15 个字")
    parts.append("- 语气可爱、轻松，像一个贴心的小伙伴")
    parts.append("- 可以根据时间、天气、节日、音乐状态来生成相关内容")
    parts.append("- 不要重复，每次都要不一样")
    parts.append("- 直接输出台词内容，不要加引号，不要解释")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Agnes API 生成（OpenAI 兼容接口）
# ---------------------------------------------------------------------------
def _generate_with_agnes(prompt: str) -> Optional[str]:
    """使用 Agnes API 生成台词（带总超时保护，10 秒内未完成则回退）"""
    result = [None]
    error = [None]

    def _do_generate():
        try:
            from openai import OpenAI
        except ImportError:
            return

        api_key = os.environ.get("MOONDECK_PET_API_KEY")
        if not api_key:
            return

        try:
            client = OpenAI(
                api_key=api_key,
                base_url="https://apihub.agnes-ai.com/v1",
            )
            resp = client.chat.completions.create(
                model="agnes-2.0-flash",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=1.0,
                timeout=8,
            )
            text = resp.choices[0].message.content.strip()
            text = text.strip('"\'').strip()
            if text and 2 <= len(text) <= 30:
                result[0] = text
        except Exception as e:
            error[0] = str(e)

    thread = threading.Thread(target=_do_generate, daemon=True)
    thread.start()
    thread.join(timeout=10)

    if thread.is_alive():
        logger.warning("Agnes API 超时（>10s），使用回退台词")
    elif error[0]:
        logger.warning(f"Agnes API 生成台词失败: {error[0]}")
    elif result[0]:
        return result[0]

    return None


# ---------------------------------------------------------------------------
# 规则引擎回退（基于上下文的智能选择）
# ---------------------------------------------------------------------------
def _rule_based_generate(context: Dict[str, Any],
                         weather: Optional[Dict] = None,
                         music: Optional[Dict] = None) -> str:
    """规则引擎：根据上下文从池中挑选合适的台词"""
    pool = []

    period = context.get("period", "")
    festival = context.get("festival")
    season = context.get("season", "")

    # 时间相关
    if period == "morning_rush":
        pool.extend(["早安呀~", "早高峰加油！", "记得吃早餐哦"])
    elif period == "morning_work":
        pool.extend(["上午好~", "工作效率怎么样？", "喝杯咖啡提提神"])
    elif period == "lunch":
        pool.extend(["午饭吃了没？", "午休时间到！", "吃饱饱~"])
    elif period == "afternoon_work":
        pool.extend(["下午了，加油！", "该起来活动一下", "下午茶时间快到了"])
    elif period == "evening":
        pool.extend(["下班啦~", "今天辛苦啦", "傍晚的风好舒服"])
    elif period == "night":
        pool.extend(["晚上好呀", "今天过得怎么样？", "夜猫子模式开启"])
    elif period == "late_night":
        pool.extend(["还没睡呀...", "夜深了，早点休息", "晚安~"])
    else:
        pool.extend(_FALLBACK_LINES["casual"])

    # 节日加成
    if festival:
        holiday_lines = {
            "元旦": "新年快乐！", "情人节": "情人节快乐~", "劳动节": "劳动节快乐！",
            "儿童节": "儿童节快乐！", "教师节": "老师辛苦了！", "万圣节": "不给糖就捣蛋！",
            "光棍节": "单身快乐！", "圣诞节": "圣诞快乐~",
        }
        pool.extend(holiday_lines.get(festival, [f"{festival}快乐！"]))

    # 天气加成
    if weather:
        cond = weather.get("condition", "").lower()
        if "雨" in cond or "rain" in cond:
            pool.extend(["今天下雨啦", "记得带伞哦", "雨天适合听歌"])
        elif "晴" in cond or "sun" in cond:
            pool.extend(["今天天气真好！", "阳光好好~", "适合出去走走"])
        elif "阴" in cond or "cloud" in cond:
            pool.extend(["阴天也没关系", "多云的天气很舒服"])
        elif "雪" in cond or "snow" in cond:
            pool.extend(["下雪啦！", "好漂亮~"])

    # 音乐加成
    if music and music.get("playing"):
        pool.extend(["音乐好听吗？", "这首歌很棒~", "跟着节奏摇摆"])

    # 周末加成
    if context.get("is_weekend"):
        pool.extend(["周末愉快！", "今天放假~", "周末想做什么？"])

    # 季节加成
    if season == "summer":
        pool.extend(["好热啊~", "多喝水", "夏天就是要冰饮"])
    elif season == "winter":
        pool.extend(["好冷啊", "注意保暖", "冬天适合窝在家里"])

    # 保底
    if not pool:
        pool = _FALLBACK_LINES["casual"]

    return random.choice(pool)


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------
def generate_dialogue(weather: Optional[Dict] = None,
                      music: Optional[Dict] = None) -> str:
    """生成一句气泡台词

    Args:
        weather: 天气信息 dict，如 {"condition": "小雨", "temperature": 25}
        music: 音乐状态 dict，如 {"playing": True, "title": "xxx", "artist": "xxx"}

    Returns:
        生成的台词字符串
    """
    context = collect_context()
    prompt = _build_prompt(context, weather, music)

    # 优先尝试 AI 生成
    ai_result = _generate_with_agnes(prompt)
    if ai_result:
        logger.info(f"AI 生成台词: {ai_result}")
        return ai_result

    # 回退到规则引擎
    result = _rule_based_generate(context, weather, music)
    logger.debug(f"规则引擎台词: {result}")
    return result
