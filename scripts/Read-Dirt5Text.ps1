<#
.SYNOPSIS
    OCR screenshots with Windows' built-in engine (Windows.Media.Ocr, offline).
    Prints one line per image: <file><TAB><text>.

.DESCRIPTION
    Needs Windows PowerShell 5.1 (WinRT projection) - call it as
        powershell -NoProfile -File scripts\Read-Dirt5Text.ps1 -Path ... [-Crop ...]
    -Crop takes fractions of the image (x,y,w,h in 0..1) so it works for any
    screenshot size; the crop is upscaled -Scale times, which the engine needs
    for small HUD text.

.EXAMPLE
    # race clock (top-left HUD) of every lap-test frame
    powershell -NoProfile -File scripts\Read-Dirt5Text.ps1 -Path extracted\shots\mod_*.png -Crop 0.06,0.115,0.12,0.045
.EXAMPLE
    # whole screen, e.g. to check which menu page is open
    powershell -NoProfile -File scripts\Read-Dirt5Text.ps1 -Path extracted\shots\menu.png
#>
param(
    [Parameter(Mandatory)] [string[]] $Path,   # comma-separated when called via -File
    [string] $Crop,                            # "x,y,w,h" fractions
    [double] $Scale = 3
)
$ErrorActionPreference = 'Stop'
$Path = $Path | ForEach-Object { $_ -split ',' } | Where-Object { $_ }
$cropv = if ($Crop) { $Crop -split ',' | ForEach-Object { [double]::Parse($_, [Globalization.CultureInfo]::InvariantCulture) } }
if ($PSVersionTable.PSVersion.Major -gt 5) { throw 'run with Windows PowerShell 5.1 (powershell.exe), not pwsh' }
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]

$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await($op, [type] $t) {
    $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result
}

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$tmp = Join-Path $env:TEMP "d5ocr_$PID.png"
$files = $Path | ForEach-Object { Get-ChildItem $_ } | Sort-Object Name
foreach ($f in $files) {
    $src = [System.Drawing.Image]::FromFile($f.FullName)
    try {
        $x = 0; $y = 0; $w = $src.Width; $h = $src.Height
        if ($cropv) { $x = [int]($cropv[0] * $src.Width); $y = [int]($cropv[1] * $src.Height)
                     $w = [int]($cropv[2] * $src.Width); $h = [int]($cropv[3] * $src.Height) }
        $k = [Math]::Min($Scale, [Math]::Floor(4000 / [Math]::Max($w, $h)))
        $bmp = New-Object System.Drawing.Bitmap ([int]($w * $k)), ([int]($h * $k))
        $g = [System.Drawing.Graphics]::FromImage($bmp); $g.InterpolationMode = 'HighQualityBicubic'
        $g.DrawImage($src, (New-Object System.Drawing.Rectangle 0, 0, $bmp.Width, $bmp.Height), $x, $y, $w, $h, 'Pixel')
        $g.Dispose(); $bmp.Save($tmp, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    } finally { $src.Dispose() }
    $sf = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($tmp)) ([Windows.Storage.StorageFile])
    $stream = Await ($sf.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $sb = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $res = Await ($engine.RecognizeAsync($sb)) ([Windows.Media.Ocr.OcrResult])
    $stream.Dispose()
    "{0}`t{1}" -f $f.Name, ($res.Text -replace '\s+', ' ')
}
Remove-Item $tmp -ErrorAction SilentlyContinue
