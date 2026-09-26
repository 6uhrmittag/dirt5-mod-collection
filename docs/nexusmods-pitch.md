# Three DIRT 5 mods that would go big on NexusMods

Research 2026-09-25. NexusMods has **no DIRT 5 game page at all**; the only DIRT 5 mods anywhere are two tiny sound swaps on OverTake (130 and 63 downloads, 2021). EA halted all rally development in May 2025 and shut down the online services of older DIRT/GRID titles in Nov 2025 — DIRT 5 was spared so far, but it is next in line. On comparable racing games the top NexusMods files are camera/FOV overhauls, graphics/ReShade overhauls, car model swaps and AI overhauls. First mover on an untouched game with a worried community = the whole front page.

Sources: [OverTake DIRT 5 downloads](https://www.overtake.gg/downloads/categories/dirt-5.219/), [Delisted Games: Codemasters DIRT/GRID online shutdown](https://delistedgames.com/codemasters-old-dirt-and-grid-titles-lose-online-services-on-march-16th-2026/), [PlayStation LifeStyle on the Nov 2025 shutdown](https://www.playstationlifestyle.net/2025/11/07/dirt-4-rally-ps4-games-shutting-down-short-notice/), [FH6 camera mod](https://www.nexusmods.com/forzahorizon6/mods/324), [FH5 mods by endorsements](https://www.nexusmods.com/games/forzahorizon5/mods?sort=endorsements), [BeamNG top mods](https://www.nexusmods.com/beamngdrive/mods/top).

## 1. D5ML — the first DIRT 5 mod loader + texture/livery studio

*"Frosty for DIRT 5."* Drop files into `mods/<name>/data/...` or PNGs into `mods/<name>/textures/...`, click Apply, play; one click back to vanilla. Every other mod on the page would depend on it — which is exactly how the top file of an unmodded game is born.

- **Already working (this repo):** the pack format (`d5x.py`), patching that never touches the shipped packs (`d5mod.py`, verified in-game), BC1 texture import at 4K (`d5tex.py`, round-trip clean, `uwutitle` built on it), UI string editing across all languages (`.loc` walker, 32 755 strings), physics/AI data edits (13 mods), an unattended in-game test harness.
- **Files of a different size: done 2026-09-25** — replacements go into fresh chunks, the chunk table in `dat.ndx` grows (`d5mod.py` relocation; **verified in-game**: `partytext_xl` puts `GO TO BED` / `ONE MORE RACE!!` on screen). Custom 4K textures are verified in-game too (`uwutitle`).
- **Missing for a release:** a generic "any file from `mods/<name>/data/...`" front-end on top of that; BC3/BC7 textures with mips (environment/car textures — header parser needs one more format); a small GUI (drag & drop, mod list, conflicts); support for the Steam build (different `dat.ndx`, same format family — needs a Steam copy to verify).
- **Launch content that sells it:** a 4K "UwU/meme" title pack, a real-world livery pack, the party physics presets.
- **Effort:** loader core 1–2 weekends, GUI + BC7 another weekend.

## 2. DIRT 5 Unlocked — hidden developer options + cinematic mode

The release exe still carries **197 developer command-line options** (`docs/dirt5-cli-options.txt`), several verified live: Micro Machines top-down camera, `--autopilotall` (the AI drives your car — instant cinematic replays), FPS/CPU/GPU overlay, unlock all cars/items/entitlements, debug vehicles, freeze time of day, no-HUD, skip intros. A one-window launcher with checkboxes and presets ("Photo mode": no HUD + frozen time + autopilot; "Couch party": Micro Machines cam + no AI; "Content creator": autopilot + overlay off) is instantly understandable and screenshot-friendly — the kind of file that gets shared on Reddit/YouTube.

- **Already working:** the option table recovered from the exe, the launcher (`Start-Dirt5Modded.ps1`, RunAsInvoker, offline guard), `--releasefps`, `--autopilotall`, `--nonetworkerrors`, `--skipvideos/--skiplegals` verified in-game.
- **Missing:** verify the rest one by one with the harness (Micro Machines cam, `noosd`, `unlockallentitlements`, `allowdebugvehicles`, `pausetimeofday`); a real GUI; a **FOV/camera slider** — the #1 request category on racing-game Nexus pages — which in DIRT 5 lives in the exe (`CamFov`, `FieldOfView`), not in data: needs the runtime-memory route from FINDINGS §4 (read proven, write not yet).
- **Legal/online angle:** keep `--disableonline` forced; unlock options are offline-only by construction.
- **Effort:** launcher GUI 1 weekend; FOV via memory 1–2 weekends of reversing.

## 3. Playground Archive — keep DIRT 5's Playgrounds alive after the servers die

DIRT 5's Playgrounds (user-built arenas, gymkhana and party games) live on Codemasters' servers. When DIRT 5 follows DIRT 4/Rally into the shutdown, every community creation disappears. A preservation mod that **exports playgrounds to shareable files and loads them offline** would be the most-endorsed DIRT 5 file for years — preservation mods get goodwill no meme can buy, and NexusMods itself becomes the new "server".

- **Clues already found:** the exe option `letmesavepartygames` ("Allows the user to save a Playground with Party Game Mode locally"), `playgroundserver` (server environment for playground storage), `pg_palette`, `pg_print_template_names`, `enableplaygroundvolumevalidation`; 63 `data:playground/` files incl. `playground/testscript.txt` and `playground_300x300` editor templates; the WGS save reader (`src/Dirt5.SaveInspector`) for locally stored playgrounds.
- **Missing (the real work):** the on-disk format of a saved playground; where the game writes it; how to inject one so the in-game browser/editor loads it offline (possibly via `--playgroundserver` pointing at a local stub server, or by writing into the local save container). Needs a playground created and saved on this PC to diff against.
- **Effort:** research spike 1 weekend to know if it's feasible; then 1–2 weekends for export/import + a small viewer.

## Build status

Ideas 1 (D5ML) and 2 (DIRT 5 Unlocked, "idea 3" in the chat ranking) were started 2026-09-25 and are release-ready since 2026-09-26: windows, CLI, all texture formats, three example mods, release zips via `scripts/Pack-Tools.ps1`, NexusMods page texts in `docs/release/`. Status, verification and TODOs: `docs/d5ml-unlocked-status.md`.

## Ranking

1. **D5ML** — biggest reach, mostly built, unblocks everything else.
2. **Playground Archive** — biggest long-term impact, highest risk (format unknown).
3. **DIRT 5 Unlocked** — fastest to ship, most shareable, FOV slider is the hard part.

Distribution note: ship **code + recipes only** (our patcher generates everything from the user's own game files — no Codemasters assets in the zip), and target the build people actually have (Steam/Store); this repo's tooling is proven on the loose Store build v1.2767.60 only.
