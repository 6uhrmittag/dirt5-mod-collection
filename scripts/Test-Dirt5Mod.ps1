<#
.SYNOPSIS
    Unattended in-game test of a DIRT 5 data mod: launch -> menus -> autopilot race
    -> lap times via OCR -> report. Lets Claude Code test mods without a human.

.DESCRIPTION
    One run (about 3.5 min):
      1. apply the mod(s) and launch the loose install via Start-Dirt5Modded.ps1
         (--autopilotall --nosave --nonetworkerrors, RunAsInvoker so input works)
      2. drive the menus with Send-Dirt5Input.ps1, checking every page with OCR
         (Read-Dirt5Text.ps1): title -> Arcade -> Free Play -> Start Event -> car -> livery
         Free Play defaults to Land Rush / Rio Seafront / Lancia 037 Evo 2 / 12 cars.
      3. record -Seconds of the race (1 frame/s), then close the game
      4. OCR the HUD clock of every frame -> lap times (the clock resets each lap)
      5. write extracted\modtests\<stamp>_<label>\report.md + a contact sheet,
         append a row to extracted\modtests\results.csv, restore vanilla data.

    Safety: refuses to run while a DIRT 5 instance is open that the harness did
    not start itself (the user may be playing). Keys and screenshots only go to
    the game window while it has focus. Driving steals focus - don't type
    elsewhere during a run.

.EXAMPLE
    .\Test-Dirt5Mod.ps1                        # vanilla baseline
.EXAMPLE
    .\Test-Dirt5Mod.ps1 -Mods tipsy=2.5 -Label tipsy
.EXAMPLE
    .\Test-Dirt5Mod.ps1 -Mods gravity=-0.6 -LocationRight 2 -TrackRight 1   # another location/track (read back from the race intro)
.EXAMPLE
    .\Test-Dirt5Mod.ps1 -CarClassNext 1 -LiveryRight 5            # first car of the next class, 4th livery texture
.EXAMPLE
    .\Test-Dirt5Mod.ps1 -Suite party           # every party preset back to back
.EXAMPLE
    .\Test-Dirt5Mod.ps1 -Summary               # results table
#>
[CmdletBinding()]
param(
    [string[]] $Mods,
    [string[]] $GameArgs,          # extra game options, e.g. '--micromachinescamera'
    [string[]] $D5ml,              # D5ML mods (mods\<name>) to apply instead of -Mods recipes
    [int] $LiveryRight = 0,        # livery page: press RIGHT n times before confirming (2 = first livery texture)
    [int] $CarClassNext = 0,       # car page: NEXT CLASS (E) n times first (a fresh profile owns the first car of each class)
    [int] $CarRight = 0,           # car page: RIGHT n times (other cars of the class; unowned ones show BUY)
    [int] $LocationRight = -1,     # Event Setup: open the LOCATION strip, RIGHT n times (0 = Brazil, 1 = China, 2 = Greece ...)
    [int] $TrackRight = 0,         # ... then RIGHT n times in that location's TRACK strip (0 = its first track)
    [int] $FocusWait = 180,        # recording pauses while the game isn't in the foreground, at most this many seconds
    [string] $Label,
    [int] $Seconds = 130,
    [ValidateSet('party', 'singles')] [string] $Suite,
    [switch] $Summary,
    [string] $Reanalyze,           # recompute lap times from an existing run folder's clock.txt
    [switch] $Keep,
    [string] $OutRoot = (Join-Path $PSScriptRoot '..\extracted\modtests')
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$input_ = Join-Path $PSScriptRoot 'Send-Dirt5Input.ps1'
$ocr = Join-Path $PSScriptRoot 'Read-Dirt5Text.ps1'
New-Item -ItemType Directory -Force $OutRoot | Out-Null
$OutRoot = (Resolve-Path $OutRoot).Path
$csv = Join-Path $OutRoot 'results.csv'
$pidFile = Join-Path $OutRoot '.harness.pid'
$clockCrop = '0.05,0.11,0.13,0.05'   # HUD race clock, top-left, fractions of the frame
$intro = ''
if (-not ('D5Harness.Focus' -as [type])) {
    Add-Type -Namespace D5Harness -Name Focus -MemberDefinition @'
[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(System.IntPtr hWnd, out uint pid);
'@
}
# by process, not by window handle: the game swaps its window during boot
function Test-GameFocus([int] $gamePid) {
    $fg = 0; [D5Harness.Focus]::GetWindowThreadProcessId([D5Harness.Focus]::GetForegroundWindow(), [ref] $fg) | Out-Null
    $fg -eq $gamePid
}

function Get-LapTimes([string[]] $clock) {
    <# clock.txt lines "<frame>`t<ocr text>" -> @{ laps = seconds per finished lap; max = last clock } #>
    $pts = foreach ($line in $clock) {
        $f, $txt = $line -split "`t", 2
        if ($txt -match '(\d\d):(\d\d)[.,](\d\d\d)') {
            [pscustomobject]@{ f = $f; t = [int]$Matches[1] * 60 + [int]$Matches[2] + [int]$Matches[3] / 1000 }
        }
    }
    $deltas = for ($i = 1; $i -lt $pts.Count; $i++) { $d = $pts[$i].t - $pts[$i - 1].t; if ($d -gt 0 -and $d -lt 5) { $d } }
    $step = if ($deltas) { ($deltas | Sort-Object)[[int]($deltas.Count / 2)] } else { 1.2 }
    # OCR misreads single digits ("01:14.0" -> "02:14.0", "00:10.9" -> "00:20.9"): a value that
    # jumps ahead by far more than one frame is corrected by -60 s / -10 s if that lands next to
    # its predecessor, otherwise dropped - so it can't fake a lap change
    $clean = [System.Collections.Generic.List[object]]::new()
    foreach ($p in $pts) {
        if ($clean.Count -and ($p.t - $clean[-1].t) -gt 3 * $step + 1) {
            $prev = $clean[-1].t
            $fix = @(60, 10) | ForEach-Object { $p.t - $_ } | Where-Object { $_ -ge $prev -and $_ -le $prev + 3 * $step + 1 } | Select-Object -First 1
            if ($null -eq $fix) { continue }
            $p = [pscustomobject]@{ f = $p.f; t = $fix }
        }
        $clean.Add($p)
    }
    $pts = @($clean)
    $laps = @(for ($i = 1; $i -lt $pts.Count; $i++) {
        if ($pts[$i].t -lt $pts[$i - 1].t - 5) { [Math]::Round($pts[$i - 1].t + [Math]::Max(0, $step - $pts[$i].t), 1) }
    })
    @{ laps = $laps; max = if ($pts) { ($pts | Measure-Object t -Maximum).Maximum } else { $null } }
}
function Format-Lap($s) { [string]::Format([Globalization.CultureInfo]::InvariantCulture, '{0}:{1:00.0}', [int][Math]::Floor($s / 60), ($s % 60)) }

if ($Reanalyze) {
    $lt = Get-LapTimes (Get-Content (Join-Path $Reanalyze 'clock.txt'))
    "laps: $(($lt.laps | ForEach-Object { Format-Lap $_ }) -join '  ')   last clock: $(if ($null -ne $lt.max) { Format-Lap $lt.max })"
    return
}

if ($Summary) {
    if (-not (Test-Path $csv)) { 'no results yet'; return }
    Import-Csv $csv | Format-Table -AutoSize | Out-String -Width 200
    return
}

if ($Suite) {
    $runs = if ($Suite -eq 'party') {
        @(@{ L = 'vanilla'; M = @() }) + ('mondfahrt', 'beschwipst', 'eiskunstlauf', 'kneipe', 'bettzeit', 'chaos' |
            ForEach-Object { @{ L = $_; M = @($_) } })
    } else {
        @(@{ L = 'vanilla'; M = @() }) +
        ('tipsy', 'drehwurm', 'glatteis', 'wackelpudding', 'windschatten', 'einkaufswagen', 'fallschirm', 'flugstunde', 'partytext' |
            ForEach-Object { @{ L = $_; M = @($_) } })
    }
    foreach ($r in $runs) {
        try { & $PSCommandPath -Mods $r.M -Label $r.L -Seconds $Seconds }
        catch { Write-Warning "run '$($r.L)' failed: $_" }
    }
    & $PSCommandPath -Summary
    return
}

if (-not $Label) {
    $Label = if ($D5ml) { 'd5ml_' + ($D5ml -join '+') } elseif ($Mods) { $Mods -join '+' }
             elseif ($GameArgs) { ($GameArgs -join '+').TrimStart('-') } else { 'vanilla' }
    $Label = $Label -replace '[^\w+=.-]', '_'
}
$Mods = @($Mods | Where-Object { $_ })
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$dir = Join-Path $OutRoot "${stamp}_$Label"
New-Item -ItemType Directory -Force $dir | Out-Null
$log = Join-Path $dir 'run.log'
function Log($m) { $line = "{0:HH:mm:ss} {1}" -f (Get-Date), $m; Write-Host $line; Add-Content $log $line }

# --- safety: never kill a game the user started -----------------------------------
function Stop-HarnessGame {
    $p = Get-Process game_release -ErrorAction SilentlyContinue
    if (-not $p) { return }
    $mine = (Test-Path $pidFile) -and ((Get-Content $pidFile) -eq "$($p.Id)")
    if (-not $mine) { throw "DIRT 5 is running (pid $($p.Id)) and was not started by the harness - quit it first" }
    Stop-Process -Id $p.Id -Force; Start-Sleep 3
}
Stop-HarnessGame

function Shot([string] $name) {
    & $input_ -Shot $name -OutDir $dir 3>$null | Out-Null
    Join-Path $dir "$name.png"
}
function ScreenText([string] $name) {
    $f = Shot $name
    if (-not (Test-Path $f)) { return '' }
    ((powershell -NoProfile -File $ocr -Path $f) -split "`t", 2)[-1]
}
function Tap([string[]] $keys) { & $input_ -Tap $keys | Out-Null }
function Expect([string] $name, [string] $pattern, [int] $tries = 4) {
    for ($i = 1; $i -le $tries; $i++) {
        $t = ScreenText "$name`_$i"
        if ($t -match $pattern) { Log "page ok: $name"; return $t }
        Start-Sleep -Milliseconds 1500
    }
    throw "expected page '$name' (/$pattern/) not found; last OCR: $t"
}

$result = [ordered]@{ time = $stamp; label = $Label; mods = (@($Mods) + @($D5ml | ForEach-Object { "d5ml:$_" }) + @($GameArgs) | Where-Object { $_ }) -join ' '; lap1 = ''; lap2 = ''; resets = ''; frames = 0; status = 'fail' }
try {
    # --- 1. apply + launch ----------------------------------------------------------
    $launch = @{ FastBoot = $true; ShowFps = $true; NoSave = $true; NoNetErrors = $true; AutoPilot = $true }
    if ($D5ml) {
        Push-Location $root
        python scripts\d5ml.py apply @D5ml *>&1 | ForEach-Object { Log "$_" }
        $rc = $LASTEXITCODE; Pop-Location
        if ($rc) { throw 'd5ml apply failed - game data left vanilla' }
        $launch.ExtraArgs = @($GameArgs | Where-Object { $_ })        # data stays as d5ml left it
    } elseif ($Mods) { $launch.Mods = $Mods; $launch.ExtraArgs = @($GameArgs | Where-Object { $_ }) }
    else { $launch.Vanilla = $true; $launch.ExtraArgs = @('--uselocalhandlingdefs') + @($GameArgs | Where-Object { $_ }) }
    & (Join-Path $PSScriptRoot 'Start-Dirt5Modded.ps1') @launch *>&1 | ForEach-Object { Log "$_" }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    do { Start-Sleep 1; $p = Get-Process game_release -ErrorAction SilentlyContinue } until (($p -and $p.MainWindowHandle -ne 0) -or $sw.Elapsed.TotalSeconds -gt 90)
    if (-not $p) { throw 'game window never appeared' }
    Set-Content $pidFile $p.Id
    Log "game pid $($p.Id)"

    # --- 2. menus -----------------------------------------------------------------------
    $sw.Restart()
    while ($sw.Elapsed.TotalSeconds -lt 90) { if ((ScreenText 'title') -match 'STA[RW]T') { break }; Start-Sleep 3 }
    Tap ENTER; Start-Sleep 6
    for ($i = 1; $i -le 8; $i++) {       # notices before the main menu
        $t = ScreenText "boot_$i"
        if ($t -match 'CA[RW]EE[RW].*A[RW]CADE') { break }
        if ($t -match 'latest game updates|Certain game modes|Wasserpause|connection|Raspberry|OK') { Tap ENTER; Start-Sleep 2 }
        else { Start-Sleep 2 }
    }
    Log 'main menu'
    Tap DOWN, DOWN, ENTER; Start-Sleep 2
    # OCR mangles uwu'd W ("FWEE" -> "FVVEE"), so any Arcade token counts; only clear
    # Career text means a key got lost on the main menu
    $arcade = 'F[RW]EE P[LW]AY|F[RW]EE BEE[RW]|FREIBIER|TIME T[RW]IA[LW]|TIME TVVIA|PVVAY'
    $career = 'Become|pwotég|protég|CONTENT PACK|Content Pack'
    $t = Expect 'arcade' "$arcade|$career" 3
    if ($t -match $career -and $t -notmatch $arcade) {        # landed in Career: back out, retry
        Log 'wrong page, retrying'; Tap ESC; Start-Sleep 2; Tap DOWN, DOWN, ENTER; Start-Sleep 2
        Expect 'arcade2' $arcade | Out-Null
    }
    Tap ENTER; Start-Sleep 2
    $t = Expect 'setup' 'STA[RW]T EVENT|NOCH EINS|ONE MO[RW]E'
    $track = if ($t -match 'RIO SEAFRONT|SEAFRONT') { 'Rio Seafront' } else { 'unknown track' }
    if ($LocationRight -ge 0) {
        # the page opens with the LOCATION tile selected; its strip and the TRACK strip use a display
        # font OCR can't read, so we count presses and read the track off the race intro instead
        Tap ENTER; Start-Sleep 2
        if ($LocationRight) { Tap (@('RIGHT') * $LocationRight); Start-Sleep 1 }
        Shot 'location_pick' | Out-Null
        Tap ENTER; Start-Sleep 2
        if ($TrackRight) { Tap (@('RIGHT') * $TrackRight); Start-Sleep 1 }
        Shot 'track_pick' | Out-Null
        Tap ENTER; Start-Sleep 2
        Expect 'setup_track' 'STA[RW]T EVENT|NOCH EINS|ONE MO[RW]E' | Out-Null
        $track = "location +$LocationRight, track +$TrackRight"
        Log "track: $track"
    }
    Tap DOWN, ENTER; Start-Sleep 2
    # page titles use a display font OCR can't read; the button bars it can
    Expect 'car' 'VEHIC[LW]E|NEXT C[LW]ASS|HAND[LW]ING|PE[RW]FO[RW]MANCE' | Out-Null
    if ($CarClassNext -or $CarRight) {
        for ($i = 0; $i -lt $CarClassNext; $i++) { Tap E; Start-Sleep 2 }
        if ($CarRight) { Tap (@('RIGHT') * $CarRight); Start-Sleep 1 }
        Shot 'car_pick' | Out-Null
        Log "car: NEXT CLASS x$CarClassNext, RIGHT x$CarRight"
    }
    Tap ENTER; Start-Sleep 2
    Expect 'livery' '[LW]IVE[RW]Y|C[RW]EATE' | Out-Null
    if ($LiveryRight) {        # slot 1 = default paint, then CREATE, then the livery textures
        Tap (@('RIGHT') * $LiveryRight); Start-Sleep 1
        Shot 'livery_pick' | Out-Null
        Log "livery: RIGHT x$LiveryRight"
    }
    Tap ENTER
    Log "race loading ($track)"

    # --- 3. race --------------------------------------------------------------------------
    # intro fly-over shows "Lancia 037 Evo 2 / RIO SEAFRONT, BRAZIL / DAWN" - so does the
    # livery page, hence also require that the page chrome (SELECT/LIVERY) is gone
    Start-Sleep 8; $sw.Restart(); $seen = $false
    while (-not $seen -and $sw.Elapsed.TotalSeconds -lt 60) {
        $t = ScreenText 'intro'
        $seen = ($t -match '037|Evo|DYNAMIC|DAWN|DUSK|MORNING|AFTERNOON|EVENING|NIGHT|CLEAR|RAIN|SNOW|BRAZIL|CHINA|GREECE|ITALY|MOROCCO|NORWAY|NEPAL|AFRICA|USA|ARIZONA|NEW YORK') -and
                 ($t -notmatch '[LW]IVE[RW]Y|SE[LW]ECT')
        if (-not $seen) { Start-Sleep 2 }
    }
    if (-not $seen) { throw "race intro not detected; last OCR: $t" }
    $intro = ($t -replace '\s+', ' ').Trim()
    Log "race intro: $intro"
    Tap ENTER
    $sw.Restart(); $n = 0
    while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
        if (-not (Test-GameFocus $p.Id)) {
            # the user clicked elsewhere or a popup took focus: screenshots would be skipped, so wait
            $sw.Stop(); $since = Get-Date; Log 'paused: DIRT 5 is not in the foreground'
            while (-not (Test-GameFocus $p.Id) -and ((Get-Date) - $since).TotalSeconds -lt $FocusWait) { Start-Sleep 1 }
            if (-not (Test-GameFocus $p.Id)) { Log "no focus for $FocusWait s - stopping the recording"; break }
            Log ("resumed after {0:0} s" -f ((Get-Date) - $since).TotalSeconds); $sw.Start()
        }
        $n++; Shot ('f_{0:D3}' -f $n) | Out-Null
        Start-Sleep -Milliseconds 700
    }
    $saved = @(Get-ChildItem $dir -Filter 'f_*.png').Count
    $result.frames = $saved
    Log "recorded $saved of $n frames$(if ($saved -lt $n) { " ($($n - $saved) skipped: game was not in the foreground)" })"
} catch {
    Log "ERROR: $_"
} finally {
    if (-not $Keep) {
        try { Stop-HarnessGame } catch { Log "not stopping: $_" }
        Push-Location $root; python scripts\d5mod.py restore | Out-Null; Pop-Location
        Log 'game closed, data restored to vanilla'
    }
}

# --- 4. lap times from the HUD clock ----------------------------------------------------
$frames = Get-ChildItem $dir -Filter 'f_*.png' | Sort-Object Name
if ($frames) {
    $clock = powershell -NoProfile -File $ocr -Path ($frames.FullName -join ',') -Crop $clockCrop
    $clock | Set-Content (Join-Path $dir 'clock.txt')
    $lt = Get-LapTimes $clock
    if ($lt.laps.Count -ge 1) { $result.lap1 = Format-Lap $lt.laps[0] }
    elseif ($null -ne $lt.max) { $result.lap1 = '>' + (Format-Lap $lt.max) }   # lap 1 not finished
    if ($lt.laps.Count -ge 2) { $result.lap2 = Format-Lap $lt.laps[1] }
    if ($result.frames -gt 0) { $result.status = if ($lt.laps) { 'ok' } else { 'no lap' } }
    Push-Location $root
    python scripts\d5sheet.py (Join-Path $dir 'sheet.png') @($frames.FullName) --cols 8 --width 240 | Out-Null
    $r = python scripts\d5sheet.py --resets @($frames.FullName)
    if ("$r" -match 'resets=(\d+)') { $result.resets = [int]$Matches[1] }
    Pop-Location
}

@"
# Mod test: $Label

| | |
|---|---|
| mods / options | ``$(if ($result.mods) { $result.mods } else { 'vanilla' })`` |
| when | $stamp |
| status | $($result.status) |
| lap 1 (standing start) | $($result.lap1) |
| lap 2 (flying) | $($result.lap2) |
| car resets (flips/crashes put back on track) | $($result.resets) |
| frames | $($result.frames) |

Event: Arcade Free Play$(if ($LocationRight -ge 0 -or $CarRight -or $CarClassNext) { " - location +$LocationRight, track +$TrackRight, class +$CarClassNext, car +$CarRight" } else { ' default (Land Rush, Rio Seafront, Lancia 037 Evo 2, 12 cars)' }), ``--autopilotall``.
Race intro (OCR): $intro
Clock OCR per frame: ``clock.txt``. Contact sheet: ``sheet.png``. Log: ``run.log``.
"@ | Set-Content (Join-Path $dir 'report.md')
[pscustomobject]$result | Export-Csv $csv -Append -NoTypeInformation
Log "result: $($result.status)  lap1=$($result.lap1)  lap2=$($result.lap2)  -> $dir"
