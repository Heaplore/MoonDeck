"""MoonDeck 全局事件总线

基于 Qt Signal/Slot 的单例事件总线。
任何模块都可以 emit/subscribe,不依赖彼此引用。

使用示例:
    bus = EventBus.instance()
    bus.emit("card:token:recharge", {"amount": 100})

    def on_recharge(payload):
        print(f"收到充值请求: {payload}")
    bus.subscribe("card:token:recharge", on_recharge)

事件命名规范:
    - card:<card_id>:<action>     卡片主动发的事件
    - system:<action>             系统事件
    - user:<action>               用户操作事件
    - service:<svc>:<event>       服务层事件
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List

from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    """全局事件总线(Qt Signal 实现)

    单例模式(全局唯一):
        bus = EventBus.instance()
    """

    # 全局事件 signal:event_name, payload
    event = pyqtSignal(str, object)

    _instance: "EventBus | None" = None
    _lock = threading.Lock()

    def __init__(self):
        super().__init__()
        # 订阅表:{event_name: [callback, ...]}
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        # 用一个统一的 dispatcher 连接 signal → 路由到订阅者
        self.event.connect(self._dispatch)
        # 调试用:事件历史(最近 100 条)
        self._history: List[tuple[str, Any]] = []
        self._max_history = 100

    @classmethod
    def instance(cls) -> "EventBus":
        """获取单例(线程安全)"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = EventBus()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例(仅测试用)"""
        with cls._lock:
            cls._instance = None

    def _dispatch(self, event_name: str, payload: Any) -> None:
        """signal 槽:分发到具体订阅者"""
        # 记录历史
        self._history.append((event_name, payload))
        if len(self._history) > self._max_history:
            self._history.pop(0)
        # 派发
        callbacks = self._subscribers.get(event_name, [])
        for cb in callbacks:
            try:
                cb(payload)
            except Exception as e:
                # 不让一个订阅者崩溃影响其他订阅者
                # 真实项目用 logging
                import traceback
                print(f"[EventBus] 订阅者 {cb.__name__} 处理 {event_name} 失败: {e}")
                traceback.print_exc()

    def emit(self, event_name: str, payload: Any = None) -> None:
        """发送事件

        Args:
            event_name: 事件名(如 "card:token:recharge")
            payload: 任意可序列化对象(dict/str/int/自定义)
        """
        self.event.emit(event_name, payload)

    def subscribe(self, event_name: str, callback: Callable[[Any], None]) -> Callable[[], None]:
        """订阅事件

        Args:
            event_name: 事件名
            callback: 回调函数,签名 callback(payload)

        Returns:
            unsubscribe 函数(调用即可取消订阅)
        """
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(callback)

        def _unsubscribe():
            try:
                self._subscribers[event_name].remove(callback)
            except (KeyError, ValueError):
                pass
        return _unsubscribe

    def subscriber_count(self, event_name: str) -> int:
        """获取某事件的订阅者数(测试用)"""
        return len(self._subscribers.get(event_name, []))

    def history(self) -> List[tuple[str, Any]]:
        """获取事件历史(测试/调试用)"""
        return list(self._history)

    def clear_history(self) -> None:
        """清空历史(测试用)"""
        self._history.clear()
