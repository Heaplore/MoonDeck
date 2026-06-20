"""MoonDeck 打包脚本 - PyInstaller"""
import subprocess
import sys
import os

def build():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--onefile',           # 单文件 exe
        '--windowed',          # 无控制台窗口
        '--name', 'MoonDeck',
        '--icon', 'assets/moon.ico',
        # 数据文件
        '--add-data', 'config;config',
        '--add-data', 'core;core',
        '--add-data', 'cards;cards',
        '--add-data', 'ui;ui',
        '--add-data', 'services;services',
        '--add-data', 'assets;assets',
        # 隐含导入
        '--hidden-import', 'PyQt6.QtWidgets',
        '--hidden-import', 'PyQt6.QtCore',
        '--hidden-import', 'PyQt6.QtGui',
        '--hidden-import', 'yaml',
        '--hidden-import', 'psutil',
        '--hidden-import', 'requests',
        '--hidden-import', 'apscheduler',
        '--hidden-import', 'watchdog',
        '--hidden-import', 'PIL',
        '--hidden-import', 'dateutil',
        '--hidden-import', 'pytz',
        '--hidden-import', 'cards.music_card.now_playing',
        # 入口
        'main.py',
    ]
    # 过滤 None
    cmd = [c for c in cmd if c is not None]
    
    print('🔨 开始打包 MoonDeck...')
    print(' '.join(cmd))
    result = subprocess.run(cmd, capture_output=False)
    
    if result.returncode == 0:
        print('\n✅ 打包成功! exe 位于: dist/MoonDeck.exe')
    else:
        print(f'\n❌ 打包失败, returncode={result.returncode}')
        sys.exit(1)

if __name__ == '__main__':
    build()
