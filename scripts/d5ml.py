"""d5ml - DIRT 5 Mod Loader. Drop mods into mods/<name>/, apply them in one go.

A mod is a folder:
  mods/<name>/mod.json                  {"name", "version", "author", "description",
                                         "recipes": ["uwu", "tipsy=2"]}   (d5mod specs/presets, optional)
  mods/<name>/files/<path>              loose file replacing data:<path> - ANY size
                                        (e.g. files/physics/vehicledefs/_basecar.vdef)
  mods/<name>/textures/<path>.gtx.png   picture re-encoded into data:<path>.gtx in the texture's
                                        own format (BC1/BC4/BC5/BC7/RGBA8) and size, full mip chain

Usage:
  python d5ml.py list                       mods found and what they touch
  python d5ml.py check <mod> [<mod> ...]    dry run: what would change, conflicts
  python d5ml.py apply <mod> [<mod> ...]    apply in this order (later mods win conflicts)
  python d5ml.py restore | status           same as d5mod
  python d5ml.py install <zip|folder>       add a downloaded mod to mods/ (checks for mod.json)
  python d5ml.py list --json                machine-readable list (used by scripts/D5ML.ps1)
  python d5ml.py doctor                     self-check (Python packages, game folder, index, mods)
starter kit:
  python d5ml.py search <word> [<word> ...] game files whose path contains all words
  python d5ml.py new <mod> ["description"]  scaffold mods/<mod>/ (mod.json stamped with the game build)
  python d5ml.py extract <mod> <glob|word>  copy game files into the mod to edit them;
                                            .gtx textures arrive as editable PNGs (--raw: keep .gtx);
                                            car liveries also get a *.guide.png (paint mask overlay)
  python d5ml.py new-livery <car> [--png f] a NEW livery slot for any car (clone + database entry,
                                            unlocked); --png paints it, else a colour shift

Engine: scripts/d5mod.py (original packs are never written; changed files go into
pack slot 0, files that change size are relocated into new chunks; restore = vanilla).
Set DIRT5_DAT to point at another install (or a sandbox), D5ML_MODS at another mods folder.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import d5mod  # noqa: E402
from d5x import Index  # noqa: E402

MODS_DIR = os.environ.get("D5ML_MODS", os.path.join(os.path.dirname(HERE), "mods"))


def _exact(path):
    """d5mod target for one exact file (direct lookup, no glob matching)."""
    return "=" + path


def _override(data: bytes):
    def t(_text, _v):
        return data.decode("latin1"), 1
    t.resize = True  # any size: d5mod relocates the file if the length changes
    return t


def _texture(png_path):
    def t(text, _v):
        import d5tex
        from PIL import Image
        orig = text.encode("latin1")
        try:
            d5tex.parse(orig)
        except ValueError as e:
            raise SystemExit(f"{png_path}: can't re-encode this texture ({e})")
        with Image.open(png_path) as im:
            return d5tex.build(orig, im).decode("latin1"), 1
    return t


# --- effects: textures generated from the ORIGINAL at apply time (mods ship no game art) ---

def _fx_hue(im, amount, **_):
    """rotate hue by `amount` degrees, keep brightness/saturation/alpha."""
    import numpy as np
    from PIL import Image
    rgba = im.convert("RGBA")
    hsv = np.array(rgba.convert("RGB").convert("HSV"), dtype=np.int32)
    hsv[..., 0] = (hsv[..., 0] + round(amount / 360 * 256)) % 256
    out = Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB").convert("RGBA")
    out.putalpha(rgba.getchannel("A"))
    return out


def _fx_saturate(im, amount, **_):
    from PIL import ImageEnhance
    a = im.convert("RGBA").getchannel("A")
    out = ImageEnhance.Color(im.convert("RGB")).enhance(amount).convert("RGBA")
    out.putalpha(a)
    return out


def _fx_invert(im, **_):
    from PIL import ImageOps
    rgba = im.convert("RGBA")
    out = ImageOps.invert(rgba.convert("RGB")).convert("RGBA")
    out.putalpha(rgba.getchannel("A"))
    return out


def _fx_overlay(im, image, box=None, **_):
    """composite the mod's own PNG (with alpha) onto the texture. box = [x, y, w, h] as
    fractions of the texture (default: whole texture), so it works for every mip/tier size."""
    from PIL import Image
    base = im.convert("RGBA")
    x, y, w, h = box or (0, 0, 1, 1)
    W, H = base.size
    with Image.open(image) as src:
        dec = src.convert("RGBA").resize((max(1, round(w * W)), max(1, round(h * H))), Image.LANCZOS)
    base.alpha_composite(dec, (round(x * W), round(y * H)))
    return base


EFFECTS = {"hue": _fx_hue, "saturate": _fx_saturate, "invert": _fx_invert, "overlay": _fx_overlay}


# --- colour-grade effects: operate on the graded OUTPUT colours of a LUT (render/luts/*.gtx) ---

def _grade_colours(c, saturation=1.0, contrast=1.0, brightness=1.0, hue=0.0, tint=None, gamma=1.0, **_):
    """Photo-style adjustments on linear colours c (..., 3)."""
    import numpy as np
    c = np.clip(c * brightness, 0, None)
    if gamma != 1.0:
        c = c ** (1.0 / gamma)
    luma = (c * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    c = luma + (c - luma) * saturation
    c = 0.18 + (c - 0.18) * contrast                        # pivot around mid grey (linear)
    if hue:
        a = np.deg2rad(hue)                                  # rotate around the grey axis
        k = np.ones(3, np.float32) / np.sqrt(3)
        c = (c * np.cos(a) + np.cross(k, c) * np.sin(a) + k * (c @ k)[..., None] * (1 - np.cos(a)))
    if tint:
        c = c * np.asarray(tint, np.float32)
    return np.clip(c, 0, 1)


def _lut_source(path):
    import d5tex
    idx = Index(ndx_path=d5mod.NDX_ORIG) if os.path.exists(d5mod.NDX_ORIG) else Index()
    try:
        data = idx.read(idx.find(path))
    except KeyError:
        raise SystemExit(f"lut effect: source {path} is not a game file")
    if not d5tex.is_lut(data):
        raise SystemExit(f"lut effect: {path} is not a colour-grading LUT")
    return d5tex.lut_read(data)


LUT_EFFECTS = {"grade", "lut"}
EFFECT_PARAMS = {  # effect -> allowed / required step keys (besides "effect")
    "hue": {"allowed": {"amount"}, "required": {"amount"}},
    "saturate": {"allowed": {"amount"}, "required": {"amount"}},
    "invert": {"allowed": set(), "required": set()},
    "overlay": {"allowed": {"image", "box"}, "required": {"image"}},
    "grade": {"allowed": {"saturation", "contrast", "brightness", "gamma", "hue", "tint", "mix"}, "required": set()},
    "lut": {"allowed": {"source", "mix"}, "required": {"source"}},
}
MOD_KEYS = {"name", "version", "author", "description", "recipes", "generate", "clone", "json", "text", "game_build", "url",
            "license"}


def validate_meta(name, meta):
    """Clear messages for typos in mod.json instead of tracebacks later."""
    extra = set(meta) - MOD_KEYS
    if extra:
        print(f"  warning: {name}/mod.json: unknown key(s) {', '.join(sorted(extra))} (known: {', '.join(sorted(MOD_KEYS))})")
    for i, g in enumerate(meta.get("generate", [])):
        where = f"{name}/mod.json generate[{i}]"
        if not isinstance(g, dict) or "target" not in g or "steps" not in g:
            raise SystemExit(f"{where}: needs \"target\" and \"steps\"")
        bad = set(g) - {"target", "exclude", "steps"}
        if bad:
            raise SystemExit(f"{where}: unknown key(s) {', '.join(sorted(bad))} (use target, exclude, steps)")
    if not isinstance(meta.get("recipes", []), list):
        raise SystemExit(f"{name}/mod.json: \"recipes\" must be a list, e.g. [\"uwu\", \"tipsy=2\"]")
    text = meta.get("text", {})
    tables = ([text] if not any(isinstance(v, dict) for v in text.values()) else list(text.values())) if isinstance(text, dict) else [None]
    if any(not isinstance(t, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in t.items()) for t in tables):
        raise SystemExit(f"{name}/mod.json: \"text\" must map LocID -> text, e.g. {{\"ID_SHORT_ADELE_JACQUET\": \"C. Handbrake\"}}, "
                         f"or per language {{\"*\": {{...}}, \"ger\": {{...}}}}")
    for j in meta.get("json", []):
        for op in _ops(j.get("set_object")):
            if not isinstance(op, dict) or "match" not in op or "set" not in op:
                raise SystemExit(f"{name}/mod.json json {j.get('file')}: set_object needs \"match\" and \"set\"")


def _generated(steps, mod_dir):
    """steps = [{"effect": "hue", "amount": 150}, {"effect": "overlay", "image": "decal.png", "box": [...]}]
    On colour-grading LUTs: {"effect": "grade", "saturation": 1.2, "contrast": 1.1, ...} and
    {"effect": "lut", "source": "data:textures/render/luts/pm_night_vision.gtx", "mix": 1}."""
    for st in steps:
        name = st.get("effect")
        if name not in EFFECT_PARAMS:
            raise SystemExit(f"unknown effect '{name}' (have: {', '.join(EFFECT_PARAMS)})")
        extra = set(st) - {"effect"} - EFFECT_PARAMS[name]["allowed"]
        missing = EFFECT_PARAMS[name]["required"] - set(st)
        if extra:
            raise SystemExit(f"effect '{name}': unknown parameter(s) {', '.join(sorted(extra))} "
                             f"(allowed: {', '.join(sorted(EFFECT_PARAMS[name]['allowed'])) or 'none'})")
        if missing:
            raise SystemExit(f"effect '{name}': missing {', '.join(sorted(missing))}")
        if "image" in st and not os.path.exists(os.path.join(mod_dir, st["image"])):
            raise SystemExit(f"effect '{name}': image '{st['image']}' not found in {mod_dir}")

    def t(text, _v):
        import d5tex
        orig = text.encode("latin1")
        if d5tex.is_lut(orig):
            lut = d5tex.lut_read(orig)
            for st in steps:
                args = {k: v for k, v in st.items() if k != "effect"}
                mix = float(args.pop("mix", 1.0))
                if st["effect"] == "grade":
                    new = _grade_colours(lut, **args)
                elif st["effect"] == "lut":
                    new = d5tex.lut_sample(_lut_source(args["source"]), lut)   # filter AFTER the track grade
                else:
                    raise SystemExit(f"effect '{st['effect']}' doesn't work on a colour LUT (use grade / lut)")
                lut = lut + (new - lut) * mix
            return d5tex.lut_write(orig, lut).decode("latin1"), 1
        im = d5tex.decode(orig)
        for st in steps:
            if st["effect"] in LUT_EFFECTS:
                raise SystemExit(f"effect '{st['effect']}' only works on colour LUTs (textures/render/luts/)")
            args = {k: v for k, v in st.items() if k != "effect"}
            if "image" in args:
                args["image"] = os.path.join(mod_dir, args["image"])
            im = EFFECTS[st["effect"]](im, **args)
        return d5tex.build(orig, im).decode("latin1"), 1
    return t


def with_tiers(path, known):
    """X.gtx -> [X.gtx, X_tier1.gmp, ...]: the streamed high-res levels of the same texture."""
    if not path.endswith(".gtx"):
        return [path]
    stem = path[:-4]
    return [path] + sorted(p for p in known if p.startswith(stem + "_tier") and p.endswith(".gmp"))


def load(name):
    """-> dict(name, dir, meta, files {pack path: local file}, textures {pack path: png})."""
    d = os.path.join(MODS_DIR, name)
    if not os.path.isdir(d):
        raise SystemExit(f"no mod '{name}' in {MODS_DIR}")
    meta = {}
    if os.path.exists(os.path.join(d, "mod.json")):
        with open(os.path.join(d, "mod.json"), encoding="utf-8") as f:
            try:
                meta = json.load(f)
            except json.JSONDecodeError as e:
                raise SystemExit(f"{name}/mod.json is not valid JSON: line {e.lineno}, column {e.colno}: {e.msg}")
        validate_meta(name, meta)
    files, textures = {}, {}
    for sub, out in (("files", files), ("textures", textures)):
        root = os.path.join(d, sub)
        for base, _, names in os.walk(root):
            for n in names:
                local = os.path.join(base, n)
                rel = os.path.relpath(local, root).replace(os.sep, "/")
                if sub == "textures":
                    if not rel.lower().endswith(".gtx.png"):
                        continue
                    rel = rel[:-4]
                out["data:" + rel] = local
    return {"name": name, "dir": d, "meta": meta, "files": files, "textures": textures}


def build_stamp(idx):
    """Identifies the game data a mod was made for: dat.ndx build time + file count."""
    import struct
    return f"{struct.unpack_from('<Q', idx.raw, 0x18)[0]}-{idx.entry_count}"


def check_build(mods, idx):
    here = build_stamp(idx)
    for m in mods:
        want = m["meta"].get("game_build")
        if want and want != here:
            print(f"  warning: {m['name']} was made for game build {want}, this install is {here}")


def all_mods():
    if not os.path.isdir(MODS_DIR):
        return []
    return sorted(n for n in os.listdir(MODS_DIR) if os.path.isdir(os.path.join(MODS_DIR, n)))


def generate_targets(g, known):
    """`target` / `exclude`: one glob or a list of globs over pack paths."""
    import fnmatch

    def globs(v):
        return [v] if isinstance(v, str) else list(v or [])
    inc, exc = globs(g.get("target")), globs(g.get("exclude"))
    return sorted(p for p in known if any(fnmatch.fnmatch(p, t) for t in inc)
                  and not any(fnmatch.fnmatch(p, x) for x in exc))


def fnv1a64(s: str) -> int:
    """Codemasters' name hash: livery Guids and the name hashes inside texture headers."""
    h = 0xCBF29CE484222325
    for c in s.encode("latin1"):
        h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


LANGS = ("bra", "eng", "fre", "ger", "ita", "jap", "kor", "sim", "spa")


def loc_id(key: str) -> int:
    """.loc entry id of a LocID name = FNV-1a-64 of the string (ID_LONG_ADELE_JACQUET -> "Adèle Jacquet";
    driverdata/vehicledata point at these names). A literal "0x..." id works too."""
    return int(key, 16) if key.lower().startswith("0x") else fnv1a64(key)


def text_tables(text):
    """mod.json "text" -> {lang: {entry id: text}}. {"ID_X": "..."} = every language;
    {"*": {...}, "ger": {...}} = default + per-language overrides. Unknown ids become NEW entries."""
    per_lang = bool(text) and all(isinstance(v, dict) for v in text.values())
    out = {}
    for lang in LANGS:
        t = dict(text.get("*", {}), **text.get(lang, {})) if per_lang else dict(text)
        if t:
            out[lang] = {loc_id(k): v for k, v in t.items()}
    return out


def clone_pairs(c, known):
    """clone {"from": "lancia_037_livery_03", "to": "lancia_037_livery_04", "in": "data:.../"}:
    every game file in `in` whose name starts with `from` -> same name with `to` instead."""
    frm, to, folder = c["from"], c["to"], c["in"]
    if len(frm) != len(to):
        raise SystemExit(f"clone: '{frm}' -> '{to}' must keep the name length (header strings are length-prefixed)")
    if not folder.endswith("/"):
        folder += "/"
    out = {}
    for p in sorted(known):
        if p.startswith(folder) and "/" not in p[len(folder):] and p[len(folder):].startswith(frm):
            new = folder + to + p[len(folder) + len(frm):]
            if new in known:
                raise SystemExit(f"clone: {new} already exists in the game")
            out[p] = new
    if not out:
        raise SystemExit(f"clone: nothing in {folder} starts with '{frm}'")
    return out


def _clone(src, frm, to, known):
    """New file = the source file with its own name strings and name hashes swapped, so
    textures (name + FNV-1a name hashes in the header) stay self-consistent."""
    folder = src[:src.rfind("/") + 1]
    stems = {p[len(folder):].rsplit(".", 1)[0] for p in known if p.startswith(folder + frm)}

    def t(_text, _v):
        idx = _orig_index()
        data = idx.read(idx.find(src))
        for stem in sorted(stems, key=len, reverse=True):
            new_stem = to + stem[len(frm):]
            data = data.replace(struct_q(fnv1a64(stem)), struct_q(fnv1a64(new_stem)))
        data = data.replace(frm.encode("latin1"), to.encode("latin1"))
        return data.decode("latin1"), 1
    t.resize = True
    return t


def struct_q(v):
    import struct
    return struct.pack("<Q", v)


def _ops(v):
    return [v] if isinstance(v, dict) else list(v or [])


def _obj_text(o):
    """One objectInstances entry in the game's own layout (4-space indent, "key":value)."""
    return "    " + json.dumps(o, indent=2, ensure_ascii=False).replace("\n", "\n    ").replace('": ', '":')


def _json_patch(j):
    """{"file": ..., "clone_object": {"match": {"Name": "x"}, "set": {"Name": "y", ...}}}:
    copy a matching entry of objectInstances, apply `set`, give it the next id and - if the
    Name changed and no Guid is set - Guid = FNV-1a(Name).
    {"file": ..., "set_object": {"match": {...}, "set": {...}, "all": false}}: change entries in
    place (exactly one match unless "all": true). Only touched objects are rewritten, the rest
    of the file stays byte-identical."""
    import copy
    import re

    def t(text, _v):
        raw = text.encode("latin1")
        body = raw.rstrip(b"\0")
        tail = raw[len(body):]
        doc = json.loads(body.decode("utf-8"))
        objs = doc["objectInstances"]
        new_objs = []
        for op in ([j["clone_object"]] if isinstance(j.get("clone_object"), dict) else j.get("clone_object", [])):
            src = [o for o in objs if all(o.get(k) == v for k, v in op["match"].items())]
            if len(src) != 1:
                raise SystemExit(f"json patch {j['file']}: match {op['match']} found {len(src)} entries (need exactly 1)")
            o = copy.deepcopy(src[0])
            o.update(op.get("set", {}))
            o["id"] = max(x["id"] for x in objs + new_objs) + 1
            if "Guid" in o and "Guid" not in op.get("set", {}) and o.get("Name") != src[0].get("Name"):
                o["Guid"] = fnv1a64(o["Name"])
            new_objs.append(o)
        s = body.decode("utf-8")
        changed = 0
        for op in _ops(j.get("set_object")):
            hits = [o for o in objs if all(o.get(k) == v for k, v in op["match"].items())]
            if not hits or (len(hits) > 1 and not op.get("all")):
                raise SystemExit(f"json patch {j['file']}: set_object match {op['match']} found {len(hits)} entries "
                                 f"(need exactly 1, or \"all\": true)")
            for o in hits:
                o.update(op["set"])
                m = re.search(r'\n    \{\n      "id":%d,\n' % o["id"], s)
                end = s.find("\n    }", m.end()) if m else -1
                if end < 0:
                    raise SystemExit(f"json patch {j['file']}: object id {o['id']} not in the expected layout")
                s = s[:m.start() + 1] + _obj_text(o) + s[end + len("\n    }"):]
                changed += 1
        end = s.rstrip().rstrip("}").rstrip()          # ... last object "}" + newline + "]"
        if not end.endswith("]"):
            raise SystemExit(f"json patch {j['file']}: unexpected layout (objectInstances must be last)")
        insert = "".join(",\n" + _obj_text(o) for o in new_objs)
        k = len(end) - 1                               # position of the closing "]"
        head = s[:k].rstrip()
        out = head + insert + "\n  " + s[k:]
        json.loads(out)                                 # must still parse
        return (out.encode("utf-8") + tail).decode("latin1"), len(new_objs) + changed
    t.resize = True
    return t


def specs_for(mods, idx):
    """Register each mod's files/textures/effects as a d5mod entry; -> ordered d5mod specs.
    Validates every target path against the index first (clear errors)."""
    import fnmatch
    known = {e["path"] for e in idx.files()}
    specs = []
    for m in mods:
        for p in m["textures"]:
            if p not in known:
                raise SystemExit(f"{m['name']}: {p} is not a game texture (a .gtx.png needs an existing "
                                 f"texture to take format/size from - put brand-new files into files/)")
        # files/ that aren't in the game yet become NEW files ("+path": created in the index)
        targets = [(("=" if p in known else "+") + p, _override(open(f, "rb").read())) for p, f in m["files"].items()]
        for p, f in m["textures"].items():
            targets += [(_exact(q), _texture(f)) for q in with_tiers(p, known)]
        # clones first (new files), so json patches and effects can build on them
        cloned = {}
        for c in m["meta"].get("clone", []):
            for src, dst in clone_pairs(c, known).items():
                e = idx.find(src)
                if not os.path.exists(idx.pack_path(idx.chunk(e["first_chunk"])[0])):
                    continue                    # source pack not shipped (e.g. *_tier3.gmp)
                cloned[dst] = src
                targets.append(("+" + dst, _clone(src, c["from"], c["to"], known)))
        for j in m["meta"].get("json", []):
            if j["file"] not in known:
                raise SystemExit(f"{m['name']}: json patch target {j['file']} is not a game file")
            targets.append(("=" + j["file"], _json_patch(j)))
        for lang, ids in text_tables(m["meta"].get("text", {})).items():
            targets.append((f"{d5mod.LOC}{lang}.loc", d5mod._loc_set_ids(ids)))      # pc, ps4 and xbox copies
        pool = known | set(cloned)
        for g in m["meta"].get("generate", []):
            hits = generate_targets(g, pool)
            if not hits:
                raise SystemExit(f"{m['name']}: generate target '{g['target']}' matches no game file")
            fx = _generated(g["steps"], m["dir"])
            for p in hits:
                targets += [(("+" if q in cloned else "=") + q, fx) for q in with_tiers(p, pool)]
        specs += list(m["meta"].get("recipes", []))
        if targets:
            key = f"d5ml:{m['name']}"
            d5mod.MODS[key] = (m["meta"].get("description", m["name"]), 1.0, targets)
            specs.append(key)
    return specs


def touched(m, idx):
    """Pack paths a mod changes (files, textures, effects and what its recipes edit)."""
    import fnmatch
    known = {e["path"] for e in idx.files()}
    paths = set(m["files"])
    for p in m["textures"]:
        paths |= set(with_tiers(p, known))
    cloned = set()
    for c in m["meta"].get("clone", []):
        cloned |= set(clone_pairs(c, known).values())
    paths |= cloned | {j["file"] for j in m["meta"].get("json", [])}
    langs = text_tables(m["meta"].get("text", {}))
    paths |= {p for p in known for lang in langs if fnmatch.fnmatch(p, f"{d5mod.LOC}{lang}.loc")}
    for g in m["meta"].get("generate", []):
        for p in generate_targets(g, known | cloned):
            paths |= set(with_tiers(p, known | cloned))
    if m["meta"].get("recipes"):
        edits, _, _ = d5mod.compute(idx, list(m["meta"]["recipes"]), quiet=True)
        paths |= set(edits)
    return paths


def conflicts(mods, idx):
    owners = {}
    for m in mods:
        for p in touched(m, idx):
            owners.setdefault(p, []).append(m["name"])
    return {p: o for p, o in owners.items() if len(o) > 1}


def cmd_list_json():
    out = []
    for n in all_mods():
        m = load(n)
        meta = m["meta"]
        prev = os.path.join(m["dir"], "preview.png")
        out.append({"id": n, "name": meta.get("name", n), "version": meta.get("version", ""),
                    "author": meta.get("author", ""), "description": meta.get("description", ""),
                    "files": len(m["files"]), "textures": len(m["textures"]),
                    "effects": len(meta.get("generate", [])), "recipes": meta.get("recipes", []),
                    "preview": prev if os.path.exists(prev) else None, "dir": m["dir"]})
    print(json.dumps(out, indent=1))


def cmd_install(src):
    """zip or folder -> mods/<id>/. The mod root is the folder that holds mod.json."""
    import shutil
    import tempfile
    import zipfile
    tmp = None
    if os.path.isfile(src) and src.lower().endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="d5ml_")
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():  # no absolute paths / .. escapes
                if n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/"):
                    raise SystemExit(f"refusing unsafe path in zip: {n}")
            z.extractall(tmp)
        src_dir = tmp
    elif os.path.isdir(src):
        src_dir = src
    else:
        raise SystemExit(f"not a .zip or folder: {src}")
    roots = [b for b, _, names in os.walk(src_dir) if "mod.json" in names]
    if not roots:
        raise SystemExit("no mod.json found - is this a d5ml mod?")
    root = min(roots, key=len)
    with open(os.path.join(root, "mod.json"), encoding="utf-8") as f:
        meta = json.load(f)
    mod_id = os.path.basename(root.rstrip("/\\")) if root != src_dir else os.path.splitext(os.path.basename(src))[0]
    mod_id = "".join(c if c.isalnum() or c in "-_." else "-" for c in mod_id) or "mod"
    dest = os.path.join(MODS_DIR, mod_id)
    if os.path.exists(dest):
        raise SystemExit(f"{dest} already exists - remove it first to reinstall")
    shutil.copytree(root, dest)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"installed '{meta.get('name', mod_id)}' {meta.get('version', '')} -> {dest}")


def cmd_list():
    names = all_mods()
    if not names:
        print(f"no mods in {MODS_DIR}")
    for n in names:
        m = load(n)
        meta = m["meta"]
        print(f"  {n:<24} v{meta.get('version', '?'):<7} {meta.get('description', '')}")
        print(f"  {'':<24} {len(m['files'])} file(s), {len(m['textures'])} texture(s), "
              f"{len(meta.get('generate', []))} effect(s), recipes: {' '.join(meta.get('recipes', [])) or '-'}")


def _orig_index():
    return Index(ndx_path=d5mod.NDX_ORIG) if os.path.exists(d5mod.NDX_ORIG) else Index()


def _find(idx, pattern):
    import fnmatch
    if any(c in pattern for c in "*?["):
        return [e for e in idx.files() if fnmatch.fnmatch(e["path"], pattern)]
    return [e for e in idx.files() if pattern.lower() in e["path"].lower()]


def cmd_search(words):
    idx = _orig_index()
    hits = [e for e in idx.files() if all(w.lower() in e["path"].lower() for w in words)]
    for e in hits[:200]:
        print(f"  {e['size']:>10}  {e['path']}")
    print(f"{len(hits)} file(s)" + (" (first 200 shown)" if len(hits) > 200 else ""))


def cmd_new(name, description=""):
    d = os.path.join(MODS_DIR, name)
    if os.path.exists(d):
        raise SystemExit(f"{d} already exists")
    for sub in ("files", "textures"):
        os.makedirs(os.path.join(d, sub))
    meta = {"name": name, "version": "0.1.0", "author": "", "description": description,
            "recipes": [], "game_build": build_stamp(_orig_index())}
    with open(os.path.join(d, "mod.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"created {d}")
    print(f"  next: python d5ml.py extract {name} <file or word>, edit, then apply {name}")


LIVERY_DIR = "data:textures/vehicles/liveries/"
LIVERY_DB = "data:event/liverydata/liverydata.json"


def cmd_new_livery(car, png=None):
    """mods/<car>-livery-NN/: a brand-new livery slot for any car - clone of the car's last
    texture livery (all files: colour, mask, streamed tiers) + a new liverydata entry, unlocked
    for everyone. --png paints it (see the *.guide.png from `extract` for where it shows),
    otherwise it gets a colour shift so you can spot it in livery select."""
    import re
    import shutil
    idx = _orig_index()
    known = {e["path"] for e in idx.files()}
    rx = re.compile(re.escape(LIVERY_DIR + car) + r"_livery_(\d\d)\.gtx$")
    have = sorted(int(m.group(1)) for m in (rx.match(p) for p in known) if m)
    if not have:
        raise SystemExit(f"no livery textures for '{car}' - car ids: python d5ml.py search livery_01.gtx")
    db = [o for o in json.loads(idx.read(idx.find(LIVERY_DB)).rstrip(b"\0"))["objectInstances"] if o.get("type") == "LvrDta"]
    # texture liveries: database Name == texture name (any case) and index == its number (212 of 212)
    by_name = {o["Name"].lower(): o for o in db}
    cands = [n for n in reversed(have) if f"{car}_livery_{n:02d}" in by_name]
    # prefer a normal livery as the source (2 of 391 are RaceNet rewards, hidden without a sign-in)
    src_n = next((n for n in cands if not by_name[f"{car}_livery_{n:02d}"].get("isRacenet")), cands[0] if cands else None)
    if src_n is None:
        raise SystemExit(f"{car}: its livery textures have no livery-database entry (unused or editor-recipe car)")
    src = by_name[f"{car}_livery_{src_n:02d}"]
    used = {o["index"] for o in db if o.get("Vehicle ID") == src["Vehicle ID"]}
    new_n = max(max(have), max(used)) + 1
    if new_n > 99:
        raise SystemExit(f"{car}: no free two-digit livery number left")
    new = f"{car}_livery_{new_n:02d}"
    new_db_name = src["Name"][:-2] + f"{new_n:02d}"         # keeps the car's own spelling, e.g. Alpine_..._Livery_04
    index = new_n
    cars = json.loads(idx.read(idx.find("data:event/vehicledata/vehicledata.json")).rstrip(b"\0"))["objectInstances"]
    pretty = next((c["Name"] for c in cars if c.get("Guid") == src["Vehicle ID"]), car)
    d = os.path.join(MODS_DIR, f"{car}-livery-{new_n:02d}")
    if os.path.exists(d):
        raise SystemExit(f"{d} already exists")
    os.makedirs(d)
    if png:
        shutil.copy(png, os.path.join(d, "livery.png"))
        steps = [{"effect": "overlay", "image": "livery.png"}]
    else:
        steps = [{"effect": "hue", "amount": 180}, {"effect": "saturate", "amount": 1.3}]
    meta = {
        "name": f"{pretty} - livery {new_n:02d} (NEW)", "version": "0.1.0", "author": "",
        "description": f"a new livery slot for the {pretty}: {car}_livery_{src_n:02d} cloned to {new}, unlocked for everyone",
        "clone": [{"from": f"{car}_livery_{src_n:02d}", "to": new, "in": LIVERY_DIR}],
        "json": [{"file": LIVERY_DB, "clone_object": {"match": {"Name": src["Name"]}, "set": {
            "Name": new_db_name, "index": index, "Recipe Path": "", "Event Unlock": [], "Sponsor": 0, "SponsorRank": 0,
            "PlayerLevel": 0, "Entitlement": 0, "isRacenet": False}}}],     # RaceNet liveries want a sign-in
        "generate": [{"target": f"{LIVERY_DIR}{new}.gtx", "steps": steps}],
        "game_build": build_stamp(idx),
    }
    with open(os.path.join(d, "mod.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"created {d}  ({pretty}: livery {src_n:02d} -> {new_n:02d})")
    if not png:
        print(f"  paint it: python d5ml.py extract {os.path.basename(d)} {car}_livery_{src_n:02d}.gtx  -> PNG + .guide.png,")
        print(f"  save your picture as {os.path.join(d, 'livery.png')} and use {{\"effect\": \"overlay\", \"image\": \"livery.png\"}}")
    print(f"  then: python d5ml.py apply {os.path.basename(d)}   (livery select: the new tile is the last one)")


def cmd_extract(name, pattern, raw=False):
    import d5tex
    d = os.path.join(MODS_DIR, name)
    if not os.path.isdir(d):
        raise SystemExit(f"no mod '{name}' - create it first: python d5ml.py new {name}")
    idx = _orig_index()
    hits = _find(idx, pattern)
    if not hits:
        raise SystemExit(f"nothing matches '{pattern}' (try: python d5ml.py search <word>)")
    if len(hits) > 300:
        raise SystemExit(f"{len(hits)} files match '{pattern}' - narrow it down")
    known = {e["path"]: e for e in idx.files()}

    def readable(e):
        return os.path.exists(idx.pack_path(idx.chunk(e["first_chunk"])[0]))
    hits = [e for e in hits if readable(e)]
    tiered = {e["path"] for e in hits if e["path"].endswith(".gtx")}
    for e in hits:
        rel = e["path"].split(":", 1)[1]
        if not raw and e["path"].endswith(".gmp") and any(e["path"].startswith(t[:-4] + "_tier") for t in tiered):
            continue  # a streamed level of a texture we export as one PNG anyway
        data = idx.read(e)
        if rel.endswith(".gtx") and not raw:
            try:
                # edit at the best installed resolution: the highest *_tierN.gmp if there is one
                tiers = [known[q] for q in with_tiers(e["path"], known)[1:] if readable(known[q])]
                src = idx.read(tiers[-1]) if tiers else data
                out = os.path.join(d, "textures", *rel.split("/")) + ".png"
                os.makedirs(os.path.dirname(out), exist_ok=True)
                im = d5tex.decode(src)
                im.save(out)
                print(f"  texture  {out}  ({im.width}x{im.height}{', from ' + tiers[-1]['path'].rsplit('/', 1)[-1] if tiers else ''})")
                guide = livery_guide(idx, known, e["path"], im)
                if guide is not None:
                    gpath = out[:-len(".gtx.png")] + ".guide.png"   # not picked up by apply
                    guide.save(gpath)
                    print(f"  guide    {gpath}  (paint mask overlay - where the livery shows on the car)")
                continue
            except ValueError as ex:
                print(f"  (texture {rel}: {ex} - copied raw)")
        out = os.path.join(d, "files", *rel.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(data)
        print(f"  file     {out}")
    print(f"{len(hits)} file(s) extracted into {d}")


def livery_guide(idx, known, path, im):
    """For a car livery X.gtx: the livery with its paint mask X_m.gtx laid over it, so painters
    see which regions of the UV sheet are body paint. None for other textures."""
    import d5tex
    from PIL import Image
    if "/vehicles/liveries/" not in path or path.endswith("_m.gtx"):
        return None
    mask_path = path[:-4] + "_m.gtx"
    if mask_path not in known:
        return None
    cands = [known[q] for q in with_tiers(mask_path, known)]
    cands = [e for e in cands if os.path.exists(idx.pack_path(idx.chunk(e["first_chunk"])[0]))]
    if not cands:
        return None
    mask = d5tex.decode(idx.read(cands[-1])).convert("RGB").resize(im.size)
    base = im.convert("RGB")
    return Image.blend(base, mask, 0.55)


def cmd_doctor():
    """Environment + install self-check, for bug reports."""
    import importlib
    import platform
    import struct
    ok = True

    def line(good, text):
        nonlocal ok
        ok &= good
        print(f"  [{'ok' if good else '!!'}] {text}")
    print(f"python {platform.python_version()} on {platform.platform()}")
    for mod in ("lz4", "numpy", "PIL"):
        try:
            m = importlib.import_module(mod)
            line(True, f"{mod} {getattr(m, '__version__', '')}")
        except ImportError:
            line(False, f"{mod} missing - run: python -m pip install lz4 numpy pillow")
    from d5x import GAME_DAT
    ndx = os.path.join(GAME_DAT, "index", "dat.ndx")
    line(os.path.exists(ndx), f"game data: {GAME_DAT}")
    if not os.path.exists(ndx):
        print("  set the game folder in the D5ML window (Game folder...) or DIRT5_DAT=<game>\\dat")
        return 1
    raw = open(ndx, "rb").read(0x30)
    version = struct.unpack_from("<I", raw, 8)[0]
    line(version == 5, f"dat.ndx version {version} (D5ML knows 5)")
    idx = _orig_index()
    missing = [p for i, p in enumerate(idx.packs) if not os.path.exists(idx.pack_path(i))]
    print(f"  [..] {len(idx.packs) - len(missing)} of {len(idx.packs)} pack slots installed "
          f"(normal: slots for other platforms are absent)")
    print(f"  [..] game build stamp {build_stamp(idx)}")
    line(os.access(os.path.dirname(ndx), os.W_OK), "index folder writable (needed for apply/restore)")
    backup = os.path.exists(d5mod.NDX_ORIG)
    print(f"  [..] backup dat.ndx.d5x-orig: {'present' if backup else 'not yet (created on first apply)'}")
    d5mod.status()
    print(f"  [..] mods folder: {MODS_DIR} ({len(all_mods())} mod(s))")
    for n in all_mods():
        try:
            specs_for([load(n)], idx)       # validates mod.json, targets and effect parameters
        except SystemExit as e:
            line(False, f"mod {n}: {e}")
    print("all good" if ok else "problems found - see [!!] lines")
    return 0 if ok else 1


def cmd_check(names):
    idx = _orig_index()
    mods = [load(n) for n in names]
    check_build(mods, idx)
    specs = specs_for(mods, idx)
    edits, applied, _ = d5mod.compute(idx, specs, quiet=True)
    for a in applied:
        print(f"  ok  {a['mod']}: {a['edits']} change(s)")
    for p, (e, data) in sorted(edits.items()):
        note = (f"NEW file, {len(data)} B" if e.get("new") else
                "same size" if len(data) == e["size"] else f"{e['size']} -> {len(data)} B (relocated)")
        print(f"      {p}  [{note}]")
    for p, owners in sorted(conflicts(mods, idx).items()):
        print(f"  conflict: {p}: {' < '.join(owners)}  ({owners[-1]} wins)")
    print(f"{len(edits)} file(s) would change")


def cmd_apply(names):
    idx = _orig_index()
    mods = [load(n) for n in names]
    check_build(mods, idx)
    for p, owners in sorted(conflicts(mods, idx).items()):
        print(f"  conflict: {p}: {' < '.join(owners)}  ({owners[-1]} wins)")
    d5mod.apply(specs_for(mods, idx))
    print("launch offline, e.g.: .\\scripts\\Start-Dirt5Modded.ps1 -FastBoot   (adds --uselocalhandlingdefs)")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "list" and "--json" in argv:
        cmd_list_json()
    elif cmd == "list":
        cmd_list()
    elif cmd == "install" and len(argv) > 2:
        cmd_install(argv[2])
    elif cmd == "check" and len(argv) > 2:
        cmd_check(argv[2:])
    elif cmd == "apply" and len(argv) > 2:
        cmd_apply(argv[2:])
    elif cmd == "search" and len(argv) > 2:
        cmd_search(argv[2:])
    elif cmd == "new" and len(argv) > 2:
        cmd_new(argv[2], " ".join(argv[3:]))
    elif cmd == "new-livery" and len(argv) > 2:
        cmd_new_livery(argv[2], argv[argv.index("--png") + 1] if "--png" in argv else None)
    elif cmd == "extract" and len(argv) > 3:
        cmd_extract(argv[2], argv[3], raw="--raw" in argv)
    elif cmd == "doctor":
        return cmd_doctor()
    elif cmd == "restore":
        d5mod.restore()
    elif cmd == "status":
        d5mod.status()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
