"""release_ci.py - create one GitHub release per tool and per mod whose version isn't released yet.

Run by .github/workflows/release.yml on every push to main (and manually). Locally:
  python scripts/release_ci.py --dry       show the plan (which tags would be released)
  python scripts/release_ci.py --build     build the zips into release/ without publishing

Release units + tags:
  tools   d5ml/v<ver>, unlocked/v<ver>   versions in release.json, built by scripts/Pack-Tools.ps1
  mods    mod/<id>/v<ver>                version in mods/_example-<id>/mod.json, built by scripts/pack_mod.py
A unit is released when its tag doesn't exist yet - bump the version to publish a new release.
Needs `gh` (authenticated via GH_TOKEN in CI) and PowerShell 7 for the tool zips.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import pack_mod  # noqa: E402

REPO = os.environ.get("GITHUB_REPOSITORY", "6uhrmittag/dirt5-mod-collection")
OUT = os.path.join(ROOT, "release")
TOOLS = {  # key in release.json -> (display name, Pack-Tools -Only value, zip stem, release page)
    "d5ml": ("D5ML — DIRT 5 Mod Loader", "D5ML", "D5ML", "docs/release/D5ML.md"),
    "unlocked": ("DIRT 5 Unlocked", "Unlocked", "DIRT5-Unlocked", "docs/release/Unlocked.md"),
}


def run(cmd, check=True):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        raise SystemExit(f"{' '.join(cmd[:3])} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r


def existing_tags():
    r = run(["git", "ls-remote", "--tags", "origin"], check=False)
    return {line.split("refs/tags/", 1)[1].removesuffix("^{}") for line in r.stdout.splitlines() if "refs/tags/" in line}


def page_notes(page, version):
    text = open(os.path.join(ROOT, page), encoding="utf-8").read()
    warn = re.search(r"^> \*\*⚠ Read this first\.\*\*.*?(?=\n\n)", text, re.S | re.M)
    changes = re.search(r"^## Changelog\s*\n(.*?)(?=\n## |\Z)", text, re.S | re.M)
    parts = [warn.group(0) if warn else "", f"Full page: https://github.com/{REPO}/blob/main/{page}"]
    if changes:
        parts.append("## Changelog\n" + changes.group(1).strip())
    return "\n\n".join(p for p in parts if p) + "\n"


def plan():
    rel = json.load(open(os.path.join(ROOT, "release.json"), encoding="utf-8"))
    units = []
    for key, (title, only, stem, page) in TOOLS.items():
        ver = rel[key]
        units.append({"tag": f"{key}/v{ver}", "title": f"{title} v{ver}", "kind": "tool", "only": only,
                      "zip": os.path.join(OUT, f"{stem}-{ver}.zip"), "version": ver, "page": page})
    for prefix, ver, folder in pack_mod.units():
        meta = json.load(open(os.path.join(ROOT, folder, "mod.json"), encoding="utf-8"))
        units.append({"tag": f"{prefix}/v{ver}", "title": f"{meta.get('name', prefix)} v{ver} (D5ML mod)", "kind": "mod",
                      "folder": folder, "zip": os.path.join(OUT, f"{pack_mod.mod_id(folder)}-{ver}.zip"), "version": ver, "meta": meta})
    return units


def build(u):
    if u["kind"] == "tool":
        run(["pwsh", "-NoProfile", "-File", os.path.join(ROOT, "scripts", "Pack-Tools.ps1"), "-Version", u["version"], "-Only", u["only"]])
        return page_notes(u["page"], u["version"])
    pack_mod.pack(u["folder"], OUT, u["version"])
    return pack_mod.readme(u["meta"], pack_mod.mod_id(u["folder"]), u["version"])


def main(argv):
    dry, build_only = "--dry" in argv, "--build" in argv
    tags = set() if build_only else existing_tags()
    todo = [u for u in plan() if u["tag"] not in tags]
    for u in plan():
        print(f"{'NEW ' if u in todo else 'have'}  {u['tag']:36} {os.path.basename(u['zip'])}")
    if dry:
        return 0
    sha = os.environ.get("GITHUB_SHA") or run(["git", "rev-parse", "HEAD"]).stdout.strip()
    for u in todo:
        notes = build(u)
        if build_only:
            continue
        notes_path = os.path.join(OUT, "notes.md")
        open(notes_path, "w", encoding="utf-8").write(notes)
        run(["gh", "release", "create", u["tag"], u["zip"], "-R", REPO, "--target", sha,     # "Latest" = the mod loader
             "--title", u["title"], "--notes-file", notes_path, f"--latest={str(u['tag'].startswith('d5ml/')).lower()}"])
        print(f"released {u['tag']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
