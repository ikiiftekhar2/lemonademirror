#!/usr/bin/env python3
# Read named symbols' bytes out of a vmlinux ELF (PT_LOAD segments).
# Usage: _extract_amp_tables.py <vmlinux> <symbol:outfile> [<symbol:outfile> ...]
import sys, struct, subprocess, hashlib

TABLE_LEN = 3264  # vendor registers_{tweeters,woofers} size

def load_segments(path):
    f = open(path, "rb").read()
    assert f[:4] == b"\x7fELF", "not an ELF"
    is64 = f[4] == 2
    assert is64, "expected ELF64 aarch64 vmlinux"
    phoff = struct.unpack_from("<Q", f, 0x20)[0]
    phentsz, phnum = struct.unpack_from("<HH", f, 0x36)
    segs = []
    for i in range(phnum):
        p = struct.unpack_from("<IIQQQQQQ", f, phoff + i * phentsz)
        if p[0] == 1:  # PT_LOAD
            segs.append(dict(off=p[2], vaddr=p[3], filesz=p[5]))
    return f, segs

def read_va(f, segs, va, n):
    for s in segs:
        if s["vaddr"] <= va < s["vaddr"] + s["filesz"]:
            o = s["off"] + (va - s["vaddr"])
            return f[o:o + n]
    raise SystemExit(f"vaddr {va:#x} not in any PT_LOAD segment")

def symbols(path):
    out = subprocess.run(["nm", path], capture_output=True, text=True).stdout
    d = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3:
            d[parts[2]] = int(parts[0], 16)
    return d

def main():
    vmlinux = sys.argv[1]
    f, segs = load_segments(vmlinux)
    syms = symbols(vmlinux)
    for spec in sys.argv[2:]:
        name, outfile = spec.split(":", 1)
        if name not in syms:
            raise SystemExit(f"symbol {name} not found (is the vmlinux unstripped / has kallsyms?)")
        data = read_va(f, segs, syms[name], TABLE_LEN)
        open(outfile, "wb").write(data)
        print(f"{name} @ {syms[name]:#x} -> {outfile}  ({len(data)} bytes, "
              f"sha256 {hashlib.sha256(data).hexdigest()[:16]}…)")

if __name__ == "__main__":
    main()
