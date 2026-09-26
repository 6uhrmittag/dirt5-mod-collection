"""d5mod - apply/restore DIRT 5 data mods on the loose install (C:\\Games\\DIRT 5).

How a mod is applied (never touches the original N_*.dat packs):
  1. dat.ndx is backed up once to dat.ndx.d5x-orig; every `apply` starts from it.
  2. The chunks holding each edited file are decompressed, the file bytes are
     replaced *in place with identical length* (numbers rewritten, whitespace
     shrunk/padded to fit), and the chunk is LZ4-recompressed.
  3. Recompressed chunks are written to pack slot 0 (0_DISC_INIT.dat, a slot
     that is listed in dat.ndx but not shipped), and only those chunk records
     in dat.ndx are repointed there.
  `restore` puts the original dat.ndx back and deletes 0_DISC_INIT.dat.

Usage:
  python d5mod.py list
  python d5mod.py check [<mod>[=value] ...]      dry run, writes nothing (default: every mod)
  python d5mod.py apply <mod|preset>[=value] [...]   e.g. apply beschwipst  /  apply roulette=3
  python d5mod.py restore
  python d5mod.py status
"""
import hashlib
import json
import os
import re
import shutil
import struct
import sys

import lz4.block

from d5x import CHUNK_REC, ENTRY_SIZE, GAME_DAT, Index

MOD_PACK = 0  # "0_DISC_INIT": listed in the index, absent from the install
NDX = os.path.join(GAME_DAT, "index", "dat.ndx")
NDX_ORIG = NDX + ".d5x-orig"
STATE = os.path.join(GAME_DAT, "index", "d5mod-state.json")
VDEFS = "data:physics/vehicledefs/"


def _num(v):
    return f"{v:.3f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def sub_numbers(text, key, fn):
    """Rewrite the first number after every `key` token: key<ws>NUMBER -> fn(NUMBER).
    Skips commented-out lines (`# key ...`); counts only values that really change."""
    pat = re.compile(rf"((?<![A-Za-z_]){re.escape(key)}[ \t\":]+)(-?\d+(?:\.\d+)?)")
    changed = 0

    def rep(m):
        nonlocal changed
        line_start = text.rfind("\n", 0, m.start()) + 1
        if "#" in text[line_start:m.start()]:
            return m.group(0)
        old = float(m.group(2))
        new = fn(old)
        if new == old:
            return m.group(0)
        changed += 1
        return m.group(1) + _num(new)
    return pat.sub(rep, text), changed


# --- mod catalogue -----------------------------------------------------------
# Each mod: (description, default value, [(glob-or-path, transform(text, value) -> (text, n))])

def _gravity(text, v):
    return sub_numbers(text, "ExtraGravityFactor", lambda _: v)


def _torque(text, v):
    return sub_numbers(text, "MaxTorque_Nm", lambda x: x * v)


def _mass(text, v):
    return sub_numbers(text, "Mass", lambda x: x * v)


def _json_field_by_name(names, field, fn):
    """In objectInstances, rewrite `field` of every instance whose Name is in names."""
    def t(text, v):
        n_total = 0
        for name in names:
            pat = re.compile(rf'("Name":"{re.escape(name)}"[^}}]*?"{field}":)(-?\d+(?:\.\d+)?)', re.S)
            text, n = pat.subn(lambda m: m.group(1) + f"{fn(float(m.group(2)), v):.6f}", text)
            n_total += n
        return text, n_total
    return t


def _scale(*keys, only_positive=True):
    """Multiply the number after each key by the mod value. Negative numbers are
    engine sentinels ("-1 = use default") and stay untouched."""
    def t(text, v):
        total = 0
        for key in keys:
            text, n = sub_numbers(text, key, lambda x: x * v if (x > 0 or not only_positive) else x)
            total += n
        return text, total
    return t


def _set(key, value):
    """Force the number after `key` to a fixed value (ignores the mod value)."""
    return lambda text, _: sub_numbers(text, key, lambda _x: value)


def _with(key, factor):
    """Scale `key` by a fixed factor that comes with the mod (ignores the mod value)."""
    return lambda text, _: sub_numbers(text, key, lambda x: x * factor if x > 0 else x)


def _setv(key):
    """Set `key` to the mod value itself."""
    return lambda text, v: sub_numbers(text, key, lambda _x: v)


def _loc_swap(pairs):
    """Swap UI strings in a .loc file. Entries are [u64 id][u32 byte length][UTF-8 text];
    a replacement must have the SAME byte length (shorter ones are space-padded)."""
    def t(text, _v):
        n_total = 0
        for old, new in pairs:
            ob, nb = old.encode("utf-8"), new.encode("utf-8")
            if len(nb) > len(ob):
                raise SystemExit(f"loc replacement too long: {new!r} ({len(nb)} > {len(ob)} bytes)")
            nb += b" " * (len(ob) - len(nb))
            pre = struct.pack("<I", len(ob)).decode("latin1")
            n = text.count(pre + ob.decode("latin1"))
            text = text.replace(pre + ob.decode("latin1"), pre + nb.decode("latin1"))
            n_total += n
        return text, n_total
    return t


PARTY_ENG = [
    ("START EVENT", "NOCH EINS!!"), ("QUIT", "BETT"), ("NEW LAP!", "PROST!!!"),
    ("FINAL LAP!", "LAST ORDER"), ("FREE PLAY", "FREIBIER!"), ("RESTART", "NOCHMAL"),
    ("RESET TO TRACK", "WO BIN ICH?!?!"),
    ("Certain game modes and features are only available with the latest game updates. "
     "Please ensure that you have the latest version.",
     "Wasserpause! Trink zwischendurch ein Glas Wasser. Wer verliert, holt die Chips. "
     "Um 2 Uhr ist wirklich Schluss. Versprochen."),
]
PARTY_GER = [
    ("EVENT BEGINNEN", "EINS GEHT NOCH"), ("BEENDEN", "PENNEN!"), ("NEUE RUNDE!", "NOCH EINE!!"),
    ("LETZTE RUNDE!", "SPERRSTUNDE!!"), ("FREE PLAY", "FREIBIER!"), ("NEU STARTEN", "AUF EIN NEU"),
    ("AUF STRECKE SETZEN", "WO BIN ICH DENN?!?"),
    ("Manche Spielmodi und Features sind nur mit den neuesten Spiel-Updates verfügbar. "
     "Bitte stelle sicher, dass du über die neueste Version verfügst.",
     "Wasserpause! Trink zwischendurch ein Glas Wasser. Wer verliert, holt die Chips. "
     "Um 2 Uhr ist wirklich Schluss. Versprochen."),
]
LOC = "data:localisation/*/"


def _loc_swap_resize(pairs):
    """Like _loc_swap but replacements may be LONGER: the entry's length prefix is
    rewritten and the container's 'bytes remaining' header field (a u32 near 0xac whose
    value = file size - its own end) is grown to match. The file is then relocated."""
    def t(text, _v):
        raw = text.encode("latin1")
        size_at = next(p for p in range(0x40, 0x100) if struct.unpack_from("<I", raw, p)[0] == len(raw) - p - 4)
        n = 0
        for old, new in pairs:
            ob, nb = old.encode("utf-8"), new.encode("utf-8")
            a, b = struct.pack("<I", len(ob)) + ob, struct.pack("<I", len(nb)) + nb
            n += raw.count(a)
            raw = raw.replace(a, b)
        raw = bytearray(raw)
        struct.pack_into("<I", raw, size_at, len(raw) - size_at - 4)
        return bytes(raw).decode("latin1"), n
    t.resize = True
    return t


PARTY_XL_ENG = [("START EVENT", "ONE MORE RACE!!"), ("QUIT", "GO TO BED"), ("NEW LAP!", "PROST! NEW LAP!"),
                ("FINAL LAP!", "LAST ORDERS, MATE!"), ("FREE PLAY", "FREE BEER PLAY")]
PARTY_XL_GER = [("EVENT BEGINNEN", "NOCH EIN RENNEN!"), ("BEENDEN", "INS BETT GEHEN"),
                ("NEUE RUNDE!", "PROST! NEUE RUNDE!"), ("LETZTE RUNDE!", "LETZTE RUNDE, DANN BETT!"),
                ("FREE PLAY", "FREIBIER-MODUS")]

# AI drivers are plain .loc entries of the form "A. Jacquet" (57 of them, 5..12 bytes).
STAMMTISCH = ["Tante Erna", "Onkel Uwe", "Opa Heinz", "Der Wirt", "Kalle", "Hansi", "Der Kellner",
              "Frau Mueller", "Stammgast", "Bierdeckel", "Korn-Klaus", "Pils-Peter", "Zapfhahn",
              "Radler-Rudi", "Kurze Karin", "Tresen-Toni", "Mett-Manni", "Kater", "Promille",
              "Nachbar", "Taxi-Tom", "Schlafmuetze", "Sandmann", "Nachtschicht", "Brezel-Bernd",
              "Fritten-Fred", "Oma Lise", "Kiosk-Kai", "Spaetkauf", "Karaoke-Kim", "Mitternacht",
              "Absacker", "Wegbier", "Schnapsidee", "Chips-Chris", "Fahrer-Fritz", "Nuechtern",
              "Gerd", "Moni", "Ede", "Uwe", "Schorle", "Kurzer", "Lokalrunde", "Tischkicker"]


LOBBY = ["xXDriftGodXx", "N00bSlayer", "Sk8erBoi", "Touch Grass", "Big Chungus", "Ping 999ms",
         "AFK Andy", "360NoScope", "Rage Quit", "Git Gud", "Sussy Baka", "Nyan Cat", "Rickroll",
         "F in chat", "Stonks", "No Brakes", "Drift King", "L + Ratio", "W Rizz", "Skibidi",
         "Sigma", "NPC #42", "Lag Lord", "Bruh", "Yeet", "Pog Champ", "Mod Abuse", "Speedrun",
         "Cringe", "Main Char", "Ohio Rizz", "Lil Drifty", "Mom's Car", "Tryhard", "Ez Clap",
         "Glitch", "Uwu", "Owo", "Nerf This", "Hacker!!1", "Low FPS", "Wifi Down", "Tutorial"]


def _rename_ai(pool):
    """Every 'X. Surname' loc entry -> a pick from `pool` of at most the same byte length
    (space-padded; the same original name always gets the same pick)."""
    pat = re.compile(r"([\x03-\x20])\x00\x00\x00([A-Z]\. [A-Z][A-Za-z'\-]+)")

    def t(text, _v):
        n = 0

        def rep(m):
            nonlocal n
            size, name = ord(m.group(1)), m.group(2)
            if len(name) != size:  # not a whole entry
                return m.group(0)
            fits = [s for s in pool if len(s) <= size]
            pick = fits[int(hashlib.md5(name.encode()).hexdigest(), 16) % len(fits)]
            n += 1
            return m.group(1) + "\x00\x00\x00" + pick.ljust(size)
        return pat.sub(rep, text), n
    return t


def _loc_entries(raw: bytes):
    """(offset, length) of every [u64 id][u32 len][text] entry; the table runs to EOF."""
    for start in range(0, 4096):
        out, i = [], start
        while i + 12 <= len(raw):
            ln = struct.unpack_from("<I", raw, i + 8)[0]
            if ln > 20000 or i + 12 + ln > len(raw):
                break
            out.append((i + 12, ln))
            i += 12 + ln
        if i == len(raw) and len(out) > 1000:
            return out
    raise SystemExit("not a .loc string table")


def _loc_map(fn):
    """Apply fn(str) -> str (same UTF-8 byte length!) to every UI string of a .loc."""
    def t(text, _v):
        raw = bytearray(text.encode("latin1"))
        n = 0
        for off, ln in _loc_entries(bytes(raw)):
            old = raw[off:off + ln].decode("utf-8", "replace")
            new = fn(old).encode("utf-8")
            if len(new) == ln and new != raw[off:off + ln]:
                raw[off:off + ln] = new
                n += 1
        return raw.decode("latin1"), n
    return t


def _texture(fn):
    """Texture mod: decode the original .gtx, fn(path, PIL image) -> image, re-encode (BC1,
    same byte size). The art is generated from the game's own texture at apply time."""
    def t(text, _v, path=""):
        import d5tex
        orig = text.encode("latin1")
        new = d5tex.build(orig, fn(path, d5tex.decode(orig)))
        return new.decode("latin1"), 1
    t.wants_path = True
    return t


def _uwu_title(path, img):
    import d5art
    return d5art.uwu_title(img, eyes=path.endswith("/startScreen.gtx"))


def _uwu(s):
    """r/l -> w outside [0] placeholders, <laughs> subtitle tags and %-codes."""
    out, depth = [], 0
    for k, c in enumerate(s):
        if c in "[<{":
            depth += 1
        elif c in "]>}":
            depth = max(0, depth - 1)
        elif depth == 0 and not (k and s[k - 1] == "%"):
            c = {"r": "w", "l": "w", "R": "W", "L": "W"}.get(c, c)
        out.append(c)
    return "".join(out)

RUBBER = ["rubberband_midrangeBand_frictionMultiplier", "rubberband_farthestBand_frictionMultiplier"]
AI = "data:ai/ai_diff_params.json"
ALL = VDEFS + "*.vdef"
BASE = VDEFS + "_basecar.vdef"
GRIP = ["Friction_Smooth", "Friction_Dirt", "Friction_Rough", "Friction_Loose", "Friction_Ice"]
DAMPING = ["SpringLSCompressionDampingFactor", "SpringHSCompressionDampingFactor",
           "SpringLSReboundDampingFactor", "SpringHSReboundDampingFactor", "AntiRollDampFactor"]

MODS = {
    "gravity": ("ExtraGravityFactor for every car (stock 0.5 = arcade extra down-force; "
                "lower = floatier, negative = moon jumps)", -0.6,
                [(VDEFS + "_basecar.vdef", _gravity)]),
    "power": ("multiply MaxTorque_Nm of every car", 2.0, [(VDEFS + "*.vdef", _torque)]),
    "mass": ("multiply chassis Mass of every car", 0.5, [(VDEFS + "*.vdef", _mass)]),
    "norubberband": ("AI loses its catch-up grip bonus (stock 1.35 / 1.85)", 1.0,
                     [(AI, _json_field_by_name(RUBBER, "lowerParameterValue", lambda _, v: v)),
                      (AI, _json_field_by_name(RUBBER, "upperParameterValue", lambda _, v: v))]),
    "clumsyai": ("AI mistake probability (stock 0.05..0.25)", 0.6,
                 [(AI, _json_field_by_name(["mistake_probability"], "lowerParameterValue", lambda _, v: v)),
                  (AI, _json_field_by_name(["mistake_probability"], "upperParameterValue", lambda _, v: v))]),

    # --- party mods (2026-09-25): splitscreen, two pads, late night -------------
    "tipsy": ("beschwipst: centre of mass x value (stock ~0.4 m) and the anti-rollover "
              "assist mostly off - cars lean, wobble and tip over in corners", 2.5,
              [(ALL, _scale("CMHeight_m")), (ALL, _with("RollOverSpring", 0.1))]),
    "drehwurm": ("spinny: arcade yaw torque x value and yaw damping /5 - "
                 "the car wants to pirouette", 6.0,
                 [(BASE, _scale("ExtraYawTorqueScale")), (ALL, _with("YawRateDamping", 0.2))]),
    "glatteis": ("black ice: every tyre-vs-surface friction x value (stock 0.7..1.1)", 0.55,
                 [(ALL, _scale(*GRIP))]),
    "wackelpudding": ("jelly: suspension damping + anti-roll x value - cars bounce "
                      "and roll like a bouncy castle", 0.12,
                      [(ALL, _scale(*DAMPING)), (ALL, _scale("AntiRollSpring_G"))]),
    "windschatten": ("slipstream taxi: draft strength x value, 3x wider/longer - "
                     "whoever falls behind gets sucked back to the other", 6.0,
                     [(ALL, _scale("SlipStreamWakeStrength")), (ALL, _with("SlipStreamCentreWidth_m", 3.0)),
                      (ALL, _with("SlipStreamMaxAngle_deg", 3.0)), (ALL, _set("TimeBehindForFullSlipStream_s", 0.1))]),
    "einkaufswagen": ("shopping trolley: max steering angle x value (stock 37.5 deg)", 1.8,
                      [(ALL, _scale("MaxSteerAngle_deg"))]),
    "fallschirm": ("parachute: aero drag x value - slow-motion racing for the last round", 5.0,
                   [(ALL, _scale("DragCoef"))]),
    "flugstunde": ("flying lessons: in-air pitch/roll/yaw control x value, kicks in "
                   "earlier - steer your car mid-air (best with gravity)", 4.0,
                   [(ALL, _scale("PitchStrength", "RollStrength", "YawStrength")),
                    (ALL, _set("ActivateBelow_G", 1.0))]),
    "partytext": ("pub UI (English + German): START EVENT -> NOCH EINS!!, QUIT -> BETT, "
                  "NEW LAP -> PROST!!!, FINAL LAP -> LAST ORDER, the update nag -> water break", 1.0,
                  [(LOC + "eng.loc", _loc_swap(PARTY_ENG)), (LOC + "ger.loc", _loc_swap(PARTY_GER))]),
    "stammtisch": ("the pub regulars race you: all 57 AI drivers renamed (Tante Erna, Korn-Klaus, "
                   "Sandmann, Fahrer-Fritz ...), English + German UI", 1.0,
                   [(LOC + "eng.loc", _rename_ai(STAMMTISCH)), (LOC + "ger.loc", _rename_ai(STAMMTISCH))]),
    "lobby": ("the AI field is a Discord lobby: xXDriftGodXx, Touch Grass, Big Chungus, "
              "Ping 999ms, Hacker!!1 ... (pick this OR stammtisch)", 1.0,
              [(LOC + "eng.loc", _rename_ai(LOBBY)), (LOC + "ger.loc", _rename_ai(LOBBY))]),
    "uwu": ("UwU mode: every English + German UI string and subtitle, r/l -> w "
            "(STAWT EVENT, FWEE PWAY, Youw connection to the sewvews ...)", 1.0,
            [(LOC + "eng.loc", _loc_map(_uwu)), (LOC + "ger.loc", _loc_map(_uwu))]),
    "partytext_xl": ("EXPERIMENTAL resize test: LONGER pub texts (QUIT -> GO TO BED / INS BETT GEHEN, "
                     "FINAL LAP -> LAST ORDERS, MATE! / LETZTE RUNDE, DANN BETT!) - files grow, "
                     "get relocated into new chunks", 1.0,
                     [(LOC + "eng.loc", _loc_swap_resize(PARTY_XL_ENG)), (LOC + "ger.loc", _loc_swap_resize(PARTY_XL_GER))]),
    "uwutitle": ("title screen, UwU EDITION: googly-eyed headlights, Impact captions, "
                 "Minecraft splash text, credits (all 6 title-art variants, 4K BC1)", 1.0,
                 [("data:textures/ui/art/backgrounds/startScreen*.gtx", _texture(_uwu_title))]),
}

# Party presets: one word on the launcher -> several mods. `roulette` picks at random.
PRESETS = {
    "mondfahrt": ["gravity=-0.6", "flugstunde=4"],                  # moon trip + air control
    "beschwipst": ["tipsy=1.8", "wackelpudding=0.15"],              # tipsy jelly cars (2.5 = flips every 10 s)
    "eiskunstlauf": ["glatteis=0.55", "drehwurm=4"],                # figure skating
    "kneipe": ["clumsyai=1", "norubberband", "windschatten=6"],     # pub AI, the two of you win
    "bettzeit": ["fallschirm=4", "power=0.7"],                      # bedtime slow-mo last round
    "chaos": ["gravity=-0.3", "tipsy=1.8", "drehwurm=3", "einkaufswagen=1.5", "windschatten=4"],
    "uwumax": ["uwu", "uwutitle", "lobby", "gravity=-0.3"],               # discord kid final form
}
ROULETTE_POOL = ["gravity=-0.6", "power=2.5", "mass=0.4", "tipsy=2.5", "drehwurm=5", "glatteis=0.55",
                 "wackelpudding=0.12", "windschatten=6", "einkaufswagen=1.8", "fallschirm=4",
                 "flugstunde=4", "clumsyai=1"]


def expand(specs):
    """Presets -> mod specs; `roulette[=n]` -> n random mods (default 2)."""
    import random
    out = []
    for spec in specs:
        name, _, val = spec.partition("=")
        if name == "roulette":
            picks = random.sample(ROULETTE_POOL, int(val) if val else 2)
            print("roulette tonight: " + ", ".join(picks))
            out += picks
        elif name in PRESETS:
            out += PRESETS[name]
        else:
            out.append(spec)
    return out


# --- same-size fitting ---------------------------------------------------------

def fit(new: bytes, size: int) -> bytes:
    """Make `new` exactly `size` bytes without changing its tokens.
    Keeps a trailing NUL run (JSON files are NUL-terminated), collapses runs of
    blanks to a single one if too long, pads with spaces if too short."""
    body = new.rstrip(b"\0")
    tail = new[len(body):]
    room = size - len(tail)
    while len(body) > room:
        m = None
        for m in re.finditer(rb"[ \t]{2,}", body):
            pass  # shrink from the end so the top of the file stays readable
        if m is None:
            raise ValueError(f"edited file is {len(body) - room} bytes too long and has no slack")
        cut = min(len(body) - room, len(m.group()) - 1)
        body = body[:m.end() - cut] + body[m.end():]
    return body + b" " * (room - len(body)) + tail


# --- patch engine --------------------------------------------------------------

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ensure_backup():
    if not os.path.exists(NDX_ORIG):
        if os.path.exists(STATE):
            raise SystemExit("state file exists but backup is missing - refusing to continue")
        shutil.copy2(NDX, NDX_ORIG)
        print(f"backup: {NDX_ORIG}")


def restore(quiet=False):
    mod_pack = None
    if os.path.exists(NDX_ORIG):
        idx = Index(ndx_path=NDX_ORIG)
        mod_pack = idx.pack_path(MOD_PACK)
        shutil.copy2(NDX_ORIG, NDX)
    if mod_pack and os.path.exists(mod_pack):
        os.remove(mod_pack)
    if os.path.exists(STATE):
        os.remove(STATE)
    if not quiet:
        print("restored original dat.ndx; mod pack removed")


def compute(idx, specs, quiet=False):
    """New file contents for `specs` -> (edits {path: (entry, bytes)}, applied, all_files)."""
    import fnmatch
    all_files = list(idx.files())
    by_path = {e["path"]: e for e in all_files}
    edits = {}  # path -> (entry, bytes)
    applied = []

    installed = {}

    def present(e):
        # files whose pack isn't shipped with this install (e.g. *_tier3.gmp in N_WIP_HI) can't be read
        pack = idx.chunk(e["first_chunk"])[0]
        if pack not in installed:
            installed[pack] = os.path.exists(idx.pack_path(pack))
        return installed[pack]

    def matching(pattern):
        # "=<path>" = one exact file (d5ml loose files), "+<path>" = exact file that may be NEW
        # (created in the index if it doesn't exist), anything else is an fnmatch glob
        if pattern.startswith("+"):
            p = pattern[1:]
            if p in by_path:
                return [by_path[p]] if present(by_path[p]) else []
            if p.endswith("/") or ":" not in p:
                raise SystemExit(f"new file needs a full pack path like data:dir/name.ext, got '{p}'")
            return [{"path": p, "new": True, "size": 0, "index": None, "first_chunk": None}]
        if pattern.startswith("="):
            hits = [by_path[pattern[1:]]] if pattern[1:] in by_path else []
        else:
            hits = [e for e in all_files if fnmatch.fnmatch(e["path"], pattern)]
        return [e for e in hits if present(e)]
    for spec in expand(specs):
        name, _, val = spec.partition("=")
        if name not in MODS:
            raise SystemExit(f"unknown mod '{name}' (see: d5mod.py list)")
        desc, default, targets = MODS[name]
        v = float(val) if val else default
        hits = 0
        for pattern, transform in targets:
            for e in matching(pattern):
                if e["path"] in edits:
                    cur = edits[e["path"]][1]
                else:
                    cur = b"" if e.get("new") else idx.read(e)
                if getattr(transform, "wants_path", False):
                    text, n = transform(cur.decode("latin1"), v, path=e["path"])
                else:
                    text, n = transform(cur.decode("latin1"), v)
                if n:
                    new = text.encode("latin1")
                    # resize transforms may change the length: the file gets relocated
                    edits[e["path"]] = (e, new if getattr(transform, "resize", False) else fit(new, len(cur)))
                    hits += n
        if not hits:
            raise SystemExit(f"mod '{name}' matched nothing - format changed?")
        applied.append({"mod": name, "value": v, "edits": hits})
        if not quiet:
            print(f"  {name}={_num(v)}: {hits} value(s) rewritten")
    return edits, applied, all_files


def check(specs):
    """Dry run against the ORIGINAL index: hit counts + one before/after line per mod."""
    idx = Index(ndx_path=NDX_ORIG) if os.path.exists(NDX_ORIG) else Index()
    names = specs or [f"{k}={_num(d)}" for k, (_, d, _) in MODS.items()]
    for spec in names:
        edits, applied, _ = compute(idx, [spec], quiet=True)
        for a in applied:
            print(f"  ok  {a['mod']}={_num(a['value'])}: {a['edits']} value(s)")
        print(f"      -> {len(edits)} file(s) patched")
        path, (e, new) = next(iter(sorted(edits.items())))
        old = idx.read(e).decode("latin1").splitlines()
        def show(s):  # binary files (.loc) -> printable ASCII only
            return "".join(c if " " <= c <= "~" else "." for c in " ".join(s.split()))[-90:]
        for o, n in zip(old, new.decode("latin1").splitlines()):
            if o.split() != n.split():
                print(f"      e.g. {path.rsplit('/', 1)[-1]}: {show(o)}  ->  {show(n)}")
                break


def path_hash(path: str) -> int:
    """dat.ndx entry hash = first 8 bytes of MD5(full path), little-endian (verified on all
    112 452 entries of the loose install, files and folders)."""
    return struct.unpack("<Q", hashlib.md5(path.encode("latin1")).digest()[:8])[0]


NO_ENTRY = 0xFFFFFFFF


def _children_paths(idx, parent):
    # entry: u64 pathOff, hash, nameOff | u32 size @24, firstChunk @28, offsetInChunk @32,
    #        parent @36, nextSibling @40, firstChild @44, isDir @48, 0 @52
    out, k = [], struct.unpack_from("<I", idx.raw, idx.entries_off + parent * ENTRY_SIZE + 44)[0]
    while k != NO_ENTRY and len(out) < 100000:
        out.append(idx.entry(k)["path"])
        k = struct.unpack_from("<I", idx.raw, idx.entries_off + k * ENTRY_SIZE + 40)[0]
    return out


def _new_entries(idx, new_files):
    """new_files [(path, size, first_chunk)] -> (entry bytes to append, string bytes to append).
    Missing parent folders are created too. Each new entry is prepended to its parent's child
    list (parent.firstChild -> new, new.nextSibling -> old first child); existing parent
    entries are patched in idx.raw."""
    if not new_files:
        return b"", b""
    dirs = {}
    for i in range(idx.entry_count):
        e = idx.entry(i)
        if e["is_dir"]:
            dirs[e["path"]] = i
    strings = bytearray()
    str_base = len(idx.raw) - idx.strings_off
    rows = []                                   # new entries as mutable lists

    def add_string(s):
        off = str_base + len(strings)
        strings.extend(s.encode("latin1") + b"\0")
        return off

    def first_child_slot(parent):               # -> (get, set) for parent.firstChild
        if parent < idx.entry_count:
            o = idx.entries_off + parent * ENTRY_SIZE + 44       # firstChild
            return (lambda: struct.unpack_from("<I", idx.raw, o)[0],
                    lambda v: struct.pack_into("<I", idx.raw, o, v))
        row = rows[parent - idx.entry_count]
        return (lambda: row[8], lambda v: row.__setitem__(8, v))

    def new_row(path, name, size, first, parent, is_dir):
        index = idx.entry_count + len(rows)
        get, put = first_child_slot(parent)
        rows.append([add_string(path), path_hash(path), add_string(name), size,
                     first if not is_dir else NO_ENTRY, 0, parent, get(),
                     NO_ENTRY, 1 if is_dir else 0, 0])
        put(index)
        return index

    def ensure_dir(dpath):                      # "data:a/b/" -> entry index
        if dpath in dirs:
            return dirs[dpath]
        head = dpath[:-1]
        parent_path = head[:head.rfind("/") + 1] if "/" in head else head.split(":")[0] + ":"
        parent = ensure_dir(parent_path)
        name = head.rsplit("/", 1)[-1].split(":")[-1]
        dirs[dpath] = new_row(dpath, name, 0, NO_ENTRY, parent, True)
        return dirs[dpath]

    for path, size, first in new_files:
        folder = path[:path.rfind("/") + 1] if "/" in path else path.split(":")[0] + ":"
        new_row(path, path.rsplit("/", 1)[-1].split(":")[-1], size, first, ensure_dir(folder), False)
    return b"".join(struct.pack("<QQQ8I", *r) for r in rows), bytes(strings)


def apply(specs):
    ensure_backup()
    restore(quiet=True)
    idx = Index()
    if os.path.exists(idx.pack_path(MOD_PACK)):
        raise SystemExit("mod pack slot unexpectedly present after restore")

    # 1) compute new file contents
    edits, applied, all_files = compute(idx, specs)

    # 2) splice same-size edits into their chunks; resized files are relocated in 3b),
    #    new files (not in the index yet) get fresh chunks + new index entries in 3c)
    created = {p: v for p, v in edits.items() if v[0].get("new")}
    same = {p: v for p, v in edits.items() if p not in created and len(v[1]) == v[0]["size"]}
    moved = {p: v for p, v in edits.items() if p not in same and p not in created}
    chunks = {}  # chunk index -> bytearray (decompressed)
    for e, data in same.values():
        k, pos, left, src = e["first_chunk"], e["chunk_off"], e["size"], 0
        while left:
            if k not in chunks:
                chunks[k] = bytearray(idx.read_chunk(k))
            buf = chunks[k]
            n = min(left, len(buf) - pos)
            buf[pos:pos + n] = data[src:src + n]
            src += n
            left -= n
            k, pos = k + 1, 0

    # 3) write mod pack + repoint chunk records
    out_path = idx.pack_path(MOD_PACK)
    with open(out_path, "wb") as out:
        out.write(b"\0" * 8)  # same 8-byte zero lead-in as the shipped INIT packs
        for k in sorted(chunks):
            raw = bytes(chunks[k])
            comp = lz4.block.compress(raw, mode="high_compression", compression=12, store_size=False)
            if len(comp) >= idx.chunk_size:
                if len(raw) != idx.chunk_size:
                    raise SystemExit(f"chunk {k} is a short tail chunk and does not compress")
                comp = raw  # stored raw: the reader treats compSize == chunkSize as uncompressed
            off = out.tell()
            out.write(comp)
            struct.pack_into("<3I", idx.raw, idx.chunks_off + k * CHUNK_REC, MOD_PACK, off, len(comp))

        # 3b) relocate resized files: fresh chunks appended to the chunk table, entry repointed.
        #     Name/path offsets are relative to the string table, so inserting records is safe.
        new_recs, next_k = bytearray(), idx.chunk_count

        def write_fresh(data):
            nonlocal next_k, new_recs
            padded = data + b"\0" * (-len(data) % idx.chunk_size)   # full chunks only
            first = next_k
            for j in range(0, max(len(padded), idx.chunk_size), idx.chunk_size):
                raw = padded[j:j + idx.chunk_size].ljust(idx.chunk_size, b"\0")
                comp = lz4.block.compress(raw, mode="high_compression", compression=12, store_size=False)
                if len(comp) >= idx.chunk_size:
                    comp = raw
                off = out.tell()
                out.write(comp)
                new_recs += struct.pack("<3I", MOD_PACK, off, len(comp))
                next_k += 1
            return first
        for e, data in moved.values():
            first = write_fresh(data)
            struct.pack_into("<3I", idx.raw, idx.entries_off + e["index"] * ENTRY_SIZE + 24, len(data), first, 0)
        new_files = [(p, len(data), write_fresh(data)) for p, (e, data) in sorted(created.items())]

    # 3c) new index entries (files + missing folders), linked into their parent folder
    new_entries, new_strings = _new_entries(idx, new_files)
    ndx = idx.raw
    if new_recs or new_entries:
        c_end = idx.chunks_off + idx.chunk_count * CHUNK_REC
        ndx = (idx.raw[:idx.chunks_off] + new_entries          # entries (old, patched) + new
               + idx.raw[idx.chunks_off:c_end] + new_recs     # chunk records (old) + new
               + idx.raw[c_end:] + new_strings)               # pack names + strings (+ new)
        struct.pack_into("<I", ndx, 0x0C, idx.entry_count + len(new_entries) // ENTRY_SIZE)
        struct.pack_into("<I", ndx, 0x10, next_k)
        struct.pack_into("<Q", ndx, 0x28, len(idx.raw) - idx.strings_off + len(new_strings))
    with open(NDX, "wb") as f:
        f.write(ndx)

    # 4) verify from disk: edited files read back exactly, neighbours unchanged
    orig, now = Index(ndx_path=NDX_ORIG), Index()
    for path, (e, data) in edits.items():
        got = now.find(path) if e.get("new") else now.entry(e["index"])
        assert now.read(got) == data, f"verify failed: {path}"
    if created:
        for i in range(orig.entry_count):          # old entries keep their path, hash and data refs
            a, b = orig.entry(i), now.entry(i)
            assert a["path"] == b["path"] and a["hash"] == b["hash"], f"entry {i} changed"
        for path in created:                       # reachable through the folder tree
            e = now.find(path)
            assert path in _children_paths(now, e["parent"]), f"new file not linked: {path}"
    touched = set(chunks)
    checked = 0
    for e in all_files:
        if e["path"] in edits or e["first_chunk"] not in touched:
            continue
        assert now.read(e) == orig.read(e), f"neighbour changed: {e['path']}"
        checked += 1
    with open(STATE, "w") as f:
        json.dump({"mods": applied, "files": sorted(edits), "chunks": sorted(chunks),
                   "ndx_orig_sha256": sha(NDX_ORIG)}, f, indent=2)
    print(f"ok: {len(edits)} file(s), {len(chunks)} chunk(s) -> {os.path.basename(out_path)}; "
          f"verified, {checked} neighbouring file(s) unchanged")


def status():
    if not os.path.exists(STATE):
        print("vanilla (no d5mod mods applied)")
        return
    with open(STATE) as f:
        s = json.load(f)
    print("applied:", ", ".join(f"{m['mod']}={_num(m['value'])}" for m in s["mods"]))
    print(f"{len(s['files'])} file(s) patched, {len(s['chunks'])} chunk(s)")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "list":
        for k, (desc, default, _) in MODS.items():
            print(f"  {k:<13} default={_num(default):<5} {desc}")
        print("\n  presets:")
        for k, specs in PRESETS.items():
            print(f"  {k:<13} {' '.join(specs)}")
        print(f"  {'roulette[=n]':<13} n random picks (default 2) from: {' '.join(ROULETTE_POOL)}")
    elif cmd == "apply" and len(argv) > 2:
        apply(argv[2:])
    elif cmd == "check":
        check(argv[2:])
    elif cmd == "restore":
        restore()
    elif cmd == "status":
        status()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
