using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Globalization;
using System.Text.RegularExpressions;

namespace Dirt5.TrackCompanion;

/// <summary>
/// "Couch Session Wall" — a live, full-screen gallery of the players' current
/// DIRT 5 session, shown on the SECOND monitor while they play on the first.
///
/// Every few seconds it grabs a frame of the game (read-only screen capture —
/// the one thing proven rock-solid in this project), scores it for "action"
/// (colourfulness/contrast), and curates:
///   - a big LIVE view,
///   - a rotating TOP MOMENTS column (best-scored, time-separated shots),
///   - a chronological filmstrip of the last minutes,
/// and periodically renders everything into a shareable SESSION POSTER png.
///
/// Zero game files touched, zero injection, zero OCR dependency — it cannot
/// break and it cannot be wrong. The window never activates itself, so the
/// game never loses focus (WS_EX_NOACTIVATE): mouse-only controls.
/// </summary>
public sealed class SessionWallForm : Form
{
    private sealed class Shot : IDisposable
    {
        public required Bitmap Medium;   // 960x540 (poster tiles)
        public required Bitmap Thumb;    // 266x150 (filmstrip)
        public DateTime At;
        public double Score;
        public void Dispose() { Medium.Dispose(); Thumb.Dispose(); }
    }

    private readonly Players _players;
    private readonly System.Windows.Forms.Timer _capTimer;
    private readonly System.Windows.Forms.Timer _uiTimer;
    private readonly DateTime _start = DateTime.Now;
    private readonly string _posterDir;

    private readonly List<Shot> _film = new();   // chronological (owns its shots)
    private readonly List<Shot> _best = new();   // top by score (owns clones)
    private Bitmap? _latest;                     // 1280x720 live view
    private int _shots;
    private bool _fromGame;
    private string _flash = "";
    private DateTime _flashUntil;
    private DateTime _lastAutosave = DateTime.Now;
    private volatile bool _capturing;

    // --- session diary (OCR-driven, German UI) ---
    private readonly Ocr? _ocr;
    private bool _racing;
    private int _racingStreak, _menuStreak;      // hysteresis vs. OCR dropouts in dusty frames
    private int _races;
    private int _racingFrames;                   // × capture interval = Fahrzeit
    private readonly List<(TimeSpan At, string Text)> _log = new();
    private string _lastLoc = "";
    private DateTime _lastLocAt = DateTime.MinValue;

    // We detect MENUS instead of the tiny race HUD: the big German frontend words OCR
    // reliably, whereas the HUD timer is too small after downscale AND its format
    // collides with leaderboard times shown in menus. "Not a menu" == racing.
    private static readonly string[] MenuWords =
    {
        "SPIELEN", "ZURÜCK", "ZURUCK", "PROFIL", "BESTENLISTEN", "ERNEUERN", "AUSWÄHLEN",
        "AUSWAHLEN", "EVENTS", "THROWDOWNS", "SPONSOREN", "PODCASTS", "GESAMT", "SPLITSCREEN",
        "SPONSOREZIELE", "EVENTZIELE", "FORTSETZEN", "NEU STARTEN", "NEUSTART", "KARRIERE",
        "HAUPTMENÜ", "EINSTELLUNGEN", "FORTFAHREN", "ergebnisse", "ERGEBNISSE", "WIEDERHOLUNG",
    };
    // Optional positive HUD confirm (helps, not required).
    private static readonly Regex RxHud = new(@"\b[1-9]/[1-9]\b", RegexOptions.Compiled);
    private static readonly string _dbgPath = Path.Combine(Path.GetTempPath(), "dirt5-wall-debug.log");
    // Event cards & loading screens: "XIAMO RUN, CHINA" — German country/region names.
    // Matched case-insensitively on OCR-normalised text (see NormalizeForLocation).
    private static readonly Regex RxLocation = new(
        @"([A-ZÄÖÜ][A-ZÄÖÜa-zäöüß\- ]{2,28}),\s*(ITALIEN|CHINA|BRASILIEN|NORWEGEN|GRIECHENLAND|MAROKKO|NEPAL|SÜDAFRIKA|USA|NEW YORK|ARIZONA)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    /// <summary>Fix the classic OCR confusions before location matching ("BRAS'LIEN" -> "BRASILIEN").</summary>
    private static string NormalizeForLocation(string text) =>
        text.Replace('\'', 'I').Replace('’', 'I').Replace('|', 'I').Replace('!', 'I');
    private static readonly string[] EventTypes =
    {
        "LAND RUSH", "ULTRA CROSS", "ULTRACROSS", "STAMPEDE", "ICE BREAKER", "ICEBREAKER",
        "GYMKHANA", "SPRINT", "RALLY RAID", "PATH FINDER", "PATHFINDER",
    };

    private static readonly Color Accent = Color.FromArgb(255, 138, 0);
    private static readonly Color Live = Color.FromArgb(90, 220, 120);

    // Never steal focus from the game (splitscreen would pause otherwise).
    protected override bool ShowWithoutActivation => true;
    protected override CreateParams CreateParams
    {
        get { var cp = base.CreateParams; cp.ExStyle |= 0x08000000; return cp; } // WS_EX_NOACTIVATE
    }

    public SessionWallForm(Players players)
    {
        _players = players;
        _posterDir = Directory.Exists("docs")
            ? Path.GetFullPath("docs")
            : Environment.GetFolderPath(Environment.SpecialFolder.MyPictures);
        try { _ocr = new Ocr(); } catch { _ocr = null; }   // diary degrades gracefully

        var screen = Screen.AllScreens.FirstOrDefault(s => !s.Primary) ?? Screen.PrimaryScreen!;
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        Bounds = screen.Bounds;
        BackColor = Color.FromArgb(12, 12, 16);
        DoubleBuffered = true;
        ShowInTaskbar = false;

        _capTimer = new System.Windows.Forms.Timer { Interval = 3000 };
        _capTimer.Tick += (_, __) => _ = CaptureTickAsync();
        _capTimer.Start();

        _uiTimer = new System.Windows.Forms.Timer { Interval = 250 };
        _uiTimer.Tick += (_, __) => Invalidate();
        _uiTimer.Start();

        MouseDown += (_, e) =>
        {
            if (e.Button == MouseButtons.Left && e.Clicks == 2) SavePoster("POSTER GESPEICHERT");
            if (e.Button == MouseButtons.Right && e.Clicks == 2) { SavePoster("FINAL POSTER GESPEICHERT"); Close(); }
        };
    }

    // ------------------------------------------------------------------ capture

    private async Task CaptureTickAsync()
    {
        if (_capturing) return;
        _capturing = true;
        try
        {
            var (frame, fromGame) = await Task.Run(ScreenCapture.CaptureGameOrScreen);
            string ocrText = "";
            using (frame)
            {
                var medium = Resize(frame, 960, 540, saturate: true);
                var thumb = Resize(frame, 266, 150, saturate: true);
                var latest = Resize(frame, 1280, 720, saturate: true);
                var score = ActionScore(thumb);

                // Read the frame text (event cards, loading screens, race HUD) for the diary.
                if (_ocr is not null)
                {
                    try
                    {
                        var maxW = Math.Min(2560, Ocr.MaxImageDimension);
                        using var ocrImg = Resize(frame, maxW, maxW * frame.Height / frame.Width, saturate: false);
                        ocrText = (await _ocr.ReadAsync(ocrImg)).Text;
                    }
                    catch { /* diary is best-effort */ }
                }

                var shot = new Shot { Medium = medium, Thumb = thumb, At = DateTime.Now, Score = score };
                if (IsHandleCreated)
                    BeginInvoke(() => Integrate(shot, latest, fromGame, ocrText));
                else { shot.Dispose(); latest.Dispose(); }
            }
        }
        catch { /* capture hiccups are fine — next tick retries */ }
        finally { _capturing = false; }
    }

    private void Integrate(Shot shot, Bitmap latest, bool fromGame, string ocrText)
    {
        _latest?.Dispose();
        _latest = latest;
        _fromGame = fromGame;
        _shots++;
        ParseDiary(ocrText, shot.At);

        _film.Add(shot);
        while (_film.Count > 8) { _film[0].Dispose(); _film.RemoveAt(0); }

        // Curate TOP MOMENTS: best score wins per ~20s window, max 6, own clones.
        var near = _best.FirstOrDefault(b => Math.Abs((b.At - shot.At).TotalSeconds) < 20);
        if (near is not null)
        {
            if (shot.Score > near.Score) { _best.Remove(near); near.Dispose(); _best.Add(Clone(shot)); }
        }
        else _best.Add(Clone(shot));
        _best.Sort((a, b) => b.Score.CompareTo(a.Score));
        while (_best.Count > 6) { _best[^1].Dispose(); _best.RemoveAt(_best.Count - 1); }

        if ((DateTime.Now - _lastAutosave).TotalMinutes >= 2)
        {
            SavePoster("autosave");
            _lastAutosave = DateTime.Now;
        }
        Invalidate();
    }

    /// <summary>Turn frame text into diary facts: racing state, race count, tracks played.</summary>
    private void ParseDiary(string text, DateTime at)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        var t = at - _start;

        // State detection, reworked after live testing: the race HUD is too small to
        // OCR reliably after downscale, AND its ms-time format collides with the
        // leaderboard times shown in menus — so we detect MENUS instead. The big
        // German frontend words OCR dependably; "no menu words" => racing (loading
        // screens count towards racing, an accepted approximation for Fahrzeit).
        // NOTE: not yet verified against a live session — see the debug log.
        var upper = text.ToUpperInvariant();
        var isMenu = MenuWords.Any(w => upper.Contains(w.ToUpperInvariant()));
        var hudHit = RxHud.IsMatch(text);           // optional positive confirm
        var racingNow = !isMenu || hudHit;
        if (racingNow) { _racingStreak++; _menuStreak = 0; }
        else { _menuStreak++; _racingStreak = 0; }

        if (!_racing && _racingStreak >= 2)          // ~6s without menu UI => race started
        {
            _racing = true;
            _races++;
            AddLog(t, $"» Rennen #{_races} gestartet");
        }
        else if (_racing && _menuStreak >= 2)        // menu words are reliable => flip back fast
        {
            _racing = false;
        }
        if (_racing) _racingFrames++;

        // Decision trace for offline verification of the detector.
        try
        {
            File.AppendAllText(_dbgPath,
                $"{at:HH:mm:ss} menu={isMenu} hud={hudHit} racing={_racing} races={_races} | {text[..Math.Min(text.Length, 110)].ReplaceLineEndings(" ")}{Environment.NewLine}");
        }
        catch { /* debug log is best-effort */ }

        var m = RxLocation.Match(NormalizeForLocation(text));
        if (m.Success)
        {
            var ti = CultureInfo.GetCultureInfo("de-DE").TextInfo;
            var track = ti.ToTitleCase(m.Groups[1].Value.Trim().ToLowerInvariant());
            var country = ti.ToTitleCase(m.Groups[2].Value.ToLowerInvariant());
            var ev = EventTypes.FirstOrDefault(e => text.Contains(e, StringComparison.OrdinalIgnoreCase));
            var loc = ev is null ? $"{track}, {country}" : $"{Pretty(ev)} · {track}, {country}";
            if (loc != _lastLoc || (at - _lastLocAt).TotalSeconds > 120)
            {
                _lastLoc = loc;
                _lastLocAt = at;
                AddLog(t, $"• {loc}");
            }
        }
    }

    private static string Pretty(string ev) =>
        CultureInfo.GetCultureInfo("de-DE").TextInfo.ToTitleCase(ev.ToLowerInvariant());

    private void AddLog(TimeSpan at, string text)
    {
        if (_log.Count > 0 && _log[^1].Text == text) return;
        _log.Add((at, text));
        while (_log.Count > 40) _log.RemoveAt(0);
    }

    private static Shot Clone(Shot s) => new()
    {
        Medium = (Bitmap)s.Medium.Clone(),
        Thumb = (Bitmap)s.Thumb.Clone(),
        At = s.At,
        Score = s.Score,
    };

    // ------------------------------------------------------------------ paint

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;
        int W = ClientSize.Width, H = ClientSize.Height;

        using var fTitle = new Font("Segoe UI Black", 26f, FontStyle.Bold);
        using var fSub = new Font("Segoe UI Semibold", 12f, FontStyle.Bold);
        using var fHead = new Font("Segoe UI Semibold", 10f, FontStyle.Bold);
        using var fSmall = new Font("Segoe UI", 9f);
        using var white = new SolidBrush(Color.White);
        using var amber = new SolidBrush(Accent);
        using var grey = new SolidBrush(Color.FromArgb(150, 150, 158));
        using var dim = new SolidBrush(Color.FromArgb(90, 90, 98));
        using var live = new SolidBrush(Live);

        // Header -----------------------------------------------------------
        using (var bar = new SolidBrush(Accent)) g.FillRectangle(bar, 0, 0, W, 5);
        g.DrawString("DIRT 5 · COUCH SESSION", fTitle, amber, 20, 16);
        g.DrawString($"{_players.P1}  ×  {_players.P2}", fSub, white, 24, 62);

        var dur = DateTime.Now - _start;
        var clock = $"{(int)dur.TotalMinutes:00}:{dur.Seconds:00}";
        var fahrzeit = TimeSpan.FromSeconds(_racingFrames * _capTimer.Interval / 1000.0);
        var statsLine =
            $"Session {clock}   ·   {_races} Rennen   ·   Fahrzeit {(int)fahrzeit.TotalMinutes:00}:{fahrzeit.Seconds:00}   ·   {_shots} Shots   ·   ";
        g.DrawString(statsLine, fHead, grey, 24, 88);
        using (var sb = new SolidBrush(_racing ? Live : Color.FromArgb(120, 120, 128)))
            g.DrawString(_racing ? "● IM RENNEN" : "● IM MENÜ", fHead, sb,
                24 + g.MeasureString(statsLine, fHead).Width, 88);

        // pulsing LIVE dot
        var liveText = _fromGame ? "LIVE · game feed" : "LIVE · screen";
        var liveW = g.MeasureString(liveText, fHead).Width;
        var pulse = (float)(0.55 + 0.45 * Math.Sin(Environment.TickCount64 / 350.0));
        using (var pb = new SolidBrush(Color.FromArgb((int)(255 * pulse), Live)))
            g.FillEllipse(pb, W - liveW - 52, 30, 14, 14);
        g.DrawString(liveText, fHead, live, W - liveW - 30, 27);

        int top = 120;

        // Big live view ------------------------------------------------------
        int bigW = (int)(W * 0.615), bigH = bigW * 9 / 16;
        var bigRect = new Rectangle(24, top, bigW, bigH);
        DrawShadowed(g, _latest, bigRect);
        g.DrawString("LIVE VIEW", fHead, amber, 24, top + bigH + 6);
        if (_latest is null)
            g.DrawString("warte auf ersten Frame …", fSub, dim, 24 + 40, top + bigH / 2);

        // Filmstrip position first, so the moments column can size itself to fit.
        int stripY = Math.Max(top + bigH + 46, H - 218);

        // Right column: ONE top moment + the session diary ---------------------
        int colX = 24 + bigW + 24;
        int colW = W - colX - 24;
        int tileW = colW;
        int tileH = tileW * 9 / 16;
        g.DrawString("★ TOP MOMENT", fHead, amber, colX, top - 22);
        if (_best.Count > 0)
        {
            var s = _best[0];
            var r = new Rectangle(colX, top, tileW, tileH);
            DrawShadowed(g, s.Medium, r);
            var off = s.At - _start;
            g.DrawString($"★ +{(int)off.TotalMinutes:00}:{off.Seconds:00}", fSmall, live, r.X, r.Bottom + 3);
        }
        else DrawShadowed(g, null, new Rectangle(colX, top, tileW, tileH));

        // SESSION-LOG — automatic diary of what you actually played.
        int logY = top + tileH + 46;
        g.DrawString("SESSION-LOG — automatisch erkannt", fHead, amber, colX, logY - 22);
        using (var panel = new SolidBrush(Color.FromArgb(22, 22, 28)))
            g.FillRectangle(panel, colX, logY, colW, stripY - logY - 34);
        var maxLines = Math.Max(1, (stripY - logY - 44) / 24);
        var lines = _log.TakeLast(maxLines).ToList();
        if (lines.Count == 0)
            g.DrawString("lauschen … (Events, Strecken, Rennen\nwerden hier automatisch eingetragen)", fSmall, dim, colX + 12, logY + 10);
        for (var i = 0; i < lines.Count; i++)
        {
            var (at, txt) = lines[i];
            g.DrawString($"+{(int)at.TotalMinutes:00}:{at.Seconds:00}", fSmall, grey, colX + 10, logY + 8 + i * 24);
            g.DrawString(txt, fSmall, white, colX + 72, logY + 8 + i * 24);
        }
        g.DrawString("FILMSTRIP — die letzten Minuten", fHead, grey, 24, stripY - 22);
        int fx = 24;
        foreach (var s in _film.TakeLast(6))
        {
            var r = new Rectangle(fx, stripY, 266, 150);
            DrawShadowed(g, s.Thumb, r, shadow: 4);
            var off = s.At - _start;
            g.DrawString($"+{(int)off.TotalMinutes:00}:{off.Seconds:00}", fSmall, dim, fx, stripY + 152);
            fx += 266 + 16;
        }

        // Footer / flash -----------------------------------------------------
        g.DrawString("läuft vollautomatisch — keine Eingaben nötig · Poster alle 2 min",
            fSmall, dim, 24, H - 28);
        g.DrawString($"Poster → {_posterDir}", fSmall, dim, W - 560, H - 28);
        if (DateTime.Now < _flashUntil)
        {
            var size = g.MeasureString(_flash, fTitle);
            g.DrawString(_flash, fTitle, live, (W - size.Width) / 2, H / 2 - 40);
        }
    }

    private static void DrawShadowed(Graphics g, Bitmap? bmp, Rectangle r, int shadow = 7)
    {
        using (var sh = new SolidBrush(Color.FromArgb(120, 0, 0, 0)))
            g.FillRectangle(sh, r.X + shadow, r.Y + shadow, r.Width, r.Height);
        if (bmp is null)
        {
            using var bg = new SolidBrush(Color.FromArgb(26, 26, 32));
            g.FillRectangle(bg, r);
        }
        else g.DrawImage(bmp, r);
        using var pen = new Pen(Color.FromArgb(60, 60, 68));
        g.DrawRectangle(pen, r);
    }

    // ------------------------------------------------------------------ poster

    private void SavePoster(string flash)
    {
        try
        {
            using var poster = RenderPoster();
            Directory.CreateDirectory(_posterDir);
            var stamp = _start.ToString("yyyyMMdd-HHmm");
            poster.Save(Path.Combine(_posterDir, $"dirt5-session-{stamp}.png"), ImageFormat.Png);
            poster.Save(Path.Combine(_posterDir, "dirt5-session-latest.png"), ImageFormat.Png);
            _flash = flash;
            _flashUntil = DateTime.Now.AddSeconds(3);
        }
        catch { /* poster is a bonus — never crash the wall */ }
    }

    private Bitmap RenderPoster()
    {
        const int W = 2560, H = 1440;
        var bmp = new Bitmap(W, H);
        using var g = Graphics.FromImage(bmp);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;
        g.Clear(Color.FromArgb(12, 12, 16));

        using var fTitle = new Font("Segoe UI Black", 40f, FontStyle.Bold);
        using var fSub = new Font("Segoe UI Semibold", 16f, FontStyle.Bold);
        using var fSmall = new Font("Segoe UI", 11f);
        using var amber = new SolidBrush(Accent);
        using var white = new SolidBrush(Color.White);
        using var grey = new SolidBrush(Color.FromArgb(150, 150, 158));
        using var live = new SolidBrush(Live);

        using (var bar = new SolidBrush(Accent)) g.FillRectangle(bar, 0, 0, W, 8);
        g.DrawString("DIRT 5 · COUCH SESSION", fTitle, amber, 40, 28);
        var dur = DateTime.Now - _start;
        var fahrzeit = TimeSpan.FromSeconds(_racingFrames * _capTimer.Interval / 1000.0);
        g.DrawString($"{_players.P1}  ×  {_players.P2}", fSub, white, 46, 96);
        g.DrawString(
            $"{_start:dd.MM.yyyy HH:mm} Uhr  ·  {(int)dur.TotalMinutes} min  ·  {_races} Rennen  ·  Fahrzeit {(int)fahrzeit.TotalMinutes} min  ·  {_shots} Shots",
            fSub, grey, 46, 128);

        // best 6 grid (3×2)
        int tw = 780, th = 439, gap = 40, x0 = 40, y0 = 190;
        var best = _best.OrderBy(b => b.At).ToList();
        for (var i = 0; i < Math.Min(6, best.Count); i++)
        {
            int cx = x0 + (i % 3) * (tw + gap), cy = y0 + (i / 3) * (th + 62);
            var r = new Rectangle(cx, cy, tw, th);
            DrawShadowed(g, best[i].Medium, r, shadow: 9);
            var off = best[i].At - _start;
            g.DrawString($"★ Moment +{(int)off.TotalMinutes:00}:{off.Seconds:00}", fSmall, live, cx, cy + th + 6);
        }

        // filmstrip bottom-left, session log bottom-right
        int fy = 1210, fx = 40;
        foreach (var s in _film.TakeLast(5))
        {
            g.DrawImage(s.Thumb, new Rectangle(fx, fy, 266, 150));
            fx += 266 + 14;
        }
        int lx = fx + 26;
        g.DrawString("SESSION-LOG", fSub, amber, lx, fy - 6);
        var logLines = _log.TakeLast(5).ToList();
        for (var i = 0; i < logLines.Count; i++)
        {
            var (at, txt) = logLines[i];
            g.DrawString($"+{(int)at.TotalMinutes:00}:{at.Seconds:00}  {txt}", fSmall, white, lx, fy + 26 + i * 24);
        }
        g.DrawString("created by DIRT 5 Companion — external mod, no game files touched",
            fSmall, grey, 40, H - 44);
        return bmp;
    }

    // ------------------------------------------------------------------ helpers

    /// <summary>High-quality resize; optional saturation boost to counter HDR wash-out.</summary>
    private static Bitmap Resize(Bitmap src, int w, int h, bool saturate)
    {
        var dst = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        using var g = Graphics.FromImage(dst);
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        var rect = new Rectangle(0, 0, w, h);
        if (!saturate)
        {
            g.DrawImage(src, rect, 0, 0, src.Width, src.Height, GraphicsUnit.Pixel);
            return dst;
        }
        const float s = 1.30f, lumR = 0.3086f, lumG = 0.6094f, lumB = 0.0820f;
        float a = (1 - s) * lumR, b = (1 - s) * lumG, c = (1 - s) * lumB;
        var cm = new ColorMatrix(new[]
        {
            new[] { a + s, a, a, 0f, 0f },
            new[] { b, b + s, b, 0f, 0f },
            new[] { c, c, c + s, 0f, 0f },
            new[] { 0f, 0f, 0f, 1f, 0f },
            new[] { -0.02f, -0.02f, -0.02f, 0f, 1f },   // slight contrast dip on brights
        });
        using var ia = new ImageAttributes();
        ia.SetColorMatrix(cm);
        g.DrawImage(src, rect, 0, 0, src.Width, src.Height, GraphicsUnit.Pixel, ia);
        return dst;
    }

    /// <summary>Cheap "action" score: colourfulness + luminance spread of a thumbnail.</summary>
    private static double ActionScore(Bitmap thumb)
    {
        double satSum = 0, lumSum = 0, lumSqSum = 0;
        int n = 0;
        for (var y = 0; y < thumb.Height; y += 4)
            for (var x = 0; x < thumb.Width; x += 4)
            {
                var p = thumb.GetPixel(x, y);
                int max = Math.Max(p.R, Math.Max(p.G, p.B)), min = Math.Min(p.R, Math.Min(p.G, p.B));
                double lum = 0.2126 * p.R + 0.7152 * p.G + 0.0722 * p.B;
                satSum += max == 0 ? 0 : (max - min) / (double)max;
                lumSum += lum; lumSqSum += lum * lum;
                n++;
            }
        if (n == 0) return 0;
        var meanSat = satSum / n;
        var meanLum = lumSum / n;
        var std = Math.Sqrt(Math.Max(0, lumSqSum / n - meanLum * meanLum));
        return meanSat * 0.65 + std / 128.0 * 0.35;
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        _capTimer.Dispose();
        _uiTimer.Dispose();
        _latest?.Dispose();
        foreach (var s in _film) s.Dispose();
        foreach (var s in _best) s.Dispose();
        base.OnFormClosed(e);
    }
}
