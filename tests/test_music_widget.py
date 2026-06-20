"""Music Card Widget 渲染测试 v0.1"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

app = QApplication.instance() or QApplication(sys.argv)

from cards.music_card.widget import MusicCardWidget
from cards.music_card.service import MusicInfo


class TestMusicWidget(unittest.TestCase):
    """MusicCardWidget 基础测试"""

    def test_init(self):
        w = MusicCardWidget()
        self.assertIsNotNone(w)
        self.assertEqual(w.card_id, "music_card")

    def test_default_size(self):
        w = MusicCardWidget()
        self.assertEqual(w.default_size, (280, 180))

    def test_has_anim_timer(self):
        w = MusicCardWidget()
        self.assertIsNotNone(w._anim_timer)

    def test_update_data_no_player(self):
        w = MusicCardWidget()
        with patch('cards.music_card.widget.detect_music_simple', return_value=None):
            w.update_data()
            self.assertIsNone(w._info)

    def test_update_data_with_player(self):
        w = MusicCardWidget()
        info = MusicInfo(
            player_name="Spotify",
            player_icon="🎧",
            song_title="Test Song",
            song_artist="Test Artist",
            is_playing=True,
        )
        with patch('cards.music_card.widget.detect_music_simple', return_value=info):
            w.update_data()
            self.assertIsNotNone(w._info)
            self.assertEqual(w._info.player_name, "Spotify")

    def test_animate_playing(self):
        w = MusicCardWidget()
        w.resize(280, 160)
        info = MusicInfo(
            player_name="Spotify",
            player_icon="🎧",
            song_title="Test",
            is_playing=True,
        )
        w._info = info
        old_tick = w._tick
        w._animate()
        self.assertGreater(w._tick, old_tick)

    def test_animate_stopped(self):
        w = MusicCardWidget()
        w.resize(280, 160)
        w._info = None
        w._particles = [MagicMock()]
        w._animate()
        self.assertEqual(len(w._particles), 0)

    def test_paint_no_crash(self):
        """渲染不崩溃"""
        w = MusicCardWidget()
        w.resize(280, 180)
        w.show()
        w.repaint()
        w.hide()

    def test_paint_with_player(self):
        """有播放器时渲染不崩溃"""
        w = MusicCardWidget()
        w.resize(280, 180)
        info = MusicInfo(
            player_name="Spotify",
            player_icon="🎧",
            song_title="Long Song Name That Might Need Truncation",
            song_artist="Artist Name",
            is_playing=True,
        )
        w._info = info
        w._tick = 1.5
        w.show()
        w.repaint()
        w.hide()


if __name__ == "__main__":
    unittest.main()
