typedef unsigned int u32;
struct record { u32 key; u32 value; };
__declspec(dllexport) volatile u32 counter = 7;
__declspec(dllexport) const char message[] = "shared program fixture";
__declspec(dllexport) __declspec(noinline) u32 mix(u32 x) {
    x ^= x >> 16; x *= 0x45d9f3bU; x ^= x >> 16; return x;
}
__declspec(dllexport) __declspec(noinline) u32 sum_records(struct record *p, u32 n) {
    u32 s = 0; for (u32 i = 0; i < n; ++i) s += mix(p[i].key) + p[i].value;
    return s;
}
__declspec(dllexport) __declspec(noinline) u32 dispatch(u32 x) {
    switch(x & 3) { case 0: return mix(x); case 1: return x+counter;
      case 2: return x*x; default: return message[x%20]; }
}
void entry(void) { counter = dispatch(counter); }
