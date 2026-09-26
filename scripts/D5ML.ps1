<#
.SYNOPSIS
    D5ML - DIRT 5 Mod Loader, the window. Tick mods, order them, Apply, play.

.DESCRIPTION
    Front-end for scripts\d5ml.py:
      - mod list from mods\ (tick = active, order = load order, later mods win conflicts)
      - details + preview.png of the selected mod
      - Check (dry run with conflicts), APPLY, Restore vanilla
      - drop a mod .zip or folder onto the window to install it (or "Install zip...")
      - Launch DIRT 5 offline with the applied mods, or open DIRT 5 Unlocked
    Apply/Restore are disabled while the game runs (data is read at boot).
    The ticked set + order are remembered in mods\.d5ml-profile.json.

.EXAMPLE
    .\scripts\D5ML.ps1
.EXAMPLE
    .\scripts\D5ML.ps1 -Snapshot extracted\d5ml-window.png     # render the window to a PNG, don't show it
#>
param(
    [string] $Snapshot,
    [string[]] $Select,        # with -Snapshot: tick these mod ids and show the first one
    [string] $ModsDir = $(if ($env:D5ML_MODS) { $env:D5ML_MODS } else { Join-Path $PSScriptRoot '..\mods' })
)
$ErrorActionPreference = 'Stop'
$ModsDir = [IO.Path]::GetFullPath($ModsDir)
$d5ml = Join-Path $PSScriptRoot 'd5ml.py'
$profilePath = Join-Path $ModsDir '.d5ml-profile.json'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
. (Join-Path $PSScriptRoot '_SnapshotForm.ps1')
. (Join-Path $PSScriptRoot '_GameDir.ps1')
$script:gameDir = Use-GameDir

$C = @{
    bg = [System.Drawing.Color]::FromArgb(24, 18, 40); panel = [System.Drawing.Color]::FromArgb(40, 30, 64)
    pink = [System.Drawing.Color]::FromArgb(255, 0, 170); cyan = [System.Drawing.Color]::FromArgb(120, 255, 255)
    yellow = [System.Drawing.Color]::FromArgb(255, 230, 90); fg = [System.Drawing.Color]::White
}

function Invoke-D5ml([string[]] $argv) {
    $env:D5ML_MODS = $ModsDir
    $out = & python $d5ml @argv 2>&1 | ForEach-Object { "$_" }
    [pscustomobject]@{ ok = ($LASTEXITCODE -eq 0); text = ($out -join "`r`n") }
}

# --- window -------------------------------------------------------------------------------
$form = New-Object $(if ($Snapshot) { 'D5SnapshotForm' } else { 'System.Windows.Forms.Form' }) -Property @{
    Text = 'D5ML - DIRT 5 Mod Loader   (~99 % AI-written hobby project - nothing is guaranteed)'; Width = 1100; Height = 760; StartPosition = 'CenterScreen'
    BackColor = $C.bg; ForeColor = $C.fg; Font = New-Object System.Drawing.Font('Segoe UI', 10); AllowDrop = $true
}
$title = New-Object System.Windows.Forms.Label -Property @{
    Text = 'D5ML'; Location = '16,10'; AutoSize = $true; ForeColor = $C.pink
    Font = New-Object System.Drawing.Font('Impact', 30)
}
$subtitle = New-Object System.Windows.Forms.Label -Property @{
    Text = 'the first DIRT 5 mod loader  -  tick mods, order them, APPLY, play offline'; Location = '120,26'; AutoSize = $true; ForeColor = $C.cyan
}
$aiNote = New-Object System.Windows.Forms.Label -Property @{
    Text = 'hobby project by @6uhrmittag & @VoidCrowned, ~99 % written by an AI - nothing is guaranteed, keep backups, offline only'
    Location = '122,46'; AutoSize = $true; ForeColor = [System.Drawing.Color]::Silver; UseMnemonic = $false
    Font = New-Object System.Drawing.Font('Segoe UI', 8.5)
}
$list = New-Object System.Windows.Forms.CheckedListBox -Property @{
    Location = '16,70'; Width = 360; Height = 470; BackColor = $C.panel; ForeColor = $C.fg; BorderStyle = 'None'
    CheckOnClick = $true; IntegralHeight = $false; Font = New-Object System.Drawing.Font('Segoe UI', 11); DisplayMember = 'label'
}
$up = New-Object System.Windows.Forms.Button -Property @{ Text = 'up'; Location = '16,546'; Width = 70; Height = 30 }
$down = New-Object System.Windows.Forms.Button -Property @{ Text = 'down'; Location = '92,546'; Width = 70; Height = 30 }
$orderHint = New-Object System.Windows.Forms.Label -Property @{ Text = 'lower = loads later = wins'; Location = '170,552'; AutoSize = $true; ForeColor = [System.Drawing.Color]::Silver }

$name = New-Object System.Windows.Forms.Label -Property @{ Location = '396,70'; Width = 670; Height = 34; UseMnemonic = $false; ForeColor = $C.yellow; Font = New-Object System.Drawing.Font('Segoe UI Semibold', 16) }
$meta = New-Object System.Windows.Forms.Label -Property @{ Location = '396,106'; Width = 670; Height = 22; ForeColor = [System.Drawing.Color]::Silver; UseMnemonic = $false }
$desc = New-Object System.Windows.Forms.TextBox -Property @{
    Location = '396,132'; Width = 670; Height = 70; Multiline = $true; ReadOnly = $true; BorderStyle = 'None'; BackColor = $C.bg; ForeColor = $C.fg
}
$preview = New-Object System.Windows.Forms.PictureBox -Property @{ Location = '396,208'; Width = 670; Height = 250; SizeMode = 'Zoom'; BackColor = $C.panel }
$log = New-Object System.Windows.Forms.TextBox -Property @{
    Location = '396,466'; Width = 670; Height = 110; Multiline = $true; ReadOnly = $true; ScrollBars = 'Vertical'
    BackColor = [System.Drawing.Color]::FromArgb(14, 10, 26); ForeColor = $C.cyan; Font = New-Object System.Drawing.Font('Consolas', 9); BorderStyle = 'None'
}
function New-Button($text, $x, $w, $accent) {
    $b = New-Object System.Windows.Forms.Button -Property @{ Text = $text; Location = "$x,592"; Width = $w; Height = 40; FlatStyle = 'Flat' }
    $b.FlatAppearance.BorderColor = $C.pink
    if ($accent) { $b.BackColor = $C.pink; $b.ForeColor = $C.fg; $b.Font = New-Object System.Drawing.Font('Segoe UI Semibold', 11) }
    $b
}
$btnCheck = New-Button 'Check' 16 110
$btnApply = New-Button 'APPLY' 132 150 $true
$btnRestore = New-Button 'Restore vanilla' 288 150
$btnInstall = New-Button 'Install zip...' 444 130
$btnFolder = New-Button 'Mods folder' 580 120
$btnUnlocked = New-Button 'DIRT 5 Unlocked...' 706 170
$btnLaunch = New-Button 'LAUNCH (offline)' 882 184 $true
$btnGame = New-Object System.Windows.Forms.Button -Property @{ Text = 'Game folder...'; Location = '946,20'; Width = 120; Height = 30; FlatStyle = 'Flat' }
$btnGame.FlatAppearance.BorderColor = $C.cyan
$status = New-Object System.Windows.Forms.Label -Property @{ Location = '16,645'; Width = 1050; Height = 60; ForeColor = $C.yellow; UseMnemonic = $false }
$form.Controls.AddRange(@($btnGame, $title, $subtitle, $aiNote, $list, $up, $down, $orderHint, $name, $meta, $desc, $preview, $log,
        $btnCheck, $btnApply, $btnRestore, $btnInstall, $btnFolder, $btnUnlocked, $btnLaunch, $status))

# --- state ----------------------------------------------------------------------------------
$script:mods = @()
function Save-Profile {
    $p = @{ order = @($list.Items | ForEach-Object { $_.id }); active = @($list.CheckedItems | ForEach-Object { $_.id }) }
    $p | ConvertTo-Json | Set-Content $profilePath -Encoding utf8
}
function Load-Mods {
    $r = Invoke-D5ml @('list', '--json')
    $script:mods = if ($r.ok -and $r.text.Trim()) { @($r.text | ConvertFrom-Json) } else { @() }
    $saved = if (Test-Path $profilePath) { Get-Content $profilePath -Raw | ConvertFrom-Json } else { $null }
    $ids = @($script:mods.id)
    $order = @($saved.order | Where-Object { $ids -contains $_ }) + @($ids | Where-Object { @($saved.order) -notcontains $_ })
    $list.Items.Clear()
    foreach ($id in $order) {
        $m = $script:mods | Where-Object id -eq $id | Select-Object -First 1
        $item = [pscustomobject]@{ id = $id; label = "$($m.name)  v$($m.version)" }
        [void]$list.Items.Add($item, [bool](@($saved.active) -contains $id))
    }
    if ($list.Items.Count) { $list.SelectedIndex = 0 } else { Show-Mod $null }
}
function Show-Mod($id) {
    $m = $script:mods | Where-Object id -eq $id | Select-Object -First 1
    if (-not $m) { $name.Text = 'no mods yet'; $meta.Text = "drop a mod .zip here, or create one: python scripts\d5ml.py new my-mod"; $desc.Text = ''; $preview.Image = $null; return }
    $name.Text = $m.name
    $parts = @("v$($m.version)", $(if ($m.author) { "by $($m.author)" }), "$($m.files) file(s)", "$($m.textures) texture(s)", "$($m.effects) effect(s)") + $(if ($m.recipes) { "recipes: $($m.recipes -join ' ')" })
    $meta.Text = ($parts | Where-Object { $_ }) -join '   '
    $desc.Text = $m.description
    $preview.Image = if ($m.preview) { [System.Drawing.Image]::FromFile($m.preview) } else { $null }
}
function Update-Status {
    $running = [bool](Get-Process game_release -ErrorAction SilentlyContinue)
    if (-not $script:gameDir) {
        $status.Text = 'DIRT 5 not found - click "Game folder..." and pick the folder with game_release.exe'
        foreach ($b in $btnCheck, $btnApply, $btnRestore, $btnLaunch) { $b.Enabled = $false }
        return
    }
    $s = (Invoke-D5ml @('status')).text -replace "`r?`n", '   '
    $status.Text = "game: $($script:gameDir)`r`ndata: $s" + $(if ($running) { "`r`nDIRT 5 is running - quit it to change mods (data is read at boot)" })
    $btnCheck.Enabled = $true
    foreach ($b in $btnApply, $btnRestore, $btnLaunch) { $b.Enabled = -not $running }
}
function Run-Busy([string] $what, [string[]] $argv) {
    $form.Cursor = 'WaitCursor'; $log.Text = "$what ..."; $form.Refresh()
    try { $r = Invoke-D5ml $argv; $log.Text = $r.text } finally { $form.Cursor = 'Default' }
    Update-Status
    $r
}
function Active { @($list.CheckedItems | ForEach-Object { $_.id }) }

# --- events ---------------------------------------------------------------------------------
$list.Add_SelectedIndexChanged({ Show-Mod $list.SelectedItem.id })
$list.Add_ItemCheck({ if ($form.IsHandleCreated -and -not $Snapshot) { $form.BeginInvoke([Action] { Save-Profile }) | Out-Null } })
$move = {
    param($delta)
    $i = $list.SelectedIndex; $j = $i + $delta
    if ($i -lt 0 -or $j -lt 0 -or $j -ge $list.Items.Count) { return }
    $item = $list.Items[$i]; $chk = $list.GetItemChecked($i)
    $list.Items.RemoveAt($i); $list.Items.Insert($j, $item); $list.SetItemChecked($j, $chk); $list.SelectedIndex = $j
    Save-Profile
}
$up.Add_Click({ & $move -1 }); $down.Add_Click({ & $move 1 })
$btnCheck.Add_Click({
    if (-not (Active)) { $log.Text = 'tick at least one mod'; return }
    Run-Busy 'checking' (@('check') + (Active)) | Out-Null
})
$btnApply.Add_Click({
    if (-not (Active)) { $log.Text = 'tick at least one mod (or use Restore vanilla)'; return }
    $r = Run-Busy "applying $((Active) -join ', ')" (@('apply') + (Active))
    if ($r.ok) { $log.AppendText("`r`n`r`nDone - launch the game offline and have fun :3") }
})
$btnRestore.Add_Click({ Run-Busy 'restoring vanilla' @('restore') | Out-Null })
$install = {
    param([string[]] $paths)
    foreach ($p in $paths) { $r = Run-Busy "installing $p" @('install', $p) }
    Load-Mods
}
$btnInstall.Add_Click({
    $dlg = New-Object System.Windows.Forms.OpenFileDialog -Property @{ Filter = 'd5ml mod (*.zip)|*.zip'; Multiselect = $true }
    if ($dlg.ShowDialog() -eq 'OK') { & $install $dlg.FileNames }
})
$form.Add_DragEnter({ if ($_.Data.GetDataPresent([System.Windows.Forms.DataFormats]::FileDrop)) { $_.Effect = 'Copy' } })
$form.Add_DragDrop({ & $install @($_.Data.GetData([System.Windows.Forms.DataFormats]::FileDrop)) })
$btnFolder.Add_Click({ New-Item -ItemType Directory -Force $ModsDir | Out-Null; Start-Process explorer.exe $ModsDir })
$btnGame.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog -Property @{ Description = 'DIRT 5 folder (contains game_release.exe)' }
    if ($script:gameDir) { $dlg.SelectedPath = $script:gameDir }
    if ($dlg.ShowDialog() -ne 'OK') { return }
    try { Set-GameDir $dlg.SelectedPath; $script:gameDir = $dlg.SelectedPath; $log.Text = "game folder: $($script:gameDir)" }
    catch { $log.Text = "$_" }
    Update-Status
})
$btnUnlocked.Add_Click({ Start-Process pwsh -ArgumentList '-NoProfile', '-File', (Join-Path $PSScriptRoot 'Dirt5-Unlocked.ps1') })
$btnLaunch.Add_Click({
    try {
        & (Join-Path $PSScriptRoot 'Start-Dirt5Modded.ps1') -FastBoot -NoNetErrors -GameDir $script:gameDir *>&1 | ForEach-Object { $log.AppendText("`r`n$_") }
        $log.AppendText("`r`nDIRT 5 started (offline).")
    } catch { $log.AppendText("`r`nlaunch failed: $_") }
    Update-Status
})
$timer = New-Object System.Windows.Forms.Timer -Property @{ Interval = 3000 }
$timer.Add_Tick({
    $running = [bool](Get-Process game_release -ErrorAction SilentlyContinue)
    if ($running -eq $btnApply.Enabled) { Update-Status }
})

New-Item -ItemType Directory -Force $ModsDir | Out-Null
Load-Mods
Update-Status
if ($Snapshot) {
    if ($Select) {
        $Select = @($Select | ForEach-Object { $_ -split ',' } | Where-Object { $_ })
        for ($i = 0; $i -lt $list.Items.Count; $i++) { $list.SetItemChecked($i, @($Select) -contains $list.Items[$i].id) }
        $first = [array]::IndexOf(@($list.Items | ForEach-Object { $_.id }), $Select[0])
        if ($first -ge 0) { $list.SelectedIndex = $first }
    }
    Save-FormSnapshot $form $Snapshot; return
}
$timer.Start()
[void]$form.ShowDialog()
