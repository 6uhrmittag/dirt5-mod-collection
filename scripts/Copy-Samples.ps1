<#
.SYNOPSIS
    Copy a small, safe set of DIRT 5 archive samples into the project workspace
    for offline study. COPIES ONLY — never opens the originals for writing.

.DESCRIPTION
    Pulls three kinds of sample from the read-only WindowsApps install:
      1. The full master index  dat\index\dat.ndx  (~29 MB) — the file table.
      2. A full copy of the smallest real .dat pack (for end-to-end tool tests).
      3. Header WINDOWS (first N MB) of a few representative large packs, so we can
         study container structure without copying multi-GB files.

    Uses FileStream for the header windows, which avoids .NET's 2 GB
    File.ReadAllBytes limit (the >2 GB packs choke on ReadAllBytes).

.PARAMETER WindowMB
    Size (MB) of the header window pulled from large packs. Default 16.

.PARAMETER Force
    Overwrite existing samples.

.EXAMPLE
    .\Copy-Samples.ps1
    .\Copy-Samples.ps1 -WindowMB 32 -Force
#>
[CmdletBinding()]
param(
    [int]    $WindowMB = 16,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'

$PackageName = 'CodemastersSoftwareCompan.DiRT5'
$OutDir      = Join-Path $PSScriptRoot '..\samples' | Resolve-Path | Select-Object -ExpandProperty Path

function Get-Dirt5InstallPath {
    try {
        $pkg = Get-AppxPackage -Name $PackageName -ErrorAction Stop | Select-Object -First 1
        if ($pkg -and $pkg.InstallLocation) { return $pkg.InstallLocation }
    } catch { }
    $glob = Join-Path $env:ProgramFiles "WindowsApps\$PackageName*_x64__*"
    (Get-ChildItem $glob -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1).FullName
}

function Copy-HeaderWindow {
    param([string]$SrcPath, [string]$DstPath, [int]$Bytes)
    $in = [System.IO.File]::Open($SrcPath, 'Open', 'Read', 'ReadWrite')
    try {
        $take = [Math]::Min([long]$Bytes, $in.Length)
        $buf  = New-Object byte[] $take
        [void]$in.Read($buf, 0, $take)
        [System.IO.File]::WriteAllBytes($DstPath, $buf)
    } finally { $in.Close() }
    return $take
}

$base = Get-Dirt5InstallPath
if (-not $base) { throw "DIRT 5 (Xbox build) install not found." }
$datDir = Join-Path $base 'dat'
Write-Host "Source install: $base"
Write-Host "Output:         $OutDir`n"

$window = $WindowMB * 1MB

# --- 1. Full index -----------------------------------------------------------
$ndxSrc = Join-Path $datDir 'index\dat.ndx'
if (Test-Path $ndxSrc) {
    $ndxDst = Join-Path $OutDir 'dat.ndx'
    if ((Test-Path $ndxDst) -and -not $Force) { Write-Host "skip (exists): dat.ndx" }
    else { Copy-Item $ndxSrc $ndxDst -Force; Write-Host ("copied index:  dat.ndx  ({0:N0} bytes)" -f (Get-Item $ndxDst).Length) }
} else { Write-Warning "index not found: $ndxSrc" }

# --- 2. Smallest full pack ---------------------------------------------------
$smallest = Get-ChildItem "$datDir\*.dat" | Where-Object { $_.Length -gt 0 } |
            Sort-Object Length | Select-Object -First 1
if ($smallest) {
    $dst = Join-Path $OutDir $smallest.Name
    if ((Test-Path $dst) -and -not $Force) { Write-Host "skip (exists): $($smallest.Name)" }
    else { Copy-Item $smallest.FullName $dst -Force; Write-Host ("copied pack:   {0}  ({1:N0} bytes)" -f $smallest.Name, $smallest.Length) }
}

# --- 3. Header windows of representative packs -------------------------------
# One of each interesting KIND we can find, so the scanner sees each layout.
$reps = @()
foreach ($kind in 'ARC','FPX','OTH','INIT','WIN','DEV') {
    $cand = Get-ChildItem "$datDir\*_$kind.dat" -ErrorAction SilentlyContinue |
            Where-Object { $_.Length -gt 0 } | Sort-Object Length -Descending | Select-Object -First 1
    if ($cand) { $reps += $cand }
}
foreach ($r in $reps) {
    $dst = Join-Path $OutDir ("{0}.head.bin" -f [IO.Path]::GetFileNameWithoutExtension($r.Name))
    if ((Test-Path $dst) -and -not $Force) { Write-Host "skip (exists): $(Split-Path $dst -Leaf)"; continue }
    $got = Copy-HeaderWindow -SrcPath $r.FullName -DstPath $dst -Bytes $window
    Write-Host ("header window: {0,-22} <- {1}  ({2:N0} bytes)" -f (Split-Path $dst -Leaf), $r.Name, $got)
}

Write-Host "`nDone. Samples in: $OutDir"
