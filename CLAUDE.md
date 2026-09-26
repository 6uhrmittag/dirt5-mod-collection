# CLAUDE.md — DIRT 5 mod collection (working notes for Claude Code)

Read this before running anything. `FINDINGS.md` is the technical source of truth (formats, offsets, evidence); this file holds the **rules, workflows and lessons** that make work in this repo go smoothly. Public repo: https://github.com/6uhrmittag/dirt5-mod-collection — author name **macha**.

---

## 1. What this project is now

Started 2026-07 as a weekend reverse-engineering study of DIRT 5 (Codemasters EGO/EVO engine). Since 2026-09-26 it is a **public mod collection**: the first real mod tools for DIRT 5 plus the research behind them. Tone: serious research **and** silly party mods — both are welcome ("go silly" = Discord-modder-kid energy: meme mods, new content, NexusMods-style packages, not infrastructure for its own sake).

| part | entry point | status |
|---|---|---|
| D5ML mod loader | `scripts/D5ML.ps1` (window), `scripts/d5ml.py` (CLI) | 1.0.0, verified in-game |
| DIRT 5 Unlocked (hidden options) | `scripts/Dirt5-Unlocked.ps1` | 1.0.0, 7 options verified, 3 no-effect, 19 untested |
| patch engine + recipes | `scripts/d5mod.py` | verified in-game |
| party mods + launcher | `docs/party-mods.md`, `scripts/Start-Dirt5Party.ps1` | verified in-game (most) |
| unattended test harness | `scripts/Test-Dirt5Mod.ps1` | works |
| companion apps (C#) | `src/Dirt5.TrackCompanion`, `src/Dirt5.SaveInspector`, `src/Dirt5.Probe` | wall works, OCR diary experimental |
| release packaging | `scripts/Pack-Tools.ps1` → `release/*.zip`, pages in `docs/release/` | ready |

Framing for anything public: **personal & experimental, offline only, not affiliated with Codemasters/EA, no game files in the repo.** Every mod generates its content from the player's own game copy at apply time.

---

## 2. The installs on this machine

- **Sealed Microsoft Store / MSIX install** (WindowsApps): readable but integrity-protected — no file edits. Used for read-only work: extraction, save inspection, memory *reading* (FINDINGS §4). No Denuvo on the Store build.
- **Loose folder install `C:\Games\DIRT 5`** (Store build v1.2767.60, unsealed, readable `game_release.exe`) — **the mod target**. 25 of 75 pack slots are shipped; slot `0_DISC_INIT` is unused and becomes the mod pack; `44_WIP_HI.dat` (the `_tier3.gmp` textures) is absent, so the game runs on tier2 max.
- The loose install carries a `RUNASADMIN` compat flag (HKCU AppCompatFlags\Layers) → an elevated game silently drops injected input. Always start it through `scripts/Start-Dirt5Modded.ps1` (uses `__COMPAT_LAYER=RunAsInvoker`).
- UI language on this machine is **German**; OCR patterns must accept German and English (and uwu'd text when the `uwu` mod is active).

---

## 3. Hard rules

1. **Offline only.** Never take modded data online. `Start-Dirt5Modded.ps1` always adds `--disableonline`; a firewall outbound block exists (`scripts/Set-Dirt5Offline.ps1 -Enable -InstallPath 'C:\Games\DIRT 5'`, needs elevation → UAC click by the user).
2. **Never write the shipped `.dat` packs.** Only `d5mod.py` touches the install, and only `dat/index/dat.ndx` (backup `dat.ndx.d5x-orig`, state `d5mod-state.json`) + the mod pack `0_DISC_INIT.dat`. `restore` must give back the original index byte for byte.
3. **Leave the install vanilla** after every test (`python scripts\d5mod.py status` must say `vanilla`), and close any game instance you started.
4. **No game files in git.** `samples/`, `extracted/`, `tools/`, `release/`, own mods under `mods/*` are git-ignored; only `mods/README.md` and `mods/_example-*/` (own art + recipes/effects) are versioned. Never commit `.gtx/.gmp/.dat/.ndx/.vdef/.loc` or extracted JSON — `Pack-Tools.ps1` refuses to package game-format files from the examples.
5. **Public-safety rules** for every commit, doc and screenshot:
   - no gamertags, real names, relationship words, Windows user paths, save-data GUIDs/IDs, e-mail addresses in docs;
   - no names of repack or crack groups, no hints about where the loose install came from — describe it only as "a regular (loose, unpacked) folder install";
   - the loose install's in-game profile name must not appear in public screenshots: **pixelate the race-HUD leaderboard** (fractions of a 16:9 frame: x 0.775–0.972, y 0.105–0.285) in every race screenshot before committing it; check with OCR afterwards;
   - wording: "decoded / reverse-engineered", not "cracked".
6. **Git:** commit when a task is done (short conventional subject like the existing log: `feat(d5ml): …`, `docs: …`), **no AI attribution trailers**. Push permission granted by the maintainer (2026-09-26): push when a change is complete and verified (a local hook needs the git-ignored marker `.claude/allow-agent-push`). **Never push `archive/pre-public`** and never use `--all`: that local branch holds the old private history (37 commits, contains personal data) and must never leave this machine. Branch only on request.
7. **GitHub issues** track open work (`gh issue list`); close them with a note on what was verified, and open new ones with the knowledge you gained (commands, file paths, evidence).
8. **Launching the game:** standing permission (2026-09-26) — launch DIRT 5 for tests without asking, but first check the foreground window (another fullscreen game/app in use → wait or skip). Runs steal focus and send keys: tell the user what you launched.
9. PowerShell 7 for scripts; **Windows PowerShell 5.1** only for the WinRT OCR (`Read-Dirt5Text.ps1`). Not WSL.

---

## 4. Lessons learned (do / don't)

- **Never edit a script that a background run is executing.** 2026-09-25 a NUL byte slipped into `d5mod.py` while a test chain ran → 7 runs failed (safe failure, data restored by hand). During chains: only new files, or wait.
- **Scripted edits and escape traps:** Python heredoc edits with `"\t"`, `"\d"`, `"\0"`, `"\n"` inside normal strings broke files three times (NUL byte, broken f-string, lost backslashes in Windows paths). Use the Edit tool, or raw strings `r"..."` in a quoted heredoc, and after any scripted edit check: `ast.parse`, PowerShell parser, **count NUL bytes and stray tabs**.
- **Sandbox before the real install:** hard-link the shipped packs into `extracted/sandbox/dat/`, copy `dat.ndx.d5x-orig` as `index/dat.ndx`, set `DIRT5_DAT` to the sandbox, apply, read back, compare 400–600 random untouched files, `restore` → `cmp` against the backup. Delete the sandbox afterwards (hard links — deleting them never touches the originals). Then prove it in-game with the harness.
- **"Verified" means seen in-game.** Docs and the options catalogue carry honest status (`verified` / `untested` / `no-effect`, `tested` note with date). Simulated previews are labelled as simulated.
- **Game file quirks:** `.vdef` = CRLF, no NUL terminator, inheritance via `vehicledefsmanifest.vdef`, partial blocks merge over parents; AI/DB JSON = NUL-terminated; `.loc` = `[u64 id][u32 len][text]` with a "bytes remaining" u32 near 0xac; texture headers repeat the name + FNV-1a-64(name); livery GUIDs = FNV-1a-64(`Name`); index entry hash = MD5(path)[:8].
- **Autopilot is a bad judge of handling mods** (steering/spin mods show ~no lap-time change; a human notices). Grip, power, drag, gravity-with-jumps, rollover show up clearly.
- **Hidden options:** accepted ≠ working. `--micromachinescamera`, `--disableai`, `--showresolutions` do nothing in the release build; `--script <wbs>` hangs on the loading page; `--benchmark` does nothing by itself.
- **Harness quirks:** frames are only captured while the game has focus (popups or user clicks → skipped frames; the log says `recorded X of Y`); OCR can't read the page titles (display font) — pages are recognised by their button bars; the race clock OCR misreads single digits (`01:14` → `02:14`), `Get-LapTimes` repairs that (`-Reanalyze <run dir>` recomputes old runs).
- **Background monitors:** watch an explicit output file path (not "newest file", which can pick the monitor's own output); stop old monitors before arming new ones for the same run.
- **Markdown:** one paragraph = one source line (a local hook blocks hard-wrapped paragraphs).
- **Decisions belong to the user:** ask with clickable options before outward-facing or hard-to-undo steps (creating repos, pushing, deleting history); yesterday's OK is not today's OK — except the standing launch permission above.

---

## 5. How to drive and test the game

```powershell
.\scripts\Start-Dirt5Modded.ps1 -Mods tipsy=2 -FastBoot -NoSave -NoNetErrors -AutoPilot   # launch (RunAsInvoker, offline)
.\scripts\Send-Dirt5Input.ps1 -Info                       # game + shell integrity, foreground
.\scripts\Send-Dirt5Input.ps1 -Tap DOWN,DOWN,ENTER -Wait 2000 -Shot menu
.\scripts\Send-Dirt5Input.ps1 -Hold 'W:3000','W+D:600' -Shot race -ShotEvery 700
.\scripts\Test-Dirt5Mod.ps1 -Mods glatteis                # unattended ~4.5 min, results in extracted\modtests\
.\scripts\Test-Dirt5Mod.ps1 -D5ml _example-trackside-takeover -GameArgs '--noitemlocks' -LiveryRight 2
.\scripts\Test-Dirt5Mod.ps1 -Summary                      # results.csv table
pwsh -File scripts\D5ML.ps1 -Snapshot shot.png -Select a,b    # render a window to PNG without focus
```

- Input: SendInput **scan codes** (DirectInput8). Keys need ~1 s after focusing. Menus: arrows, `ENTER` select, `ESC` back; driving: **W** throttle (not arrow-up), **A/D** steer, `TAB` reset.
- Menu path to a race: title `ENTER` → OK the "latest updates" notice → `DOWN DOWN ENTER` (Arcade) → `ENTER` (Free Play) → `DOWN ENTER` (Start Event) → `ENTER` (car) → `ENTER` (livery; `RIGHT`×n picks another) → ~20 s load → `ENTER` skips the intro.
- Free Play default event: Land Rush, Rio Seafront, Lancia 037 Evo 2, 3 laps, 12 cars. Vanilla autopilot lap 1 ≈ **1:14**. Rio has no big jumps (gravity mods need another track). Lancia liveries 02/03 are rank-locked on a fresh profile (`--noitemlocks` unlocks them).
- `--nosave` for every test; `--releasefps` overlay is in the frames (harmless); `--nonetworkerrors` hides the offline popups.

---

## 6. Tool map

| tool | purpose |
|---|---|
| `d5x.py` | pack reader: `list`, `extract` (read-only) |
| `d5mod.py` | patch engine (same-size splice, relocation, new files) + recipes/presets: `list`, `check`, `apply`, `restore`, `status` |
| `d5tex.py` | `.gtx`/`.gmp` codec: BC1/4/5/7, RGBA8/16F/32F, R11G11B10F, arrays, tiers; LUT read/write/sample |
| `d5ml.py` + `D5ML.ps1` | mod loader: `list [--json]`, `check`, `apply`, `restore`, `install`, `new`, `search`, `extract`, `doctor`; mod.json `recipes`, `generate` (hue/saturate/invert/overlay, grade/lut), `clone`, `json` |
| `d5art.py` | generated meme art (UwU title) |
| `Dirt5-Unlocked.ps1` + `docs/unlocked-options.json` | hidden-options launcher + catalogue with status |
| `Start-Dirt5Modded.ps1`, `Start-Dirt5Party.ps1` | launchers (offline, RunAsInvoker) |
| `Send-Dirt5Input.ps1`, `Read-Dirt5Text.ps1`, `Test-Dirt5Mod.ps1`, `d5sheet.py` | drive the game, OCR, unattended tests, contact sheets / reset counter |
| `Pack-Tools.ps1`, `Pack-Dirt5Mod.ps1` | release zips |
| `Set-Dirt5Offline.ps1` | firewall block |
| `Hunt-Dirt5.ps1` | memory scanner (MSIX research, FINDINGS §4) |
| `header_scan.py`, `strings_scan.py`, `Copy-Samples.ps1` | early format survey |

---

## 7. Open work — GitHub issues

Open work lives in the issues (each carries the facts, file paths and a plan): https://github.com/6uhrmittag/dirt5-mod-collection/issues — `gh issue list -R 6uhrmittag/dirt5-mod-collection`. Highest value first:

- **New content:** #1 car variants (vehicledata clone + own vdef), #2 livery thumbnails, #3 livery packs for any car, #4 AI drivers
- **Graphics:** #5 LUT per track/weather + verify Vivid
- **Unlocked:** #6 the 19 untested options, #7 FOV slider via memory
- **Reach:** #8 Steam build, #15 NexusMods checklist (tools), #19 CI: per-mod builds + automated GitHub releases, #20 one NexusMods page per mod
- **Research:** #10 Playground Archive, #11 boot scripts, #13 audio, #14 models, #18 memory on the loose build
- **Quality:** #9 BC7 modes, #12 harness improvements, #16 Car Companion real stats, #17 party texts for 9 languages

---

## 8. Timeline (where knowledge came from)

- 2026-07-04/06 — MSIX install: container survey, NefsLib rejects all packs, Track/Car Companion + Session Wall, WGS save inspector, memory read proven (both players' speed).
- 2026-09-23 — loose install: `dat.ndx` + LZ4 pack format decoded (`d5x.py`), first data mods (`d5mod.py`), hidden option table recovered from the exe.
- 2026-09-25 — input injection solved (RunAsInvoker), autopilot A/B proves vdef mods in-game, party mods, OCR test harness, uwu/pub text mods, BC1 textures (UwU title), variable-size files, NexusMods pitch.
- 2026-09-26 — D5ML + DIRT 5 Unlocked windows and release zips, all texture formats + arrays + tiers, Trackside Takeover, Synthwave livery, colour-grading LUTs (Night Vision verified), new files (MD5 index hash), clone/json → first new DIRT 5 content (4th Lancia livery), public repo with fresh history.
