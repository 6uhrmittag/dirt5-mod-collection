<#
.SYNOPSIS
    Party launcher for splitscreen nights: picks tonight's silly mod set, shows
    it big in the console, launches DIRT 5 (loose install, offline).

.DESCRIPTION
    Data mods are read at boot, so a mod set lasts one game session; quit and run
    this again for the next round of roulette.

    Without -Preset the clock decides ("-Tonight" logic):
      before 23:00   roulette (2 random mods) - warming up
      23:00 - 01:00  one of the tipsy presets (beschwipst, eiskunstlauf, mondfahrt, chaos)
      01:00 - 06:00  bettzeit: slow-motion last round, then bed
    All mods hit every car equally (both players and the AI) - fair for two pads.

    Presets (see `python scripts\d5mod.py list`):
      mondfahrt     moon gravity + steer mid-air
      beschwipst    top-heavy wobbly jelly cars
      eiskunstlauf  black ice + pirouettes
      kneipe        the AI is hammered and never catches up; big slipstream for
                    whoever is behind - the two of you fight for the win
      bettzeit      parachute drag + less power: slow motion
      chaos         a bit of everything
      roulette[=n]  n random mods
    Always added (unless -NoPartyText): partytext - QUIT says BETT, START EVENT says
    NOCH EINS!!, NEW LAP says PROST!!!, the final lap is LAST ORDER, and the
    "latest updates" nag at every boot becomes a water-break reminder - and
    stammtisch: the AI field are pub regulars (Tante Erna, Korn-Klaus, Sandmann ...).

.EXAMPLE
    .\Start-Dirt5Party.ps1                  # the clock picks
.EXAMPLE
    .\Start-Dirt5Party.ps1 -Preset kneipe -JustUs    # no AI at all, only the two of you
.EXAMPLE
    .\Start-Dirt5Party.ps1 -Preset roulette=3 -WhatIf
#>
[CmdletBinding()]
param(
    [string] $Preset,
    [switch] $JustUs,          # --disableai: no AI cars
    [switch] $Night,           # --pausetimeofday: the clock stops (keep night races dark)
    [switch] $NoPartyText,     # keep the normal menu texts (partytext is on by default)
    [switch] $Vanilla,
    [switch] $WhatIf,
    [datetime] $Now = (Get-Date)
)
$ErrorActionPreference = 'Stop'

$lines = @{
    roulette     = 'Roulette! Keiner weiss, was passiert. Auch der Code nicht.'
    mondfahrt    = 'Mondfahrt: Schwerkraft ist heute optional. Lenken in der Luft erlaubt.'
    beschwipst   = 'Beschwipst: Die Autos haben mehr getrunken als ihr.'
    eiskunstlauf = 'Eiskunstlauf: Glatteis und Pirouetten. Punktrichter sind anwesend.'
    kneipe       = 'Kneipe: Die KI ist voll. Wer hinten liegt, wird im Windschatten heimgezogen.'
    bettzeit     = 'Bettzeit: Letzte Runde in Zeitlupe. Danach wirklich schlafen!'
    chaos        = 'Chaos: von allem ein bisschen. Viel Glueck.'
    uwumax       = 'UwU MAX: Die ganze Welt spricht jetzt wie euer Gamertag. OwO'
}

if (-not $Preset -and -not $Vanilla) {
    $h = $Now.Hour
    $Preset = if ($h -ge 1 -and $h -lt 6) { 'bettzeit' }
              elseif ($h -ge 23 -or $h -lt 1) { Get-Random -InputObject 'beschwipst', 'eiskunstlauf', 'mondfahrt', 'chaos' }
              else { 'roulette' }
}
$key = ($Preset -split '=')[0]

$banner = if ($Vanilla) { 'Heute ohne Mods. Langweilig, aber ehrlich.' } elseif ($lines[$key]) { $lines[$key] } else { "Mods: $Preset" }
$w = [Math]::Max(40, $banner.Length + 6)
Write-Host ('=' * $w) -ForegroundColor Magenta
Write-Host ("   DIRT 5 PARTY  -  {0:HH:mm}" -f $Now) -ForegroundColor Yellow
Write-Host "   $banner" -ForegroundColor Cyan
Write-Host ('=' * $w) -ForegroundColor Magenta
if ($Now.Hour -ge 2 -and $Now.Hour -lt 6) { Write-Host "   Es ist $('{0:HH:mm}' -f $Now). Nur noch EIN Rennen. Versprochen." -ForegroundColor Red }

$launch = @{ FastBoot = $true; NoNetErrors = $true; WhatIf = $WhatIf; NoAI = $JustUs; FreezeTimeOfDay = $Night }
if ($Vanilla) { $launch.Vanilla = $true }
else {
    $extra = if ($NoPartyText) { @() } elseif ($key -eq 'uwumax') { @('partytext') } else { @('partytext', 'stammtisch') }
    $launch.Mods = @($Preset) + $extra
}
& (Join-Path $PSScriptRoot 'Start-Dirt5Modded.ps1') @launch
