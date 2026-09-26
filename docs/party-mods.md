# DIRT 5 party mods — splitscreen, two pads, late night

Data mods for the loose install (`C:\Games\DIRT 5`), applied by `scripts/d5mod.py` before launch. They change the physics files every car inherits from, so **both players and the AI get the same mod** — fair for splitscreen. A mod set lasts one game session (the data is read at boot): quit, launch again, next round.

Offline only (firewall rule + `--disableonline`), original packs never touched, `python scripts\d5mod.py restore` = vanilla.

## Tonight, one command

```powershell
.\scripts\Start-Dirt5Party.ps1                 # the clock picks the mods
.\scripts\Start-Dirt5Party.ps1 -Preset kneipe  # pick one yourself
.\scripts\Start-Dirt5Party.ps1 -Preset roulette=3 -JustUs   # 3 random mods, no AI
```

| time | what the launcher picks |
|---|---|
| before 23:00 | `roulette` (2 random mods) |
| 23:00 – 01:00 | one of `beschwipst`, `eiskunstlauf`, `mondfahrt`, `chaos` |
| 01:00 – 06:00 | `bettzeit` — slow-motion last round, then bed |

`-JustUs` = no AI cars (`--disableai`), `-Night` = time of day frozen (`--pausetimeofday`), `-WhatIf` = only show what would happen.

The party launcher always adds `partytext` + `stammtisch` (skip with `-NoPartyText`): the menus turn into a pub and the AI field are the regulars.

| English UI | → | German UI | → |
|---|---|---|---|
| START EVENT | NOCH EINS!! | EVENT BEGINNEN | EINS GEHT NOCH |
| QUIT | BETT | BEENDEN | PENNEN! |
| NEW LAP! | PROST!!! | NEUE RUNDE! | NOCH EINE!! |
| FINAL LAP! | LAST ORDER | LETZTE RUNDE! | SPERRSTUNDE!! |
| FREE PLAY | FREIBIER! | FREE PLAY | FREIBIER! |
| RESTART | NOCHMAL | NEU STARTEN | AUF EIN NEU |
| RESET TO TRACK | WO BIN ICH?!?! | AUF STRECKE SETZEN | WO BIN ICH DENN?!? |
| the "latest game updates" nag at every boot | *Wasserpause! Trink zwischendurch ein Glas Wasser. Wer verliert, holt die Chips. Um 2 Uhr ist wirklich Schluss. Versprochen.* | | |

English and German keep their exact-length swaps above. **The other 7 languages** get the same jokes, translated (`PARTY_I18N` in `scripts/d5mod.py`), plus the water-break nag in each language:

| UI text | French | Italian | Spanish | Portuguese (BR) | Japanese | Korean | Chinese (simpl.) |
|---|---|---|---|---|---|---|---|
| START EVENT | ENCORE UNE !! | ANCORA UNA!! | ¡¡OTRA MÁS!! | MAIS UMA!! | もう一杯！！ | 한 판 더!! | 再来一局！！ |
| QUIT | AU DODO | A NANNA | A LA CAMA | CAMA | 寝る | 잘래 | 睡觉 |
| NEW LAP! | SANTÉ !!! | CIN CIN!!! | ¡¡¡SALUD!!! | SAÚDE!!! | 乾杯！！！ | 건배!!! | 干杯！！！ |
| FINAL LAP! | DERNIÈRE TOURNÉE ! | ULTIMO GIRO DI BIRRA! | ¡ÚLTIMA RONDA! | SAIDEIRA! | ラストオーダー！ | 마지막 주문! | 最后一轮！ |
| FREE PLAY | TOURNÉE GÉNÉRALE | BIRRA GRATIS! | ¡BARRA LIBRE! | OPEN BAR! | 飲み放題 | 무한 리필 | 免费酒水！ |
| RESTART | ON REMET ÇA | DI NUOVO! | OTRA VEZ | DE NOVO | もう一回 | 한 번 더 | 再来一次 |
| RESET TO TRACK | OÙ SUIS-JE ?! | DOVE SONO?! | ¿¡DÓNDE ESTOY!? | ONDE EU ESTOU?! | ここどこ？！ | 여기 어디?! | 我在哪？！ |

How it works (and how to translate your own texts):

- `.loc` entries are `[u64 id][u32 byte length][UTF-8 text]`. **The ids are the same in every language**, so one id table (`LOC_ID`) finds "QUIT" in French, Korean, ... alike.
- English/German use same-length swaps (space-padded). The other languages use `_loc_set_ids`: the entry table is rebuilt with texts of **any length** and the container's "bytes remaining" u32 is updated; d5mod relocates the grown file (`resize`). All platform copies (`pc`, `ps4`, `xbox`) are patched.
- `stammtisch`, `lobby` and `uwu` (driver names + UI speak) cover the 6 Latin-script languages; Japanese, Korean and Chinese write driver names in their own script, so they stay vanilla there.
- **CJK fonts only contain the glyphs the vanilla text uses.** A new character renders as a red box (seen in-game: 菓 in Japanese, 喝 and 啤 in Chinese). `_loc_set_ids` now warns: `warning: 喝 not in the vanilla text of this language - may show as a red box` — pick a word whose characters the game already uses.
- **Test any language without changing Windows:** the hidden option `--language <code>` (`eng ger fre ita spa bra jap kor sim`) forces the game language. `scripts/Start-Dirt5Modded.ps1 -ExtraArgs '--language','fre'`. Verified in-game 2026-09-26: French, Italian, Spanish, Portuguese show all four test screens (water-break nag, main-menu `ESC` hint, arcade `FREE PLAY`, event `START EVENT`); Japanese, Korean, Chinese show the nag and the `ESC` hint (the scripted menu walk ended up in Career there, so `FREE PLAY`/`START EVENT` weren't screenshotted — same code path).


## Presets

| preset | mods | the idea |
|---|---|---|
| `mondfahrt` | `gravity=-0.6 flugstunde=4` | moon trip: floaty jumps, steer in the air |
| `beschwipst` | `tipsy=1.8 wackelpudding=0.15` | the cars had more to drink than you (`tipsy=2.5` alone flips the car every ~10 s) |
| `eiskunstlauf` | `glatteis=0.55 drehwurm=4` | black ice + pirouettes |
| `kneipe` | `clumsyai=1 norubberband windschatten=6` | the AI is hammered and gets no catch-up; whoever is behind gets towed home in the slipstream |
| `bettzeit` | `fallschirm=4 power=0.7` | parachute drag, less power: slow motion |
| `chaos` | `gravity=-0.3 tipsy=1.8 drehwurm=3 einkaufswagen=1.5 windschatten=4` | a bit of everything |
| `uwumax` | `uwu uwutitle lobby gravity=-0.3` | discord kid final form: the whole UI speaks like your gamertag, googly-eyed title screen, the AI lobby is xXDriftGodXx & co |
| `roulette[=n]` | n random picks | nobody knows. not even the code |

## Single mods (`python scripts\d5mod.py list`)

| mod | default | what it edits | files |
|---|---|---|---|
| `gravity` | -0.6 | `ExtraGravityFactor` (stock 0.5, arcade extra downforce) | 1 (`_basecar`) |
| `power` | 2 | × `MaxTorque_Nm` | 104 |
| `mass` | 0.5 | × chassis `Mass` | 103 |
| `tipsy` | 2.5 | × `CMHeight_m` (centre of mass), `RollOverSpring` × 0.1 (anti-rollover assist) | 100 |
| `drehwurm` | 6 | `ExtraYawTorqueScale` × value, `YawRateDamping` × 0.2 | 1 |
| `glatteis` | 0.55 | × every positive `Friction_*` (tyre vs smooth/dirt/rough/loose/ice) | 7 |
| `wackelpudding` | 0.12 | × suspension damping factors and `AntiRollSpring_G` | 106 |
| `windschatten` | 6 | × `SlipStreamWakeStrength`, 3× wider/longer, full draft after 0.1 s | 2 |
| `einkaufswagen` | 1.8 | × `MaxSteerAngle_deg` (stock 37.5°) | 4 |
| `fallschirm` | 5 | × `DragCoef` | 71 |
| `flugstunde` | 4 | × in-air `PitchStrength/RollStrength/YawStrength`, air control from 1 G | 3 |
| `norubberband` | 1 | AI catch-up grip bonus off (stock 1.35 / 1.85) | 1 (AI json) |
| `clumsyai` | 0.6 | AI `mistake_probability` (stock 0.05..0.25) | 1 (AI json) |
| `partytext` | – | menu/HUD strings in all 9 languages (tables above) | 27 (`.loc`) |
| `partytext_xl` | – | experimental: *longer* pub texts (QUIT → GO TO BED / INS BETT GEHEN, FINAL LAP → LAST ORDERS, MATE! / LETZTE RUNDE, DANN BETT!) — the files grow and get relocated into new chunks | 6 (`.loc`) |
| `stammtisch` | – | all 57 AI driver names → pub regulars (A. Jacquet → Sandmann, G. Spengler → Tresen-Toni, N. Krahmer → Der Wirt, B. Durand → Kalle …), same byte length, deterministic | 6 (`.loc`) |
| `lobby` | – | all 57 AI drivers → a Discord lobby (xXDriftGodXx, Touch Grass, Big Chungus, Ping 999ms, Hacker!!1 …) — pick this *or* `stammtisch` | 6 (`.loc`) |
| `uwu` | – | UwU mode: every English + German UI string and subtitle gets r/l → w (STAWT EVENT, FWEE PWAY, "Youw connection to the DIWT 5 sewvews has been wost"); `[0]` placeholders, `<laughs>` tags and `%` codes untouched | 6 (`.loc`, 32 755 strings) |
| `uwutitle` | – | the title screen, UwU EDITION: googly-eyed headlights, Impact captions ("PRESS START TO YEET"), yellow Minecraft splash text, credits — generated on top of the game's own 4K art at apply time and re-encoded to BC1 (`scripts/d5art.py`, `scripts/d5tex.py`) | 6 (`startScreen*.gtx`) |

`python scripts\d5mod.py check [mods]` dry-runs a mod against the game data (writes nothing) and shows one before → after line.

## Testing a mod without a human

```powershell
.\scripts\Test-Dirt5Mod.ps1 -Mods tipsy=2.5 -Label tipsy   # ~3.5 min, unattended
.\scripts\Test-Dirt5Mod.ps1 -Suite party                   # vanilla + every preset
.\scripts\Test-Dirt5Mod.ps1 -Summary
```

The harness launches with the mod + `--autopilotall`, drives the menus (every page checked by OCR), records the race, reads lap times off the HUD clock, writes `extracted\modtests\<stamp>_<label>\report.md` + `sheet.png` and restores vanilla. It refuses to run while a DIRT 5 the harness didn't start is open.

## Results (autopilot, Rio Seafront, Lancia 037)

2026-09-25, `--autopilotall`, Arcade Free Play default event, 130 s recorded per run. Lap times read off the HUD clock by OCR (two single-frame misreads corrected by hand, see `docs/d5ml-unlocked-status.md`). Every mod hits the AI field too, so lap times compare the *player's* autopilot only. AI traffic makes ±2 s noise.

| mod | lap 1 | car resets | verdict |
|---|---|---|---|
| vanilla | 1:13.8 (manual) / ≈1:14.1 (harness) | 0 | baseline |
| `power=0.25` | 1:38.5 | – | proof the vdefs are read (manual A/B) |
| `gravity=-0.6 power=2` | 1:11.1 | 0 | slightly faster; no jumps on this track to show the float |
| `tipsy=2.5` | > 2:03 (lap not finished) | **11** | flips every ~10 s — hence `beschwipst` uses 1.8 |
| `drehwurm=6` | 1:14.2 | 0 | the autopilot catches the spin; humans won't |
| `glatteis=0.55` | **1:39.5** | 0 | +26 s, big effect |
| `einkaufswagen=1.8` | 1:13.7 | 0 | no effect on the autopilot (it steers less) |
| `fallschirm=5` | 1:17.6 | 0 | +4 s, top speed capped |
| `flugstunde=4` | ≈1:13.6 | 0 | no effect here — Rio Seafront has no jumps |
| `partytext` | 1:16.0 | 0 | in-game UI: `FREIBIER!`, `NOCH EINS!!` |
| `partytext_xl` | 1:14.9 | 0 | in-game UI: `ESC GO TO BED`, `ONE MORE RACE!!` (grown, relocated files) |
| `uwumax` | – | – | harness page check failed (fixed since); screenshots prove the UwU title texture + `CAWEEW … AWCADE`, `WTN STAWT` |
| `wackelpudding=0.12` | 1:14.3 | 0 | ≈ vanilla: the autopilot soaks up soft suspension (re-run 2026-09-26) |
| `windschatten=6` | **1:08.8** | 0 | −5 s: the slipstream tows you along (re-run 2026-09-26) |
