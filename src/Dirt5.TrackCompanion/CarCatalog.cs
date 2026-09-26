using System.Text.Json;

namespace Dirt5.TrackCompanion;

/// <summary>
/// A DIRT 5 car. <see cref="Stats"/> is the game's own car card (from
/// scripts/export_car_stats.py); null when that export hasn't been run yet.
/// </summary>
public sealed record Car(string Id, string Name)
{
    public CarStats? Stats { get; init; }
}

/// <summary>
/// The car card as the game stores it in data:event/vehicledata/vehicledata.json.
/// Performance/Handling are the grade letters of the in-game card (S, A, B, C).
/// </summary>
public sealed record CarStats(string? Name, string? Manufacturer, string? Performance, string? Handling,
    int? PowerBhp, int? TorqueNm, int? WeightKg, string? Drivetrain, string? CarClass)
{
    public bool HasAny => Performance is not null || Handling is not null || PowerBhp is not null;

    /// <summary>Grade letter as a 0..10 bar value (S = full bar, C = under a third).</summary>
    public static int? GradeValue(string? grade) => grade switch
    {
        "S" => 10, "A" => 7, "B" => 5, "C" => 3, _ => null,
    };
}

/// <summary>
/// The DIRT 5 car roster, enumerated from the game's asset index
/// (<see cref="CarExtractor"/>) and cached to %APPDATA% so startup is instant.
/// </summary>
public sealed class CarCatalog
{
    public IReadOnlyList<Car> Cars { get; }

    private CarCatalog(IReadOnlyList<Car> cars) => Cars = cars;

    public static string CachePath() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "Dirt5TrackCompanion", "cars.json");

    /// <summary>Written by scripts/export_car_stats.py (game data - stays on this PC).</summary>
    public static string StatsPath() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "Dirt5TrackCompanion", "carstats.json");

    private static Dictionary<string, CarStats> LoadStats()
    {
        try
        {
            var path = StatsPath();
            if (!File.Exists(path)) return new();
            var opts = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
            var map = JsonSerializer.Deserialize<Dictionary<string, CarStats>>(File.ReadAllText(path), opts) ?? new();
            return new Dictionary<string, CarStats>(map, StringComparer.OrdinalIgnoreCase);
        }
        catch { return new(); }
    }

    /// <summary>
    /// Build the roster. Prefers a live scan of <paramref name="scanPath"/> (game
    /// index/packs); falls back to the %APPDATA% cache; and if neither is available,
    /// a tiny curated seed so the overlay still shows real cars.
    /// </summary>
    public static CarCatalog Build(string? scanPath, bool useCache = true)
    {
        // 1) Live extraction from the game files.
        var ids = new List<string>();
        if (!string.IsNullOrWhiteSpace(scanPath) && (File.Exists(scanPath) || Directory.Exists(scanPath)))
            ids = CarExtractor.Extract(scanPath).ToList();

        // 2) Cache fallback / refresh.
        var cache = CachePath();
        if (ids.Count == 0 && useCache && File.Exists(cache))
        {
            try { ids = JsonSerializer.Deserialize<List<string>>(File.ReadAllText(cache)) ?? new(); }
            catch { /* ignore */ }
        }
        else if (ids.Count > 0 && useCache)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(cache)!);
                File.WriteAllText(cache, JsonSerializer.Serialize(ids));
            }
            catch { /* non-fatal */ }
        }

        // 3) Curated seed if we still have nothing.
        if (ids.Count == 0)
            ids = new() { "alfa_romeo_giulia_gtam", "baja_beetle", "ariel_nomad", "audi_s1_eks_rx_quattro" };

        var stats = LoadStats();
        var cars = ids
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Select(id => stats.TryGetValue(id, out var st)
                ? new Car(id, st.Name ?? Naming.Prettify(id)) { Stats = st }
                : new Car(id, Naming.Prettify(id)))
            .OrderBy(c => c.Name, StringComparer.OrdinalIgnoreCase)
            .ToList();
        return new CarCatalog(cars);
    }
}
