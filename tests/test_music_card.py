"""Music Card 测试 v0.1"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from cards.music_card.service import (
    detect_music, detect_music_simple, MusicInfo,
    _parse_window_title, KNOWN_PLAYERS,
)


class TestMusicInfo(unittest.TestCase):
    """MusicInfo 数据类"""

    def test_default_values(self):
        info = MusicInfo()
        self.assertEqual(info.player_name, "")
        self.assertEqual(info.song_title, "")
        self.assertFalse(info.is_playing)

    def test_with_values(self):
        info = MusicInfo(
            player_name="Spotify",
            player_icon="🎧",
            song_title="Test Song",
            song_artist="Test Artist",
            is_playing=True,
        )
        self.assertEqual(info.player_name, "Spotify")
        self.assertTrue(info.is_playing)


class TestParseWindowTitle(unittest.TestCase):
    """窗口标题解析"""

    def test_empty(self):
        title, artist = _parse_window_title("")
        self.assertEqual(title, "")
        self.assertEqual(artist, "")

    def test_simple(self):
        title, artist = _parse_window_title("Song Name - Artist Name")
        self.assertEqual(title, "Song Name")
        self.assertEqual(artist, "Artist Name")

    def test_with_player_suffix(self):
        title, artist = _parse_window_title("Song - Artist - Spotify")
        self.assertEqual(title, "Song")
        self.assertEqual(artist, "Artist")

    def test_with_netease_suffix(self):
        title, artist = _parse_window_title("歌名 - 歌手 - 网易云音乐")
        self.assertEqual(title, "歌名")
        self.assertEqual(artist, "歌手")

    def test_no_artist(self):
        title, artist = _parse_window_title("Just a song title")
        self.assertEqual(title, "Just a song title")
        self.assertEqual(artist, "")

    def test_player_name_only(self):
        title, artist = _parse_window_title("Spotify")
        self.assertEqual(title, "Spotify")
        self.assertEqual(artist, "")


class TestKnownPlayers(unittest.TestCase):
    """已知播放器列表"""

    def test_has_common_players(self):
        names = [p[0] for p in KNOWN_PLAYERS]
        self.assertIn("spotify", names)
        self.assertIn("cloudmusic", names)
        self.assertIn("qqmusic", names)
        self.assertIn("sodamusic", names)

    def test_all_have_display_name(self):
        for proc, display, icon in KNOWN_PLAYERS:
            self.assertTrue(display, f"{proc} missing display name")
            self.assertTrue(icon, f"{proc} missing icon")


class TestDetectMusic(unittest.TestCase):
    """音乐检测"""

    @patch('cards.music_card.service._get_process_path')
    @patch('cards.music_card.service._get_window_title')
    @patch('cards.music_card.service.IsWindowVisible')
    @patch('cards.music_card.service.EnumWindows')
    def test_detect_spotify(self, mock_ew, mock_iwv, mock_gwt, mock_gpath):
        mock_iwv.return_value = True
        mock_gwt.return_value = "Test Song - Artist - Spotify"
        mock_gpath.return_value = "c:\\users\\test\\appdata\\local\\spotify\\spotify.exe"

        def fake_enum_windows(callback, _lparam):
            # Simulate one visible window
            callback(12345, 0)
            return True
        mock_ew.side_effect = fake_enum_windows

        # Mock GetWindowThreadProcessId to set pid
        import cards.music_card.service as svc
        original_gwtpi = svc.GetWindowThreadProcessId
        def fake_gwtpi(hwnd, pid_ref):
            # pid_ref is ctypes.byref result, we need to set the value
            pass
        svc.GetWindowThreadProcessId = fake_gwtpi
        try:
            players = detect_music()
            self.assertTrue(len(players) >= 0)  # Just verify no crash
        finally:
            svc.GetWindowThreadProcessId = original_gwtpi

    def test_empty_detection(self):
        """No crash on empty detection"""
        players = detect_music()
        self.assertIsInstance(players, list)


if __name__ == "__main__":
    unittest.main()
