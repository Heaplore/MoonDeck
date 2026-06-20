# 馃寵 MoonDeck 鏈堝潪

> **Windows 妗岄潰娴獥鍗＄墖绯荤粺** 鈥斺€?閫忔槑鐢诲竷 + 鏈堝巻 + 闊充箰 + 妗岄潰瀹犵墿 + 绮掑瓙鍔ㄦ晥

![Python](https://img.shields.io/badge/python-%E2%89%A53.11-green)
![PyQt](https://img.shields.io/badge/gui-PyQt6-blue)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2B-lightgrey)

---

## 杩欐槸浠€涔?
MoonDeck 涓嶆槸浼犵粺 APP锛屽畠鏄竴涓?*閫忔槑鐨勬闈㈢敾甯?*锛岄摵婊℃暣涓睆骞曪紙鐪嬭捣鏉ヤ笉瀛樺湪锛夛紝涓婇潰鍙互鏀句换鎰忔暟閲忕殑娴獥鍗＄墖銆?
## 宸插疄鐜?
| # | 缁勪欢 | 璇存槑 |
|---|------|------|
| 1 | 馃棑锔?**鏈堝巻鍗?* | 鍐滃巻 + 椋炰功鏃ョ▼ + Token 棰濆害 + 澶╂皵闆嗘垚 + 搴曢儴闊充箰鍖哄煙 |
| 2 | 馃幍 **闊充箰鍗?* | 鐙珛闊充箰鍗＄墖锛歐ASAPI 棰戣氨寰嬪姩 + SMTC 鍏冩暟鎹?+ 姝岃瘝婊氬姩 + 鎾斁鎺у埗 |
| 3 | 馃寣 **妗岄潰鑳屾櫙鍔ㄦ晥** | 绮掑瓙鏄熶簯 / 鏄熺┖ / 鍑犱綍鏇奸檧缃楋紝70 绮掑瓙闅忛煶涔愬緥鍔?|
| 4 | 馃挰 **姝岃瘝鍔ㄦ晥** | 椋樺瓧娴?/ 绮掑瓙瀛椾袱绉嶆ā寮?|
| 5 | 馃惥 **灏忕传妗屽疇** | 8 瑙掕壊鍒囨崲 + 姘旀场鍙拌瘝 + 鎷栨嫿璺熼殢 |
| 6 | 馃帹 **涓婚鍒囨崲** | 娣辫壊 / 娴呰壊 / 姣涚幓鐠?/ 闇撹櫣锛? 濂椾富棰?|
| 7 | 鈱笍 **蹇嵎閿郴缁?* | Alt 鍞よ捣浜や簰 / Ctrl+Alt+T 鍒囨崲涓婚 / 鑳屾櫙/妗屽疇/姝岃瘝鍔ㄦ晥鍒囨崲 |
| 8 | 馃搵 **绯荤粺鎵樼洏** | 鍙抽敭鑿滃崟锛氬叏鏄?鍏ㄩ殣/鍗曞崱鏄鹃殣/涓婚鍒囨崲/鍔ㄦ晥鍒囨崲/閫€鍑?|

## 鏍稿績鐗规€?
### 鏋佽嚧閫忔槑
- 鐢诲竷**姘歌繙涓嶆姠鐒︾偣**
- 榛樿榧犳爣鍙互"绌胯繃"鍗＄墖鐐瑰埌涓嬮潰鐨勫簲鐢?- 鎸変綇 `Alt` 閿?鈫?杩涘叆浜や簰鎬?鈫?鍙互鎷栧姩銆佺偣鍑汇€佹粴鍔?
### 澶氭樉绀哄櫒 + DPI 鑷€傚簲
- 鏀寔 4K 灞忋€?K 灞忋€佹贩鍚?DPI
- 鍗＄墖浣嶇疆**鎸夋樉绀哄櫒淇濆瓨**锛屼笉涓蹭綅

### 宕╂簝闅旂
- 涓€涓崱鐗囨寕浜?鈮?鏁翠釜鐢诲竷鎸?- 閿欒鏃ュ織鍐欏埌 `logs/` 涓嶅奖鍝嶄富杩涚▼

### 鏁版嵁鏈湴鍖?- 鎵€鏈夋暟鎹瓨 SQLite锛屼笉涓婁簯
- 瀵煎嚭 / 瀵煎叆閰嶇疆锛堜竴浠?YAML 璧板ぉ涓嬶級

---

## 馃彈锔?鐩綍缁撴瀯

```
MoonDeck/
鈹溾攢鈹€ main.py                    # 鍏ュ彛
鈹溾攢鈹€ config/                    # 閰嶇疆
鈹?  鈹溾攢鈹€ default.yaml           # 榛樿閰嶇疆锛堝崱鐗囧垪琛ㄣ€佷綅缃€佸揩鎹烽敭锛?鈹?  鈹溾攢鈹€ theme.yaml             # 涓婚閰嶇疆
鈹?  鈹斺攢鈹€ hotkeys.yaml           # 蹇嵎閿?鈹溾攢鈹€ core/                      # 鐢诲竷鏍稿績
鈹?  鈹溾攢鈹€ canvas.py              # 閫忔槑鍏ㄥ睆涓荤獥鍙?鈹?  鈹溾攢鈹€ card_base.py           # 鍗＄墖鍩虹被
鈹?  鈹溾攢鈹€ theme.py               # 涓婚绠＄悊鍣?鈹?  鈹溾攢鈹€ drag_manager.py        # 鎷栨嫿 + 缂╂斁 + 鍚搁檮
鈹?  鈹溾攢鈹€ click_manager.py       # 鍙抽敭鑿滃崟
鈹?  鈹溾攢鈹€ event_bus.py           # 鍗＄墖闂撮€氫俊
鈹?  鈹溾攢鈹€ hotkey_manager.py      # 鍏ㄥ眬蹇嵎閿?鈹?  鈹溾攢鈹€ desktop_bg.py          # 妗岄潰鑳屾櫙鍔ㄦ晥锛堢矑瀛?鏄熺┖/鏇奸檧缃楋級
鈹?  鈹溾攢鈹€ desktop_pet.py         # 灏忕传妗屽疇锛坰prite sheet + 澶氳鑹诧級
鈹?  鈹斺攢鈹€ tray.py                # 绯荤粺鎵樼洏
鈹溾攢鈹€ cards/                     # 鍗＄墖妯″潡
鈹?  鈹溾攢鈹€ calendar_card/         # 馃棑锔?鏈堝巻锛堝啘鍘?鏃ョ▼+Token+澶╂皵+闊充箰鍖猴級
鈹?  鈹溾攢鈹€ music_card/            # 馃幍 闊充箰锛堥璋?SMTC+姝岃瘝+鎺у埗锛?鈹?  鈹溾攢鈹€ token_card/            # Token 鏈嶅姟锛堝凡闆嗘垚杩涙湀鍘嗭級
鈹?  鈹斺攢鈹€ weather_card/          # 澶╂皵鏈嶅姟锛堝凡闆嗘垚杩涙湀鍘嗭級
鈹溾攢鈹€ tests/                     # 娴嬭瘯
鈹溾攢鈹€ docs/                      # 鏂囨。
鈹溾攢鈹€ PROJECT_PLAN.md            # 瀹屾暣椤圭洰瑙勫垝
鈹溾攢鈹€ requirements.txt           # 渚濊禆
鈹斺攢鈹€ MoonDeck.v0.4.spec              # PyInstaller 鎵撳寘閰嶇疆
```

---

## 馃洜锔?鎶€鏈爤

| 灞?| 閫夊瀷 |
|----|------|
| **GUI** | PyQt6 |
| **閰嶇疆** | PyYAML |
| **鏁版嵁搴?* | SQLite |
| **闊抽閲囬泦** | pyaudiowpatch (WASAPI Loopback) |
| **绯荤粺濯掍綋鎺у埗** | winrt (SMTC) |
| **绯荤粺鐩戞帶** | psutil |
| **鏂囦欢鐩戞帶** | watchdog |
| **鎵撳寘** | PyInstaller |

---

## 馃殌 蹇€熷紑濮?
```bash
# 瀹夎渚濊禆
pip install -r requirements.txt

# 鍚姩
python main.py

# 璋冭瘯妯″紡
python main.py --debug
```

---

## 蹇嵎閿?
| 蹇嵎閿?| 鍔熻兘 |
|--------|------|
| `Alt` | 杩涘叆浜や簰鎬侊紙鍙嫋鎷?鐐瑰嚮锛?|
| `Esc` | 閫€鍑轰氦浜掓€?|
| `Ctrl+Alt+T` | 鍒囨崲涓婚 |
| `Ctrl+Alt+B` | 鍒囨崲妗岄潰鑳屾櫙鍔ㄦ晥 |
| `Ctrl+Alt+L` | 鍒囨崲姝岃瘝鍔ㄦ晥 |
| `Ctrl+Alt+P` | 鍒囨崲妗屽疇鏄剧ず |

---

## 馃摎 鏂囨。

- [PROJECT_PLAN.md](./PROJECT_PLAN.md) 鈥斺€?瀹屾暣鏋舵瀯璁捐
- [config/default.yaml](./config/default.yaml) 鈥斺€?閰嶇疆璇存槑

---

## 绗笁鏂硅祫婧?
鏈」鐩娇鐢ㄧ殑閮ㄥ垎妗屽疇 sprite sheet 鏉ヨ嚜 [Petdex](https://petdex.dev)锛堝紑婧?Codex 瀹犵墿鐢诲粖锛?000+ 绀惧尯鎻愪氦瑙掕壊锛夛細

| 瑙掕壊 | Petdex 淇℃伅 |
|------|-------------|
| 闄堝崈璇?(chen-qianyu) | [Petdex #2028](https://petdex.dev/pets/chen-qianyu) by ZIHAN L. |
| 姹愭湀鍚屽 (xiyue) | [Petdex](https://petdex.dev/pets/xiyue) by bluefrog |
| 鏅曟檿 (yunyun) | [Petdex](https://petdex.dev/pets/yunyun) by march-7th-mini |
| Lian | [Petdex](https://petdex.dev/pets/lian) by ustinaian |
| 闂紟鐜嬫灄 (wang-lin-wending) | [Petdex](https://petdex.dev/pets/wang-lin-wending-pixel) by 15821914639 |
| 闊╃珛 (han-li) | [Petdex](https://petdex.dev/pets/han-li) by 鑰佸ぇ |
| 閾舵湀 (yinyue) | [Petdex](https://petdex.dev/pets/yinyue-2) by 鑰佸ぇ |
| 閾舵湀濡栫嫄 (yinyue-yaohu) | [Petdex](https://petdex.dev/pets/yinyue-yaohu) by 鑰佸ぇ |

> 浠ヤ笂瑙掕壊 sprite sheet 閬靛惊 Petdex 椤圭洰璁稿彲鍗忚銆?
鍏朵綑璧勬簮鍧囦负鏈」鐩師鍒涳細
- **灏忕传妗屽疇锛堢煝閲忕増锛?*锛氱函 QPainter 缁樺埗锛屼笉渚濊禆澶栭儴 sprite
- **妗岄潰鑳屾櫙鍔ㄦ晥**锛氱矑瀛愭槦浜?/ 鏄熺┖ / 鍑犱綍鏇奸檧缃?/ 姝岃瘝椋樺瓧娴?/ 姝岃瘝绮掑瓙瀛?- **pet_gen/** 鐩綍锛欰I 鐢熸垚绱犳潗锛屼笉闅忎粨搴撳垎鍙?
---

## 馃惡 浣滆€?
**鑰佸ぇ**锛堜骇鍝?+ 鏋舵瀯锛?+ **閾舵湀**锛圓I 鍗忎綔鑰?路 馃寵 鐙肩伒锛?
---

*鏈€鍚庢洿鏂帮細2026-06-20*

