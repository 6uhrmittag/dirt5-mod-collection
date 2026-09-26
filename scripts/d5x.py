"""d5x - DIRT 5 pack reader (dat/index/dat.ndx + N_*.dat).

Format (reverse-engineered 2026-09-23, see FINDINGS.md section 5):

  dat.ndx
    0x00  8 x 00
    0x08  u32 version (=5)
    0x0C  u32 entryCount          (files + directories)
    0x10  u32 chunkCount
    0x14  u32 chunkSize           (=0x20000, uncompressed bytes per chunk)
    0x30  entryCount x 56-byte entries:
            u64 fullPathOff, u64 hash, u64 nameOff,
            u32 size, u32 firstChunk, u32 offsetInChunk,
            u32 parent, u32 nextSibling, u32 firstChild, u32 isDir, u32 0
    then  chunkCount x 12-byte chunks: u32 pack, u32 packOffset, u32 compSize
    then  packCount x u64 pack-name offsets
    then  string table (offsets above are relative to its start)

  N_*.dat
    Solid stream: files are concatenated, cut into 128 KiB chunks, and each
    chunk is an independent raw LZ4 block (stored raw if compSize == chunkSize).

Usage:
  python d5x.py list  [glob]            list files (fnmatch on full path)
  python d5x.py extract <glob> <outdir> extract matching files (read-only)
"""
import fnmatch
import os
import struct
import sys

import lz4.block

GAME_DAT = os.environ.get("DIRT5_DAT", r"C:\Games\DIRT 5\dat")
ENTRY_SIZE = 56
CHUNK_REC = 12


class Index:
    def __init__(self, dat_dir=GAME_DAT, ndx_path=None):
        self.dat_dir = dat_dir
        self.ndx_path = ndx_path or os.path.join(dat_dir, "index", "dat.ndx")
        with open(self.ndx_path, "rb") as f:
            self.raw = bytearray(f.read())
        d = self.raw
        (self.version, self.entry_count, self.chunk_count,
         self.chunk_size) = struct.unpack_from("<4I", d, 8)
        if self.version != 5:
            raise ValueError(f"unexpected ndx version {self.version}")
        self.entries_off = 0x30
        self.chunks_off = self.entries_off + self.entry_count * ENTRY_SIZE
        packs_off = self.chunks_off + self.chunk_count * CHUNK_REC
        # pack-name offset list runs until the first string (string table
        # starts right after it, and the first pack name sits at offset 0)
        offs = []
        p = packs_off
        while True:
            (o,) = struct.unpack_from("<Q", d, p)
            if offs and o == 0 or o > 0x10000:
                break
            offs.append(o)
            p += 8
        self.strings_off = p
        self.packs = [self._str(o) for o in offs]

    def _str(self, off):
        s = self.strings_off + off
        return self.raw[s:self.raw.index(0, s)].decode("latin1")

    def entry(self, i):
        f = struct.unpack_from("<QQQ8I", self.raw, self.entries_off + i * ENTRY_SIZE)
        return {
            "index": i, "path": self._str(f[0]), "hash": f[1], "name": self._str(f[2]),
            "size": f[3], "first_chunk": f[4], "chunk_off": f[5],
            "parent": f[6], "is_dir": f[9] == 1 or f[4] == 0xFFFFFFFF,
        }

    def files(self):
        for i in range(self.entry_count):
            e = self.entry(i)
            if not e["is_dir"]:
                yield e

    def find(self, path):
        for e in self.files():
            if e["path"] == path:
                return e
        raise KeyError(path)

    def chunk(self, k):
        return struct.unpack_from("<3I", self.raw, self.chunks_off + k * CHUNK_REC)

    def pack_path(self, pack):
        return os.path.join(self.dat_dir, self.packs[pack] + ".dat")

    def read_chunk(self, k):
        pack, off, comp = self.chunk(k)
        with open(self.pack_path(pack), "rb") as f:
            f.seek(off)
            c = f.read(comp)
        if comp == self.chunk_size:
            return c
        return lz4.block.decompress(c, uncompressed_size=self.chunk_size)

    def read(self, e):
        buf = bytearray()
        k = e["first_chunk"]
        need = e["chunk_off"] + e["size"]
        while len(buf) < need:
            buf += self.read_chunk(k)
            k += 1
        return bytes(buf[e["chunk_off"]:need])


def main(argv):
    if len(argv) < 2 or argv[1] not in ("list", "extract"):
        print(__doc__)
        return 2
    idx = Index()
    pattern = argv[2] if len(argv) > 2 else "*"
    matches = [e for e in idx.files() if fnmatch.fnmatch(e["path"].lower(), pattern.lower())]
    if argv[1] == "list":
        for e in matches:
            print(f'{e["size"]:>10}  {idx.packs[idx.chunk(e["first_chunk"])[0]]:<14} {e["path"]}')
        print(f"{len(matches)} files", file=sys.stderr)
        return 0
    out_dir = argv[3]
    for e in matches:
        rel = e["path"].replace(":", "/", 1)
        dst = os.path.join(out_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            data = idx.read(e)
        except FileNotFoundError as ex:  # pack not shipped in this install
            print(f"SKIP {e['path']}: {ex.filename} missing", file=sys.stderr)
            continue
        with open(dst, "wb") as f:
            f.write(data)
    print(f"extracted {len(matches)} files -> {out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
