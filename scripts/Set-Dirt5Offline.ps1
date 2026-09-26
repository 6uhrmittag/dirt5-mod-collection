<#
.SYNOPSIS
    Toggle DIRT 5 (Xbox / Microsoft Store build) into a network-blocked "offline"
    state using Windows Firewall outbound rules. Touches ZERO game files, fully
    reversible. This is the project's anti-ban safety net.

.DESCRIPTION
    Creates or removes outbound "block" rules (grouped under 'DIRT5-Offline') that
    target the game's executables. When enabled, the game cannot reach the network,
    so there is no way to accidentally connect to online/multiplayer while
    experimenting locally.

    WHY a firewall rule instead of a mod:
      - We do NOT modify any game files, so the package integrity stays intact and
        there is no tamper/ban vector.
      - Blocking the network makes online play impossible while we tinker offline.
      - It is instantly reversible (-Disable) and observable (-Status).

    GAME PASS / STORE LICENSE CAVEAT:
      Store & Game Pass licenses re-validate periodically (~monthly). A permanent
      hard block can eventually fail that re-check and make the game refuse to
      launch until it can phone home. If the game stops launching, run -Disable,
      launch once online to re-validate, then -Enable again for offline play.

.PARAMETER Enable
    Create the outbound block rules (offline mode ON).

.PARAMETER Disable
    Remove the block rules (offline mode OFF / back to normal).

.PARAMETER Status
    Show whether the rules currently exist. Does not require elevation.

.PARAMETER InstallPath
    Target a loose (non-Store) install instead of the MSIX package, e.g.
    'C:\Games\DIRT 5'.

.EXAMPLE
    # From an ELEVATED PowerShell:
    .\Set-Dirt5Offline.ps1 -Enable
    .\Set-Dirt5Offline.ps1 -Status
    .\Set-Dirt5Offline.ps1 -Disable

.NOTES
    Requires Administrator for -Enable / -Disable (firewall changes).
    -Status works without elevation.
#>
[CmdletBinding(DefaultParameterSetName = 'Status')]
param(
    [Parameter(ParameterSetName = 'Enable')]  [switch] $Enable,
    [Parameter(ParameterSetName = 'Disable')] [switch] $Disable,
    [Parameter(ParameterSetName = 'Status')]  [switch] $Status,
    [string] $InstallPath
)

$ErrorActionPreference = 'Stop'

# --- Configuration -----------------------------------------------------------
$RuleGroup   = 'DIRT5-Offline'
$PackageName = 'CodemastersSoftwareCompan.DiRT5'

# Executables to block. We resolve the versioned install path at runtime so this
# keeps working after game updates (the version in the folder name changes).
$ExeNames = @('game_release.exe', 'GameLaunchHelper.exe')

# --- Helpers -----------------------------------------------------------------
function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-Dirt5InstallPath {
    if ($InstallPath) { return $InstallPath }
    # Prefer the AppxPackage record (authoritative, version-agnostic).
    try {
        $pkg = Get-AppxPackage -Name $PackageName -ErrorAction Stop | Select-Object -First 1
        if ($pkg -and $pkg.InstallLocation) { return $pkg.InstallLocation }
    } catch { }
    # Fallback: glob WindowsApps for the versioned folder.
    $glob = Join-Path $env:ProgramFiles "WindowsApps\$PackageName*_x64__*"
    $dir  = Get-ChildItem $glob -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | Select-Object -First 1
    if ($dir) { return $dir.FullName }
    return $null
}

function Resolve-Dirt5Exes {
    $base = Get-Dirt5InstallPath
    if (-not $base) {
        Write-Warning "Could not locate the DIRT 5 install. Is the Xbox build installed?"
        return @()
    }
    $found = @()
    foreach ($name in $ExeNames) {
        $p = Join-Path $base $name
        if (Test-Path $p) { $found += $p }
        else { Write-Verbose "Not present (ok): $p" }
    }
    if (-not $found) { Write-Warning "No target executables found under: $base" }
    return $found
}

function Get-Dirt5Rules {
    Get-NetFirewallRule -Group $RuleGroup -ErrorAction SilentlyContinue
}

# --- Actions -----------------------------------------------------------------
function Show-Status {
    $rules = Get-Dirt5Rules
    if (-not $rules) {
        Write-Host "DIRT5 offline mode: OFF  (no '$RuleGroup' firewall rules present)" -ForegroundColor Yellow
        return
    }
    Write-Host "DIRT5 offline mode: ON   ($($rules.Count) '$RuleGroup' rule(s) active)" -ForegroundColor Green
    foreach ($r in $rules) {
        $af = $r | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue
        "  [{0}] {1} -> {2}" -f $r.Enabled, $r.DisplayName, $af.Program | Write-Host
    }
}

function Enable-Offline {
    if (-not (Test-Admin)) {
        Write-Warning "Administrator required. Re-run in an elevated PowerShell (Start-Process powershell -Verb RunAs)."
        return
    }
    $exes = Resolve-Dirt5Exes
    if (-not $exes) { return }

    # Idempotent: clear any prior rules in our group first.
    Get-Dirt5Rules | Remove-NetFirewallRule -ErrorAction SilentlyContinue

    foreach ($exe in $exes) {
        $leaf = Split-Path $exe -Leaf
        foreach ($dir in @('Outbound')) {
            $name = "DIRT5-Offline Block $dir $leaf"
            New-NetFirewallRule -DisplayName $name -Group $RuleGroup `
                -Direction $dir -Action Block -Program $exe `
                -Profile Any -Enabled True | Out-Null
            Write-Host "Added: $name" -ForegroundColor Green
        }
    }
    Write-Host "`nDIRT5 is now network-blocked (offline). Verify with -Status." -ForegroundColor Green
    Write-Host "Reminder: toggle -Disable occasionally so the Store license can re-validate." -ForegroundColor DarkYellow
}

function Disable-Offline {
    if (-not (Test-Admin)) {
        Write-Warning "Administrator required. Re-run in an elevated PowerShell."
        return
    }
    $rules = Get-Dirt5Rules
    if (-not $rules) { Write-Host "Nothing to remove; offline mode already OFF." -ForegroundColor Yellow; return }
    $rules | Remove-NetFirewallRule
    Write-Host "Removed all '$RuleGroup' rules. DIRT5 network access restored." -ForegroundColor Green
}

# --- Dispatch ----------------------------------------------------------------
switch ($PSCmdlet.ParameterSetName) {
    'Enable'  { Enable-Offline }
    'Disable' { Disable-Offline }
    default   { Show-Status }
}
