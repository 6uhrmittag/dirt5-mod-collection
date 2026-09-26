<#
.SYNOPSIS
    Package a d5mod mod/preset as a NexusMods-style release: release\<Name>\ + release\<Name>.zip

.DESCRIPTION
    The package contains OUR code only (d5x/d5mod/d5tex/d5art + install/uninstall
    .bat) - no Codemasters files. install.bat patches the user's own game data
    (original packs are never written; uninstall.bat = vanilla).
    -Preview copies a screenshot (e.g. a frame from extracted\modtests\...) as preview.png.

.EXAMPLE
    .\Pack-Dirt5Mod.ps1 -Mods uwumax -Name UwU-MAX -Title 'UwU MAX' -Tagline 'the whole game talks like ur discord kitten now' -Preview extracted\modtests\...\title.png
#>
param(
    [Parameter(Mandatory)] [string[]] $Mods,
    [Parameter(Mandatory)] [string] $Name,
    [string] $Title = $Name,
    [string] $Tagline = 'a DIRT 5 mod',
    [string[]] $Features,
    [string] $Preview,
    [string] $Version = '1.0.0',
    [string] $OutRoot = (Join-Path $PSScriptRoot '..\release')
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$OutRoot = [IO.Path]::GetFullPath($OutRoot)
$dir = Join-Path $OutRoot $Name
Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force (Join-Path $dir 'tools') | Out-Null
'd5x.py', 'd5mod.py', 'd5tex.py', 'd5art.py' | ForEach-Object { Copy-Item (Join-Path $PSScriptRoot $_) (Join-Path $dir 'tools') }
if ($Preview) { Copy-Item $Preview (Join-Path $dir 'preview.png') }

$modArgs = $Mods -join ' '
if (-not $Features) {
    Push-Location $root
    $Features = python scripts\d5mod.py list | Where-Object { $_ -match '^\s{2}(\S+)\s' -and ($Mods -contains $Matches[1]) } |
        ForEach-Object { ($_ -replace '^\s+(\S+)\s+default=\S+\s+', '**$1**: ') }
    Pop-Location
}

$bat = @"
@echo off
rem $Title $Version - installer. Needs Python 3.12+ with: pip install lz4 numpy pillow
setlocal
if not defined DIRT5_DAT set "DIRT5_DAT=C:\Games\DIRT 5\dat"
if not exist "%DIRT5_DAT%\index\dat.ndx" (
  set /p "GAME=DIRT 5 folder (the one with game_release.exe): "
  call set "DIRT5_DAT=%%GAME%%\dat"
)
tasklist /fi "imagename eq game_release.exe" | find /i "game_release.exe" >nul && (echo Quit DIRT 5 first. & pause & exit /b 1)
python "%~dp0tools\d5mod.py" apply $modArgs || (echo Install failed - your game data was left untouched. & pause & exit /b 1)
echo.
echo  $Title installed. Launch DIRT 5 OFFLINE and have fun :3
echo  (tip: start game_release.exe with --uselocalhandlingdefs --disableonline)
pause
"@
Set-Content (Join-Path $dir 'install.bat') $bat -Encoding ascii
@"
@echo off
if not defined DIRT5_DAT set "DIRT5_DAT=C:\Games\DIRT 5\dat"
python "%~dp0tools\d5mod.py" restore
echo DIRT 5 is vanilla again. :(
pause
"@ | Set-Content (Join-Path $dir 'uninstall.bat') -Encoding ascii

@"
# $Title for DIRT 5 ✨ v$Version

> $Tagline

> **⚠ read this first.** about 99 % of this mod's code was written by an AI (Claude Code), directed and play-tested by us. it's a **hobby project**: [@6uhrmittag](https://github.com/6uhrmittag) and [@VoidCrowned](https://github.com/VoidCrowned) love DIRT 5 and wanted a bit more variety in this lovely game. **nothing is guaranteed** — no warranty, no support promise. keep backups, play offline.

$(if ($Preview) { '![preview](preview.png)' })

## what it does

$(($Features | ForEach-Object { "- $_" }) -join "`n")

## install (30 seconds, no cap)

1. get **Python 3.12+** and run ``pip install lz4 numpy pillow`` once
2. quit DIRT 5, double-click **install.bat** (asks for the game folder if it isn't ``C:\Games\DIRT 5``)
3. play **offline** — start the game with ``--uselocalhandlingdefs --disableonline``

**uninstall:** double-click **uninstall.bat** → vanilla again.

## is it safe?

- the original ``.dat`` packs are **never written**. the mod lands in an extra pack slot + a patched ``dat.ndx`` (backup: ``dat.ndx.d5x-orig``)
- this zip contains **no game files** — everything is generated from *your* copy of the game on install
- **offline only.** don't take modded data online. seriously.
- tested on the DIRT 5 Microsoft Store build v1.2767.60 (loose install). Steam: untested, report back pls

## credits

made by macha with a suspicious amount of energy drinks. format reversing + tools: this repo (``d5x`` pack reader, ``d5mod`` patcher, ``d5tex`` BC1 texture encoder).
"@ | Set-Content (Join-Path $dir 'README.md') -Encoding utf8

$zip = Join-Path $OutRoot "$Name-$Version.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $dir '*') -DestinationPath $zip
Write-Host "packaged: $zip"
Get-ChildItem $dir -Recurse -File | ForEach-Object { '  ' + $_.FullName.Substring($dir.Length + 1) }
