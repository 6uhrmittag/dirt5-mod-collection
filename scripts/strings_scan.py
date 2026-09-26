#!/usr/bin/env python3
"""
strings_scan.py — pull printable ASCII strings from a binary and (optionally)
filter to ones matching keywords. Used to find real DIRT 5 track/location/route
identifiers inside the readable .dat packs.

Usage:
    python strings_scan.py <file> [--min N] [--grep w1,w2,...] [--limit N]
"""
from __future__ import annotations
import argparse, re, sys

def strings(path, minlen):
    pat = re.compile(rb"[\x20-\x7e]{%d,}" % minlen)
    with open(path, "rb") as f:
        data = f.read()
    for m in pat.finditer(data):
        yield m.start(), m.group().decode("latin1")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--min", type=int, default=5)
    ap.add_argument("--grep", default="")
    ap.add_argument("--limit", type=int, default=200)
    a = ap.parse_args()

    words = [w.lower() for w in a.grep.split(",") if w]
    seen, n = set(), 0
    for off, s in strings(a.file, a.min):
        low = s.lower()
        if words and not any(w in low for w in words):
            continue
        if s in seen:
            continue
        seen.add(s)
        print(f"0x{off:08X}  {s}")
        n += 1
        if n >= a.limit:
            break
    print(f"\n[{n} unique strings shown]", file=sys.stderr)

if __name__ == "__main__":
    raise SystemExit(main())
