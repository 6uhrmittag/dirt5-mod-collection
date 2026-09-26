using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.Globalization;

namespace Dirt5.TrackCompanion;

/// <summary>
/// Car-selection companion HUD. For the currently selected car + track it shows the
/// car's stats and — the thing the user asked for — how often each splitscreen
/// player has raced that car on that track, side by side with a "who's faster" mark.
///
/// It is a normal top-level overlay window: no hooking, no injection, no game-file
/// changes, so it is splitscreen-safe and carries no ban risk. Selection is driven
/// from the overlay (arrow keys) since the MSIX build can't be read live.
/// </summary>
public sealed class OverlayForm : Form
{
    private readonly CarCatalog _cars;
    private readonly TrackCatalog _tracks;
    private readonly StatsStore _stats;
    private readonly Players _players;

    private int _car;
    private int _track;
    private Point _dragStart;
    private bool _dragging;
    private bool _watching;
    private string _liveText = "";

    private const int W = 540;
    private const int H = 396;
    private const int PadX = 18;
    private static readonly Color Accent = Color.FromArgb(255, 138, 0);
    private static readonly Color Faster = Color.FromArgb(90, 220, 120);

    public OverlayForm(CarCatalog cars, TrackCatalog tracks, StatsStore stats, Players players,
                       int carIndex = 0, int trackIndex = 0)
    {
        _cars = cars; _tracks = tracks; _stats = stats; _players = players;
        _car = Clamp(carIndex, cars.Cars.Count);
        _track = Clamp(trackIndex, tracks.Tracks.Count);

        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        ShowInTaskbar = false;
        TopMost = true;
        BackColor = Color.FromArgb(18, 18, 22);
        Opacity = 0.93;
        DoubleBuffered = true;
        Width = W; Height = H;
        Location = new Point(40, 120);

        KeyPreview = true;
        KeyDown += OnKey;
        MouseDown += (_, e) => { _dragging = true; _dragStart = e.Location; };
        MouseUp += (_, __) => _dragging = false;
        MouseMove += (_, e) =>
        {
            if (_dragging)
                Location = new Point(Location.X + e.X - _dragStart.X, Location.Y + e.Y - _dragStart.Y);
        };
    }

    private static int Clamp(int i, int count) => count == 0 ? 0 : ((i % count) + count) % count;

    /// <summary>Enable the "● LIVE" indicator (screen-watch mode is on).</summary>
    public void EnableLive() => _watching = true;

    /// <summary>Position the overlay on a specific screen (e.g. a second monitor).</summary>
    public void PlaceOn(Screen screen)
    {
        var wa = screen.WorkingArea;
        Location = new Point(wa.Left + 40, wa.Top + 60);
    }

    /// <summary>Update the last-detected status line (thread-safe).</summary>
    public void SetLive(string text) => OnUi(() => { _liveText = text; Invalidate(); });

    /// <summary>Externally drive the selection (from the screen watcher). Thread-safe.</summary>
    public void SetSelection(string? carId, string? trackId) => OnUi(() =>
    {
        if (carId is not null) { var i = IndexOf(_cars.Cars, c => c.Id == carId); if (i >= 0) _car = i; }
        if (trackId is not null) { var i = IndexOf(_tracks.Tracks, t => t.Id == trackId); if (i >= 0) _track = i; }
        Invalidate();
    });

    private void OnUi(Action a)
    {
        if (IsHandleCreated && InvokeRequired) BeginInvoke(a);
        else a();
    }

    private static int IndexOf<T>(IReadOnlyList<T> list, Func<T, bool> pred)
    {
        for (var i = 0; i < list.Count; i++) if (pred(list[i])) return i;
        return -1;
    }

    private void OnKey(object? s, KeyEventArgs e)
    {
        switch (e.KeyCode)
        {
            case Keys.Escape: Close(); break;
            case Keys.Left:  _car = Clamp(_car - 1, _cars.Cars.Count); Invalidate(); break;
            case Keys.Right: _car = Clamp(_car + 1, _cars.Cars.Count); Invalidate(); break;
            case Keys.Up:    _track = Clamp(_track - 1, _tracks.Tracks.Count); Invalidate(); break;
            case Keys.Down:  _track = Clamp(_track + 1, _tracks.Tracks.Count); Invalidate(); break;
        }
    }

    protected override void OnPaint(PaintEventArgs e) => Render(e.Graphics, Width, Height);

    /// <summary>Shared renderer so the live overlay and the PNG capture match exactly.</summary>
    public void Render(Graphics g, int width, int height)
    {
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;

        var car = _cars.Cars.Count > 0 ? _cars.Cars[_car] : new Car("none", "—");
        var track = _tracks.Tracks.Count > 0 ? _tracks.Tracks[_track] : new Track("none", "—", "—", "—");

        using var bg = new SolidBrush(Color.FromArgb(18, 18, 22));
        g.FillRectangle(bg, 0, 0, width, height);
        using (var ab = new SolidBrush(Accent)) g.FillRectangle(ab, 0, 0, width, 4);

        using var fTitle = new Font("Segoe UI Semibold", 12f, FontStyle.Bold);
        using var fCar = new Font("Segoe UI Semibold", 16f, FontStyle.Bold);
        using var fTrack = new Font("Segoe UI", 10.5f);
        using var fHead = new Font("Segoe UI Semibold", 8.5f, FontStyle.Bold);
        using var fCell = new Font("Segoe UI", 10.5f);
        using var fMono = new Font("Consolas", 11f, FontStyle.Bold);
        using var fSmall = new Font("Segoe UI", 8.5f);

        using var white = new SolidBrush(Color.White);
        using var amber = new SolidBrush(Accent);
        using var grey = new SolidBrush(Color.FromArgb(155, 155, 163));
        using var dim = new SolidBrush(Color.FromArgb(95, 95, 103));
        using var faster = new SolidBrush(Faster);

        // --- Header --------------------------------------------------------
        g.DrawString("DIRT 5 — Car Companion", fTitle, amber, PadX, 12);
        g.DrawString($"◄ {_car + 1}/{_cars.Cars.Count} ►", fSmall, dim, width - 96, 16);
        g.DrawString(car.Name, fCar, white, PadX, 34);
        g.DrawString($"on  {track.Name}  ·  {track.Region}", fTrack, grey, PadX, 66);

        using (var line = new Pen(Color.FromArgb(55, 55, 62)))
            g.DrawLine(line, PadX, 92, width - PadX, 92);

        // --- Car stats block ----------------------------------------------
        g.DrawString("CAR STATS", fHead, grey, PadX, 100);
        var cats = new (string Label, int? Val)[]
        {
            ("Speed", car.Stats?.Speed),
            ("Acceleration", car.Stats?.Acceleration),
            ("Handling", car.Stats?.Handling),
            ("Toughness", car.Stats?.Toughness),
        };
        int sy = 118;
        foreach (var (label, val) in cats)
        {
            g.DrawString(label, fCell, grey, PadX, sy);
            DrawRatingBar(g, 150, sy + 4, 250, 12, val);
            g.DrawString(val is { } v ? v.ToString() : "—", fSmall, val is null ? dim : amber, 410, sy);
            sy += 20;
        }
        if (car.Stats?.HasAny != true)
            g.DrawString("(game ratings pending file extraction — usage below is live)",
                fSmall, dim, PadX, sy);

        // --- Who's-faster comparison --------------------------------------
        int cy = 226;
        using (var line = new Pen(Color.FromArgb(55, 55, 62)))
            g.DrawLine(line, PadX, cy - 8, width - PadX, cy - 8);
        g.DrawString("THIS CAR ON THIS TRACK", fHead, grey, PadX, cy);

        var s1 = _stats.Get("p1", car.Id, track.Id);
        var s2 = _stats.Get("p2", car.Id, track.Id);
        int xLabel = PadX, xP1 = 250, xP2 = 395;

        g.DrawString(_players.P1, fHead, grey, xP1, cy);
        g.DrawString(_players.P2, fHead, grey, xP2, cy);

        // Best time row with faster highlight + gap.
        int ry = cy + 22;
        g.DrawString("Best time", fCell, grey, xLabel, ry);
        var (b1, b2) = (s1.BestTimeSeconds, s2.BestTimeSeconds);
        bool p1Faster = b1 is { } && (b2 is null || b1 < b2);
        bool p2Faster = b2 is { } && (b1 is null || b2 < b1);
        g.DrawString(s1.BestTimeDisplay, fMono, p1Faster ? faster : white, xP1, ry - 1);
        g.DrawString(s2.BestTimeDisplay, fMono, p2Faster ? faster : white, xP2, ry - 1);
        if (b1 is { } bb1 && b2 is { } bb2)
        {
            var delta = Math.Abs(bb1 - bb2);
            var who = bb1 < bb2 ? _players.P1 : _players.P2;
            var txt = string.Format(CultureInfo.InvariantCulture, "{0} faster by {1:0.000}s", who, delta);
            g.DrawString(txt, fSmall, faster, xLabel, ry + 22);
        }

        // Races + Wins rows.
        int ry2 = ry + 44;
        g.DrawString("Races", fCell, grey, xLabel, ry2);
        g.DrawString(s1.Attempts.ToString(), fMono, s1.Attempts > 0 ? white : dim, xP1, ry2 - 1);
        g.DrawString(s2.Attempts.ToString(), fMono, s2.Attempts > 0 ? white : dim, xP2, ry2 - 1);
        int ry3 = ry2 + 24;
        g.DrawString("Wins", fCell, grey, xLabel, ry3);
        g.DrawString(s1.Wins.ToString(), fMono, s1.Wins > 0 ? amber : dim, xP1, ry3 - 1);
        g.DrawString(s2.Wins.ToString(), fMono, s2.Wins > 0 ? amber : dim, xP2, ry3 - 1);

        var together = _stats.TotalAttempts(car.Id, track.Id);
        g.DrawString($"Together you've raced this combo {together}×", fSmall, grey, xLabel, ry3 + 26);

        // Live screen-watch indicator.
        if (_watching)
        {
            g.FillEllipse(faster, PadX, height - 40, 9, 9);
            g.DrawString("LIVE", fHead, faster, PadX + 14, height - 42);
            g.DrawString(_liveText.Length == 0 ? "watching screen…" : _liveText,
                fSmall, grey, PadX + 52, height - 41);
        }

        g.DrawString(_watching
            ? "auto-sync on · drag to move · Esc hide"
            : "◄ ► car   ▲ ▼ track   ·   drag to move   ·   Esc hide",
            fSmall, dim, PadX, height - 22);
    }

    private static void DrawRatingBar(Graphics g, int x, int y, int w, int h, int? val)
    {
        using var track = new SolidBrush(Color.FromArgb(38, 38, 44));
        g.FillRectangle(track, x, y, w, h);
        if (val is { } v)
        {
            var frac = Math.Clamp(v / 10.0, 0, 1);
            using var fill = new SolidBrush(Accent);
            g.FillRectangle(fill, x, y, (int)(w * frac), h);
        }
        else
        {
            using var pen = new Pen(Color.FromArgb(60, 60, 68)) { DashStyle = DashStyle.Dot };
            g.DrawRectangle(pen, x, y, w, h);
        }
    }
}
