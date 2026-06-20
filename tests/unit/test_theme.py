"""ThemeManager 单元测试"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.theme import ThemeManager


class TestThemeManager(unittest.TestCase):
    """ThemeManager 内置主题 + 切换 + 订阅"""

    def setUp(self):
        ThemeManager.reset_instance()

    def tearDown(self):
        ThemeManager.reset_instance()

    def test_01_builtin_themes_exist(self):
        """4 个内置主题存在"""
        tm = ThemeManager()
        names = tm.themes()
        for name in ("dark", "light", "glass", "neon"):
            self.assertIn(name, names)

    def test_02_default_is_dark(self):
        """默认主题 = dark"""
        tm = ThemeManager()
        self.assertEqual(tm.current_name(), "dark")

    def test_03_get_color(self):
        """取色值"""
        tm = ThemeManager()
        bg = tm.get("background")
        self.assertEqual(bg, "#1a1a2e")

    def test_04_set_theme(self):
        """切换主题"""
        tm = ThemeManager()
        self.assertTrue(tm.set_theme("light"))
        self.assertEqual(tm.current_name(), "light")
        self.assertEqual(tm.get("background"), "#ffffff")

    def test_05_set_unknown_theme_fails(self):
        """未知主题返回 False"""
        tm = ThemeManager()
        self.assertFalse(tm.set_theme("nope"))
        self.assertEqual(tm.current_name(), "dark")  # 保持原主题

    def test_06_cycle_theme(self):
        """循环切换"""
        tm = ThemeManager()
        # 起始 dark
        self.assertEqual(tm.current_name(), "dark")
        n1 = tm.cycle_theme()
        self.assertNotEqual(n1, "dark")
        n2 = tm.cycle_theme()
        self.assertNotEqual(n2, n1)
        self.assertNotEqual(n2, "dark")

    def test_07_subscribe_notify(self):
        """订阅主题变化"""
        tm = ThemeManager()
        changes = []
        tm.subscribe(lambda name, theme: changes.append((name, theme.get("background"))))
        tm.set_theme("light")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][0], "light")
        self.assertEqual(changes[0][1], "#ffffff")

    def test_08_unsubscribe(self):
        """取消订阅"""
        tm = ThemeManager()
        changes = []
        unsub = tm.subscribe(lambda n, t: changes.append(n))
        tm.set_theme("light")
        unsub()
        tm.set_theme("dark")
        self.assertEqual(changes, ["light"])

    def test_09_load_from_yaml(self):
        """从 yaml 加载(用户主题覆盖内置)"""
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("""
themes:
  dark:
    background: "#000000"
  custom_theme:
    background: "#abcdef"
    text_primary: "#fff"
""")
            path = Path(f.name)
        try:
            tm = ThemeManager(theme_yaml_path=path)
            # dark 的 background 被覆盖
            self.assertEqual(tm.get("background"), "#000000")
            # 自定义主题存在
            self.assertIn("custom_theme", tm.themes())
        finally:
            path.unlink()

    def test_10_singleton(self):
        """单例"""
        a = ThemeManager.instance()
        b = ThemeManager.instance()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
