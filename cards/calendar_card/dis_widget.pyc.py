"""
Translate widget.cpython-311.pyc bytecode back to Python source.
Strategy: For each code object, walk co_varnames/co_names/co_consts and produce
a 'signature' (def line) and a 'body hint' (list of consts/loads).
This is *not* a full decompiler — it recovers structure but body remains
'human translation needed'. We pair this with manual reconstruction.
"""
import dis, marshal, types, json, sys, io

PYC = r'C:\Users\Administrator\.easyclaw\workspace\tools\desktop-canvas\cards\calendar_card\__pycache__\widget.cpython-311.pyc'
OUT = r'C:\Users\Administrator\.easyclaw\workspace\tools\desktop-canvas\cards\calendar_card\widget_dis.txt'

with open(PYC, 'rb') as f:
    f.read(16)
    top = marshal.load(f)

def collect(c, prefix):
    out = [(prefix, c)]
    for const in c.co_consts:
        if isinstance(const, types.CodeType):
            out.extend(collect(const, prefix + '/' + c.co_name))
    return out

codes = collect(top, '<top>')

# Use dis to get the bytecode of each
buf = io.StringIO()
for path, c in codes:
    buf.write('=' * 80 + '\n')
    buf.write(f'PATH: {path}\n')
    buf.write(f'NAME: {c.co_name}\n')
    buf.write(f'LINE: {c.co_firstlineno}\n')
    buf.write(f'ARGC: {c.co_argcount} pos={c.co_posonlyargcount} kw={c.co_kwonlyargcount}\n')
    buf.write(f'VARS: {list(c.co_varnames)}\n')
    buf.write(f'NAMES (globals/attrs): {list(c.co_names)}\n')
    buf.write(f'FREE: {list(c.co_freevars)} CELL: {list(c.co_cellvars)}\n')
    buf.write(f'CONSTS:\n')
    for i, x in enumerate(c.co_consts):
        if isinstance(x, types.CodeType):
            buf.write(f'  [{i}] <code: {x.co_name}>\n')
        else:
            buf.write(f'  [{i}] {x!r}\n')
    buf.write('--- BYTECODE ---\n')
    dis.dis(c, file=buf)
    buf.write('\n\n')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(buf.getvalue())
print(f'dis output: {OUT}')
print(f'size: {sys.getsizeof(buf.getvalue())} bytes')
