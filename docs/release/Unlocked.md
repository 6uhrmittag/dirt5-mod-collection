# DIRT 5 Unlocked — the game's hidden developer options, one click away

DIRT 5 still carries **197 developer command-line options** from Codemasters' own builds. DIRT 5 Unlocked finds them for you: tick boxes, pick a preset, launch. It changes **no game files** — everything is a start option.

![DIRT 5 Unlocked window](screenshots/unlocked-window.png)

## Highlights

| option | what it does | status |
|---|---|---|
| Autopilot | the AI drives *your* car — sit back, film, screenshot | ✓ verified |
| Hide HUD | no clock, positions, speedometer or minimap — clean shots | ✓ verified |
| FPS / CPU / GPU overlay | developer performance overlay | ✓ verified |
| No "servers lost" popups | hides the network error codes offline | ✓ verified |
| Skip intro videos + legal screens | straight to the title screen | ✓ verified |
| Freeze time of day, no music, no rumble, skip tutorial … | small quality-of-life switches | untested |
| All items unlocked | every livery/item selectable, rank locks gone (forces *don't save*) | ✓ verified |
| Everything free / all entitlement cars / whole career | offline sandbox (forces *don't save*) | untested |
| P1 picks the cars for everyone | splitscreen quality of life | untested |
| Micro Machines camera, no AI opponents, resolution overlay | accepted by the game but **no effect** in the release build | ✗ greyed out |

✓ = seen working in-game, ✗ = tested and does nothing in the release build (probably dev-build only; shown greyed out). Everything else is accepted by the game's option table and is being verified one by one. The full list with the developers' own help texts is in `docs\dirt5-cli-options.txt`.

## Presets

- **Photo mode** — no HUD, frozen time of day, autopilot
- **Couch party** — P1 picks the cars, no inactivity warning, no network popups
- **Content creator** — autopilot, no HUD, no music
- **Cheat day** — free/unlocked everything; forces *don't save the profile* so nothing leaks into your career

Unlock-type options **always force `--nosave`**. Your real profile stays exactly as it was.

## Install

1. Unzip anywhere
2. Double-click **`DIRT5-Unlocked.bat`** (needs [PowerShell 7](https://aka.ms/powershell); Python only for the optional data-mods box)
3. First start: if DIRT 5 isn't found, set the game folder once in D5ML (**Game folder…**) or keep the default `C:\Games\DIRT 5`

The window also takes **data mods** (D5ML recipes like `beschwipst` or `gravity=-0.6`). The full mod loader with textures and mod folders is **D5ML** — same zip, `D5ML.bat`.

## Safety

- **Offline only:** every launch adds `--disableonline`. Don't take developer options into online races.
- No game file is modified by the options themselves.
- The game is started unelevated (RunAsInvoker) — some installs carry a "run as admin" flag that isn't needed.

## Compatibility

Tested on the DIRT 5 Microsoft Store build v1.2767.60 (loose folder install), Windows 11. Steam: untested — options are part of the game's own code, so they very likely exist there too. Please report!

## Credits

Made by **macha**. The option table was recovered from `game_release.exe` (name/help pointer pairs).

## Changelog

- **1.0.0** — first release: 29 curated options in 5 groups, 4 presets, command preview, copy, offline launch.
