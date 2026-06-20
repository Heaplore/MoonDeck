"""StorageManager 单元测试"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.storage import StorageManager


class TestStorageManager(unittest.TestCase):
    """SQLite 布局/通用 KV 持久化"""

    def setUp(self):
        """每个测试用独立临时 DB"""
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_path = Path(self._tmp.name)
        self.storage = StorageManager(db_path=self.db_path)

    def tearDown(self):
        self.storage.close()
        if self.db_path.exists():
            self.db_path.unlink()
        StorageManager.reset_instance()

    def test_01_save_load_layout(self):
        """保存/加载布局"""
        self.storage.save_layout("card_a", 100, 200, 300, 400, visible=True)
        data = self.storage.load_layout("card_a")
        self.assertIsNotNone(data)
        self.assertEqual(data["x"], 100)
        self.assertEqual(data["y"], 200)
        self.assertEqual(data["w"], 300)
        self.assertEqual(data["h"], 400)
        self.assertTrue(data["visible"])

    def test_02_update_layout(self):
        """更新布局(upsert)"""
        self.storage.save_layout("card_a", 100, 200, 300, 400)
        self.storage.save_layout("card_a", 150, 250, 350, 450)
        data = self.storage.load_layout("card_a")
        self.assertEqual(data["x"], 150)
        self.assertEqual(data["y"], 250)
        self.assertEqual(data["w"], 350)
        self.assertEqual(data["h"], 450)

    def test_03_load_nonexistent(self):
        """不存在的 card_id 返回 None"""
        data = self.storage.load_layout("nope")
        self.assertIsNone(data)

    def test_04_load_all(self):
        """加载所有布局"""
        self.storage.save_layout("a", 1, 1, 1, 1)
        self.storage.save_layout("b", 2, 2, 2, 2)
        all_data = self.storage.load_all_layouts()
        ids = {d["card_id"] for d in all_data}
        self.assertEqual(ids, {"a", "b"})

    def test_05_delete_layout(self):
        """删除布局"""
        self.storage.save_layout("a", 1, 1, 1, 1)
        self.storage.delete_layout("a")
        self.assertIsNone(self.storage.load_layout("a"))

    def test_06_kv_string(self):
        """KV 存字符串"""
        self.storage.set_kv("theme", "dark")
        self.assertEqual(self.storage.get_kv("theme"), "dark")

    def test_07_kv_dict_auto_json(self):
        """KV 存 dict 自动 json 序列化"""
        self.storage.set_kv("user", {"name": "老大", "age": 30})
        self.assertEqual(self.storage.get_kv("user"), {"name": "老大", "age": 30})

    def test_08_kv_default(self):
        """KV 不存在时返回 default"""
        self.assertIsNone(self.storage.get_kv("nope"))
        self.assertEqual(self.storage.get_kv("nope", "default"), "default")

    def test_09_visible_flag(self):
        """visible 标记"""
        self.storage.save_layout("a", 1, 1, 1, 1, visible=False)
        data = self.storage.load_layout("a")
        self.assertFalse(data["visible"])

    def test_10_persistence_across_instances(self):
        """关闭重开后数据还在(真正持久化)"""
        self.storage.save_layout("a", 100, 200, 300, 400)
        self.storage.close()
        # 新实例指向同一文件
        new_storage = StorageManager(db_path=self.db_path)
        data = new_storage.load_layout("a")
        self.assertEqual(data["x"], 100)
        new_storage.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
