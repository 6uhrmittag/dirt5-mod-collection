// DIRT 5 Car Companion — external car-selection overlay for splitscreen.
//
// Shows the selected car's stats and, per player (P1 vs P2), how often
// each has raced that car on the selected track — with a "who's faster" mark.
// A companion window only: no hooking/injection/game-file edits => splitscreen-safe,
// no ban risk. Selection is via arrow keys (MSIX can't be read live).
//
// Modes:
//   (no args)                          show the overlay
//   --scan <path>                      extract cars+tracks from a game/sample path
//   --dump-cars                        print the extracted roster
//   --dump                             print players + any recorded stats
//   --set-player <1|2> <name>          rename a player, save, exit
//   --record <p1|p2> <car> <track> <sec> <win>   log a run, save, exit
//   --demo                             seed example runs for both players
//   --capture <png> [--car <id>] [--track <id>]  render to PNG and exit

using System.Drawing.Imaging;
using System.Globalization;
using Dirt5.TrackCompanion;

// Must run before any screen access so capture uses true physical resolution.
ScreenCapture.EnableDpiAwareness();

string? scanPath = null, capturePath = null, carSel = null, trackSel = null;
bool demo = false, dump = false, dumpCars = false, watch = false, secondary = false, wall = false;
string? setPlayerNum = null, setPlayerName = null;
string? calibratePath = null, ocrImg = null, ocrAs = null, detectImg = null;
string? recPlayer = null, recCar = null, recTrack = null; double? recSec = null; bool recWin = false;

for (var i = 0; i < args.Length; i++)
{
    switch (args[i])
    {
        case "--scan" when i + 1 < args.Length: scanPath = args[++i]; break;
        case "--capture" when i + 1 < args.Length: capturePath = args[++i]; break;
        case "--car" when i + 1 < args.Length: carSel = args[++i]; break;
        case "--track" when i + 1 < args.Length: trackSel = args[++i]; break;
        case "--watch": watch = true; break;
        case "--secondary": secondary = true; break;
        case "--wall": wall = true; break;
        case "--calibrate" when i + 1 < args.Length: calibratePath = args[++i]; break;
        case "--ocr" when i + 1 < args.Length: ocrImg = args[++i]; break;
        case "--as" when i + 1 < args.Length: ocrAs = args[++i]; break;
        case "--detect" when i + 1 < args.Length: detectImg = args[++i]; break;
        case "--demo": demo = true; break;
        case "--dump": dump = true; break;
        case "--dump-cars": dumpCars = true; break;
        case "--set-player" when i + 2 < args.Length: setPlayerNum = args[++i]; setPlayerName = args[++i]; break;
        case "--record" when i + 5 < args.Length:
            recPlayer = args[++i]; recCar = args[++i]; recTrack = args[++i];
            recSec = double.TryParse(args[++i], CultureInfo.InvariantCulture, out var sc) ? sc : null;
            recWin = bool.TryParse(args[++i], out var w) && w;
            break;
    }
}

scanPath ??= FindDefaultScanPath();

var players = Players.Load();
var stats = new StatsStore();

// --- Mutating one-shot modes ------------------------------------------------
if (setPlayerNum is not null)
{
    if (setPlayerNum == "1") players.P1 = setPlayerName!;
    else if (setPlayerNum == "2") players.P2 = setPlayerName!;
    players.Save();
    Console.WriteLine($"Players: 1={players.P1}  2={players.P2}");
    return 0;
}

if (recPlayer is not null)
{
    stats.RecordRun(recPlayer, recCar!, recTrack!, recSec, recWin);
    stats.Save();
    Console.WriteLine($"Recorded: {players.Name(recPlayer)}  {recCar} @ {recTrack}  time={recSec?.ToString(CultureInfo.InvariantCulture) ?? "—"}  win={recWin}");
    return 0;
}

// --- Couch Session Wall (second-monitor live gallery) ------------------------
if (wall)
{
    System.Windows.Forms.Application.EnableVisualStyles();
    System.Windows.Forms.Application.SetCompatibleTextRenderingDefault(false);
    Console.WriteLine("Session Wall läuft — Monitor 2. Doppelklick = Poster, Rechts-Doppelklick = Ende.");
    System.Windows.Forms.Application.Run(new SessionWallForm(players));
    return 0;
}

// --- Catalogs ---------------------------------------------------------------
var carCatalog = CarCatalog.Build(scanPath);
// Track axis = curated real DIRT 5 locations (clean cycle). The index over-extracts
// asset subfolders, so we don't feed raw extraction into the selectable track list;
// extraction still powers the car roster and is documented in FINDINGS.
var trackCatalog = TrackCatalog.Build(null);

if (demo) SeedDemo(stats);

// --- Read-only report modes -------------------------------------------------
if (dumpCars)
{
    Console.WriteLine($"DIRT 5 roster — {carCatalog.Cars.Count} cars (scan: {scanPath ?? "seed"})");
    foreach (var c in carCatalog.Cars) Console.WriteLine($"  {c.Id,-42} {c.Name}");
    return 0;
}

if (dump)
{
    Console.WriteLine($"Players: 1={players.P1}  2={players.P2}");
    Console.WriteLine($"Cars: {carCatalog.Cars.Count}   Tracks: {trackCatalog.Tracks.Count}");
    Console.WriteLine("Recorded stats (car @ track — player: best/races/wins):");
    var any = false;
    foreach (var c in carCatalog.Cars)
        foreach (var t in trackCatalog.Tracks)
        {
            var a = stats.Get("p1", c.Id, t.Id);
            var b = stats.Get("p2", c.Id, t.Id);
            if (a.Attempts == 0 && b.Attempts == 0) continue;
            any = true;
            Console.WriteLine($"  {c.Name} @ {t.Name}");
            Console.WriteLine($"      {players.P1,-18} {a.BestTimeDisplay,-12} races={a.Attempts} wins={a.Wins}");
            Console.WriteLine($"      {players.P2,-18} {b.BestTimeDisplay,-12} races={b.Attempts} wins={b.Wins}");
        }
    if (!any) Console.WriteLine("  (none yet — use --record or --demo)");
    return 0;
}

// --- OCR a single image (validation / debugging) ----------------------------
if (ocrImg is not null)
{
    using var img = new Bitmap(ocrImg);
    var ocr = new Ocr();
    var res = await ocr.ReadAsync(img);
    Console.WriteLine($"OCR ({ocr.Language}) text: \"{res.Text}\"");
    if (ocrAs is null or "car")
    {
        var m = FuzzyMatch.Best(res.Text, carCatalog.Cars, c => c.Name, 0.4);
        Console.WriteLine($"  car match:   {(m is { } cm ? $"{cm.Display}  ({cm.Score:0.00})" : "none")}");
    }
    if (ocrAs is null or "track")
    {
        var m = FuzzyMatch.Best(res.Text, trackCatalog.Tracks,
            t => new[] { t.Name, t.Region, $"{t.Name} {t.Region}" }, 0.4);
        Console.WriteLine($"  track match: {(m is { } tm ? $"{tm.Display}  ({tm.Score:0.00})" : "none")}");
    }
    if (ocrAs is null or "time")
    {
        var t = LapTime.TryParse(res.Text);
        Console.WriteLine($"  lap-time:    {(t is { } sec ? $"{sec:0.000}s" : "none")}");
    }
    return 0;
}

// --- Detect: run confident-only car detection on a static screenshot ---------
if (detectImg is not null)
{
    using var bmp = new Bitmap(detectImg);
    var regions = RegionConfig.Load();
    var set = regions.For(bmp.Width, bmp.Height);
    var det = new ScreenWatcher(new Ocr(), regions, carCatalog, trackCatalog);
    var (p1, p2) = await det.DetectCarsAsync(bmp, set);
    Console.WriteLine($"detect on {Path.GetFileName(detectImg)} ({bmp.Width}x{bmp.Height}):");
    Console.WriteLine($"  P1: {(p1 is { } a ? $"{a.Display}  (conf {a.Score:0.00})" : "— not confident (keeps manual)")}");
    Console.WriteLine($"  P2: {(p2 is { } b ? $"{b.Display}  (conf {b.Score:0.00})" : "— not confident (keeps manual)")}");
    return 0;
}

// --- Calibrate: capture the screen + full OCR dump (for tuning regions.json) --
if (calibratePath is not null)
{
    var (shot, fromGame) = ScreenCapture.CaptureGameOrScreen();
    using (shot)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(calibratePath))!);
        shot.Save(calibratePath, ImageFormat.Png);
        var ocr = new Ocr();
        var res = await ocr.ReadAsync(shot);
        var dumpPath = Path.ChangeExtension(calibratePath, ".ocr.txt");
        var lines = res.Words.Select(w =>
            $"[{w.Box.X / shot.Width:0.000},{w.Box.Y / shot.Height:0.000} " +
            $"{w.Box.Width / shot.Width:0.000}x{w.Box.Height / shot.Height:0.000}] {w.Text}");
        File.WriteAllLines(dumpPath, lines);
        Console.WriteLine($"Captured {shot.Width}x{shot.Height} (fromGameWindow={fromGame}) -> {calibratePath}");
        Console.WriteLine($"OCR words: {res.Words.Count} -> {dumpPath}");
    }
    return 0;
}

// --- Selection resolution (for capture) -------------------------------------
int carIdx = ResolveIndex(carSel, carCatalog.Cars.Select(c => c.Id).ToList());
int trackIdx = ResolveIndex(trackSel, trackCatalog.Tracks.Select(t => t.Id).ToList());

if (capturePath is not null)
{
    using var capForm = new OverlayForm(carCatalog, trackCatalog, stats, players, carIdx, trackIdx);
    using var bmp = new Bitmap(capForm.Width, capForm.Height);
    using (var g = Graphics.FromImage(bmp)) capForm.Render(g, capForm.Width, capForm.Height);
    Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(capturePath))!);
    bmp.Save(capturePath, ImageFormat.Png);
    Console.WriteLine($"Wrote capture: {Path.GetFullPath(capturePath)} ({capForm.Width}x{capForm.Height})");
    return 0;
}

// --- Interactive overlay ----------------------------------------------------
if (demo) stats.Save();
System.Windows.Forms.Application.EnableVisualStyles();
System.Windows.Forms.Application.SetCompatibleTextRenderingDefault(false);

var form = new OverlayForm(carCatalog, trackCatalog, stats, players, carIdx, trackIdx);

if (secondary)
{
    var s = System.Windows.Forms.Screen.AllScreens.FirstOrDefault(x => !x.Primary);
    if (s is not null) { form.PlaceOn(s); Console.WriteLine($"overlay placed on secondary monitor {s.DeviceName} {s.Bounds}"); }
    else Console.WriteLine("no secondary monitor found; overlay stays on primary");
}

ScreenWatcher? watcher = null;
if (watch)
{
    try
    {
        var ocr = new Ocr();
        var regions = RegionConfig.Load();
        watcher = new ScreenWatcher(ocr, regions, carCatalog, trackCatalog);
        string? curP1 = null, curP2 = null, curTrack = null;

        watcher.SelectionDetected += sel =>
        {
            curP1 = sel.CarP1Id ?? curP1;
            curP2 = sel.CarP2Id ?? curP2;
            curTrack = sel.TrackId ?? curTrack;
            // P2 is "you" — steer the overlay to your car by default.
            form.SetSelection(sel.CarP2Id ?? sel.CarP1Id, sel.TrackId);
            form.SetLive($"detected {DisplayFor(sel, carCatalog, trackCatalog)} ({sel.Confidence:0%})");
        };
        watcher.ResultDetected += (player, seconds) =>
        {
            var carId = player == "p1" ? curP1 : curP2;
            if (carId is null || curTrack is null) return;
            form.BeginInvoke(() =>
            {
                stats.RecordRun(player, carId, curTrack, seconds, won: false);
                stats.Save();
                form.SetLive($"logged {players.Name(player)} {seconds:0.000}s");
            });
        };
        watcher.Status += msg => form.SetLive(msg);
        form.EnableLive();
        form.Shown += (_, __) => watcher.Start();
    }
    catch (Exception ex)
    {
        Console.Error.WriteLine($"--watch disabled: {ex.Message}");
    }
}

System.Windows.Forms.Application.Run(form);
watcher?.Stop();
return 0;

// ---------------------------------------------------------------------------
static string? FindDefaultScanPath()
{
    foreach (var rel in new[] { "samples/dat.ndx", "../samples/dat.ndx", "../../samples/dat.ndx", "../../../samples/dat.ndx" })
        if (File.Exists(rel)) return Path.GetFullPath(rel);
    foreach (var rel in new[] { "samples", "../samples", "../../samples", "../../../samples" })
        if (Directory.Exists(rel)) return Path.GetFullPath(rel);
    return null;
}

static string DisplayFor(SelectionResult sel, CarCatalog cars, TrackCatalog tracks)
{
    var carId = sel.CarP2Id ?? sel.CarP1Id;
    var car = carId is not null ? cars.Cars.FirstOrDefault(c => c.Id == carId)?.Name : null;
    var track = sel.TrackId is not null ? tracks.Tracks.FirstOrDefault(t => t.Id == sel.TrackId)?.Name : null;
    return $"{car ?? "?"} @ {track ?? "?"}";
}

static int ResolveIndex(string? sel, List<string> ids)
{
    if (string.IsNullOrWhiteSpace(sel)) return 0;
    var byId = ids.FindIndex(x => x.Equals(sel, StringComparison.OrdinalIgnoreCase));
    if (byId >= 0) return byId;
    return int.TryParse(sel, out var n) ? Math.Max(0, n) : 0;
}

// Example runs across both players so a fresh install / screenshot shows a comparison.
static void SeedDemo(StatsStore s)
{
    // Baja Beetle @ Nepal — a close splitscreen duel (you edge it).
    s.RecordRun("p1", "baja_beetle", "nepal/himalaya", 145.230, won: false);
    s.RecordRun("p1", "baja_beetle", "nepal/himalaya", 141.117, won: true);
    s.RecordRun("p2", "baja_beetle", "nepal/himalaya", 142.004, won: false);
    s.RecordRun("p2", "baja_beetle", "nepal/himalaya", 139.900, won: true);
    s.RecordRun("p2", "baja_beetle", "nepal/himalaya", 140.550, won: true);
    // Some other combos.
    s.RecordRun("p1", "lancia_stratos", "italy/carrara", 128.004, won: true);
    s.RecordRun("p2", "lancia_stratos", "italy/carrara", 131.220, won: false);
}
