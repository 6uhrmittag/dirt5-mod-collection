<#
.SYNOPSIS
    Build the NexusMods release zips of D5ML (mod loader) and DIRT 5 Unlocked (hidden options).

.DESCRIPTION
    Both zips contain the same small toolkit (our code only - no Codemasters files) with a
    different entry point and README:
      release\D5ML-<v>.zip            D5ML.bat          + README from docs\release\D5ML.md
      release\DIRT5-Unlocked-<v>.zip  DIRT5-Unlocked.bat + README from docs\release\Unlocked.md
    Screenshots: docs\release\screenshots\*.png|jpg (copied as screenshots\).
    Example mods: mods\_example-* (own art only).
#>
param(
    [string] $Version = '1.0.0',
    [ValidateSet('D5ML', 'Unlocked', 'All')] [string] $Only = 'All',   # CI releases each tool separately
    [string] $OutRoot = (Join-Path $PSScriptRoot '..\release')
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$OutRoot = [IO.Path]::GetFullPath($OutRoot)
$tool = 'd5x.py', 'd5mod.py', 'd5tex.py', 'd5art.py', 'd5ml.py', 'D5ML.ps1', 'Dirt5-Unlocked.ps1',
        '_SnapshotForm.ps1', '_GameDir.ps1', 'Start-Dirt5Modded.ps1'

$check = @'
where pwsh >nul 2>nul || (echo PowerShell 7 is needed: winget install Microsoft.PowerShell & pause & exit /b 1)
where python >nul 2>nul || (echo Python 3.12+ is needed: winget install Python.Python.3.12 & pause & exit /b 1)
python -c "import lz4, numpy, PIL" 2>nul || (
  echo First start: installing the Python packages lz4, numpy, pillow ...
  python -m pip install --user -r "%~dp0requirements.txt" || (echo pip failed - run: python -m pip install lz4 numpy pillow & pause & exit /b 1)
)
'@

function New-Package([string] $name, [string] $readme, [string] $entryBat, [string] $entryScript) {
    $dir = Join-Path $OutRoot $name
    Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force "$dir\scripts", "$dir\docs", "$dir\mods", "$dir\screenshots" | Out-Null
    $tool | ForEach-Object { Copy-Item (Join-Path $root "scripts\$_") "$dir\scripts\" }
    'unlocked-options.json', 'dirt5-cli-options.txt' | ForEach-Object { Copy-Item (Join-Path $root "docs\$_") "$dir\docs\" }
    Copy-Item (Join-Path $root 'mods\README.md') "$dir\mods\"
    Get-ChildItem (Join-Path $root 'mods') -Directory -Filter '_example-*' | ForEach-Object { Copy-Item $_.FullName "$dir\mods\" -Recurse }
    Get-ChildItem (Join-Path $root 'docs\release\screenshots\*') -Include '*.png', '*.jpg' -ErrorAction SilentlyContinue | Copy-Item -Destination "$dir\screenshots\"
    Copy-Item (Join-Path $root "docs\release\$readme") "$dir\README.md"
    "lz4`nnumpy`npillow" | Set-Content "$dir\requirements.txt" -Encoding ascii
    foreach ($bat in @(@('D5ML.bat', 'D5ML.ps1'), @('DIRT5-Unlocked.bat', 'Dirt5-Unlocked.ps1'))) {
        "@echo off`r`nsetlocal`r`n$check`r`nstart `"`" pwsh -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"%~dp0scripts\$($bat[1])`"`r`n" |
            Set-Content (Join-Path $dir $bat[0]) -Encoding ascii
    }
    $zip = Join-Path $OutRoot "$name-$Version.zip"
    Remove-Item $zip -ErrorAction SilentlyContinue
    Compress-Archive -Path "$dir\*" -DestinationPath $zip
    $files = (Get-ChildItem $dir -Recurse -File).Count
    Write-Host ("{0}  ({1} files, {2:N0} KB)" -f $zip, $files, ((Get-Item $zip).Length / 1KB))
}

# never ship game data: fail loudly if anything that looks like it is in the example mods
$suspect = Get-ChildItem (Join-Path $root 'mods') -Recurse -File -Include '*.gtx', '*.gmp', '*.dat', '*.ndx', '*.vdef', '*.loc' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '\\_example-' }
if ($suspect) { throw "example mods contain game-format files: $($suspect.FullName -join ', ')" }

New-Item -ItemType Directory -Force $OutRoot | Out-Null
if ($Only -in 'D5ML', 'All') { New-Package 'D5ML' 'D5ML.md' 'D5ML.bat' 'D5ML.ps1' }
if ($Only -in 'Unlocked', 'All') { New-Package 'DIRT5-Unlocked' 'Unlocked.md' 'DIRT5-Unlocked.bat' 'Dirt5-Unlocked.ps1' }
