"""Pytest 配置:确保 widget 测试有 QApplication 实例

PyQt6 在没有 QApplication 时构造 QWidget 会直接段错误(0xC0000409)
必须在所有 widget 测试前先有 QApplication。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 强制 offscreen 平台
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 注入根路径
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 老测试有 from _fake_card import ... 需要 tests/unit 在路径上
TESTS_DIR = Path(__file__).parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """session 级 QApplication(单例)"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # 不 quit,让 pytest 清理
