"""
截图 MoonDeck 真机画布 v2
- 用 QScreen.grabWindow(winId) 抓整个 Qt 顶层窗（含透明+WS_EX_LAYERED）
- 找不到就 grabWindow(0) 抓主屏
"""
import sys, os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
import win32gui

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
app = QApplication(sys.argv)

target_title = "MoonDeck 月坞"

# 1. 枚举所有顶层窗，找 MoonDeck
def find_all_hwnds(title):
    out = []
    def cb(hwnd, _):
        t = win32gui.GetWindowText(hwnd)
        if t and title in t:
            out.append((hwnd, t))
    win32gui.EnumWindows(cb, None)
    return out

hits = find_all_hwnds("MoonDeck")
print(f"[INFO] 找到 {len(hits)} 个 MoonDeck 窗: {hits}")

if not hits:
    print("[FATAL] 没找到 MoonDeck 窗")
    sys.exit(1)

# 2. 抓每个窗
from PyQt6.QtGui import QGuiApplication
screen = QGuiApplication.primaryScreen()
print(f"[INFO] 主屏 {screen.size().width()}x{screen.size().height()}")

out_dir = Path(r"C:\Users\Administrator\.easyclaw\media\outbound")
out_dir.mkdir(parents=True, exist_ok=True)

saved = []
for i, (hwnd, title) in enumerate(hits):
    try:
        pix = screen.grabWindow(hwnd)
    except Exception as e:
        print(f"[WARN] grabWindow(hwnd={hwnd}) 失败: {e}")
        continue
    if pix.isNull() or pix.width() < 10:
        print(f"[WARN] hwnd={hwnd} pix null/小，size={pix.width()}x{pix.height()}")
        continue
    out = out_dir / f"moondeck_v032_win_{i}_{hwnd}.png"
    pix.save(str(out), "PNG")
    print(f"[OK] hwnd={hwnd} title='{title}' size={pix.width()}x{pix.height()} -> {out}")
    saved.append(out)

# 3. 兜底：抓整屏作为对照
full = screen.grabWindow(0)
full_path = out_dir / "moondeck_v032_fullscreen.png"
full.save(str(full_path), "PNG")
print(f"[OK] fullscreen -> {full_path} size={full.width()}x{full.height()}")

# 4. 如果 MoonDeck 抓不到，列所有顶层窗看是什么
if not saved:
    print("\n[DEBUG] 列出所有顶层窗:")
    def cb(hwnd, _):
        t = win32gui.GetWindowText(hwnd)
        if t:
            vis = win32gui.IsWindowVisible(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            print(f"  hwnd={hwnd} vis={vis} rect={rect} title='{t}'")
    win32gui.EnumWindows(cb, None)
