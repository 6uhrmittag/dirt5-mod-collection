#!/usr/bin/env python3
"""
header_scan.py — heuristic format scanner for DIRT 5 (Xbox build) archives.

The .dat packs use a custom Codemasters chunk container: 4-byte tags stored
BYTE-REVERSED (e.g. bytes 'RDHM' == tag "MHDR") followed by a uint32 LE length.
We do not yet know the full record layout, so this tool reports *evidence*
rather than pretending to fully parse:

  1. Entropy of the header window  -> flags obfuscated / compressed packs.
  2. FourCC tag discovery          -> printable 4-char runs, normal + reversed,
                                       with offsets (surfaces MHDR/PHYX/... vocab).
  3. Best-effort chunk walk        -> from the first anchor tag, read tag+u32 len
                                       and follow it; report how far it stays
                                       self-consistent (lengths land on more tags).

Usage:
    python header_scan.py <dir-or-file> [<dir-or-file> ...] [--window-mb N]
                          [--report FINDINGS.md]

Prints a report to stdout; with --report also appends a Markdown section.
"""
from __future__ import annotations

import argparse
import math
import os
import string
import sys
from pathlib import Path

PRINTABLE = set(string.ascii_letters + string.digits + " _-/.")
SCAN_EXTS = {".dat", ".ndx", ".bin"}
DEFAULT_WINDOW = 1 * 1024 * 1024  # 1 MiB is plenty for top-of-file structure


def shannon_entropy(data: bytes) -> float:
    """Bits per byte, 0..8. ~8.0 => random/compressed/encrypted."""
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    ent = 0.0
    for c in counts:
        if c:
            p = c / n
            ent -= p * math.log2(p)
    return ent


def is_tag(four: bytes) -> bool:
    """True if all 4 bytes are 'tag-like' printable characters."""
    if len(four) != 4:
        return False
    return all(chr(b) in PRINTABLE for b in four)


def find_tags(data: bytes, limit: int = 40):
    """
    Scan every offset for a printable 4-byte run. Report both the literal reading
    and its byte-reversed form (the container stores tags reversed).
    Returns list of (offset, literal, reversed, u32_len_after).
    """
    out = []
    n = len(data)
    i = 0
    while i < n - 8 and len(out) < limit:
        four = data[i : i + 4]
        if is_tag(four):
            literal = four.decode("latin1")
            rev = four[::-1].decode("latin1")
            length = int.from_bytes(data[i + 4 : i + 8], "little")
            out.append((i, literal, rev, length))
            i += 4
        else:
            i += 1
    return out


def walk_chunks(data: bytes, start: int, max_chunks: int = 64):
    """
    Best-effort: from `start`, treat layout as [tag:4][len:u32][payload:len]...
    Stop when a tag is non-printable or we run off the window. Returns the list of
    (offset, reversed_tag, length) and whether it stayed consistent to the end.
    """
    chunks = []
    pos = start
    n = len(data)
    consistent = True
    while pos + 8 <= n and len(chunks) < max_chunks:
        four = data[pos : pos + 4]
        if not is_tag(four):
            consistent = False
            break
        length = int.from_bytes(data[pos + 4 : pos + 8], "little")
        chunks.append((pos, four[::-1].decode("latin1"), length))
        # Sanity: absurd length => layout guess is wrong here.
        if length > n * 4 or length < 0:
            consistent = False
            break
        pos += 8 + length
    return chunks, consistent


def classify(entropy: float, tags: list) -> str:
    if entropy >= 7.5 and len(tags) < 3:
        return "high-entropy (compressed/encrypted/obfuscated) — no plain chunk header"
    if len(tags) >= 3:
        return "chunk-structured (FourCC tag/length container)"
    return "unknown / mixed"


def scan_file(path: Path, window: int) -> dict:
    with open(path, "rb") as f:
        data = f.read(window)
    ent = shannon_entropy(data)
    tags = find_tags(data)
    first_anchor = tags[0][0] if tags else None
    walk, consistent = (walk_chunks(data, first_anchor) if first_anchor is not None else ([], False))
    return {
        "path": path,
        "read": len(data),
        "entropy": ent,
        "tags": tags,
        "anchor": first_anchor,
        "walk": walk,
        "walk_consistent": consistent,
        "verdict": classify(ent, tags),
    }


def iter_targets(paths, exts):
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for child in sorted(p.iterdir()):
                if child.is_file() and (child.suffix.lower() in exts):
                    yield child
        elif p.is_file():
            yield p


def render(results: list) -> str:
    lines = []
    lines.append("## header_scan report\n")
    for r in results:
        lines.append(f"### {r['path'].name}")
        lines.append(f"- read: {r['read']:,} bytes   entropy: {r['entropy']:.3f} bits/byte")
        lines.append(f"- verdict: **{r['verdict']}**")
        if r["tags"]:
            uniq = []
            seen = set()
            for off, lit, rev, ln in r["tags"]:
                if rev not in seen:
                    seen.add(rev)
                    uniq.append(rev)
            lines.append(f"- tags seen (reversed->readable): {', '.join(uniq[:20])}")
            first = r["tags"][0]
            lines.append(f"- first tag @0x{first[0]:X}: '{first[1]}' (rev '{first[2]}'), next-u32={first[3]:,}")
        if r["walk"]:
            walked = "consistent to window end" if r["walk_consistent"] else "diverged (layout not a plain tag+len stream)"
            lines.append(f"- chunk walk from 0x{r['anchor']:X}: {len(r['walk'])} chunk(s), {walked}")
            for off, tag, ln in r["walk"][:8]:
                lines.append(f"    0x{off:06X}  {tag:<4}  len={ln:,}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="+", help="files or directories to scan")
    ap.add_argument("--window-mb", type=float, default=DEFAULT_WINDOW / (1024 * 1024))
    ap.add_argument("--report", help="append the Markdown report to this file")
    args = ap.parse_args(argv)

    window = int(args.window_mb * 1024 * 1024)
    results = [scan_file(p, window) for p in iter_targets(args.targets, SCAN_EXTS)]
    if not results:
        print("No matching files found.", file=sys.stderr)
        return 1

    report = render(results)
    print(report)
    if args.report:
        with open(args.report, "a", encoding="utf-8") as f:
            f.write("\n---\n\n" + report + "\n")
        print(f"[appended to {args.report}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
