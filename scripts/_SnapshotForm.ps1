# Shared by the D5ML / DIRT 5 Unlocked windows: -Snapshot renders the real window to a PNG
# without ever activating it (non-activating tool window, shown off-screen), so screenshots
# for docs/NexusMods can be made while the user works (or plays) on the same PC.
if (-not ([System.Management.Automation.PSTypeName]'D5SnapshotForm').Type) {
    $refs = @([System.Windows.Forms.Form].Assembly.Location, [System.ComponentModel.Component].Assembly.Location,
              [System.Drawing.Color].Assembly.Location)
    $prim = [AppDomain]::CurrentDomain.GetAssemblies() | Where-Object { $_.GetName().Name -in 'System.Windows.Forms.Primitives', 'System.Drawing.Primitives', 'System.Private.Windows.Core', 'System.ComponentModel.Primitives' }
    $refs += @($prim | ForEach-Object { $_.Location })
    Add-Type -ReferencedAssemblies $refs -TypeDefinition @"
public class D5SnapshotForm : System.Windows.Forms.Form {
    protected override bool ShowWithoutActivation { get { return true; } }
    protected override System.Windows.Forms.CreateParams CreateParams {
        get { var cp = base.CreateParams; cp.ExStyle |= 0x08000000 | 0x00000080; return cp; }  // NOACTIVATE | TOOLWINDOW
    }
}
"@
}
function Save-FormSnapshot($form, [string] $path) {
    $form.StartPosition = 'Manual'
    $form.Location = New-Object System.Drawing.Point(-20000, -20000)
    $form.Show()
    [System.Windows.Forms.Application]::DoEvents()
    $bmp = New-Object System.Drawing.Bitmap $form.Width, $form.Height
    $form.DrawToBitmap($bmp, (New-Object System.Drawing.Rectangle 0, 0, $form.Width, $form.Height))
    $bmp.Save([IO.Path]::GetFullPath($path), [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose(); $form.Close(); $form.Dispose()
    Write-Host "snapshot: $path"
}
