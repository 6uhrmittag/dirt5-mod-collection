"""check_repo.py - the repo's CI gate (runs on every push, see .github/workflows/ci.yml).

Checks, all without a game install:
  1. syntax: every tracked *.py parses
  2. JSON: every mods/*/mod.json + docs/unlocked-options.json parses; D5ML validates each
     example mod (keys, generate targets/steps, effect parameters, images exist)
  3. no game files: no tracked file with a game-data extension (.gtx .gmp .dat .ndx .vdef .loc ...)
  4. public safety: no gamertags / crack-group names (compared as SHA-256 hashes, so the
     names themselves never appear in this repo), no personal Windows user paths, no e-mails
  5. hygiene: no NUL bytes in text files, no tab characters in .py/.ps1/.md/.json
     (both came from escape accidents in scripted edits, see CLAUDE.md "lessons learned")

python scripts/check_repo.py          exit code 0 = all good
"""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

GAME_EXT = {".gtx", ".gmp", ".dat", ".ndx", ".vdef", ".loc", ".wem", ".bnk", ".gso", ".phx", ".gr2", ".lvl", ".wbs", ".prf", ".spooky"}
TEXT_EXT = {".py", ".ps1", ".md", ".json", ".txt", ".cs", ".csproj", ".sln", ".yml", ".yaml", ".gitignore", ""}
NO_TABS = {".py", ".ps1", ".md", ".json", ".yml"}
# sha256 of lower-case tokens that must never be published (gamertags, crack/repack group names)
FORBIDDEN = {
    "55cb03288665019a084d0d5989a73d6c23eb912a15f80330d7c18cfa5de68767",
    "d2e124a92a721f299e60db89f1023632c60ef973ce5c2b73f1523f93c6a31bdd",
    "02f07c7229e17e5cbe18421724937e2de21fefd81e14529d9dbb7ebd78aec992",
    "c222764d863697c84b096f5a483cee5fa8719ab90ecfa6d3c60bbd0c4ed2db8c",
    "187d6b69b464614b65bbed98ca0c92fa47563b9d817cca5c38d3d0f27896810f",
    "09b8b6330172c68bce7418bd55ae5c7a4b252351e7417c20369a08a0d8880d32",
    "11e8b305044f8c54ad50ad3b2e1f2e0165838d90a0b8f0fa1eadde19ea2dd71a",
    "d2f12d879e340cc4231317f481402557b6481b9cdf68747e6a87d1a0fd09defc",
    "64646fbc4b7b5a8e31ba9f701573f34fe7f6f7fef0d1a76652c377ddcda8a1cb",
}
USER_PATH = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(?!Public|Default|<|%|\$|\{)[A-Za-z0-9._-]+", re.I)
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
EMAIL_OK = re.compile(r"noreply|example\.|users\.noreply\.github\.com")


def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    return [p for p in out.splitlines() if p and os.path.exists(os.path.join(ROOT, p))]


def main():
    problems = []
    files = tracked()
    for rel in files:
        path = os.path.join(ROOT, rel)
        ext = os.path.splitext(rel)[1].lower()
        if ext in GAME_EXT:
            problems.append(f"game-format file is tracked: {rel}")
            continue
        data = open(path, "rb").read()
        is_text = ext in TEXT_EXT or os.path.basename(rel) in ("LICENSE",)
        if not is_text:
            continue
        if b"\0" in data:
            problems.append(f"NUL byte in text file: {rel}")
        if ext in NO_TABS and b"\t" in data:
            problems.append(f"tab character in {rel} (line {data[:data.index(b'\t')].count(b'\n') + 1})")
        text = data.decode("utf-8", "replace")
        if ext == ".py":
            try:
                ast.parse(text, rel)
            except SyntaxError as e:
                problems.append(f"python syntax: {rel}:{e.lineno}: {e.msg}")
        for token in set(re.findall(r"[A-Za-z0-9_]{3,}", text)):
            if hashlib.sha256(token.lower().encode()).hexdigest() in FORBIDDEN:
                problems.append(f"forbidden name (public-safety rule) in {rel}")
                break
        for m in USER_PATH.finditer(text):
            problems.append(f"personal user path in {rel}: {m.group(0)[:40]}")
        for m in EMAIL.finditer(text):
            if not EMAIL_OK.search(m.group(0)):
                problems.append(f"e-mail address in {rel}: {m.group(0)}")
    # JSON + D5ML validation of the example mods
    for rel in ["docs/unlocked-options.json"] + [f for f in files if f.startswith("mods/") and f.endswith("mod.json")]:
        try:
            json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))
        except ValueError as e:
            problems.append(f"invalid JSON {rel}: {e}")
    try:
        import d5ml
        d5ml.MODS_DIR = os.path.join(ROOT, "mods")
        for name in d5ml.all_mods():
            try:
                m = d5ml.load(name)
                for g in m["meta"].get("generate", []):
                    d5ml._generated(g["steps"], m["dir"])      # validates effects + images
            except SystemExit as e:
                problems.append(f"mod {name}: {e}")
    except ImportError as e:
        problems.append(f"cannot import d5ml (pip install lz4 numpy pillow): {e}")
    for p in problems:
        print("FAIL", p)
    print(f"{len(files)} tracked files checked - {'all good' if not problems else str(len(problems)) + ' problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
