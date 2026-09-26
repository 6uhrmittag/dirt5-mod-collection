"""pack_mod.py - package ONE D5ML mod folder as its own release zip.

  python scripts/pack_mod.py mods/_example-trackside-takeover [--out release] [--version 1.0.0]
  python scripts/pack_mod.py --list          release units: <tag prefix> <version> <folder>

Zip layout (D5ML's "Install zip..." / drag & drop / `d5ml.py install` take it as is):
  <mod-id>/mod.json, <mod-id>/<own art + textures>, README.md (generated from mod.json)
The mod id drops the repo's "_example-" prefix: trackside-takeover, synthwave-037, ...
Refuses game-format files (the repo never ships game data; mods generate from the player's copy).
"""
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_EXT = {".gtx", ".gmp", ".dat", ".ndx", ".vdef", ".loc", ".wem", ".bnk", ".gso", ".phx"}
SKIP = {"__pycache__"}
DISCLAIMER = (
    "> **⚠ Read this first.** About 99 % of the code behind this mod was written by an AI (Claude Code), "
    "directed and play-tested by us. It's a **hobby project**: [@6uhrmittag](https://github.com/6uhrmittag) and "
    "[@VoidCrowned](https://github.com/VoidCrowned) enjoy DIRT 5 very, very much and just wanted a bit more variety "
    "in this lovely game. **Nothing is guaranteed** — no warranty, no support promise. Offline only. "
    "Not affiliated with Codemasters or EA. No game files are included: the mod generates its content "
    "from *your own* copy of the game when D5ML applies it."
)
REPO = "https://github.com/6uhrmittag/dirt5-mod-collection"


def mod_id(folder):
    base = os.path.basename(os.path.normpath(folder))
    return base[len("_example-"):] if base.startswith("_example-") else base


def units():
    """(tag prefix, version, folder) for every releasable example mod."""
    out = []
    mods = os.path.join(ROOT, "mods")
    for name in sorted(os.listdir(mods)):
        d = os.path.join(mods, name)
        if name.startswith("_example-") and os.path.exists(os.path.join(d, "mod.json")):
            meta = json.load(open(os.path.join(d, "mod.json"), encoding="utf-8"))
            out.append((f"mod/{mod_id(d)}", meta.get("version", "0.0.0"), os.path.relpath(d, ROOT).replace("\\", "/")))
    return out


def readme(meta, mid, version):
    feats = []
    if meta.get("recipes"):
        feats.append("built-in recipes: " + ", ".join(f"`{r}`" for r in meta["recipes"]))
    for g in meta.get("generate", []):
        steps = ", ".join(s["effect"] for s in g["steps"])
        tgt = g["target"] if isinstance(g["target"], str) else ", ".join(g["target"])
        feats.append(f"generates `{tgt}` from your game copy ({steps})")
    for c in meta.get("clone", []):
        feats.append(f"adds NEW game files: `{c['from']}*` → `{c['to']}*`")
    for j in meta.get("json", []):
        feats.append(f"adds a new entry to `{j['file']}`")
    lines = [f"# {meta.get('name', mid)} — a DIRT 5 mod (v{version})", "", DISCLAIMER, "",
             meta.get("description", ""), "", "![preview](" + mid + "/preview.png)", "", "## What it does", ""]
    lines += [f"- {f}" for f in feats] or ["- see mod.json"]
    lines += ["", "## Install", "",
              f"1. Get **D5ML**, the DIRT 5 mod loader: {REPO}/releases (look for `D5ML-…zip`).",
              "2. Start D5ML (`D5ML.bat`), then drag this zip onto the window — or **Install zip…**.",
              "3. Tick the mod → **APPLY** → **LAUNCH (offline)**. *Restore vanilla* undoes everything.",
              "", "## Credits", "", f"By **{meta.get('author', 'macha')}** — part of the [DIRT 5 mod collection]({REPO}). MIT licensed (our code and art only)."]
    return "\n".join(lines) + "\n"


def pack(folder, out_dir, version=None):
    folder = os.path.join(ROOT, folder) if not os.path.isabs(folder) else folder
    meta = json.load(open(os.path.join(folder, "mod.json"), encoding="utf-8"))
    ver = version or meta.get("version", "0.0.0")
    if version and meta.get("version") and version != meta["version"]:
        raise SystemExit(f"version mismatch: tag says {version}, mod.json says {meta['version']}")
    mid = mod_id(folder)
    os.makedirs(out_dir, exist_ok=True)
    zpath = os.path.join(out_dir, f"{mid}-{ver}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, names in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for n in sorted(names):
                p = os.path.join(base, n)
                rel = os.path.relpath(p, folder).replace("\\", "/")
                ext = os.path.splitext(n)[1].lower()
                if ext in GAME_EXT:
                    raise SystemExit(f"refusing game-format file {rel}")
                z.write(p, f"{mid}/{rel}")
        z.writestr("README.md", readme(meta, mid, ver))
    print(zpath)
    return zpath


def main(argv):
    if "--list" in argv:
        for tag, ver, folder in units():
            print(tag, ver, folder)
        return 0
    args = [a for a in argv[1:] if not a.startswith("--")]
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(ROOT, "release")
    ver = argv[argv.index("--version") + 1] if "--version" in argv else None
    args = [a for a in args if a not in (out, ver)]
    if not args:
        print(__doc__)
        return 2
    pack(args[0], out, ver)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
