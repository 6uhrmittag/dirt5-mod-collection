# DIRT 5 — Reverse-Engineering FINDINGS

Living log of what works, format notes, and per-tool results.
Scope: **offline, cosmetic / menu-UI study only.** Copies only. Online never.

---

## 0. Environment (captured 2026-07-04)

### Game build — **Xbox / Microsoft Store (MSIX)**, NOT Steam
This overrides several assumptions of the original plan (which assumed the Steam/Denuvo build).

| Fact | Value |
|------|-------|
| Package | `CodemastersSoftwareCompan.DiRT5` |
| Version | `1.2770.47.0` (x64) |
| Install path | `C:\Program Files\WindowsApps\CodemastersSoftwareCompan.DiRT5_1.2770.47.0_x64__4cfye3zbe1gaw` |
| DRM | **No Denuvo** on this build. Store/Game Pass uses MSIX package integrity + license protection instead. |
| Launcher entry | `GameLaunchHelper.exe` → `game_release.exe` (from `AppxManifest.xml`, EntryPoint `Windows.FullTrustApplication`) |
| Stub launcher copy | `C:\XboxGames\DIRT5 Amplified\Content\` (splash + gamelaunchhelper only; real binaries live in WindowsApps) |

**Access reality (tested):**
- Directory listing of the WindowsApps install: **works** (readable).
- `AppxManifest.xml`, `.dat` archive bytes: **readable** → extraction-for-study is feasible.
- `game_release.exe`: **Access denied** on read.
- The install is TrustedInstaller-owned + MSIX integrity-protected → **editing files in
  place breaks the package signature** (Xbox app blocks launch / repairs).
  → **In-place asset-swap modding is off the table on this build.** Realistic wins =
  **extract → view → document.** (The Steam build is the freely moddable one.)

### Installed DLC / packs (Get-AppxPackage, re-verified 2026-07-06)
Registered packages: DIRT5Amplified, DIRT5-YearOneLanyard, DIRT5-SuperSizePack,
GameplayBoosterPack, WildSpiritsContentPack, JunkyardCareerPack (all 1.0.0.0).
An "Energy Content Pack" folder exists under `C:\XboxGames` but is **not**
currently registered as an Appx package. User states they own all 4 paid DLCs;
the game runs with the **German UI** (relevant for all screen-reading features).

### Toolchain present on this PC
| Tool | Status |
|------|--------|
| Visual Studio 2022 Community | Installed (also Preview + VS2019 Community) — **chosen IDE** |
| VS Code | Installed |
| .NET SDKs | 6.0.428, 8.0.319, 9.0.315 (+9.0 preview) |
| Git | 2.49.0 |
| Python | 3.12 (`...\Python312\python.exe`) |
| 7-Zip | **not on PATH** (install / add later if needed) |
| JetBrains Rider | folders exist but no working exe found — not used |

---

## 1. Container format map (`dat/` folder)

41 `.dat` files in `...\dat\`. Many are capped at exactly ~2 GiB (0x7FFFFFFF) →
**split archive chunks**. Several are 0-byte placeholders. Names encode a pack type:

`N_<STAGE>_<KIND>.dat` where STAGE ∈ {DISC, WIP}, KIND ∈ {ARC, FPX, OTH, INIT, WIN, DEV, AUC}.

Largest real packs: `15/16/17_DISC_OTH` (~2 GiB each), `2_DISC_FPX`, `5_DISC_ARC`, `6_DISC_ARC`.

### Header samples (first 64 bytes)

**`5_DISC_ARC.dat`** — readable FourCC chunk structure, tags stored **byte-reversed**,
u32 little-endian length-prefixed:
```
00 00 00 00 00 00 00 00 f3 44 20 4f 56 45 01 00   .........D OVE..
00 00 52 44 48 4d 0d 00 00 00 4d 41 53 54 45 52   ..RDHM....MASTER
20 48 45 41 44 45 52 04 00 00 00 9c 9a ad 69 ...    HEADER....˜š­i
```
Decoded: `RDHM` (→ "MHDR") + len `0x0D` + `"MASTER HEADER"`; later `XYHP` (→ "PHYX").
→ **Custom Codemasters tag/length chunk container, NOT a vanilla NeFS archive.**
The EGO tools (NefsLib etc.) must therefore be tested empirically, not assumed to work.

**`2_DISC_FPX.dat`** — different layout: 8 zero bytes then high-entropy data
(compressed/encrypted; no plaintext chunk header — see content map below).

> Note: files >2 GB can't be read with .NET `File.ReadAllBytes` (2 GB limit) — use
> `FileStream` and read only the header window. The master index is
> `dat\index\dat.ndx` (~29 MB, fixed-stride binary records with 8-byte hashes +
> `ffffffff` sentinels — likely hashed filenames; full RE deferred).

### Common container signature (all structured packs)
Every non-encrypted pack begins:
`[8×00] [ "EVO " engine marker @~0x8 ] [ MHDR "MASTER HEADER" ] [ MAST… ]`
i.e. Codemasters **EGO/EVO** engine container, reversed-FourCC + u32-length chunks.
(`MHDR`, `MAST`, `EADE`, `PHYX`/`Phys` are recurring structural tags.)

### Pack-type content map (from `header_scan.py` on 1 MiB windows)

| KIND | Entropy | Content (from plaintext tag/string fragments) | Extract priority |
|------|---------|-----------------------------------------------|------------------|
| **ARC** | ~7.0 | World/model/asset data with **readable paths**: `/dir`, `model`, `built`, `_dat`, `/pat`(h); physics (`PHYX`) | High — plaintext paths |
| **OTH** | ~6.8 | **Textures**: `Text`(ure), `tile`, `cladding`, `BPIM` (mip block) | **High — cosmetic textures** |
| **DEV** | ~6.5 | **Materials / config**: `Material`, `Template`, `Condition`, `texture`, `Update` | **High — materials** |
| **WIN** | ~7.9 | **Wwise audio**: `BKHD`, `RIFF`, `WAVE`, `fmt `, `data` | Medium — audio |
| **FPX** | ~7.8 | High-entropy, **compressed/encrypted**, no plaintext (FX/particles?) | Low — needs decompression |
| **INIT** | ~7.9 | High-entropy, **compressed/encrypted**, no plaintext (init/boot data) | Low — needs decompression |

**Implication for our cosmetic/menu scope:** the readable wins live in **OTH
(textures)**, **DEV (materials)** and **ARC (models/paths)**. Menu/UI textures are
most likely in OTH. FPX/INIT are compressed — defer until we identify the codec
(QuickBMS comtype scan in Phase 3 fallback).

---

## 2. Per-tool results

### NefsLib (VictorBush ego.nefsedit, `net8.0`) — **does NOT open DIRT 5 packs**
Tested via `src/Dirt5.Probe` (references NefsLib directly, built in VS2022/dotnet).
- NeFS magic is `0x5346654E` = ASCII `"NefS"` (`Header/NefsConstants.cs`).
  DIRT 5 packs start `00×8` then `EVO`/`MHDR` — no `NefS` magic.
- Result on **every** sample (ARC/OTH/WIN/FPX): 
  `InvalidDataException: Header magic number mismatch.`
- Conclusion: DIRT 5's container is a **different EGO generation** (EVO chunk
  container) than the NeFS archives NefsLib targets (DiRT Rally 2.0 / GRID era).
  Extraction needs a **custom parser**, not NefsLib.

### Native probe (`src/Dirt5.Probe`, our own C# reader) — **WORKS**
Reads the reversed-FourCC + u32-length header directly. On the readable packs it
enumerates real chunk tags and **plaintext asset paths**, e.g. ARC yields
`/dir … t5/built_data … /models/world/ …` fragments; OTH yields
`Texture / MIPB / cladding / stone / _tile`. WIN is correctly detected as a
Wwise/RIFF audio bank (`BKHD/DIDX/DATA/RIFF/WAVE/fmt/data`, no MHDR); FPX as
high-entropy encrypted (no MHDR anchor). **This is the extraction path forward.**

> **"It works" milestone met:** VS2022 solution `Dirt5Modding.sln` builds clean
> (0 warn / 0 err), runs, reads a real game archive, and produces an empirical,
> documented result for the EGO community tool. For an MSIX-constrained, read-only
> RE project this is the correct definition of success.

### First working mod — Track Companion overlay (`src/Dirt5.TrackCompanion`)
An **external always-on-top overlay HUD** = the correct "mod" form for the MSIX
build (no game-file changes, no injection, no ban risk). Shows a per-track stats
table ("statistics next to your maps": best time / runs / wins / notes).
- **Grounded in real data:** `TrackExtractor` streams the `.dat` packs and pulls
  `worlds/<country>/<track>` paths. Verified: extraction added `greece/meteora`
  (a real DIRT 5 location) that was NOT in the hardcoded baseline — proof the
  catalog reflects actual game files, not just curation.
- **Player stats** persist to `%APPDATA%\Dirt5TrackCompanion\stats.json`.
- **Validated:** solution builds 0/0; `--dump` shows the 11-track catalog with
  correct best-time math; `--capture` renders the HUD to PNG (see
  `docs/track-companion.png`); interactive `Application.Run` launches without crash.

### Second mod — Car Companion (splitscreen), `src/Dirt5.TrackCompanion`
Evolved into a **car-selection overlay** for splitscreen: for a selected car+track it
shows per player how often each raced that car on that track, side-by-side with a
"who's faster" mark. Players (corrected 2026-07-05, verified from an in-game
screenshot): **P1** = the main profile, **P2** = the guest slot (display names = the gamertags),
editable via `--set-player`.
- **Real car roster:** `CarExtractor` reads `models/vehicles/<id>` from `dat.ndx`
  → **78 internal car ids** (alfa_romeo_giulia_gtam, baja_beetle, lancia_stratos,
  porsche_911_rgt, …). `dat.ndx` confirmed to be a **plaintext asset-path table**.
  **Known gap:** in-game display names can differ from internal ids — DIRT 5 uses
  fictional brands for some cars (observed live: "WS Auto Racing Titan" is
  internally `formula_offroad_v1`) → a display-name alias map is still needed.
- **Car "stats" block is placeholder-only.** The game's Performance/Handling ratings
  were never extracted from game data; the overlay renders empty bars. (The ratings
  ARE visible as letter grades on the car-select info panel — a future OCR/extract
  target.)
- **Track axis:** the index over-extracts world sub-paths (254 raw → 184 after
  collapsing `_lr/_rr/_nc/_vN` route variants), so the selectable list is curated.
  **Caveat:** several curated slugs are placeholders, not verified names.
  Verified from game data/screens: `guilin_yulong`, `carrara`, `meteora`,
  `cape_town`, `namche_bazaar` (in `dat.ndx`), and in-game (German UI): Asif
  Tifnout/Marokko, Xiamo Run/China, Tijuca Forest/Brasilien, Colonnata + Marmifera
  Valley/Italien, Studalsvatnet/Norwegen. Placeholders like `nepal/himalaya`,
  `norway/fjord`, `brazil/rio`, `morocco/desert` are **invented** and should be
  replaced by extracted names.
- **Stats keyed by (player, car, track)** in `%APPDATA%\Dirt5TrackCompanion\`.
- Validated: build 0/0; roster dump; per-player best-time/win math; `--capture` PNG;
  interactive launch OK. **Live-use caveat:** on the game monitor DIRT 5's
  fullscreen rendering covers normal top-most windows — the overlay is only usable
  on a second monitor (`--secondary`).

### Save data — Xbox WGS (`src/Dirt5.SaveInspector`, READ-ONLY)
DIRT 5 saves live under `…\SystemAppData\wgs\` (Xbox connected-storage). Format decoded:
- `containers.index`: `u32 version(=14)`, `u32 count`, then UTF-16 entries
  (moniker, container "Dirt5"/"SaveData", etag, GUID).
- `container.NNN`: `u32 version`, `u32 blobCount`, then `blobCount × {UTF-16 name[128B],
  GUID[16], GUID[16]}` (160 B/record). First GUID → on-disk blob filename (`Guid.ToString("N")`).
- **Blobs found:** `ghosts/*.spooky` (per-track lap ghosts), `profile/{items,private,public}.prf`,
  `profile/settings.json` (~300 KB), `recipies/*.rcp` + `swatches/*.pxx` (**livery/paint data**).
- **Implications:** ghosts = future path to auto-read best times per player; recipies/
  swatches = cosmetic livery data worth studying. **Never write to `wgs`** (corrupt saves
  are unrecoverable / integrity-checked). Tool opens files read-only only.

### Real-time telemetry — **DIRT 5 has NONE** (verified)
Unlike DiRT Rally 2.0 / F1 / GRID, DIRT 5 does **not** expose Codemasters UDP telemetry:
- No `hardware_settings_config.xml`, `motion_platform`, `dbox`, `udp`, or port `20777`
  anywhere in the asset index (`dat.ndx`). Only `ai/vehicletelemetry.json` (AI driving
  data, not a network feed).
- The player `settings.json` blob has **Force Feedback / wheel** keys but no telemetry/
  motion/UDP toggle.
→ No official real-time feed exists. Motion-rig/dashboard users hit the same wall.

### Auto-sync via screen-read OCR (`--watch`), `src/Dirt5.TrackCompanion`
**Status: experimental — NOT usable end-to-end yet** (live splitscreen test on
2026-07-05 judged it not working: selection did not follow car changes reliably).
The honest breakdown of what is and isn't verified:

**Verified working (deterministic tests + one real 4K screenshot):**
- Windows built-in OCR (offline) via TFM `net8.0-windows10.0.19041.0`.
- Fuzzy match corrects OCR errors against the finite roster: "Audi Sl EKS RX
  Quattro" → **Audi S1 EKS RX Quattro** (0.88); "BAJA BEETLE" → 1.00. Lap-time
  parse: "1:30.882" → 90.882 s.
- **DPI bug found & fixed:** capture initially returned scaled logical pixels
  (2560×1440 on the 3840×2160 @150 % display), silently cropping the bottom
  splitscreen half. Fix: `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)`
  before any screen access → true 4K capture straight from the game window.
- **Confident-only car detection** on one real 4K car-select screenshot:
  P1 Bentley Continental GT Ice Racer (0.95, via brand-wordmark path),
  P2 Audi TT Safari (0.42, via name path). Detector declines rather than guesses.

**Verified NOT working / open problems:**
- The car-name bar uses a **decorative brush font** that Windows OCR misreads even
  from clean, contrast-enhanced crops ("Bentley Continental GT Ice Race Car" →
  garbage). Only the brand-wordmark shortcut is reliable, and only for brands with
  a single car in the roster.
- **Fictional in-game brands** (e.g. "WS Auto Racing Titan" = `formula_offroad_v1`)
  can't match the internal-id roster → detector correctly stays silent.
- The car-select screen shows **no track text** → track auto-sync from that screen
  is impossible.
- **Results-screen auto-log was never calibrated or verified** — the region config
  defaults for result times are empty; no live result was ever auto-logged.
- Tight OCR crops can defeat word grouping (full-frame OCR + region filtering by
  word box works better for plain wordmarks).

### Third mod — Couch Session Wall (`--wall`), the one that works live
Full-screen live gallery on the **second monitor** while playing on the first —
**verified during a real splitscreen session (2026-07-05)**: big LIVE view of the
game feed, auto-curated TOP MOMENTS (colourfulness/contrast scoring, time-separated),
chronological filmstrip, and an auto-rendered **session poster** PNG
(autosave every 2 min).
- Built ONLY on the proven-reliable path (read-only 4K game-window capture) — the
  gallery/poster core has **no OCR dependency** and cannot be "wrong".
- **`WS_EX_NOACTIVATE`**: the window never takes focus, so the game never pauses —
  required because the players use two controllers and cannot click anything.
  Everything runs hands-free (no inputs needed).
- Saturation-boost grading counters the washed-out look of GDI captures of an HDR
  display (cosmetic only; capture itself is fine).
- Poster verified: header with player names/date/duration, top-moment grid,
  filmstrip. Known cosmetic issue: visually identical loading screens can appear
  as two separate "moments" (no visual-similarity dedupe yet).

### Session diary (OCR layer on the Wall) — **experimental, in rework**
Goal: auto-log what was played (races, Fahrzeit, event + track names, German UI).
- **v1 race/menu detection (HUD regex) FAILED live** — user-confirmed "doesn't work
  at all". Root cause (verified by OCRing a real menu frame): the race-HUD timer is
  too small after downscale, and its `mm:ss:fff` format **collides with leaderboard
  times shown in menus** → false positives in menus, misses in races (inflated race
  counts: 7 "races" logged during one continuous stint).
- **v2 (current): menu-word detection** — the big German frontend words (SPIELEN,
  ZURÜCK, BESTENLISTEN, …) OCR reliably; absence of menu words ⇒ racing; loading
  screens count towards Fahrzeit (accepted approximation). Compiles clean but is
  **NOT yet verified in-game**; decision trace written to
  `%TEMP%\dirt5-wall-debug.log` for offline verification next session.
- **Location extraction** ("Xiamo Run, China" style, with OCR-confusion
  normalisation "BRAS'LIEN"→BRASILIEN): implemented; matched in offline frame tests,
  but **no live log entry observed yet** — unverified. Loading-screen subtitles use
  a script font OCR often misses; plain-font event cards are the better source.

### Next tools to try (future sessions)
- **QuickBMS comtype scanner** on FPX/INIT windows to ID the compression codec.
- **Ego-Engine-Modding** ERP/PSSG tools on chunks extracted by the native parser
  (PSSG textures -> DDS -> texconv/Pillow) — the cosmetic viewing path.
- Extend the native parser to follow the `MASTER HEADER` offset table and actually
  carve individual entries (currently we only enumerate top-level tags).

---

## 3. Safety: offline / anti-ban approach

Since we are **not modifying any game files** on this MSIX build, the online ban vector
is already minimal. The extra safety net is a **Windows Firewall outbound block** toggle
(`scripts/Set-Dirt5Offline.ps1`) — reversible, touches zero game files.

**Game Pass caveat:** Store/Game Pass licenses re-validate periodically (~monthly). A
permanent hard network block can eventually fail that re-check. Toggle **off**
occasionally to let the license re-validate, then back **on** for offline play.

---

## header_scan report

### 15_DISC_OTH.head.bin
- read: 1,048,576 bytes   entropy: 6.776 bits/byte
- verdict: **chunk-structured (FourCC tag/length container)**
- tags seen (reversed->readable): VO F, MHDR, TSAM, H RE, EDAE, MIPB, txeT, Ceru, idno, noit, .0.1, dalc, gnid, irb_, s_kc, enot, lit_, _c_e, reit, UUkK
- first tag @0x9: 'F OV' (rev 'VO F'), next-u32=325
- chunk walk from 0x9: 1 chunk(s), diverged (layout not a plain tag+len stream)
    0x000009  VO F  len=325

### 2_DISC_FPX.head.bin
- read: 1,048,576 bytes   entropy: 7.827 bits/byte
- verdict: **chunk-structured (FourCC tag/length container)**
- tags seen (reversed->readable): Pr7z, 10A., zZt_, VBPV, amC7, VTwA, mDjl, r8Lb, 79oh, g wD, U/hU, EODS, BY4g, 1D2O, 4w0m, ABAH, MJWZ, XMgH, fupU, Qh5l
- first tag @0x1EB: 'z7rP' (rev 'Pr7z'), next-u32=2,024,281,264
- chunk walk from 0x1EB: 1 chunk(s), diverged (layout not a plain tag+len stream)
    0x0001EB  Pr7z  len=2,024,281,264

### 37_WIP_INIT.head.bin
- read: 1,048,576 bytes   entropy: 7.938 bits/byte
- verdict: **chunk-structured (FourCC tag/length container)**
- tags seen (reversed->readable): j2BK, tZGC, WTFh, 76aA, 9Q8v, gDVD, BfTd, BB2B, 4vex, .YQr, Q1up, 7tD4, TXpt, JDRk, HN-A, C1bT, Idae, QyLQ, XNlH, grEC
- first tag @0xA: 'KB2j' (rev 'j2BK'), next-u32=136,989,808
- chunk walk from 0xA: 1 chunk(s), diverged (layout not a plain tag+len stream)
    0x00000A  j2BK  len=136,989,808

### 5_DISC_ARC.head.bin
- read: 1,048,576 bytes   entropy: 7.040 bits/byte
- verdict: **chunk-structured (FourCC tag/length container)**
- tags seen (reversed->readable): VO D, MHDR, TSAM, H RE, EDAE, PHYX, syhP, noCx, itid, reno, .0.1, rid/, b/5t, tliu, tad_, tap/, w_hc, m/pi, ledo, ow/s
- first tag @0x9: 'D OV' (rev 'VO D'), next-u32=325
- chunk walk from 0x9: 1 chunk(s), diverged (layout not a plain tag+len stream)
    0x000009  VO D  len=325

### 64_WIP_DEV.dat
- read: 1,048,576 bytes   entropy: 6.514 bits/byte
- verdict: **chunk-structured (FourCC tag/length container)**
- tags seen (reversed->readable): EVO , MHDR, TSAM, H RE, EDAE, VBLO, GMTT, etaM, lair, pmeT, etal, dnoC, oiti, .0.1, tadU, txet, seru, set/, rt/t, _see
- first tag @0xA: ' OVE' (rev 'EVO '), next-u32=1
- chunk walk from 0xA: 1 chunk(s), diverged (layout not a plain tag+len stream)
    0x00000A  EVO   len=1

### 64_WIP_DEV.head.bin
- read: 1,048,576 bytes   entropy: 6.514 bits/byte
- verdict: **chunk-structured (FourCC tag/length container)**
- tags seen (reversed->readable): EVO , MHDR, TSAM, H RE, EDAE, VBLO, GMTT, etaM, lair, pmeT, etal, dnoC, oiti, .0.1, tadU, txet, seru, set/, rt/t, _see
- first tag @0xA: ' OVE' (rev 'EVO '), next-u32=1
- chunk walk from 0xA: 1 chunk(s), diverged (layout not a plain tag+len stream)
    0x00000A  EVO   len=1

### 68_WIP_WIN.head.bin
- read: 1,048,576 bytes   entropy: 7.935 bits/byte
- verdict: **chunk-structured (FourCC tag/length container)**
- tags seen (reversed->readable): DHKB, DIDO, ATAD, FFIR, EVAW,  tmf, atad, 33DD, bRB2, A8/X, sIMQ, _NO/, quTz, lzH1, eeeo, KUky, QA_K, 8aAN, 6EDH, hi5_
- first tag @0xA: 'BKHD' (rev 'DHKB'), next-u32=24
- chunk walk from 0xA: 2 chunk(s), diverged (layout not a plain tag+len stream)
    0x00000A  DHKB  len=24
    0x00002A  0XDI  len=1,241,513,984

### dat.ndx
- read: 1,048,576 bytes   entropy: 4.765 bits/byte
- verdict: **chunk-structured (FourCC tag/length container)**
- tags seen (reversed->readable): vKAa, G0Wj, UKYM, vL1w, PpQb, EU9D, S8q4, _AzX, J5y7, 34QN, k89u, dODg, i b5, 99hd, .eTo, vZ5j, xudL, pZS7, mQEv, oAtf
- first tag @0x620: 'aAKv' (rev 'vKAa'), next-u32=859,906,484
- chunk walk from 0x620: 1 chunk(s), diverged (layout not a plain tag+len stream)
    0x000620  vKAa  len=859,906,484


---

## DIRT 5 save inspector (WGS, read-only)
- WGS root: `%LOCALAPPDATA%\Packages\CodemastersSoftwareCompan.DiRT5_4cfye3zbe1gaw\SystemAppData\wgs`
- containers.index: version=14, container-count=1
  strings: CodemastersSoftwareCompan.DiRT5_4cfye3zbe1gaw!game.release · <guid> · Dirt5 · SaveData · "<ts>"

### container `<guid>`  (manifest container.177, 8 blobs)
    ghosts/6_<id>.spooky           <guid>      37.178 B
    ghosts/6_<id>.spooky            <guid>      13.567 B
    profile/items.prf                              <guid>      26.808 B
    profile/private.prf                            <guid>      89.235 B
    profile/public.prf                             <guid>       1.473 B
    profile/settings.json                          <guid>     306.719 B
    recipies/<id>_0.rcp             <guid>         517 B
    swatches/<id>_1.pxx             <guid>     121.096 B

- totals: 8 blobs, 596.593 bytes
- NOTE: read-only inspection; nothing under wgs was modified.
- Ghost blobs (`ghosts/...`) are per-track lap data — a future path to auto-read
  best times per player. Decoding blob *contents* is out of scope for now.

---

## 4. Runtime memory access (MSIX build) — READ feasibility PROVEN (2026-07-06)

New direction (user reframe): on the sealed Store/MSIX build, file edits stay off
the table (package integrity), so the only path to *changing in-game behaviour* is
**runtime memory editing** — offline, splitscreen-only, touches zero files, reverted
by a restart. This section records the empirical feasibility.

### Step 0 — attach + read works WITHOUT elevation
Probe (`OpenProcess(QUERY|VM_READ)` + `VirtualQueryEx` + `ReadProcessMemory`) against
the live `game_release.exe`:
- **Reading succeeds with a normal (non-admin) process; `SeDebugPrivilege` not needed.**
  The game runs in an MSIX **AppContainer at *lower* integrity**, so a medium-IL
  process opens it for read (integrity blocks opening *up*, not down).
- Read genuine bytes (KUSER_SHARED_DATA @0x7FFE0000; main module `MZ`).
- ~7.7 GiB of committed **RW** memory (`PAGE_READWRITE`). Full scan is **RPM-bound
  (~180 MB/s → ~40-65 s)**; not CPU-bound.
- **WRITE still unproven** — all work so far is read-only (to never disturb a live
  splitscreen race). Writing from medium-IL to the lower-IL AppContainer *should*
  also work without admin; confirm with a deliberate poke during calibration.

### Tooling — our own Claude-driven scanner (`scripts/Hunt-Dirt5.ps1`)
PowerShell + inline C# (P/Invoke). Commands: `diffseed`, `sample`, `correlate`,
`read`, `regioninfo`, `dump`, `poke`. Fully CLI-drivable; no Cheat Engine (not
installed). Method used to pin a value **hands-free while the users just play**:
1. **diffseed** — one full RW scan keeps finite floats in a plausible band that are
   *actively changing* over ~3 s → bounded candidate set (6.1M plausible → **148k**
   changing).
2. **sample** — atomically (ms apart) capture a screenshot **and** read all
   candidates' current values; repeat over the session at naturally-varied speeds.
3. **correlate** — the true value is the one candidate whose series tracks the
   km/h read off each screenshot (as km/h *or* m/s). No timing pressure, no
   dropped-candidate risk. Clean separation: winner **err 0.65 km/h vs next 6.0**.

### RESULT — both players' speed pinned as **module-static globals** (stable)
Module base this run = `0x7FF67C990000` (`game_release.exe`, ASLR). Both are
`type=IMAGE` `.data` (RW), i.e. fixed **module + offset** → re-findable every launch:

| Value | Offset (base-relative) | Encoding | Notes |
|-------|------------------------|----------|-------|
| **P1 speed** | `+0x17330A4` | `float` m/s | = magnitude of the velocity vector beside it |
| **P1 velocity vector** | `+0x1733098..+0x17330A0` | 3× `float` (vx,vy,vz) | **the physics "behaviour lever"** |
| **P2 speed** | `+0x1733278` | `float` km/h | looks like a display/telemetry copy |

- **Stability confirmed:** the P2 address was *seeded during one race and still
  tracked speed across later races* → static global, not per-race heap. (Heap copies
  also exist at `0x17F…`, err ~1.5, but move per race → would need a pointer chain.)
- P1's speed sits immediately after a `(vx,vy,vz)` velocity vector whose magnitude
  equals it → almost certainly the **authoritative physics velocity**. Writing the
  vector is the candidate lever for "silly" behaviour (super-speed / stop / launch).
- The `0x7FF67E0C3xxx` block appears to be a **live per-player telemetry area** —
  a strong future source for the "show car stats in splitscreen" goal (read-only).

### Open / next (calibration, needs a live session)
- **Prove WRITE** with one deliberate poke (verdict for the behaviour-change MVP).
- Determine display-only vs physics-authoritative per field (poke speed scalar vs
  velocity vector, observe).
- Resolve `base+offset` at runtime in a companion (EnumProcessModules) so it
  survives restarts; harden into a hands-free second-monitor toggle.
- Map the rest of the telemetry block (RPM/gear/pos) via the same correlate method.


---

## 5. Loose install `C:\Games\DIRT 5` — pack format decoded, data mods built (2026-09-23)

A second, **loose (non-MSIX) install** of the Store build, version **1.2767.60.0**
(`MicrosoftGame.Config`; exe FileVersion 1.0.276760.537, PE timestamp 2021-11-16).
Slightly **older** than the MSIX (1.2770.47) → the §4 memory offsets do **not** carry
over. Differences that matter:
- Files are **plain and writable** (no package seal) → file-based data mods are possible.
- `game_release.exe` is a **readable, unencrypted PE** (sections normal, `.text` entropy
  6.4) → static string/option analysis works.
- Only 25 of the 75 pack slots listed in `dat.ndx` are shipped (others are other
  platforms/unused, e.g. slot 0 `0_DISC_INIT`).

### `dat.ndx` + pack format (SOLVED — `scripts/d5x.py`)
```
dat.ndx
  0x00  8×00
  0x08  u32 version=5 | u32 entryCount=112452 | u32 chunkCount=1246390 | u32 chunkSize=0x20000
  0x18  u64 build timestamp (µs, Nov 2021) | u64 packCount=75 | u64 stringTableSize
  0x30  entryCount × 56 B:  u64 fullPathOff, u64 hash, u64 nameOff,
                            u32 size, u32 firstChunk, u32 offsetInChunk,
                            u32 parent, u32 nextSibling, u32 firstChild, u32 isDir, u32 0
        chunkCount × 12 B:  u32 pack, u32 packOffset, u32 compSize
        packCount  × u64 :  pack-name offsets ("0_DISC_INIT" … "74_DISC_HI")
        string table     :  NUL-terminated; all *Off fields are relative to its start
N_*.dat
  a solid stream of files cut into 128 KiB chunks; each chunk is an independent
  raw LZ4 block (no frame header). A file = chunk[firstChunk…] decompressed,
  sliced at offsetInChunk for `size` bytes.
```
- Explains the old header-scan confusion: INIT/FPX "high entropy" = LZ4; the
  `EVO`/`MHDR` headers in ARC/OTH/DEV are simply the first *file* in those streams.
- 108,007 files, no duplicate paths. Mount prefixes: `data:`, `exe-xbox:`, …
- Verified by extracting `physics/vehicledefs/*.vdef` (133 files) and `ai/*.json`.
  NefsLib/QuickBMS were never needed.

### Editable data found
- **`physics/vehicledefs/*.vdef`**: plain-text car physics (Mass, CMHeight, gear
  ratios, `MaxTorque_Nm` + torque curve, aero, diffs, suspension). Inheritance via
  `vehicledefsmanifest.vdef` (`"audi_s1" { "blockout_rally_cross_awd" }` …); every
  car derives from `_basecar.vdef`, the only file with `ExtraGravityFactor 0.5`.
- `physics/vehicledefs/vehiclehandling.json`: a "server" copy with only 5 generic
  templates (basecar/bike/buggy/car/truck), per the exe option
  `uselocalhandlingdefs` = "Load vehicle defs from physics/vehicledefs/.. instead of
  gamesparks/server".
- **`ai/ai_diff_params.json`**: AI tuning, incl. **rubber-banding**
  (`rubberband_{midrange,farthest}Band_frictionMultiplier` 1.35 / 1.85) and
  `mistake_probability` 0.05..0.25. JSON files are NUL-terminated.

### Hidden built-in command-line options (from the exe's option table)
Registered in the release exe with help text (double-dash, e.g. `--windowx 0`).
Mod-relevant ones: `micromachinescamera`, `disableai`, `autopilotall`,
`pausetimeofday`, `noosd`, `skipvideos`, `skiplegals`, `releasefps`, `nocashlocks`,
`noitemlocks`, `unlockallentitlements`, `careercheatcode`, `allowdebugvehicles`,
`devmenu`, `nosave`, `disableonline`, `uselocalhandlingdefs`, `tweaks <evotweaks file>`.
There is also a QA cheat menu (`QACheatPage`: cash / XP / race-position / finish
cheats), which has no known entry point yet.
`--help` makes the game exit immediately (it presumably prints the table to a console).

### Data-mod engine (`scripts/d5mod.py`) + launcher (`scripts/Start-Dirt5Modded.ps1`)
- Same-length in-place edits (numbers rewritten, blank runs shrunk/padded) →
  affected chunks LZ4-recompressed into the **unused slot `0_DISC_INIT.dat`** →
  only those chunk records in `dat.ndx` are repointed. **Original packs are never
  written.** `dat.ndx.d5x-orig` backup; `restore` = copy back + delete mod pack.
- Self-verifying: patched files are re-read from disk; every other file sharing
  a touched chunk is compared against the original (e.g. 38/38 unchanged).
- Mods: `gravity`, `power`, `mass`, `norubberband`, `clumsyai`.
- **Status: WORKS IN-GAME (live A/B, 2026-09-25, below).** The engine accepts chunks
  from the unshipped slot 0 and the vehicle physics come from the patched vdefs
  (all runs used `--uselocalhandlingdefs`; the default path was not tested).

### Live test 2026-09-25 — Claude drives the game itself
**Input injection.** First attempts (SendInput scan codes, VK, `PostMessage`) were all
ignored. Cause: `HKCU\...\AppCompatFlags\Layers` holds `RUNASADMIN` for
`C:\Games\DIRT 5\game_release.exe` (and UAC auto-approves it), so the game ran at
**High** integrity while the shell is **Medium** — UIPI silently drops the input. The
exe has no manifest and runs fine unelevated: launching with
`__COMPAT_LAYER=RunAsInvoker` fixes it. The game reads the keyboard via **DirectInput8**
(imports `DINPUT8`/`XINPUT1_4`, no GameInput), so **SendInput scan codes** work.
- `scripts/Start-Dirt5Modded.ps1` now always launches via RunAsInvoker (`-Elevated` = old way).
- `scripts/Send-Dirt5Input.ps1`: `-Tap`, `-Hold 'W+D:600'`, `-Shot`/`-ShotEvery`,
  `-Info` (integrity check). Refuses to send keys or capture unless the game is the
  foreground window (never types into / screenshots the user's other apps).
- Keys: RTN select, ESC back, arrows = menus, **W throttle, A/D steer**, TAB reset.
  Arrow-Up is *not* throttle. Keys sent < ~1 s after the window gains focus are lost
  (DirectInput re-acquire) — the script waits 1.2 s after focusing.
- Menu path to a race (Arcade → Free Play defaults to **Land Rush, Rio Seafront,
  Lancia 037 Evo 2**, 3 laps, 12 cars): title `ENTER` → (OK the "latest updates" notice)
  → `DOWN DOWN ENTER` → `ENTER` → `DOWN ENTER` → `ENTER` (car) → `ENTER` (livery) →
  ~20 s load → `ENTER` skips the intro. Lap 1 time = last clock before "NEW LAP"
  (the HUD clock resets every lap).

**Built-in flags verified in the release build:** `--releasefps` (CPU/GPU/FPS/build
overlay), `--autopilotall` (AI drives the player car from the start),
`--nonetworkerrors` (no "Error Code: Raspberry" popup; the "latest updates" notice still
shows), `--disableonline`, `--skipvideos --skiplegals`. `--nosave` is accepted, its
effect is not verified. The firewall block (`Set-Dirt5Offline.ps1 -Enable
-InstallPath 'C:\Games\DIRT 5'`) is what causes the Raspberry popup — expected.

**Physics A/B** (autopilot, same event/car, `--uselocalhandlingdefs` in every run):

| data | lap 1 (standing) | lap 2 (flying) |
|---|---|---|
| `power=0.25` | **1:38.5** | — |
| vanilla | 1:13.8 | 1:08.1 |
| `gravity=-0.6 power=2` | 1:11.1 | 1:06.3 |

¼ torque costs +25 s → the vdef edits are definitely applied (to every car — the AI
field is slowed too). 2× torque with lower gravity is only ~3 % faster: on loose
surface the extra torque mostly turns into wheelspin, and less extra gravity also
means less grip. Rio Seafront has no real jumps, so the "moon jump" look of
`gravity` is still unseen — needs a track with jumps.

**Hidden script system.** The exe's full option table (197 entries, name/help pointer
pairs at file offset `0xed5fe0`) is in `docs/dirt5-cli-options.txt`. Highlights:
`--script <file>` ("stops the normal game phase flow"), `--bootscript`,
`--uiscript <name>` (→ `data:/ui/testscripts/<name>.wbs`), `--playcareerevent <name>`,
`--benchmark`, `--fixedfps`, `--endeventearly`, `--idontwanttorace`, `--skipftue`.
Scripts are `.wbs` text files shipped in the packs (`data:test/*.wbs`,
`data:ui/testscripts/*.wbs`, extract with `d5x.py extract 'data:*.wbs' <dir>`), e.g.
`test/benchmark_meteora_full_grid.wbs`:
`SetAutoPilot(true)` … `SetNextEventPhase("cruise;greece/meteora_lr_v1","Lancia 037",180,12,1)` … `Quit()`.
UI test scripts drive menus natively (`waituntil(topOfStack("ForeGround")=="MainMenuPage")`,
`selectNav`, `selectItemIndex`, `pressButton("Accept")`).

**Script test (2026-09-25): negative.** `--script data:test/benchmark_meteora_full_grid.wbs` is accepted (the title screen is skipped and the script's `ShowDefaultLoadingPage()` appears), but it then sits on the pink loading page indefinitely with memory flat at ~1.3 GB (no track loads); adding `--autoactivate` changes nothing. `--benchmark` alone boots the normal title → menu flow and starts nothing by itself. So in this release build the dev boot scripts are not a usable way into a race — the menu route below is.

### Self-test harness + party mods (2026-09-25)
- `scripts/Test-Dirt5Mod.ps1`: one unattended run per mod (~3.5 min) — apply, launch (`--autopilotall --nosave --nonetworkerrors`), drive title → Arcade → Free Play → Start Event → car → livery with every page confirmed by OCR, skip the intro, record ~95 s, close the game, restore vanilla, then read the lap times off the HUD clock. Report + contact sheet in `extracted/modtests/<stamp>_<label>/`, one row per run in `extracted/modtests/results.csv`. Refuses to run if a game it didn't start is open (pid file). `-Suite party|singles`, `-Summary`, `-GameArgs`.
- `scripts/Read-Dirt5Text.ps1`: Windows.Media.Ocr from Windows PowerShell 5.1 (WinRT projection; pwsh 7 can't). Reads the race clock exactly (`01:10.707` → `00:00.779` at the lap line); page titles use a display font it can't read, so pages are recognised by their button bars (`NEXT CLASS`, `CREATE`, `START EVENT`, `FREE PLAY`).
- **Textures (`.gtx`) decoded for BC1** (`scripts/d5tex.py`): EVO container ("MASTER HEADER" / `BLXP` "TextureConditioner"), then `u64 payloadSize | u32 width | u32 height | u32 mips`, and the mip chain sits at the **end** of the file. UI art is BC1, 1 mip: boot/legal screen 1920×1080, title screen `ui/art/backgrounds/startScreen*.gtx` 3840×2160, `arcadePoster` 3468×968. A numpy BC1 encoder rebuilds same-size files (4K in ~2 s, header untouched, round trip clean). Environment/vehicle textures use another layout (not parsed yet — likely BC7 with mips). The patcher now stores a chunk raw when LZ4 can't shrink it (the reader treats `compSize == chunkSize` as uncompressed).
- **All texture formats decoded (2026-09-26)** — header after the name block: `u32 payloadSize | u32 flags | u32 width | u32 height | u32 layers | u32 mips | u32 format`; pixels = the complete chain at the end of the file, layer-major for arrays. Format codes, verified by decoding real files: **32/33 BC1**, **38 BC4** (heights/masks), **40 BC5** (normal maps), **43/44 BC7** (most environment + vehicle colour/mask maps), **6/7 RGBA8**, **21 RGBA16F** (small data maps, e.g. `<car>_windscreen.gtx`), **28 RGBA32F** (6-face environment probe cubemaps), **30 R11G11B10_FLOAT** (colour-grading LUTs, see below). With these every sampled `.gtx` parses except a handful of odd layouts.
- **Colour-grading LUTs** `textures/render/luts/*.gtx` (71 files): 32 slices × 32×32, R11G11B10 float, x = red in, y = green in, slice = blue in, linear 0..1 — `identity.gtx` is exactly i/31. Per-track/weather grades (`track_*`, `DIRT5_Base_*`, `DIRT5_Cold_*`, `China_*`, `Lofoten_*`, `w_snow`, `wreck_slo_mo`, `Vampire_*` …) plus the photo-mode filters `pm_*` (night vision, black & white, vintage, teal/orange …). Editing them = a colour-grade/graphics mod without ReShade (`d5ml` effects `grade` and `lut`; `lut` samples a second LUT at the first one's outputs = filter applied after the track grade). **Verified in-game 2026-09-26** (`d5ml_nightvision` run): composing `pm_night_vision` onto all 42 track/weather LUTs turns the whole Land Rush race NVG green (the menus use another grade and stay normal; very bright sky partly stays white — HDR above the LUT range). Which LUT a given track uses is still unmapped.
- **Streamed high-res levels**: `X.gtx` holds the low mips; `X_tier1.gmp`, `X_tier2.gmp`, `X_tier3.gmp` (chunk `BPIM`) each hold ONE bigger level (4th header field = mip index, payload u32 right before the dims). `*_tier3.gmp` live in `44_WIP_HI.dat`, which the loose install doesn't ship — the game runs on tier2 max. A texture edit must cover `.gtx` + all installed tiers (D5ML does it automatically).
- **Texture arrays**: `layers > 1`, e.g. the trackside sponsor banners `environments/props/branding_array_<country>_c.gtx` = 8 layers × 512² BC1 (+ 1024² `_tier2.gmp`). All 10 countries share one layout: L0/L3 2×4 logo grid, L1 4 rows, L2 2×2 grid, L4 4 vertical columns, L5–L7 country art. The `hubworld_*` variants differ (BC7, flags).
- **Encoders** (`scripts/d5tex.py`, numpy): BC1 (PCA endpoints), BC4/BC5 (8-value mode), BC7 mode 6 (PCA + one least-squares refinement, shared p-bits), RGBA8. Round trip PSNR: BC1 ≈ 46 dB, BC4/BC5 > 60 dB, BC7 31–36 dB (mode 6 only — fine for art, visible on noise); 4K BC1 in ~1.5 s, 512² BC7 with mips in ~0.5 s. Header bytes stay identical, file size identical.
- **Car liveries**: `textures/vehicles/liveries/<car>_livery_NN.gtx` (+ `_m` mask, + tiers), 93 cars, 331 liveries installed. In Arcade the livery page's slot 1 is the car's plain paint (no livery texture); `livery_02`/`03` of the Lancia 037 are rank-locked (rank 15) on a fresh profile — the thumbnails there are separate UI images.
- **Variable-size edits (relocation)**: a file whose new content has a different length is written into *fresh* chunks appended to the chunk table (records inserted before the pack-name list, `chunkCount` @0x10 bumped) and its entry is repointed (`size`, `firstChunk`, `offsetInChunk=0` at entry+24). Path/name offsets are relative to the string table, so nothing else moves. The last chunk is zero-padded to a full 128 KiB. Verified in a hard-linked sandbox install (`DIRT5_DAT`): `eng.loc` 271 942 → 271 971 B moved to chunk 1 246 390, all entries walk to EOF. `.loc` containers carry a "bytes remaining" u32 (at 0xac in `pc/eng.loc`, value = file size − field end) that must grow with the file. **Verified in-game 2026-09-25 (`partytext_xl`)**: the main menu shows `ESC GO TO BED` (was QUIT), Arcade shows `FREE BEER PLAY`, the event button reads `ONE MORE RACE!!` and widens to fit — the engine reads grown, relocated files. Also verified in-game the same evening: `uwu` (main menu `CAWEEW PWAYCWOUNDS AWCADE …`, prompt `WTN STAWT`) and `uwutitle` (the googly-eyed 4K title texture is what the game shows).
- **New files (2026-09-26)**: the entry hash is **the first 8 bytes of MD5(full path)**, little-endian — matches all 112 452 entries (files and folders, e.g. `data:physics/vehicledefs/`). Entries are in tree order (not sorted by hash/path); fields after the three u64: size @24, firstChunk @28, offsetInChunk @32, parent @36, nextSibling @40, firstChild @44, isDir @48 (folders: size 0, firstChunk 0xFFFFFFFF, name without slash). Adding a file = append entries (+ missing folders) after the old ones, prepend to the parent's child list, append path/name strings, bump `entryCount` @0x0C, `chunkCount` @0x10 and `stringTableSize` @0x28. **Verified in-game**: a new `physics/vehicledefs/d5ml_proof.vdef` (tyre frictions ×0.55) inserted into the Lancia 037's chain via `vehicledefsmanifest.vdef` (`"lancia_037" { "d5ml_proof" }`, `"d5ml_proof" { "rally_car_re_rwd" }`) → autopilot lap 1 **1:38.7** (vanilla ≈ 1:14, `glatteis` 1:39.5): the game booted with 4 extra index entries and loaded the brand-new file. vdef files are CRLF, not NUL-terminated.
- **New content: a 4th livery (2026-09-26, verified in-game)**. Liveries are listed in `event/liverydata/liverydata.json` (391 `LvrDta` objects: `Name` = texture base name, `Guid` = **FNV-1a-64 of `Name`**, `index`, `Vehicle ID`, `Sponsor`/`SponsorRank`, `Event Unlock`, `isPreBuilt`). Texture headers carry their name (length-prefixed) and **FNV-1a-64(name)** several times; `.gmp` tiers carry the hash of the tier name and of the base name. Cloning `lancia_037_livery_03*` → `_04*` (swap name bytes + hashes, same size) + a cloned DB entry (`index` 4, next `id` 392, Guid = FNV-1a("lancia_037_livery_04"), no sponsor/unlock) → the livery select shows a **fifth tile**, unlocked, and the car wears the new livery in the menu and in the race. The tile thumbnail is the generic fallback image. D5ML: `clone` + `json` in `mod.json`, example `mods/_example-livery-slot-037`.
- **Localisation (`.loc`)**: `[u64 id][u32 byteLen][UTF-8 text]` entries, contiguous from offset `0xc3` to EOF (6 470 in `pc/eng.loc`); copies for `pc`, `ps4`, `xbox`, 9 languages. The 57 AI drivers are plain entries ("A. Jacquet"). Markup inside strings: `[0]` placeholders, `<laughs>`-style subtitle tags, `%`.
- `scripts/d5mod.py`: 8 new physics mods, 6 presets and `roulette`, plus `check` (dry run); text mods `partytext`, `stammtisch`, `lobby`, `uwu`; texture mod `uwutitle` (art generated by `scripts/d5art.py` on top of the original at apply time — no game assets in the repo). `sub_numbers` now skips commented-out lines and counts only values that really change. Catalogue and party launcher: `docs/party-mods.md`.
