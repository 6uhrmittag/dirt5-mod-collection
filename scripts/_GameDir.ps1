# Shared by D5ML.ps1 / Dirt5-Unlocked.ps1: where is DIRT 5? Stored in mods\.d5ml-settings.json.
# A valid folder contains game_release.exe and dat\index\dat.ndx.
$script:SettingsPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\mods\.d5ml-settings.json'))
function Test-GameDir([string] $dir) {
    $dir -and (Test-Path (Join-Path $dir 'game_release.exe')) -and (Test-Path (Join-Path $dir 'dat\index\dat.ndx'))
}
function Get-GameDir {
    if (Test-Path $script:SettingsPath) {
        $s = Get-Content $script:SettingsPath -Raw | ConvertFrom-Json
        if (Test-GameDir $s.gameDir) { return $s.gameDir }
    }
    foreach ($guess in 'C:\Games\DIRT 5', "$env:ProgramFiles\DIRT 5", "${env:ProgramFiles(x86)}\Steam\steamapps\common\DIRT 5") {
        if (Test-GameDir $guess) { return $guess }
    }
    $null
}
function Set-GameDir([string] $dir) {
    if (-not (Test-GameDir $dir)) { throw "not a DIRT 5 folder (needs game_release.exe and dat\index\dat.ndx): $dir" }
    New-Item -ItemType Directory -Force (Split-Path $script:SettingsPath) | Out-Null
    @{ gameDir = $dir } | ConvertTo-Json | Set-Content $script:SettingsPath -Encoding utf8
    $env:DIRT5_DAT = Join-Path $dir 'dat'
}
function Use-GameDir {
    $d = Get-GameDir
    if ($d) { $env:DIRT5_DAT = Join-Path $d 'dat' }
    $d
}
