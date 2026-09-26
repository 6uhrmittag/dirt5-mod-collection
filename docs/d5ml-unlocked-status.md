# D5ML + DIRT 5 Unlocked — status and handoff

Ideas 1 and 3 from `docs/nexusmods-pitch.md`. Started 2026-09-25 (late night), built out 2026-09-26. This file is the resume point.

## Resume here (2026-09-26, 20:40 — paused because the user needed the PC)

Goal of the session: finish the 10 simplest GitHub issues, document everything in the issues. **Closed with full notes: #21, #17, #16, #19, #4, #5, #11.** Game data is vanilla, no game running.

Still open, almost done (each has a progress comment with the details):

1. **#3 new-livery** — `d5ml.py new-livery` works (dry run 79/92 cars; in-game the Peugeot 306 Maxi showed our striped livery, `docs/new-livery-peugeot.jpg`). The first test cloned a RaceNet livery (tile asked for a RaceNet sign-in) → fixed: non-RaceNet source + `isRacenet: false`. **To do:** one harness run to confirm the fixed tile is selectable and races:
   `.\scripts\Test-Dirt5Mod.ps1 -D5ml peugeot_306_maxi-livery-04 -CarClassNext 1 -LiveryRight 4 -LocationRight 2 -TrackRight 2 -Label peugeot_livery04_greece` (the local mod `mods/peugeot_306_maxi-livery-04` exists; recreate with `python scripts\d5ml.py new-livery peugeot_306_maxi --png <any png>`). Then post the note and close.
2. **#12 harness** — `-LocationRight/-TrackRight/-CarClassNext/-CarRight` verified in-game (Greece → Kalabaka Town / Kastraki Village, Peugeot = first car of 90s Rally); focus pause fixed (process-id check; the reruns recorded 147/147 frames). **To do:** watch one `paused … / resumed after N s` log line (click another window for ~10 s during a run), then close. Reruns done: wackelpudding 1:14.3, windschatten 1:08.8.
3. **#6 options** — `docs/unlocked-options.json` now 10 verified / 8 no-effect / 11 untested, every entry with a dated note. **To do:** post the summary, open the couch-session checklist issue (the human-only options), close. Optional: `unlockamd` (needs the CLASS tile to reach the Citroën C3 class), `careercheatcode` (changes the Career start page — look for unlocked chapters).
4. Then: bump `unlocked` in `release.json` to 1.1.0 + changelog in `docs/release/Unlocked.md` (option statuses changed) and push → CI releases it.

Follow-ups created this session: #22 language dropdown, #23 human-like driving, #24 new AI drivers, #25 track name table.

## Release state (2026-09-26)

| | D5ML (mod loader) | DIRT 5 Unlocked (hidden options) |
|---|---|---|
| entry point | `scripts/D5ML.ps1` window, `scripts/d5ml.py` CLI | `scripts/Dirt5-Unlocked.ps1` window, `-Preset/-Flags -DryRun/-Launch` |
| release zip | `scripts/Pack-Tools.ps1` → `release/D5ML-<v>.zip` | same → `release/DIRT5-Unlocked-<v>.zip` |
| NexusMods page text | `docs/release/D5ML.md` | `docs/release/Unlocked.md` |
| screenshots | `docs/release/screenshots/` (windows rendered with `-Snapshot`, in-game shots from `extracted/modtests/`) | same |

Both zips ship the same toolkit (our code only, no Codemasters files; `Pack-Tools.ps1` refuses to package game-format files from the example mods).

## D5ML — what works

- Mod folders `mods/<name>/`: `files/` (any file, any size → relocated), `textures/*.gtx.png` (all resolution levels), `mod.json` with `recipes` (d5mod) and `generate` (effects `hue`, `saturate`, `invert`, `overlay`; `target`/`exclude` globs or lists), `preview.png`, `game_build` stamp with a warning on mismatch.
- CLI: `list [--json]`, `check`, `apply` (load order, conflict report), `restore`, `status`, `install <zip|folder>` (zip-slip safe), starter kit `new`, `search`, `extract` (textures as PNG from the best installed tier).
- Textures: every format the game uses — BC1/BC4/BC5/BC7/RGBA8, full mip chains, streamed `_tierN.gmp` levels, texture arrays (see `FINDINGS.md` §5). Round trips byte-size identical.
- Window: mod list with names/versions, tick = active, up/down = load order (saved in `mods/.d5ml-profile.json`), details + preview, Check / APPLY / Restore vanilla, Install zip + drag & drop, Mods folder, Game folder (saved in `mods/.d5ml-settings.json`, auto-detects `C:\Games\DIRT 5` and common paths), LAUNCH (offline), DIRT 5 Unlocked button. Apply/Restore/Launch are disabled while the game runs.
- Harness: `Test-Dirt5Mod.ps1 -D5ml <mods> [-GameArgs ...] [-LiveryRight n]`.

Example mods (own art only): `_example-bedtime` (own Arcade poster + `partytext_xl`), `_example-synthwave-037` (Lancia 037 liveries: hue/saturate + own star decals), `_example-trackside-takeover` (own fake sponsors on the trackside banners of all 10 countries, country art kept).

**Verified in-game:** 2026-09-26 run `d5ml_bedtime+synthwave` — D5ML apply of 16 files/82 chunks incl. relocated `.loc`, race finished normally (lap 1 1:14.4), `FREE BEER PLAY` on screen. Earlier (09-25): BC1 title texture, uwu/loc text, resized files. Trackside + livery runs: see the results table in `docs/party-mods.md` / `extracted/modtests/results.csv`.

**Known limits / TODO (ordered):**
1. ~~New files~~ — done 2026-09-26 (hash = MD5(path)[:8], tree links, strings), **verified in-game** with a new vdef in the Lancia chain (lap 1:38.7). **First new-content mod done and verified in-game:** `_example-livery-slot-037` (4th Lancia livery via `clone` + `json`, fifth tile in livery select, shows in races). Next: nicer thumbnails (the tile uses the fallback image), liveries for other cars, new AI drivers / events via their JSON databases.
2. ~~Unknown formats 21/28/30~~ — done 2026-09-26: RGBA16F, RGBA32F cubemaps, R11G11B10F colour LUTs (+ `grade`/`lut` effects, examples Vivid + Night Vision Racing; **verified in-game**: the Night Vision run turns the whole race green, so LUT edits reach the renderer. Which LUT each event/weather uses: `docs/lut-map.md` (verified in-game with a tint probe, #5).
3. BC7 encoder is mode 6 only (31–36 dB on noisy textures) — add modes 1/3 for sharper results — 1 evening.
4. **Steam build**: needs a Steam copy to check `dat.ndx`/packs — unknown.
5. ~~Livery editing workflow~~ — done: `d5ml.py extract` writes a `*.guide.png` (paint mask over the livery).
6. ~~`mod.json` validation~~ — done: unknown keys/effect parameters, bad JSON and missing images give clear messages; `d5ml.py doctor` checks everything.

## DIRT 5 Unlocked — what works

- Catalogue `docs/unlocked-options.json`: 29 options, 5 groups, `status` per option: **verified** (autopilotall, noosd, releasefps, nonetworkerrors, skipvideos, skiplegals), **no-effect** (micromachinescamera, disableai, showresolutions — tested 2026-09-26, nothing happens in the release build; greyed out in the window), **untested** (the rest). `tested` field = date + observation.
- Presets: photo, couch (no Micro Machines cam any more — it does nothing), creator, cheatday (forces `--nosave`).
- Window: ✓/?/✗ marks with a legend, tooltips with the exe's help text + test notes, preset dropdown, data-mods box, command preview, Copy, Launch (disabled while running), game folder shared with D5ML.

**TODO (ordered):**
1. Verify the remaining `untested` flags with the harness (`-GameArgs '--x'`), ~5 min each; audio/rumble ones (`nomusic`, `hapticsoff`) need a human.
2. ~~`--noitemlocks`~~ — verified 2026-09-26: rank-locked liveries become selectable. `nocashlocks`, `unlockallentitlements`, `careercheatcode` still untested.
3. `--pausetimeofday`: needs a long run (dawn → day) to see — 10 min.
4. **FOV slider** — camera values live in the exe (`CamFov`, `FieldOfView`); runtime memory write (FINDINGS §4) — 1–2 evenings.

## Rules that bit us

- Never patch a script a background run is executing (09-25: a NUL byte from a heredoc broke 7 runs). Use the Edit tool or write new files while a chain runs.
- The harness stops when the game loses focus — by design. Don't type elsewhere during runs.
- Lap parsing now repairs single-digit OCR misreads (`Get-LapTimes`, `-Reanalyze <run dir>`).

Open work is tracked as GitHub issues since 2026-09-26: https://github.com/6uhrmittag/dirt5-mod-collection/issues
