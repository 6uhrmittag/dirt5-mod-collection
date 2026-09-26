using System.Text.Json;

namespace Dirt5.TrackCompanion;

/// <summary>A screen region as fractions of the capture (0..1), resolution-independent.</summary>
public readonly record struct NormRect(double X, double Y, double W, double H)
{
    public Rectangle ToPixels(int width, int height) => new(
        (int)Math.Round(X * width), (int)Math.Round(Y * height),
        (int)Math.Round(W * width), (int)Math.Round(H * height));

    public bool IsEmpty => W <= 0 || H <= 0;
}

/// <summary>
/// The screen regions to OCR on the car-select and results screens. Kept per screen
/// resolution because DIRT 5's UI scales differently at each. Defaults are rough guesses
/// that MUST be calibrated against a real screenshot (see Program `--calibrate`).
/// </summary>
public sealed class RegionSet
{
    public NormRect BrandP1 { get; set; }     // brand wordmark on P1's info panel
    public NormRect BrandP2 { get; set; }
    public NormRect CarNameP1 { get; set; }   // car-name bar (stylised, needs contrast prep)
    public NormRect CarNameP2 { get; set; }
    public NormRect TrackName { get; set; }   // shared event/track title (not yet calibrated)
    public NormRect ResultTimeP1 { get; set; }
    public NormRect ResultTimeP2 { get; set; }

    /// <summary>
    /// Defaults CALIBRATED from a real 3840×2160 splitscreen car-select capture. Coords are
    /// normalised (0..1) so they hold at other resolutions with the same 2-player vertical
    /// layout. Track/results regions are unknown until those screens are captured.
    /// </summary>
    public static RegionSet Default() => new()
    {
        BrandP1   = new NormRect(0.83, 0.130, 0.16, 0.028),
        BrandP2   = new NormRect(0.83, 0.631, 0.16, 0.028),
        CarNameP1 = new NormRect(0.81, 0.196, 0.185, 0.030),
        CarNameP2 = new NormRect(0.81, 0.697, 0.185, 0.030),
        TrackName    = default,   // TODO: calibrate on the event/track-select screen
        ResultTimeP1 = default,   // TODO: calibrate on the results screen
        ResultTimeP2 = default,
    };
}

public sealed class RegionConfig
{
    private static readonly JsonSerializerOptions JsonOpts = new() { WriteIndented = true };

    public Dictionary<string, RegionSet> ByResolution { get; set; } = new();

    public static string DefaultPath() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "Dirt5TrackCompanion", "regions.json");

    public static string Key(int w, int h) => $"{w}x{h}";

    public RegionSet For(int w, int h) =>
        ByResolution.TryGetValue(Key(w, h), out var s) ? s : RegionSet.Default();

    public static RegionConfig Load(string? path = null)
    {
        path ??= DefaultPath();
        try
        {
            if (File.Exists(path))
                return JsonSerializer.Deserialize<RegionConfig>(File.ReadAllText(path)) ?? new RegionConfig();
        }
        catch { /* fall through */ }
        return new RegionConfig();
    }

    public void Save(string? path = null)
    {
        path ??= DefaultPath();
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, JsonSerializer.Serialize(this, JsonOpts));
    }

    /// <summary>Crop a region out of a full capture for focused OCR.</summary>
    public static Bitmap Crop(Bitmap src, NormRect region)
    {
        var r = region.ToPixels(src.Width, src.Height);
        r.Intersect(new Rectangle(0, 0, src.Width, src.Height));
        if (r.Width <= 0 || r.Height <= 0) r = new Rectangle(0, 0, Math.Min(4, src.Width), Math.Min(4, src.Height));
        return src.Clone(r, src.PixelFormat);
    }
}
