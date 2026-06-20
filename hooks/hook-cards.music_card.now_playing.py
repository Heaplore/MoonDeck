"""PyInstaller hook to force-include now_playing module."""
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('cards.music_card.now_playing')
