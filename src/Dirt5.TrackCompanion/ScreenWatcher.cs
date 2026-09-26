using System.Text;

namespace Dirt5.TrackCompanion;

public sealed record SelectionResult(string? CarP1Id, string? CarP2Id, string? TrackId, double Confidence);

/// <summary>
/// Polls the screen (read-only) and OCRs the configured regions to auto-detect the
/// selected car/track and race results — so the overlay follows the game hands-free.
/// Raises events on the thread pool; subscribers marshal to the UI themselves.
/// </summary>
public sealed class ScreenWatcher : IDisposable
{
    private readonly Ocr _ocr;
    private readonly RegionConfig _regions;
    private readonly CarCatalog _cars;
    private readonly TrackCatalog _tracks;
    private readonly CarDetector _detector;
    private readonly int _intervalMs;
    private CancellationTokenSource? _cts;

    public event Action<SelectionResult>? SelectionDetected;
    public event Action<string /*playerId*/, double /*seconds*/>? ResultDetected;
    public event Action<string>? Status;

    private SelectionResult? _lastSelection;
    private bool _resultLoggedThisScreen;

    public ScreenWatcher(Ocr ocr, RegionConfig regions, CarCatalog cars, TrackCatalog tracks, int intervalMs = 600)
    {
        _ocr = ocr; _regions = regions; _cars = cars; _tracks = tracks; _intervalMs = intervalMs;
        _detector = new CarDetector(cars.Cars);
    }

    public void Start()
    {
        _cts = new CancellationTokenSource();
        _ = Task.Run(() => LoopAsync(_cts.Token));
    }

    public void Stop() => _cts?.Cancel();
    public void Dispose() => Stop();

    private async Task LoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try { await TickAsync(); }
            catch (Exception ex) { Status?.Invoke($"watch error: {ex.Message}"); }
            try { await Task.Delay(_intervalMs, ct); } catch { break; }
        }
    }

    private async Task TickAsync()
    {
        var (shot, fromGame) = ScreenCapture.CaptureGameOrScreen();
        using (shot)
        {
            var set = _regions.For(shot.Width, shot.Height);

            // --- Selection (car-select screen) ---
            // One full-frame OCR reads the plain wordmarks (brand, player names) reliably;
            // the brush-font car name still needs a contrast-enhanced crop.
            var full = await _ocr.ReadAsync(shot);
            var carP1 = await DetectCarAsync(shot, full, set.BrandP1, set.CarNameP1);
            var carP2 = await DetectCarAsync(shot, full, set.BrandP2, set.CarNameP2);
            var track = await MatchTrackAsync(shot, set.TrackName);
            if (carP1 is not null || carP2 is not null || track is not null)
            {
                var conf = new[] { carP1?.Score ?? 0, carP2?.Score ?? 0, track?.Score ?? 0 }.Max();
                var sel = new SelectionResult(carP1?.Value.Id, carP2?.Value.Id, track?.Value.Id, conf);
                if (!sel.Equals(_lastSelection))
                {
                    _lastSelection = sel;
                    SelectionDetected?.Invoke(sel);
                }
            }

            // --- Results (finish screen) ---
            var t1 = await ReadTimeAsync(shot, set.ResultTimeP1);
            var t2 = await ReadTimeAsync(shot, set.ResultTimeP2);
            if (t1 is not null || t2 is not null)
            {
                if (!_resultLoggedThisScreen)
                {
                    if (t1 is { } a) ResultDetected?.Invoke("p1", a);
                    if (t2 is { } b) ResultDetected?.Invoke("p2", b);
                    _resultLoggedThisScreen = true;
                }
            }
            else _resultLoggedThisScreen = false; // left the results screen -> arm again
        }
    }

    /// <summary>
    /// Confident-only car detection: OCR the brand wordmark (plain) and the car-name bar
    /// (contrast-enhanced for the white-on-cyan brush font), then let CarDetector decide.
    /// </summary>
    private async Task<Match<Car>?> DetectCarAsync(Bitmap shot, OcrOutput full, NormRect brandRegion, NormRect nameRegion)
    {
        if (nameRegion.IsEmpty && brandRegion.IsEmpty) return null;

        // Brand wordmark comes from the full-frame OCR (reliable for plain text like
        // "BENTLEY"); tight crops confuse OCR's letter grouping.
        var brandText = brandRegion.IsEmpty ? "" : WordsInRegion(full, brandRegion, shot.Width, shot.Height);

        // Car name is a stylised brush font — needs the contrast-enhanced crop.
        var nameText = "";
        if (!nameRegion.IsEmpty)
        {
            using var crop = RegionConfig.Crop(shot, nameRegion);
            using var prepped = ImagePrep.RedInvertUpscale(crop, 4);
            nameText = (await _ocr.ReadAsync(prepped)).Text;
        }

        return _detector.Detect(brandText, nameText);
    }

    private static string WordsInRegion(OcrOutput full, NormRect region, int w, int h)
    {
        var r = region.ToPixels(w, h);
        var sb = new StringBuilder();
        foreach (var word in full.Words)
        {
            var cx = (int)(word.Box.X + word.Box.Width / 2f);
            var cy = (int)(word.Box.Y + word.Box.Height / 2f);
            if (r.Contains(cx, cy)) sb.Append(word.Text).Append(' ');
        }
        return sb.ToString().Trim();
    }

    /// <summary>Run car detection on a static image (for validation / calibration).</summary>
    public async Task<(Match<Car>? P1, Match<Car>? P2)> DetectCarsAsync(Bitmap shot, RegionSet set)
    {
        var full = await _ocr.ReadAsync(shot);
        return (await DetectCarAsync(shot, full, set.BrandP1, set.CarNameP1),
                await DetectCarAsync(shot, full, set.BrandP2, set.CarNameP2));
    }

    private async Task<Match<Track>?> MatchTrackAsync(Bitmap shot, NormRect region)
    {
        if (region.IsEmpty) return null;
        using var crop = RegionConfig.Crop(shot, region);
        var text = (await _ocr.ReadAsync(crop)).Text;
        // Try the location name, its region, and the combo — best alias wins.
        return FuzzyMatch.Best(text, _tracks.Tracks,
            t => new[] { t.Name, t.Region, $"{t.Name} {t.Region}" }, minScore: 0.6);
    }

    private async Task<double?> ReadTimeAsync(Bitmap shot, NormRect region)
    {
        if (region.IsEmpty) return null;
        using var crop = RegionConfig.Crop(shot, region);
        return LapTime.TryParse((await _ocr.ReadAsync(crop)).Text);
    }
}
