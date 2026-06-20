"""桌宠气泡台词 - AI 实时生成 + 预缓存

根据当前上下文（时间、天气、音乐状态、节日、心情）动态生成台词。
优先使用 Agnes API 生成，失败时回退到规则引擎。

预缓存机制：
    - 每隔 30 秒后台异步生成一条台词缓存
    - 桌宠点击时直接从缓存取，零延迟
    - 缓存过期后自动刷新

配置：
    设置环境变量 MOONDECK_PET_API_KEY 即可启用 Agnes AI 生成台词
    不设置则自动回退到规则引擎（基于时间/天气/节日的智能选词）
"""
from __future__ import annotations

import datetime
import logging
import os
import random
import threading
import time
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
    """使用 Agnes API 生成台词（同步，带超时）"""
    try:
        from openai import OpenAI
    except ImportError:
        logger.debug("openai 库未安装")
        return None

    api_key = os.environ.get("MOONDECK_PET_API_KEY")
    if not api_key:
        logger.debug("MOONDECK_PET_API_KEY 未设置")
        return None

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
            timeout=4,
        )
        text = resp.choices[0].message.content.strip()
        text = text.strip('"\'').strip()
        if text and 2 <= len(text) <= 30:
            return text
    except Exception as e:
        logger.warning(f"Agnes API 生成台词失败: {e}")

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
        pool.extend([
            "早安呀~", "早高峰加油！", "记得吃早餐哦",
            "周一也要元气满满", "新的一天开始啦", "路上注意安全",
            "早餐吃了没？", "今天也要好好吃饭哦",
        ])
    elif period == "morning_work":
        pool.extend([
            "上午好~", "工作效率怎么样？", "喝杯咖啡提提神",
            "上午精神不错呢", "继续加油", "累了就伸个懒腰",
            "上午的時光最適合專注了",
        ])
    elif period == "lunch":
        pool.extend([
            "午饭吃了没？", "午休时间到！", "吃饱饱~",
            "中午记得午睡一会儿", "今天吃什么好？",
            "午餐时间，犒劳一下自己",
        ])
    elif period == "afternoon_work":
        pool.extend([
            "下午了，加油！", "该起来活动一下", "下午茶时间快到了",
            "下午容易犯困呢", "喝口水歇会儿", "坚持一下就下班啦",
            "午后时光，适合喝杯茶",
        ])
    elif period == "evening":
        pool.extend([
            "下班啦~", "今天辛苦啦", "傍晚的风好舒服",
            "晚上打算做点什么？", "辛苦一天啦",
            "夕阳很美呢", "回家路上注意安全",
        ])
    elif period == "night":
        pool.extend([
            "晚上好呀", "今天过得怎么样？", "夜猫子模式开启",
            "晚上适合放松一下", "今天累不累？",
            "夜深了，享受属于自己的时光",
        ])
    elif period == "late_night":
        pool.extend([
            "还没睡呀...", "夜深了，早点休息", "晚安~",
            "凌晨了，身体要紧", "快去睡觉！",
            "这么晚还不睡，明天起得来吗？",
        ])
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
        pool.extend([
            "好热啊~", "多喝水", "夏天就是要冰饮",
            "今天出门要注意防晒哦", "夏天最适合吃西瓜了",
            "空调续命！", "夏日炎炎，心静自然凉",
        ])
    elif season == "winter":
        pool.extend([
            "好冷啊", "注意保暖", "冬天适合窝在家里",
            "冬天记得穿秋裤", "喝杯热茶暖暖身子",
            "冬天就要吃火锅！", "天冷多穿点",
        ])
    elif season == "spring":
        pool.extend([
            "春天来了呢", "花开得好漂亮", "春天适合出去踏青",
            "春风很舒服", "春天容易犯困哦",
        ])
    else:  # autumn
        pool.extend([
            "秋天到了", "秋高气爽", "秋天最适合散步",
            "秋天要注意补水", "落叶好美",
        ])

    # 保底
    if not pool:
        pool = _FALLBACK_LINES["casual"]

    return random.choice(pool)


# ---------------------------------------------------------------------------
# 预缓存管理器
# ---------------------------------------------------------------------------
class _DialogueCache:
    """台词预缓存：后台异步生成，前台零延迟读取"""

    def __init__(self, refresh_interval: int = 30):
        self._cached_text: Optional[str] = None
        self._weather: Optional[Dict] = None
        self._music: Optional[Dict] = None
        self._last_refresh: float = 0
        self._refresh_interval = refresh_interval
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        logger.info("台词预缓存管理器已初始化")

    def start(self) -> None:
        """启动后台刷新线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止后台刷新线程"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def set_context(self, weather: Optional[Dict] = None,
                    music: Optional[Dict] = None) -> None:
        """更新天气和音乐状态，触发重新生成"""
        with self._lock:
            self._weather = weather
            self._music = music
            self._last_refresh = 0  # 强制刷新

    def get_cached(self) -> Optional[str]:
        """获取缓存的台词（零延迟）"""
        with self._lock:
            return self._cached_text

    def _refresh_loop(self) -> None:
        """后台刷新循环"""
        while self._running:
            time.sleep(2)  # 初始等待
            self._try_refresh()

    def _try_refresh(self) -> None:
        """尝试刷新缓存"""
        with self._lock:
            now = time.time()
            if now - self._last_refresh < self._refresh_interval:
                return

        # 异步生成（不在锁内，避免阻塞）
        context = collect_context()
        prompt = _build_prompt(context, self._weather, self._music)

        # 先试 Agnes API（用线程 + 超时，不阻塞主循环太久）
        result = [None]
        error = [None]
        prev_text = self.get_cached()  # 获取上一条，用于去重

        def _gen():
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
                    timeout=4,
                )
                text = resp.choices[0].message.content.strip()
                text = text.strip('"\'').strip()
                if text and 2 <= len(text) <= 30 and text != prev_text:
                    result[0] = text
            except Exception as e:
                error[0] = str(e)

        t = threading.Thread(target=_gen, daemon=True)
        t.start()
        t.join(timeout=3)

        if t.is_alive():
            logger.debug("Agnes API 后台刷新超时，使用规则引擎")
            # 超时后用规则引擎兜底（去重）
            for _ in range(5):
                candidate = _rule_based_generate(context, self._weather, self._music)
                if candidate != prev_text:
                    result[0] = candidate
                    break
            if not result[0]:
                result[0] = prev_text  # 保底
        elif error[0]:
            logger.debug(f"Agnes API 后台刷新失败: {error[0]}, 使用规则引擎")
            for _ in range(5):
                candidate = _rule_based_generate(context, self._weather, self._music)
                if candidate != prev_text:
                    result[0] = candidate
                    break
            if not result[0]:
                result[0] = prev_text

        # 写入缓存
        with self._lock:
            self._cached_text = result[0]
            self._last_refresh = time.time()
            if result[0]:
                logger.info(f"台词缓存已更新: {result[0]}")


# 全局单例
_dialogue_cache = _DialogueCache(refresh_interval=30)


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------
def generate_dialogue(weather: Optional[Dict] = None,
                      music: Optional[Dict] = None) -> str:
    """生成一句气泡台词（优先从缓存取，零延迟）

    Args:
        weather: 天气信息 dict，如 {"condition": "小雨", "temperature": 25}
        music: 音乐状态 dict，如 {"playing": True, "title": "xxx", "artist": "xxx"}

    Returns:
        生成的台词字符串
    """
    # 更新上下文
    _dialogue_cache.set_context(weather, music)

    # 先试缓存
    cached = _dialogue_cache.get_cached()
    if cached:
        return cached

    # 缓存未就绪，直接用规则引擎兜底（零等待）
    # Agnes API 会在后台线程异步刷新缓存，下次点击就有 AI 台词了
    context = collect_context()
    result = _rule_based_generate(context, weather, music)
    logger.debug(f"缓存未命中，规则引擎兜底: {result}")
    return result


def start_cache() -> None:
    """启动台词预缓存后台线程（应用启动时调用一次）"""
    _dialogue_cache.start()


def stop_cache() -> None:
    """停止台词预缓存（应用退出时调用）"""
    _dialogue_cache.stop()
