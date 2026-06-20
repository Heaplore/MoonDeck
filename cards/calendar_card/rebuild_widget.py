"""
Auto-rebuild widget.py from dis_widget.pyc.py output.
This is a *partial* decompiler - it handles simple bytecode patterns:
- LOAD_FAST + STORE_FAST (assignments)
- LOAD_GLOBAL/LOAD_NAME/LOAD_CONST (load)
- LOAD_METHOD + CALL/PRECALL (method calls)
- BINARY_OP (+,-,*,/)
- COMPARE_OP (<, >, ==)
- POP_JUMP_* (if/else)
- BUILD_STRING, BUILD_MAP, BUILD_LIST, BUILD_TUPLE
- SETUP_FINALLY / PUSH_EXC_INFO (try/except)
- FORMAT_VALUE (f-string)
- RETURN_VALUE
- MAKE_FUNCTION (defs)
"""
import dis, types, json, sys, io, re

# We don't need this — the dis output has all the info we need.
# Instead, do MANUAL reconstruction using the dis.txt.

DIS_TXT = r'C:\Users\Administrator\.easyclaw\workspace\tools\desktop-canvas\cards\calendar_card\widget_dis.txt'

# Read dis text
with open(DIS_TXT, 'r', encoding='utf-8') as f:
    txt = f.read()

# Find sections
markers = []
for m in re.finditer(r'^NAME: (\S+)', txt, re.MULTILINE):
    first_line_match = re.search(r'LINE: (\d+)', txt[m.start():m.start()+200])
    line = int(first_line_match.group(1)) if first_line_match else 0
    markers.append((m.start(), m.group(1), line))

# Add EOF
markers.append((len(txt), 'EOF', 0))

print(f'Found {len(markers)-1} code objects')
for i in range(len(markers)-1):
    print(f'  {i+1}. {markers[i][1]} @ line {markers[i][2]}')
