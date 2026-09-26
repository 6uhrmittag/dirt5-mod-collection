# mods/ — D5ML mod folder

> ⚠ ~99 % AI-written hobby project, nothing guaranteed — see the disclaimer at the top of the [README](../README.md).

Every sub-folder is one mod for D5ML (`scripts/D5ML.ps1` window, `scripts/d5ml.py` command line). Only this README and the `_example*` mods are in git — your own mods usually contain files derived from the game and stay local.

```
mods/<name>/mod.json                  name, version, author, description, recipes, generate, clone, json, text, game_build
mods/<name>/files/<path>              replaces data:<path> — any size (e.g. files/physics/vehicledefs/_basecar.vdef);
                                      a path the game doesn't have yet becomes a NEW file (folders are created)
mods/<name>/textures/<path>.gtx.png   picture → re-encoded into data:<path>.gtx and its streamed tiers
mods/<name>/preview.png               shown in the D5ML window (own art or an in-game screenshot)
```

## mod.json

```json
{
  "name": "Synthwave 037",
  "version": "1.0.0",
  "author": "you",
  "description": "one line for the mod list",
  "recipes": ["beschwipst", "gravity=-0.6"],
  "generate": [
    {
      "target": "data:textures/vehicles/liveries/lancia_037_livery_0[12].gtx",
      "steps": [
        { "effect": "hue", "amount": 200 },
        { "effect": "saturate", "amount": 1.35 },
        { "effect": "overlay", "image": "stars.png", "box": [0, 0, 1, 1] }
      ]
    }
  ],
  "game_build": "1635955981817396-112452"
}
```

- `recipes` — built-in `scripts/d5mod.py` mods and presets (`python scripts\d5mod.py list`)
- `generate` — texture effects computed from the player's own game files at apply time, so the mod ships **no game art**. `target` is a glob over pack paths; every matching `.gtx` includes its `_tierN.gmp` high-res levels. Effects: `hue` (degrees), `saturate` (factor), `invert`, `overlay` (your PNG with alpha; `box` = x, y, w, h as fractions of the texture). On colour-grading LUTs (`data:textures/render/luts/*.gtx`): `grade` (`saturation`, `contrast`, `brightness`, `gamma`, `hue`, `tint` [r, g, b], `mix`) and `lut` (`source` = another LUT, e.g. `pm_night_vision.gtx`, applied after the track grade; `mix`)
- `clone` — `[{"from": "lancia_037_livery_03", "to": "lancia_037_livery_04", "in": "data:textures/vehicles/liveries/"}]`: copies every game file in `in` whose name starts with `from` to a NEW file named with `to` (same length), swapping the internal name strings and FNV-1a name hashes. `generate` effects can then target the new files
- `json` — `[{"file": "data:event/liverydata/liverydata.json", "clone_object": {"match": {"Name": "x"}, "set": {...}}}]`: adds a copy of a database entry with your changes; `id` = next free, `Guid` = FNV-1a(new `Name`) unless you set one. `"set_object": {"match": {"Name": "adele-jacquet"}, "set": {"racingNumber": 7}}` changes entries in place (exactly one match, or `"all": true`). Only touched entries are rewritten, the rest of the file stays byte-identical
- `text` — `{"ID_SHORT_ADELE_JACQUET": "C. Handbrake", "ID_MY_NEW_TEXT": "hello"}`: sets or **adds** UI texts in all 9 languages (pc/ps4/xbox copies), any length. The key is the LocID name the game data uses (`LongLocID`/`ShortLocID` in `driverdata.json`, …) — the `.loc` entry id is FNV-1a-64 of that name, so new names give new entries. Per language: `{"*": {...}, "ger": {...}, "jap": {...}}` (default + overrides; codes `bra eng fre ger ita jap kor sim spa`). Japanese/Korean/Chinese fonts only carry the characters the vanilla text uses — D5ML warns about others (they'd show as red boxes)
- `game_build` — written by `d5ml.py new`; D5ML warns when a mod was made for different game data

Textures: any format the game uses works (BC1, BC4, BC5, BC7, RGBA8, RGBA16F, RGBA32F, R11G11B10F), at the texture's own size with a full mip chain; `target`/`exclude` may be one glob or a list.

## Commands

```powershell
python scripts\d5ml.py new my-mod "my first mod"          # scaffold with mod.json
python scripts\d5ml.py search lancia livery               # find game files
python scripts\d5ml.py extract my-mod <glob|word>         # copy files in; textures arrive as PNG (best tier),
                                                          # car liveries also get a *.guide.png (paint mask overlay)
python scripts\d5ml.py new-livery bmw_m1_rallye --png my.png  # NEW livery slot for any car (79 of 92 cars),
                                                          # unlocked; without --png it gets a colour shift
python scripts\d5ml.py list                               # installed mods
python scripts\d5ml.py check my-mod other-mod             # dry run: sizes, conflicts
python scripts\d5ml.py apply my-mod other-mod             # later mods win conflicts
python scripts\d5ml.py install downloaded-mod.zip         # zip or folder -> mods/
python scripts\d5ml.py restore                            # vanilla
python scripts\d5ml.py doctor                             # self-check: packages, game folder, index, every mod
```

Offline only. The original `.dat` packs are never written; `restore` puts the backed-up `dat.ndx` back.
