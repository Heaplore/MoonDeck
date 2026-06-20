"""
Dumping widget.cpython-311.pyc with full const context per code object.
We need:
  - All string consts (for source strings)
  - All LOAD_GLOBAL / LOAD_ATTR / LOAD_FAST names (for variables/methods)
  - All function code objects (for method bodies)
"""
import dis, marshal, types, json, sys

PYC = r'C:\Users\Administrator\.easyclaw\workspace\tools\desktop-canvas\cards\calendar_card\__pycache__\widget.cpython-311.pyc'
OUT = r'C:\Users\Administrator\.easyclaw\workspace\tools\desktop-canvas\cards\calendar_card\widget_dump.json'

with open(PYC, 'rb') as f:
    f.read(16)  # PEP 552 header (16 bytes: magic+flags+ts+size)
    top = marshal.load(f)

# Build a tree of all code objects
def collect_code(c, depth=0, path=''):
    items = []
    items.append((path + '::' + c.co_name, c))
    for const in c.co_consts:
        if isinstance(const, types.CodeType):
            items.extend(collect_code(const, depth+1, path + '::' + c.co_name))
    return items

codes = collect_code(top)
print(f'found {len(codes)} code objects')

# For each code object, extract:
#   co_name, co_varnames, co_names, co_freevars, co_cellvars,
#   co_consts (strs only), bytecode disassembly (LOAD_* targets)
def serialize_code(c):
    strs = [x for x in c.co_consts if isinstance(x, str)]
    out = {
        'name': c.co_name,
        'argcount': c.co_argcount,
        'posonlyargcount': c.co_posonlyargcount,
        'kwonlyargcount': c.co_kwonlyargcount,
        'nlocals': c.co_nlocals,
        'stacksize': c.co_stacksize,
        'flags': c.co_flags,
        'varnames': list(c.co_varnames),
        'names': list(c.co_names),
        'freevars': list(c.co_freevars),
        'cellvars': list(c.co_cellvars),
        'consts_strs': strs,
        'consts_full': [repr(x) for x in c.co_consts],  # all consts, repr'd
        'firstlineno': c.co_firstlineno,
        'bytecode': dis.Bytecode(c).info(),
    }
    return out

dump = {'top': serialize_code(top)}
print('dumping top-level...')
for x in dump['top']['consts_strs']:
    if x: print('  const:', repr(x)[:80])

# Recursively
def collect(c, out_list, prefix):
    out_list.append((prefix, serialize_code(c)))
    for const in c.co_consts:
        if isinstance(const, types.CodeType):
            collect(const, out_list, prefix + '/' + c.co_name)

methods = []
collect(top, methods, '<top>')
dump['methods'] = [{'path': p, **m} for p, m in methods]

print(f'total methods: {len(dump["methods"])}')
print(f'total consts: top={len(dump["top"]["consts_strs"])}, all methods: {sum(len(m["consts_strs"]) for m in dump["methods"])}')

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(dump, f, ensure_ascii=False, indent=1)
print(f'dumped to {OUT}')
print(f'size: {__import__("os").path.getsize(OUT)} bytes')
