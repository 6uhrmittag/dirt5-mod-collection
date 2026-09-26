"""d5tex - DIRT 5 .gtx textures: inspect, export to PNG, build same-size replacements.

A .gtx is an EVO container ("MASTER HEADER" / "BLXP" TextureConditioner chunk):
    ... | u64 payloadSize | u32 width | u32 height | u32 depth | u32 mips | u32 format | ...
and the pixel data (top mip first, then the smaller mips) sits at the END of the file.

Format codes (verified by decoding real files, 2026-09-26):
    32 / 33  BC1   (0.5 B/px)  UI art, colour maps, livery masks
    38       BC4   (0.5 B/px)  height / single-channel masks
    40       BC5   (1 B/px)    normal maps (RG)
    43 / 44  BC7   (1 B/px)    most environment/vehicle colour + mask maps
    6 / 7    RGBA8 (4 B/px)
    21       RGBA16F (8 B/px)   small data maps, e.g. <car>_windscreen.gtx
    28       RGBA32F (16 B/px)  environment probe cubemaps (6 layers)
    30       R11G11B10F (4 B/px) colour-grading LUTs, textures/render/luts/*.gtx: 32 slices of
                                32x32, x = red in, y = green in, slice = blue in, linear 0..1
                                (identity.gtx is exactly i/31); see lut_read/lut_write
Pairs are presumably linear/sRGB variants - the stored bytes are identical either way.

Usage:
  python d5tex.py info   <file.gtx> [...]
  python d5tex.py export <file.gtx> <out.png> [--mip N]
  python d5tex.py build  <orig.gtx> <image> <out.gtx> [--fit cover|stretch]
      re-encodes <image> in the texture's own format and size (full mip chain),
      header untouched, identical byte size
"""
import io
import struct
import sys

import numpy as np
from PIL import Image

CODES = {32: "BC1", 33: "BC1", 38: "BC4", 40: "BC5", 43: "BC7", 44: "BC7", 6: "RGBA8", 7: "RGBA8",
         21: "RGBA16F", 28: "RGBA32F", 30: "R11G11B10F"}
BLOCK = {"BC1": 8, "BC4": 8, "BC5": 16, "BC7": 16}           # bytes per 4x4 block
PIXEL = {"RGBA8": 4, "RGBA16F": 8, "RGBA32F": 16, "R11G11B10F": 4}  # bytes per pixel
DXGI = {"BC4": 80, "BC5": 83, "BC7": 98}


def _mip_sizes(fmt, w, h, mips):
    out = []
    for _ in range(mips):
        if fmt in PIXEL:
            out.append((w, h, w * h * PIXEL[fmt]))
        else:
            out.append((w, h, max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * BLOCK[fmt]))
        w, h = max(1, w // 2), max(1, h // 2)
    return out


# R11G11B10 floats share float16's 5-bit exponent (bias 15): 11-bit = float16 bits >> 4, 10-bit >> 5

def _unpack_111110(raw):
    v = np.frombuffer(raw, "<u4").astype(np.uint32)
    r = ((v & 0x7FF) << 4).astype(np.uint16).view(np.float16)
    g = (((v >> 11) & 0x7FF) << 4).astype(np.uint16).view(np.float16)
    b = (((v >> 22) & 0x3FF) << 5).astype(np.uint16).view(np.float16)
    return np.stack([r, g, b], -1).astype(np.float32)


def _pack_111110(rgb):
    h = np.clip(np.asarray(rgb, np.float32), 0, 60000).astype(np.float16).view(np.uint16).astype(np.uint32)
    r = np.minimum((h[..., 0] + 0x8) >> 4, 0x7BF)       # round to nearest, stay below inf
    g = np.minimum((h[..., 1] + 0x8) >> 4, 0x7BF)
    b = np.minimum((h[..., 2] + 0x10) >> 5, 0x3DF)
    return (r | (g << 11) | (b << 22)).astype("<u4").tobytes()


def _float_image(rgba, w, h):
    return Image.fromarray(np.clip(np.rint(rgba * 255), 0, 255).astype(np.uint8).reshape(h, w, 4), "RGBA")


def parse(data: bytes):
    """-> dict(width, height, mips, layers, fmt, code, pixel_off, pixel_size, levels).

    .gtx ("BLXP" chunk): ... w, h, layers, mipCount, format; pixels = the whole mip chain,
    layer-major for texture arrays (layer 0 all mips, layer 1 all mips, ...; e.g. the
    trackside sponsor banners `branding_array_<country>_c.gtx` = 8 layers of 512x512).
    .gmp ("BPIM" chunk, streamed high-res level, e.g. *_tier1.gmp): ... w, h, depth, mipIndex,
    format; pixels = that ONE level (mipIndex 0 = the biggest level of the full chain)."""
    single = b"BPIM" in data[:0x80]
    for k in range(0x60, min(len(data) - 20, 0x200)):
        w, h, depth, mips, code = struct.unpack_from("<IIIII", data, k)
        if single:
            mips = 1                       # 4th field is the mip index, the file holds one level
        if not (4 <= w <= 16384 and 4 <= h <= 16384 and 1 <= depth <= 64 and 1 <= mips <= 16):
            continue
        # payload size right before the dims: u32 in .gmp; in .gtx u32 + u32 flags (1 for arrays)
        payload = struct.unpack_from("<I", data, k - (4 if single else 8))[0]
        if not (w * h // 8 <= payload <= len(data)):
            continue
        fmt = CODES.get(code)
        if fmt is None:
            raise ValueError(f"unknown texture format code {code} ({w}x{h}, {mips} mips)")
        levels = _mip_sizes(fmt, w, h, mips)
        chain = sum(s for _, _, s in levels)          # one layer's mip chain
        size = chain * depth
        off = len(data) - size
        if 64 <= off <= 1024:
            return {"width": w, "height": h, "mips": mips, "layers": depth, "fmt": fmt, "code": code,
                    "pixel_off": off, "pixel_size": size, "layer_size": chain, "levels": levels, "dims_off": k}
    raise ValueError("unrecognised .gtx layout")


def _dds(w, h, data, fmt):
    hdr = struct.pack("<4sIIIIIII44x", b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, h, w, len(data), 0, 1)
    four = b"DXT1" if fmt == "BC1" else b"DX10"
    pf = struct.pack("<II4sIIIII", 32, 0x4, four, 0, 0, 0, 0, 0)
    ext = b"" if fmt == "BC1" else struct.pack("<IIIII", DXGI[fmt], 3, 0, 1, 0)
    return hdr + pf + struct.pack("<IIII4x", 0x1000, 0, 0, 0) + ext + data


def _decode_level(t, data, layer, mip):
    off = t["pixel_off"] + layer * t["layer_size"] + sum(s for _, _, s in t["levels"][:mip])
    w, h, size = t["levels"][mip]
    raw = data[off:off + size]
    if t["fmt"] == "RGBA8":
        return Image.frombytes("RGBA", (w, h), raw)
    if t["fmt"] in ("RGBA16F", "RGBA32F"):    # HDR: clipped to 0..1 for viewing/editing
        return _float_image(np.frombuffer(raw, "<f2" if t["fmt"] == "RGBA16F" else "<f4").astype(np.float32), w, h)
    if t["fmt"] == "R11G11B10F":
        rgb = _unpack_111110(raw)
        return _float_image(np.concatenate([rgb, np.ones((len(rgb), 1), np.float32)], 1), w, h)
    pw, ph = max(4, (w + 3) // 4 * 4), max(4, (h + 3) // 4 * 4)
    im = Image.open(io.BytesIO(_dds(pw, ph, raw, t["fmt"])))
    im.load()
    im = im.crop((0, 0, w, h))
    return im.convert("RGB") if t["fmt"] == "BC1" else im.convert("RGBA")


def decode(data: bytes, mip: int = 0, layer: int = None) -> Image.Image:
    """One level as an image. Texture arrays come back as a vertical strip of all layers
    (layer 0 on top) unless `layer` picks one - build() takes the same strip back."""
    t = parse(data)
    if t["layers"] == 1 or layer is not None:
        return _decode_level(t, data, layer or 0, mip)
    parts = [_decode_level(t, data, i, mip) for i in range(t["layers"])]
    strip = Image.new(parts[0].mode, (parts[0].width, parts[0].height * len(parts)))
    for i, p in enumerate(parts):
        strip.paste(p, (0, i * p.height))
    return strip


# --- block encoders (numpy) ---------------------------------------------------------------

def _blocks(a, ch):
    h, w = a.shape[:2]
    return a.reshape(h // 4, 4, w // 4, 4, ch).transpose(0, 2, 1, 3, 4).reshape(-1, 16, ch)


def _pca_endpoints(b):
    """b (n,16,c) float -> endpoints (n,c) x2 along the principal axis."""
    mean = b.mean(1, keepdims=True)
    cen = b - mean
    cov = np.einsum("nki,nkj->nij", cen, cen)
    axis = np.ones((len(b), b.shape[2]), np.float32)
    for _ in range(6):
        axis = np.einsum("nij,nj->ni", cov, axis)
        axis /= np.linalg.norm(axis, axis=1, keepdims=True) + 1e-6
    proj = np.einsum("nki,ni->nk", cen, axis)
    lo = mean[:, 0] + axis * proj.min(1, keepdims=True)
    hi = mean[:, 0] + axis * proj.max(1, keepdims=True)
    return np.clip(lo, 0, 255), np.clip(hi, 0, 255)


def _to565(c):
    c = np.clip(np.rint(c), 0, 255).astype(np.uint32)
    return ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)


def _from565(v):
    r = ((v >> 11) & 31) * 255 // 31
    g = ((v >> 5) & 63) * 255 // 63
    b = (v & 31) * 255 // 31
    return np.stack([r, g, b], -1).astype(np.float32)


def bc1_encode(img: Image.Image) -> bytes:
    blocks = _blocks(np.asarray(img.convert("RGB"), dtype=np.float32), 3)
    c1, c0 = _pca_endpoints(blocks)
    e0, e1 = _to565(c0), _to565(c1)
    swap = e0 < e1                      # 4-colour mode needs e0 > e1
    e0, e1 = np.where(swap, e1, e0), np.where(swap, e0, e1)
    e0 = np.where((e0 == e1) & (e0 < 0xFFFF), e0 + 1, e0)
    p0, p1 = _from565(e0), _from565(e1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)      # n,4,3
    idx = ((blocks[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1).argmin(-1).astype(np.uint32)
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    return np.stack([e0 | (e1 << 16), bits], 1).astype("<u4").tobytes()


def _bc4_blocks(v):
    """v (n,16) float single channel -> (n,) uint64 BC4 blocks (8-value mode)."""
    e0 = np.rint(v.max(1)).astype(np.int64)
    e1 = np.rint(v.min(1)).astype(np.int64)
    w = np.arange(8)
    # palette order of the 8-value mode: e0, e1, then 6/7..1/7 blends from e0 to e1
    frac = np.array([0, 7, 1, 2, 3, 4, 5, 6]) / 7.0
    pal = e0[:, None] * (1 - frac)[None] + e1[:, None] * frac[None]
    pal[:, 1] = e1
    idx = np.abs(v[:, :, None] - pal[:, None, :]).argmin(-1).astype(np.uint64)
    same = e0 == e1
    idx[same] = 0
    out = (e0.astype(np.uint64) & np.uint64(255)) | ((e1.astype(np.uint64) & np.uint64(255)) << np.uint64(8))
    for i in range(16):
        out |= idx[:, i] << np.uint64(16 + 3 * i)
    del w
    return out


def bc4_encode(img: Image.Image) -> bytes:
    a = np.asarray(img.convert("RGBA"), dtype=np.float32)[..., :1]
    return _bc4_blocks(_blocks(a, 1)[..., 0]).astype("<u8").tobytes()


def bc5_encode(img: Image.Image) -> bytes:
    a = np.asarray(img.convert("RGBA"), dtype=np.float32)
    r = _bc4_blocks(_blocks(a[..., 0:1], 1)[..., 0])
    g = _bc4_blocks(_blocks(a[..., 1:2], 1)[..., 0])
    return np.stack([r, g], 1).astype("<u8").tobytes()


W4 = np.array([0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64], np.float32)


def _bc7_quant(e):
    """8-bit endpoint (n,4) -> 7-bit colour + shared p-bit with the smaller error."""
    best_c = best_p = best_r = None
    best_err = None
    for p in (0, 1):
        c = np.clip(np.rint((e - p) / 2), 0, 127)
        r = c * 2 + p
        err = ((r - e) ** 2).sum(1)
        if best_err is None:
            best_c, best_p, best_r, best_err = c, np.full(len(e), p), r, err
        else:
            m = err < best_err
            best_c = np.where(m[:, None], c, best_c)
            best_r = np.where(m[:, None], r, best_r)
            best_p = np.where(m, p, best_p)
            best_err = np.minimum(err, best_err)
    return best_c.astype(np.uint64), best_p.astype(np.uint64), best_r


def _bc7_indices(b, r0, r1):
    pal = np.floor(((64 - W4)[None, :, None] * r0[:, None, :] + W4[None, :, None] * r1[:, None, :] + 32) / 64)
    return ((b[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1).argmin(-1)


def _bc7_mode6(b):
    """b (n,16,4) float RGBA -> (n,2) uint64 BC7 mode-6 blocks (1 subset, 4-bit indices)."""
    e0, e1 = _pca_endpoints(b)
    c0, p0, r0 = _bc7_quant(e0)
    c1, p1, r1 = _bc7_quant(e1)
    idx = _bc7_indices(b, r0, r1)
    # one least-squares refinement of the endpoints for the chosen weights
    t = (W4[idx] / 64.0)[..., None]                                   # n,16,1
    a00, a01, a11 = ((1 - t) ** 2).sum(1), (t * (1 - t)).sum(1), (t ** 2).sum(1)
    x0, x1 = ((1 - t) * b).sum(1), (t * b).sum(1)
    det = a00 * a11 - a01 * a01
    ok = (np.abs(det) > 1e-3)[:, 0]
    safe = np.where(np.abs(det) > 1e-3, det, 1.0)
    n0 = np.clip((a11 * x0 - a01 * x1) / safe, 0, 255)
    n1 = np.clip((a00 * x1 - a01 * x0) / safe, 0, 255)
    q0, qp0, qr0 = _bc7_quant(n0)
    q1, qp1, qr1 = _bc7_quant(n1)
    idx2 = _bc7_indices(b, qr0, qr1)
    err_old = ((b - np.floor(((64 - W4[idx])[..., None] * r0[:, None] + W4[idx][..., None] * r1[:, None] + 32) / 64)) ** 2).sum((1, 2))
    err_new = ((b - np.floor(((64 - W4[idx2])[..., None] * qr0[:, None] + W4[idx2][..., None] * qr1[:, None] + 32) / 64)) ** 2).sum((1, 2))
    use = ok & (err_new < err_old)
    c0, c1 = np.where(use[:, None], q0, c0), np.where(use[:, None], q1, c1)
    p0, p1 = np.where(use, qp0, p0), np.where(use, qp1, p1)
    idx = np.where(use[:, None], idx2, idx).astype(np.uint64)
    # anchor texel 0 must have index MSB 0: swap endpoints + invert indices where needed
    flip = idx[:, 0] >= 8
    c0, c1 = np.where(flip[:, None], c1, c0), np.where(flip[:, None], c0, c1)
    p0, p1 = np.where(flip, p1, p0), np.where(flip, p0, p1)
    idx = np.where(flip[:, None], np.uint64(15) - idx, idx)
    fields = [(np.full(len(b), 64, np.uint64), 7)]                     # mode 6 = bit 6 set
    for ch in range(4):
        fields += [(c0[:, ch], 7), (c1[:, ch], 7)]
    fields += [(p0, 1), (p1, 1), (idx[:, 0], 3)] + [(idx[:, i], 4) for i in range(1, 16)]
    lo = np.zeros(len(b), np.uint64)
    hi = np.zeros(len(b), np.uint64)
    pos = 0
    for v, n in fields:
        v = v.astype(np.uint64)
        if pos + n <= 64:
            lo |= v << np.uint64(pos)
        elif pos >= 64:
            hi |= v << np.uint64(pos - 64)
        else:
            k = 64 - pos
            lo |= (v & np.uint64((1 << k) - 1)) << np.uint64(pos)
            hi |= v >> np.uint64(k)
        pos += n
    assert pos == 128
    return np.stack([lo, hi], 1)


def bc7_encode(img: Image.Image) -> bytes:
    blocks = _blocks(np.asarray(img.convert("RGBA"), dtype=np.float32), 4)
    out = [_bc7_mode6(blocks[s:s + 8192]) for s in range(0, len(blocks), 8192)]
    return np.concatenate(out).astype("<u8").tobytes()


def _rgba01(im):
    return np.asarray(im.convert("RGBA"), dtype=np.float32).reshape(-1, 4) / 255.0


ENCODERS = {"BC1": bc1_encode, "BC4": bc4_encode, "BC5": bc5_encode, "BC7": bc7_encode,
            "RGBA8": lambda im: im.convert("RGBA").tobytes(),
            "RGBA16F": lambda im: _rgba01(im).astype("<f2").tobytes(),
            "RGBA32F": lambda im: _rgba01(im).astype("<f4").tobytes(),
            "R11G11B10F": lambda im: _pack_111110(_rgba01(im)[:, :3])}


# --- colour-grading LUTs (format R11G11B10F, 32 x 32 x 32) ---------------------------------

def is_lut(data: bytes) -> bool:
    try:
        t = parse(data)
    except ValueError:
        return False
    return t["fmt"] == "R11G11B10F" and t["layers"] == t["width"] == t["height"]


def lut_read(data: bytes):
    """-> rgb float32 [b, g, r, 3] (graded output colour, linear, ~0..1) - index order =
    stored order: slice = blue in, row = green in, column = red in."""
    t = parse(data)
    n = t["width"]
    return _unpack_111110(data[t["pixel_off"]:t["pixel_off"] + n * n * n * 4]).reshape(n, n, n, 3)


def lut_write(orig: bytes, rgb) -> bytes:
    t = parse(orig)
    n = t["width"]
    body = _pack_111110(np.asarray(rgb, np.float32).reshape(-1, 3))
    assert len(body) == n * n * n * 4
    return orig[:t["pixel_off"]] + body + orig[t["pixel_off"] + len(body):]


def lut_sample(lut, rgb):
    """Trilinear lookup of colours rgb (..., 3) in lut [b, g, r, 3] -> (..., 3)."""
    n = lut.shape[0]
    p = np.clip(np.asarray(rgb, np.float32), 0, 1) * (n - 1)
    i0 = np.floor(p).astype(int)
    i1 = np.minimum(i0 + 1, n - 1)
    f = p - i0
    out = 0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                b = i1[..., 2] if db else i0[..., 2]
                g = i1[..., 1] if dg else i0[..., 1]
                r = i1[..., 0] if dr else i0[..., 0]
                w = ((f[..., 2] if db else 1 - f[..., 2]) * (f[..., 1] if dg else 1 - f[..., 1])
                     * (f[..., 0] if dr else 1 - f[..., 0]))
                out = out + lut[b, g, r] * w[..., None]
    return out


def fit_image(src: Image.Image, w, h, mode="cover") -> Image.Image:
    src = src.convert("RGBA")
    if mode == "stretch":
        return src.resize((w, h), Image.LANCZOS)
    k = max(w / src.width, h / src.height)
    r = src.resize((max(w, round(src.width * k)), max(h, round(src.height * k))), Image.LANCZOS)
    x, y = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x, y, x + w, y + h))


def build(orig: bytes, img: Image.Image, mode="cover") -> bytes:
    """Re-encode img into orig's format/size/mip chain; the header stays byte-identical."""
    t = parse(orig)
    enc = ENCODERS[t["fmt"]]
    W, H, n = t["width"], t["height"], t["layers"]
    strip = fit_image(img, W, H * n, mode)            # arrays: layers stacked vertically
    out = b""
    for i in range(n):
        level = strip.crop((0, i * H, W, (i + 1) * H))
        for w, h, size in t["levels"]:
            lv = level if level.size == (w, h) else level.resize((w, h), Image.LANCZOS)
            if t["fmt"] in BLOCK:           # block formats need 4x4-aligned levels
                pw, ph = max(4, (w + 3) // 4 * 4), max(4, (h + 3) // 4 * 4)
                if (pw, ph) != (w, h):
                    pad = Image.new("RGBA", (pw, ph))
                    pad.paste(lv)
                    lv = pad
            data = enc(lv)
            assert len(data) == size, (t["fmt"], w, h, len(data), size)
            out += data
            level = lv.crop((0, 0, w, h))
    return orig[:t["pixel_off"]] + out


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "info":
        for f in argv[2:]:
            try:
                t = parse(open(f, "rb").read())
                arr = f" x{t['layers']} layers" if t["layers"] > 1 else ""
                print(f"{f}: {t['width']}x{t['height']}{arr} {t['fmt']} (code {t['code']}) mips={t['mips']} pixels@{t['pixel_off']}")
            except ValueError as e:
                print(f"{f}: {e}")
    elif cmd == "export":
        mip = int(argv[argv.index("--mip") + 1]) if "--mip" in argv else 0
        decode(open(argv[2], "rb").read(), mip).save(argv[3])
        print(argv[3])
    elif cmd == "build":
        mode = argv[argv.index("--fit") + 1] if "--fit" in argv else "cover"
        new = build(open(argv[2], "rb").read(), Image.open(argv[3]), mode)
        open(argv[4], "wb").write(new)
        print(f"{argv[4]}: {len(new)} bytes (same as original)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
