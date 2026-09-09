"""Deterministic larger fixture source; compile with the same MSVC flags as small.c."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / '.local/fixtures/large.c'
lines = ['typedef unsigned int u32;', 'volatile u32 sink;', 'const char message[]="large synthetic fixture";']
for index in range(256):
    lines += [f'__declspec(dllexport) __declspec(noinline) u32 work_{index:03d}(u32 x, u32 *p) {{']
    for step in range(48):
        k = ((index+1)*2654435761+step*2246822519) & 0xffffffff
        lines += [f'  x ^= (x >> {(step%13)+1}) + {k}U;',
                  f'  if (x & {1 << (step%29)}U) x += p[{step%16}]; else x *= {2*step+3}U;']
    lines += ['  return x;', '}']
lines += ['u32 initial[16];', 'void entry(void) { sink=work_000(7,initial); }']
out.write_text('\n'.join(lines))
print(out.relative_to(root))
