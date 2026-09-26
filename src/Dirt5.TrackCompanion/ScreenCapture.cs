using System.Diagnostics;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using Windows.Graphics.Imaging;

namespace Dirt5.TrackCompanion;

/// <summary>
/// READ-ONLY screen capture. Grabs the desktop (or the DIRT 5 window) into a Bitmap
/// via GDI CopyFromScreen. No hooking, no injection — it only reads pixels already on
/// screen. (Exclusive-fullscreen may return black; use borderless/windowed, or a WGC
/// fallback could be added later.)
/// </summary>
public static class ScreenCapture
{
    [DllImport("user32.dll")] private static extern IntPtr FindWindow(string? cls, string? title);
    [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
    [DllImport("user32.dll")] private static extern bool IsWindow(IntPtr hWnd);
    [DllImport("user32.dll")] private static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] private static extern bool SetProcessDPIAware();

    /// <summary>
    /// Mark the process per-monitor-DPI-aware BEFORE any screen access, so
    /// Screen.Bounds / CopyFromScreen report true physical pixels (e.g. 3840×2160)
    /// instead of the scaled logical size (2560×1440 at 150%). Must run at startup.
    /// </summary>
    public static void EnableDpiAwareness()
    {
        // DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        try { if (SetProcessDpiAwarenessContext((IntPtr)(-4))) return; } catch { /* pre-1809 */ }
        try { SetProcessDPIAware(); } catch { /* very old Windows */ }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT { public int Left, Top, Right, Bottom; }

    /// <summary>Capture the whole primary screen.</summary>
    public static Bitmap CaptureScreen()
    {
        var bounds = System.Windows.Forms.Screen.PrimaryScreen!.Bounds;
        return CaptureRect(bounds.X, bounds.Y, bounds.Width, bounds.Height);
    }

    /// <summary>
    /// Capture the DIRT 5 window if we can find it (by title / process), else the whole
    /// screen. Returns the bitmap and whether it came from the game window.
    /// </summary>
    public static (Bitmap Bitmap, bool FromGameWindow) CaptureGameOrScreen()
    {
        var hWnd = FindDirt5Window();
        if (hWnd != IntPtr.Zero && IsWindow(hWnd) && GetWindowRect(hWnd, out var r))
        {
            var w = r.Right - r.Left; var h = r.Bottom - r.Top;
            if (w > 0 && h > 0) return (CaptureRect(r.Left, r.Top, w, h), true);
        }
        return (CaptureScreen(), false);
    }

    public static Bitmap CaptureRect(int x, int y, int width, int height)
    {
        var bmp = new Bitmap(width, height, PixelFormat.Format32bppArgb);
        using var g = Graphics.FromImage(bmp);
        g.CopyFromScreen(x, y, 0, 0, new Size(width, height), CopyPixelOperation.SourceCopy);
        return bmp;
    }

    private static IntPtr FindDirt5Window()
    {
        foreach (var title in new[] { "DIRT 5", "DiRT 5", "Dirt5" })
        {
            var h = FindWindow(null, title);
            if (h != IntPtr.Zero) return h;
        }
        foreach (var name in new[] { "game_release", "DIRT5", "Dirt5" })
        {
            var p = Process.GetProcessesByName(name).FirstOrDefault(p => p.MainWindowHandle != IntPtr.Zero);
            if (p is not null) return p.MainWindowHandle;
        }
        return IntPtr.Zero;
    }

    /// <summary>Convert a GDI Bitmap to a WinRT SoftwareBitmap (for OCR).</summary>
    public static async Task<SoftwareBitmap> ToSoftwareBitmapAsync(Bitmap bmp)
    {
        using var ms = new MemoryStream();
        bmp.Save(ms, ImageFormat.Bmp);
        ms.Position = 0;
        var stream = ms.AsRandomAccessStream();
        var decoder = await BitmapDecoder.CreateAsync(stream);
        return await decoder.GetSoftwareBitmapAsync();
    }
}
