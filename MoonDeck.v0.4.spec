# -*- mode: python ; coding: utf-8 -*-
# MoonDeck.spec v0.5 (Phase 5)
# 改动: 新增 pyaudiowpatch / winrt / requests / zhconv 打包支持

from PyInstaller.utils.hooks import collect_all

# 收集 winrt 整个包 (因为 SMTC 通过 winrt.windows.media.control 访问, 静态分析抓不全)
datas_winrt, binaries_winrt, hiddenimports_winrt = collect_all('winrt')
# 收集 pyaudiowpatch (包含 pyaudio + WASAPI 绑定)
datas_pyaudio, binaries_pyaudio, hiddenimports_pyaudio = collect_all('pyaudiowpatch')

a = Analysis(
    ['C:\\Users\\Administrator\\.easyclaw\\workspace\\tools\\desktop-canvas\\main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('C:\\Users\\Administrator\\.easyclaw\\workspace\\tools\\desktop-canvas\\config', 'config'),
        ('C:\\Users\\Administrator\\.easyclaw\\workspace\\tools\\desktop-canvas\\cards', 'cards'),
        ('C:\\Users\\Administrator\\.easyclaw\\workspace\\tools\\desktop-canvas\\core', 'core'),
    ] + datas_winrt + datas_pyaudio,
    hiddenimports=[
        'cards.calendar_card',
        'cards.music_card',
        'cards.note_card',
        'cards.gallery_card',
        # Phase 2: 音频 + 媒体
        'pyaudiowpatch',
        'winrt.runtime',
        'winrt.windows.media.control',
        'winrt.windows.foundation.collections',
        'winrt.windows.foundation',
        # Phase 3: 歌词
        'requests',
        'zhconv',
    ] + hiddenimports_winrt + hiddenimports_pyaudio,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'PIL.ImageQt',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MoonDeck',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
