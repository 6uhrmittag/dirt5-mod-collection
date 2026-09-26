using System.Text.Json;
using System.Text.Json.Serialization;

namespace Dirt5.TrackCompanion;

/// <summary>Stats for one (player, car, track) combination. Persisted as JSON.</summary>
public sealed class TrackStats
{
    public double? BestTimeSeconds { get; set; }
    public int Attempts { get; set; }   // races with this car on this track
    public int Wins { get; set; }
    public DateTime? LastPlayedUtc { get; set; }
    public string Notes { get; set; } = "";

    [JsonIgnore]
    public string BestTimeDisplay =>
        BestTimeSeconds is { } s
            ? TimeSpan.FromSeconds(s).ToString(s >= 3600 ? @"h\:mm\:ss\.fff" : @"m\:ss\.fff")
            : "—";
}

/// <summary>The two splitscreen players and their display names (in-game spellings).</summary>
public sealed class Players
{
    public string P1 { get; set; } = "Player 1";          // set yours: --set-player
    public string P2 { get; set; } = "Player 2";          // guest slot in splitscreen

    public string Name(string playerId) =>
        playerId.Equals("p1", StringComparison.OrdinalIgnoreCase) ? P1 : P2;

    public static string DefaultPath() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "Dirt5TrackCompanion", "players.json");

    public static Players Load(string? path = null)
    {
        path ??= DefaultPath();
        try
        {
            if (File.Exists(path))
                return JsonSerializer.Deserialize<Players>(File.ReadAllText(path)) ?? new Players();
        }
        catch { /* fall through */ }
        return new Players();
    }

    public void Save(string? path = null)
    {
        path ??= DefaultPath();
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, JsonSerializer.Serialize(this, new JsonSerializerOptions { WriteIndented = true }));
    }
}

/// <summary>
/// Per-player, per-(car,track) statistics for splitscreen play. Stored in %APPDATA%
/// — never in the game folder (external companion, no ban risk). Layout:
///   { "p1": { "carId|country/track": TrackStats, ... }, "p2": { ... } }
/// </summary>
public sealed class StatsStore
{
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    private readonly string _path;
    // playerId -> composite("carId|trackId") -> stats
    private readonly Dictionary<string, Dictionary<string, TrackStats>> _byPlayer;

    public StatsStore(string? pathOverride = null)
    {
        _path = pathOverride ?? DefaultPath();
        _byPlayer = Load(_path);
    }

    public static string DefaultPath() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "Dirt5TrackCompanion", "stats.json");

    private static string Key(string carId, string trackId) => $"{carId}|{trackId}";
    private static string NormPlayer(string playerId) => playerId.ToLowerInvariant();

    /// <summary>Stats for one player on one car+track (empty object if none yet).</summary>
    public TrackStats Get(string playerId, string carId, string trackId)
    {
        if (_byPlayer.TryGetValue(NormPlayer(playerId), out var m) &&
            m.TryGetValue(Key(carId, trackId), out var s))
            return s;
        return new TrackStats();
    }

    /// <summary>Combined race count across both players for a car+track ("how often *we* used it").</summary>
    public int TotalAttempts(string carId, string trackId)
    {
        var k = Key(carId, trackId);
        var n = 0;
        foreach (var m in _byPlayer.Values)
            if (m.TryGetValue(k, out var s)) n += s.Attempts;
        return n;
    }

    public void RecordRun(string playerId, string carId, string trackId, double? timeSeconds, bool won)
    {
        var pid = NormPlayer(playerId);
        if (!_byPlayer.TryGetValue(pid, out var m))
        {
            m = new Dictionary<string, TrackStats>();
            _byPlayer[pid] = m;
        }
        var k = Key(carId, trackId);
        if (!m.TryGetValue(k, out var s))
        {
            s = new TrackStats();
            m[k] = s;
        }
        s.Attempts++;
        if (won) s.Wins++;
        if (timeSeconds is { } t && (s.BestTimeSeconds is null || t < s.BestTimeSeconds))
            s.BestTimeSeconds = t;
        s.LastPlayedUtc = DateTime.UtcNow;
    }

    public void Save()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
        File.WriteAllText(_path, JsonSerializer.Serialize(_byPlayer, JsonOpts));
    }

    private static Dictionary<string, Dictionary<string, TrackStats>> Load(string path)
    {
        try
        {
            if (File.Exists(path))
                return JsonSerializer.Deserialize<Dictionary<string, Dictionary<string, TrackStats>>>(
                           File.ReadAllText(path)) ?? New();
        }
        catch { /* corrupt/old-format -> start fresh */ }
        return New();
    }

    private static Dictionary<string, Dictionary<string, TrackStats>> New() =>
        new(StringComparer.OrdinalIgnoreCase);
}
