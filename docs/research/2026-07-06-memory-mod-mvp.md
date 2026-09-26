# DIRT 5 — Runtime Memory-Mod MVP (feasibility probe)

**Date:** 2026-07-06
**Status:** Design approved (brainstorming), pre-implementation
**Scope:** local splitscreen (P1 + P2) only

---

## 1. Goal

Answer one question with a working artifact: **can we actually change DIRT 5's
in-game behaviour on this machine's sealed Store/MSIX build?** The deliverable is
a small tool that attaches to the running game, finds one gameplay value in RAM,
writes to it, and produces a *visible in-game change we watch together*. That
observation is the feasibility verdict — nothing less counts.

Success is deliberately small (one value, one effect). This is an MVP whose job is
to de-risk the whole "real modding" question, not to ship a trainer.

## 2. Why memory editing (and not file mods)

- The install is **Store/MSIX**, cryptographically sealed. Editing a `.dat` on
  disk breaks the package signature → Xbox app refuses launch / repairs the file.
  True **offline too**. So file-based mods stay off the table (per `FINDINGS.md`).
- Dropping the online/anti-cheat concern (we play **local splitscreen, never
  online**) does not unlock file mods — the blocker is package integrity, not
  ban-risk. It *does* make runtime memory editing completely safe: no Denuvo/EAC
  on this build, offline, touches **zero files**, and is reverted by a game
  restart.
- Therefore runtime memory editing is the only realistic path to *changing
  behaviour* on this build, and the original plan already earmarked it (via Cheat Engine).

## 3. Approach: our own Claude-driven tool

Build **`Dirt5.MemPoke`**, a C#/.NET console tool in `Dirt5Modding.sln`, rather
than hand-driving Cheat Engine (which is not installed here anyway). Rationale:

1. The discovery scanner and the eventual hands-free poke companion are the **same
   codebase** — nothing is thrown away.
2. **Fully Claude-driven** from the terminal — matches this project's ethos.
3. Building our own attach path **directly de-risks the companion**: proving *our*
   tool can open the MSIX AppContainer is the exact capability we need (CE proving
   it can would not transfer).

## 4. Pipeline

| Step | What | Driver | Decisive? |
|------|------|--------|-----------|
| **0. Attach probe** | ~30-line elevated `OpenProcess` + `ReadProcessMemory`, read a few bytes from `game_release.exe` | Claude | **Yes** — proves MSIX AppContainer is attachable, or names the true blocker |
| **1. Scanner** | Walk writable committed regions (`VirtualQueryEx`), scan int/float, narrow with successive changed/increased/decreased re-scans | Claude | no |
| **2. Hunt** | Converge on a target value while the game runs; user plays to move the value | Claude + user | no |
| **3. Poke** | `WriteProcessMemory` the confirmed address; watch the in-game effect | Claude + user | **Yes** — this is the verdict |
| **4. Stabilize + productize** | Turn address into an **AOB byte-signature** (survives restarts); wrap in a hands-free 2nd-monitor toggle | Claude | later |

## 5. Target ladder (first that lands wins)

1. **Vehicle speed** — on-screen km/h in the German HUD; changes continuously as
   you drive → fast convergence; writing it is visibly silly. Likely a `float`
   (also try the rounded display int).
2. **Lap / race timer** — a float that counts up; trivial to narrow (increased-value
   scans); modest but unmistakable effect (freeze/skew the clock).
3. **XP / level total** — narrow via increased-value scans between races; payoff is
   fast progression to unlock the content-thin DLC.

**Stretch (only after the pipeline works):** silly physics — moon gravity, global
time-scale, car scale. Higher fun, lower first-try find rate → not the MVP probe.

## 6. Technical design (`Dirt5.MemPoke`)

- **Attach:** run elevated, enable `SeDebugPrivilege`, `OpenProcess` with
  `PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_VM_WRITE |
  PROCESS_VM_OPERATION`. Elevation + debug privilege is what lets a higher-integrity
  process open an AppContainer target.
- **Region walk:** `VirtualQueryEx` across user address space; keep
  `MEM_COMMIT`, non-`PAGE_GUARD`, writable regions (`PAGE_READWRITE` /
  `PAGE_WRITECOPY`) — gameplay values live in writable heap, which shrinks the
  search a lot.
- **Scan:** `ReadProcessMemory` each region in chunks; first scan = exact value or
  unknown-snapshot; successive scans compare a persisted candidate list
  (changed / unchanged / increased / decreased). Support `int32` and `float`
  (float with a small tolerance).
- **Poke:** `WriteProcessMemory` to confirmed address(es).
- **Stabilize (Step 4):** capture bytes around the owning structure and re-scan for
  that **AOB pattern** on each launch (simpler than a pointer-scan engine, robust
  enough for a companion).
- **CLI shape (draft):** `probe`, `scan --type float --eq 142`, `next --changed`,
  `list`, `poke <addr> --type float --set 999`, `snapshot` / `diff`.

## 7. Risks & unknowns

- **AppContainer attach / elevation** — main unknown; Step 0 settles it first.
- **Display vs physics value** — the HUD number may be a rounded copy; writing it
  might only change the readout, not the car. Still proves the write path; we then
  chase the backing value. Acceptable for MVP.
- **Splitscreen = two vehicle instances** — the first value found belongs to one
  car (whoever's moving during the hunt). Proving write-works on one car is the
  MVP; "silly for both" is a follow-up.
- **Address instability across restarts** — expected; the Step-4 AOB signature is
  the fix. Not required for the MVP verdict.

## 8. Safety rules (unchanged)

- **Offline, local splitscreen, never online.** Memory edits especially never in
  any online/multiplayer context.
- **No game files touched** — memory only; reverted by a restart. The "copies only"
  rule is N/A here (nothing on disk is read-modified-written).
- **Read before write** — Step 0 reads only; we never blind-write.
- Git the tool before the first poke.

## 9. Definition of done (MVP)

Our tool, run from the terminal, **attaches to the live MSIX `game_release.exe`,
reads real bytes, finds one gameplay value, writes it, and we observe the in-game
change.** Result (including the exact target found and the AppContainer/elevation
reality) recorded in `FINDINGS.md`.

## 10. Out of scope (for the MVP)

Pointer-scanning engine; multi-value trainer UI; any file mod; anything online;
decoding save/ghost blobs; the car-stats/favorites overlay features (separate,
already-feasible track).
