<#
.SYNOPSIS
    Drive the running DIRT 5 (loose install) from a script: tap/hold keys and
    take screenshots of the game window. Lets Claude Code test menus and races
    without a human at the controller.

.DESCRIPTION
    Keys are injected with SendInput scan codes (the game reads the keyboard via
    DirectInput8). This only works when the game runs at the SAME integrity level
    as this shell: the loose install has a RUNASADMIN compat flag, and an
    elevated game silently drops injected input (UIPI). Start the game with
    scripts\Start-Dirt5Modded.ps1, which launches it via RunAsInvoker.

    Safety: before every key and every screenshot the game window must be in the
    foreground - otherwise the script stops, so it never types into (or
    captures) whatever else the user has open.

    Keyboard layout seen in-game: RTN select, ESC back, arrows navigate menus,
    W throttle, A/D steer, TAB reset to track.

.PARAMETER Tap
    Keys to tap in order, e.g. DOWN,DOWN,ENTER. 'sleep<ms>' inserts a pause.
.PARAMETER Hold
    Hold steps '<key>[+<key>...]:<ms>' in order, e.g. 'W:3000','W+D:600'.
    '-' as key means release everything for that time.
.PARAMETER Shot
    Screenshot name (after Tap/Hold). With -ShotEvery it is the name prefix.
.PARAMETER ShotEvery
    During -Hold, take a screenshot every N ms (one 4K capture takes ~0.4 s).
.PARAMETER Info
    Print the integrity level of game and shell plus the foreground state.

.EXAMPLE
    .\Send-Dirt5Input.ps1 -Tap ENTER -Wait 3000 -Shot menu
.EXAMPLE
    .\Send-Dirt5Input.ps1 -Hold 'W:4000','W+A:500' -Shot race -ShotEvery 700
#>
[CmdletBinding()]
param(
    [string[]] $Tap,
    [string[]] $Hold,
    [string] $Shot,
    [int] $ShotEvery = 0,
    [int] $Wait = 0,
    [int] $TapMs = 80,
    [int] $GapMs = 350,
    [int] $MaxWidth = 1280,
    [string] $OutDir = (Join-Path $PSScriptRoot '..\extracted\shots'),
    [switch] $Info
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
if (-not ([System.Management.Automation.PSTypeName]'D5Input').Type) {
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class D5Input {
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr v);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [DllImport("user32.dll")] static extern uint SendInput(uint n, INPUT[] i, int size);
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint a, bool i, int pid);
  [DllImport("advapi32.dll")] static extern bool OpenProcessToken(IntPtr p, uint a, out IntPtr t);
  [DllImport("advapi32.dll")] static extern bool GetTokenInformation(IntPtr t, int c, IntPtr b, int l, out int r);
  [DllImport("advapi32.dll")] static extern IntPtr GetSidSubAuthority(IntPtr sid, uint i);
  [DllImport("advapi32.dll")] static extern IntPtr GetSidSubAuthorityCount(IntPtr sid);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort vk, scan; public uint flags, time; public IntPtr extra; }
  [StructLayout(LayoutKind.Explicit, Size=40)] struct INPUT { [FieldOffset(0)] public uint type; [FieldOffset(8)] public KEYBDINPUT ki; }
  public static void Key(ushort scan, bool ext, bool up) {
    var i = new INPUT[1]; i[0].type = 1; i[0].ki.scan = scan;
    i[0].ki.flags = 0x8u | (ext ? 0x1u : 0u) | (up ? 0x2u : 0u);   // KEYEVENTF_SCANCODE
    SendInput(1, i, Marshal.SizeOf(typeof(INPUT)));
  }
  public static string Integrity(int pid) {
    IntPtr p = OpenProcess(0x1000, false, pid), t;
    if (p == IntPtr.Zero || !OpenProcessToken(p, 8, out t)) return "?";
    int n; GetTokenInformation(t, 25, IntPtr.Zero, 0, out n); IntPtr b = Marshal.AllocHGlobal(n);
    GetTokenInformation(t, 25, b, n, out n); IntPtr sid = Marshal.ReadIntPtr(b);
    int rid = Marshal.ReadInt32(GetSidSubAuthority(sid, (uint)(Marshal.ReadByte(GetSidSubAuthorityCount(sid)) - 1)));
    return rid >= 0x3000 ? "High" : rid >= 0x2000 ? "Medium" : "Low";
  }
}
"@
}
[D5Input]::SetProcessDpiAwarenessContext([IntPtr]-4) | Out-Null   # physical pixels for GetWindowRect

$scan = @{ ENTER = 0x1C; ESC = 0x01; SPACE = 0x39; TAB = 0x0F; BACK = 0x0E; LSHIFT = 0x2A
    W = 0x11; A = 0x1E; S = 0x1F; D = 0x20; Q = 0x10; E = 0x12; R = 0x13; F = 0x21; C = 0x2E; H = 0x23; X = 0x2D; P = 0x19
    UP = 0xE048; DOWN = 0xE050; LEFT = 0xE04B; RIGHT = 0xE04D; PGUP = 0xE049; PGDN = 0xE051; HOME = 0xE047; END = 0xE04F }

$proc = Get-Process game_release -ErrorAction SilentlyContinue | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
if (-not $proc) { throw 'DIRT 5 window not found' }
$hwnd = $proc.MainWindowHandle
function Test-Foreground { [D5Input]::GetForegroundWindow() -eq $hwnd }

if ($Info) {
    "game: $([D5Input]::Integrity($proc.Id))  shell: $([D5Input]::Integrity($PID))  foreground: $(Test-Foreground)"
    return
}

function Send-Key([string] $name, [bool] $up) {
    $v = $scan[$name.ToUpper()]; if ($null -eq $v) { throw "unknown key '$name'" }
    [D5Input]::Key([uint16]($v -band 0xFF), ($v -gt 0xFF), $up)
}
function Save-Shot([string] $name) {
    if (-not (Test-Foreground)) { Write-Warning "shot '$name' skipped: game not in foreground"; return }
    $r = New-Object D5Input+RECT; [D5Input]::GetWindowRect($hwnd, [ref]$r) | Out-Null
    $w = $r.R - $r.L; $h = $r.B - $r.T
    $full = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($full); $g.CopyFromScreen($r.L, $r.T, 0, 0, $full.Size); $g.Dispose()
    $k = [Math]::Min(1.0, $MaxWidth / $w)
    $out = New-Object System.Drawing.Bitmap ([int]($w * $k)), ([int]($h * $k))
    $g = [System.Drawing.Graphics]::FromImage($out); $g.InterpolationMode = 'HighQualityBicubic'
    $g.DrawImage($full, 0, 0, $out.Width, $out.Height); $g.Dispose(); $full.Dispose()
    New-Item -ItemType Directory -Force $OutDir | Out-Null
    $f = Join-Path (Resolve-Path $OutDir) "$name.png"; $out.Save($f, [System.Drawing.Imaging.ImageFormat]::Png); $out.Dispose()
    Write-Output $f
}

if ($Tap -or $Hold) {
    if (-not (Test-Foreground)) {
        # an ALT tap lifts the foreground lock so SetForegroundWindow is honoured
        [D5Input]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero); [D5Input]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
        # DirectInput re-acquires the keyboard after activation; keys sent sooner are lost
        [D5Input]::SetForegroundWindow($hwnd) | Out-Null; Start-Sleep -Milliseconds 1200
    }
    if (-not (Test-Foreground)) { throw 'game did not come to the foreground - nothing sent' }
}

foreach ($k in $Tap) {
    if ($k -match '^sleep(\d+)$') { Start-Sleep -Milliseconds ([int]$Matches[1]); continue }
    if (-not (Test-Foreground)) { throw "game lost focus before '$k' - stopped" }
    Send-Key $k $false; Start-Sleep -Milliseconds $TapMs; Send-Key $k $true
    Start-Sleep -Milliseconds $GapMs
}

$n = 0
$clock = [Diagnostics.Stopwatch]::StartNew(); $nextShot = $ShotEvery
foreach ($step in $Hold) {
    $combo, $ms = $step -split ':'
    $keys = if ($combo -eq '-') { @() } else { $combo -split '\+' }
    $keys | ForEach-Object { Send-Key $_ $false }
    try {
        $end = $clock.ElapsedMilliseconds + [int]$ms
        while ($clock.ElapsedMilliseconds -lt $end) {
            if (-not (Test-Foreground)) { throw "game lost focus during '$step' - keys released" }
            if ($ShotEvery -and $Shot -and $clock.ElapsedMilliseconds -ge $nextShot) {
                $n++; Save-Shot ('{0}_{1:D2}' -f $Shot, $n); $nextShot = $clock.ElapsedMilliseconds + $ShotEvery
            }
            Start-Sleep -Milliseconds 15
        }
    } finally { $keys | ForEach-Object { Send-Key $_ $true } }
}

if ($Wait) { Start-Sleep -Milliseconds $Wait }
if ($Shot -and -not ($ShotEvery -and $Hold)) { Save-Shot $Shot }
