<#
.SYNOPSIS
    DIRT 5 Unlocked - launcher for the game's hidden developer options (+ optional data mods).

.DESCRIPTION
    Without parameters a window opens: grouped checkboxes (✓ = verified in-game,
    ? = untested), presets, a data-mods box (d5mod specs/presets), live command preview,
    "Copy command" and "Launch". Everything goes through Start-Dirt5Modded.ps1, which
    always adds --disableonline and starts the loose install unelevated.
    Unlock-type options force --nosave so free/unlocked items can't leak into the profile.

    Catalogue: docs\unlocked-options.json (curated from docs\dirt5-cli-options.txt).

.EXAMPLE
    .\Dirt5-Unlocked.ps1                                  # window
.EXAMPLE
    .\Dirt5-Unlocked.ps1 -Preset photo -DryRun            # print the launch, do nothing
.EXAMPLE
    .\Dirt5-Unlocked.ps1 -Preset couch -Mods beschwipst -Launch
#>
[CmdletBinding()]
param(
    [string] $Preset,
    [string[]] $Flags,
    [string[]] $Mods,
    [switch] $DryRun,
    [switch] $Launch,
    [string] $Snapshot,        # render the window to a PNG without showing/activating it
    [string] $Catalog = (Join-Path $PSScriptRoot '..\docs\unlocked-options.json')
)
$ErrorActionPreference = 'Stop'
$launcher = Join-Path $PSScriptRoot 'Start-Dirt5Modded.ps1'
. (Join-Path $PSScriptRoot '_GameDir.ps1')
$gameDir = Use-GameDir
$cat = Get-Content $Catalog -Raw -Encoding utf8 | ConvertFrom-Json
$options = @{}
foreach ($g in $cat.groups) { foreach ($o in $g.options) { $options[$o.flag] = $o } }

function Resolve-Launch([string[]] $flags, [string[]] $mods) {
    $flags = @($flags | Where-Object { $_ } | ForEach-Object { $_ -split '[,\s]+' } | Where-Object { $_ } |
        ForEach-Object { $_.TrimStart('-') } | Select-Object -Unique)
    $unknown = $flags | Where-Object { -not $options.ContainsKey($_) }
    if ($unknown) { Write-Warning "not in the catalogue (passed through anyway): $($unknown -join ', ')" }
    $forceNoSave = [bool]($flags | Where-Object { $options[$_].nosave })
    $launch = @{ ExtraArgs = @($flags | Where-Object { $_ -ne 'nosave' } | ForEach-Object { "--$_" }) }
    if ($forceNoSave -or $flags -contains 'nosave') { $launch.NoSave = $true }
    $mods = @($mods | Where-Object { $_ } | ForEach-Object { $_ -split '[,\s]+' } | Where-Object { $_ })
    if ($mods) { $launch.Mods = $mods }
    if ($gameDir) { $launch.GameDir = $gameDir }
    [pscustomobject]@{ Launch = $launch; ForcedNoSave = $forceNoSave -and -not ($flags -contains 'nosave') }
}

function Show-Command($r) {
    $a = $r.Launch
    $parts = @('.\scripts\Start-Dirt5Modded.ps1')
    if ($a.Mods) { $parts += "-Mods $(($a.Mods | ForEach-Object { "'$_'" }) -join ',')" }
    if ($a.NoSave) { $parts += '-NoSave' }
    if ($a.ExtraArgs) { $parts += "-ExtraArgs $(($a.ExtraArgs | ForEach-Object { "'$_'" }) -join ',')" }
    $parts -join ' '
}

# --- headless ------------------------------------------------------------------------------
if (($Preset -or $Flags -or $DryRun -or $Launch) -and -not $Snapshot) {
    $sel = @()
    if ($Preset) {
        $p = $cat.presets.$Preset
        if (-not $p) { throw "unknown preset '$Preset' (have: $(($cat.presets.PSObject.Properties.Name) -join ', '))" }
        $sel += $p.flags
    }
    $r = Resolve-Launch ($sel + $Flags) $Mods
    if ($r.ForcedNoSave) { Write-Host 'unlock options selected -> --nosave forced' -ForegroundColor Yellow }
    Write-Host (Show-Command $r) -ForegroundColor Cyan
    if ($Launch -and -not $DryRun) { $l = $r.Launch; & $launcher @l }
    else { $l = $r.Launch; & $launcher @l -WhatIf }
    return
}

# --- window ----------------------------------------------------------------------------------
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
. (Join-Path $PSScriptRoot '_SnapshotForm.ps1')
$form = New-Object $(if ($Snapshot) { 'D5SnapshotForm' } else { 'System.Windows.Forms.Form' }) -Property @{
    Text = 'DIRT 5 Unlocked   (~99 % AI-written hobby project by @6uhrmittag & @VoidCrowned - nothing is guaranteed)'; Width = 900; Height = 760; StartPosition = 'CenterScreen'
    BackColor = [System.Drawing.Color]::FromArgb(24, 18, 40); ForeColor = [System.Drawing.Color]::White
    Font = New-Object System.Drawing.Font('Segoe UI', 10)
}
$tip = New-Object System.Windows.Forms.ToolTip
$flow = New-Object System.Windows.Forms.FlowLayoutPanel -Property @{
    Dock = 'Fill'; AutoScroll = $true; FlowDirection = 'TopDown'; WrapContents = $true; Padding = '8,8,8,8'
}
$boxes = [ordered]@{}
foreach ($g in $cat.groups) {
    $gb = New-Object System.Windows.Forms.GroupBox -Property @{ Text = $g.name -replace '&', '&&'; Width = 420; AutoSize = $true; ForeColor = [System.Drawing.Color]::FromArgb(255, 120, 255) }
    $inner = New-Object System.Windows.Forms.FlowLayoutPanel -Property @{ FlowDirection = 'TopDown'; AutoSize = $true; Dock = 'Fill'; WrapContents = $false }
    foreach ($o in $g.options) {
        $mark = switch ($o.status) { 'verified' { '✓' } 'no-effect' { '✗' } default { '?' } }
        $cb = New-Object System.Windows.Forms.CheckBox -Property @{ Text = "$mark  $($o.label)"; AutoSize = $true; ForeColor = [System.Drawing.Color]::White; Tag = $o.flag }
        if ($o.status -eq 'no-effect') { $cb.Enabled = $false }
        $tip.SetToolTip($cb, "--$($o.flag)`n$($o.help)`nstatus: $($o.status)$(if ($o.tested) { " - $($o.tested)" })$(if ($o.nosave) { "`nforces --nosave" })")
        $inner.Controls.Add($cb); $boxes[$o.flag] = $cb
    }
    $gb.Controls.Add($inner); $flow.Controls.Add($gb)
}
$bottom = New-Object System.Windows.Forms.Panel -Property @{ Dock = 'Bottom'; Height = 150; Padding = '8,4,8,8' }
$presetBox = New-Object System.Windows.Forms.ComboBox -Property @{ DropDownStyle = 'DropDownList'; Width = 260; Location = '8,8' }
[void]$presetBox.Items.Add('(preset)')
foreach ($p in $cat.presets.PSObject.Properties) { [void]$presetBox.Items.Add("$($p.Name): $($p.Value.label)") }
$presetBox.SelectedIndex = 0
$modsLabel = New-Object System.Windows.Forms.Label -Property @{ Text = 'data mods:'; Location = '285,11'; AutoSize = $true }
$modsBox = New-Object System.Windows.Forms.TextBox -Property @{ Location = '370,8'; Width = 500; PlaceholderText = 'e.g. beschwipst   or   gravity=-0.6 power=2   (python scripts\d5mod.py list)' }
$preview = New-Object System.Windows.Forms.TextBox -Property @{ Location = '8,42'; Width = 862; Height = 52; Multiline = $true; ReadOnly = $true; BackColor = [System.Drawing.Color]::FromArgb(40, 30, 64); ForeColor = [System.Drawing.Color]::FromArgb(120, 255, 255) }
$copy = New-Object System.Windows.Forms.Button -Property @{ Text = 'Copy command'; Location = '8,102'; Width = 160; Height = 34 }
$go = New-Object System.Windows.Forms.Button -Property @{ Text = 'LAUNCH (offline)'; Location = '690,102'; Width = 180; Height = 34; BackColor = [System.Drawing.Color]::FromArgb(255, 0, 170); ForeColor = [System.Drawing.Color]::White }
$legend = New-Object System.Windows.Forms.Label -Property @{ Text = '✓ verified in-game   ? untested   ✗ no effect (hover for details)'; Location = '180,96'; AutoSize = $true; ForeColor = [System.Drawing.Color]::Silver }
$state = New-Object System.Windows.Forms.Label -Property @{ Location = '180,118'; AutoSize = $true; UseMnemonic = $false; ForeColor = [System.Drawing.Color]::FromArgb(255, 230, 90) }
$bottom.Controls.AddRange(@($presetBox, $modsLabel, $modsBox, $preview, $copy, $go, $legend, $state))

function Current {
    $sel = $boxes.Keys | Where-Object { $boxes[$_].Checked }
    Resolve-Launch $sel @($modsBox.Text) 3>$null
}
function Refresh-Preview {
    $r = Current
    $preview.Text = (Show-Command $r) + $(if ($r.ForcedNoSave) { "`r`n(unlock options -> --nosave forced)" })
}
foreach ($cb in $boxes.Values) { $cb.Add_CheckedChanged({ Refresh-Preview }) }
$modsBox.Add_TextChanged({ Refresh-Preview })
$presetBox.Add_SelectedIndexChanged({
    if ($presetBox.SelectedIndex -le 0) { return }
    $name = ($presetBox.SelectedItem -split ':')[0]
    foreach ($k in $boxes.Keys) { $boxes[$k].Checked = $cat.presets.$name.flags -contains $k }
})
$copy.Add_Click({ [System.Windows.Forms.Clipboard]::SetText((Show-Command (Current))); $state.Text = 'copied' })
$go.Add_Click({
    $l = (Current).Launch
    $state.Text = 'launching...'
    try { & $launcher @l | Out-Null; $state.Text = 'DIRT 5 started (offline). have fun :3' }
    catch { $state.Text = "failed: $_" }
})
$timer = New-Object System.Windows.Forms.Timer -Property @{ Interval = 2000 }
$timer.Add_Tick({
    $running = [bool](Get-Process game_release -ErrorAction SilentlyContinue)
    $go.Enabled = -not $running
    if ($running) { $state.Text = 'DIRT 5 is running - quit it to launch again' }
})
$timer.Start()
$form.Controls.Add($flow); $form.Controls.Add($bottom)
if ($Preset -and $cat.presets.$Preset) {
    $i = [array]::IndexOf(@($cat.presets.PSObject.Properties.Name), $Preset)
    if ($i -ge 0) { $presetBox.SelectedIndex = $i + 1 }   # the handler ticks the boxes
}
if ($Mods) { $modsBox.Text = $Mods -join ' ' }
Refresh-Preview
if ($Snapshot) { $timer.Stop(); Save-FormSnapshot $form $Snapshot; return }
[void]$form.ShowDialog()
