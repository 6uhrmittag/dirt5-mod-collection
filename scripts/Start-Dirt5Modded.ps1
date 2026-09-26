<#
.SYNOPSIS
    Launch the loose DIRT 5 install (C:\Games\DIRT 5) with data mods and/or the
    game's own hidden debug command-line options. Offline only.

.DESCRIPTION
    Two mod layers, freely combinable:

    1. DATA MODS (-Mods) - patched via scripts\d5mod.py before launch. Mods,
       party presets and roulette: `python scripts\d5mod.py list`, e.g.
         -Mods 'gravity=-0.6','power=2'      -Mods beschwipst      -Mods roulette=3
       Any active data mod adds --uselocalhandlingdefs so the game reads the
       patched physics/vehicledefs instead of its gamesparks/server copy
       (harmless for the AI-only mods; vanilla + flag drives normally).
       -Vanilla restores the untouched data before launch.
       Without -Mods/-Vanilla the data is left exactly as it is.

    2. BUILT-IN OPTIONS (switches below) - strings from game_release.exe's
       option table; they need no file changes at all.

    Always added: --disableonline (never go online with modded data).

    The game is started with __COMPAT_LAYER=RunAsInvoker: the loose install
    carries a RUNASADMIN compat flag (HKCU AppCompatFlags\Layers), and an
    elevated game silently drops all input injected from a normal shell (UIPI),
    which would make scripts\Send-Dirt5Input.ps1 useless. The game runs fine
    unelevated. -Elevated keeps the old behaviour.

.EXAMPLE
    .\Start-Dirt5Modded.ps1 -FastBoot -NoSave -Script 'data:test/benchmark_meteora_full_grid.wbs'
.EXAMPLE
    .\Start-Dirt5Modded.ps1 -Mods 'gravity=-0.6','power=2' -MicroMachines
.EXAMPLE
    .\Start-Dirt5Modded.ps1 -Vanilla -FastBoot
.EXAMPLE
    .\Start-Dirt5Modded.ps1 -ListMods
#>
[CmdletBinding()]
param(
    [string[]] $Mods,
    [switch] $Vanilla,
    [switch] $ListMods,

    [switch] $MicroMachines,   # --micromachinescamera : top-down Micro Machines camera
    [switch] $NoAI,            # --disableai           : no AI opponents
    [switch] $AutoPilot,       # --autopilotall        : AI drives the player car(s)
    [switch] $FreezeTimeOfDay, # --pausetimeofday      : environment clock stops
    [switch] $NoHud,           # --noosd               : hide the on-screen display
    [switch] $FastBoot,        # --skipvideos --skiplegals
    [switch] $ShowFps,         # --releasefps
    [switch] $UnlockAll,       # --nocashlocks --noitemlocks --unlockallentitlements
    [switch] $NoSave,          # --nosave              : profile is not written this session
    [switch] $NoNetErrors,     # --nonetworkerrors     : hide the fruit-coded "servers lost" popups
    [string] $Script,          # --script <wbs>        : boot script, replaces the normal phase flow
    [switch] $Elevated,        # keep the install's RUNASADMIN flag (blocks injected input)
    [string[]] $ExtraArgs,
    [string] $GameDir = 'C:\Games\DIRT 5',
    [switch] $WhatIf
)
$ErrorActionPreference = 'Stop'
$d5mod = Join-Path $PSScriptRoot 'd5mod.py'

if ($ListMods) { python $d5mod list; return }

if (-not $WhatIf -and (Get-Process game_release -ErrorAction SilentlyContinue)) {
    throw 'DIRT 5 is already running - quit it first (data mods are read at boot).'
}

$gameArgs = [System.Collections.Generic.List[string]]::new()
$gameArgs.Add('--disableonline')

if ($Vanilla -and $Mods) { throw 'Use either -Vanilla or -Mods, not both.' }
if ($WhatIf) {
    if ($Vanilla) { Write-Host 'would restore vanilla data' -ForegroundColor DarkGray }
    if ($Mods) { Write-Host "would apply: $($Mods -join ' ')" -ForegroundColor DarkGray }
} elseif ($Vanilla) {
    python $d5mod restore
    if ($LASTEXITCODE) { throw 'd5mod restore failed' }
} elseif ($Mods) {
    python $d5mod apply @Mods
    if ($LASTEXITCODE) { throw 'd5mod apply failed - game data left vanilla' }
}
# vehicle physics mods only take effect when the game reads the local vdefs
$state = Join-Path $GameDir 'dat\index\d5mod-state.json'
$applied = if ($WhatIf -and $Mods) { $Mods | ForEach-Object { ($_ -split '=')[0] } }
           elseif ((Test-Path $state) -and -not ($WhatIf -and $Vanilla)) { (Get-Content $state -Raw | ConvertFrom-Json).mods.mod }
if ($applied) {
    if ($ExtraArgs -notcontains '--uselocalhandlingdefs') { $gameArgs.Add('--uselocalhandlingdefs') }
    Write-Host "data mods active: $($applied -join ', ')" -ForegroundColor Cyan
} else {
    Write-Host 'data: vanilla' -ForegroundColor DarkGray
}

$map = [ordered]@{
    MicroMachines   = @('--micromachinescamera')
    NoAI            = @('--disableai')
    AutoPilot       = @('--autopilotall')
    FreezeTimeOfDay = @('--pausetimeofday')
    NoHud           = @('--noosd')
    FastBoot        = @('--skipvideos', '--skiplegals')
    ShowFps         = @('--releasefps')
    UnlockAll       = @('--nocashlocks', '--noitemlocks', '--unlockallentitlements')
    NoSave          = @('--nosave')
    NoNetErrors     = @('--nonetworkerrors')
}
foreach ($k in $map.Keys) {
    if ((Get-Variable $k -ValueOnly)) { $map[$k] | ForEach-Object { $gameArgs.Add($_) } }
}
if ($UnlockAll -and -not $NoSave) {
    Write-Warning '-UnlockAll without -NoSave: anything you "buy" for free may persist in the profile.'
}
if ($Script) { $gameArgs.Add('--script'); $gameArgs.Add($Script) }
$ExtraArgs | Where-Object { $_ } | ForEach-Object { $gameArgs.Add($_) }

$exe = Join-Path $GameDir 'game_release.exe'
Write-Host "launch: $exe $($gameArgs -join ' ')$(if (-not $Elevated) { '  [RunAsInvoker]' })" -ForegroundColor Green
if ($WhatIf) { return }
$prevLayer = $env:__COMPAT_LAYER
if (-not $Elevated) { $env:__COMPAT_LAYER = 'RunAsInvoker' }
try { Start-Process -FilePath $exe -WorkingDirectory $GameDir -ArgumentList $gameArgs }
finally { $env:__COMPAT_LAYER = $prevLayer }
