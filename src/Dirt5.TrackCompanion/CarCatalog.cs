using System.Text.Json;

namespace Dirt5.TrackCompanion;

/// <summary>
/// A DIRT 5 car. <see cref="Stats"/> holds the game's card ratings when we manage
/// to extract them (stretch); until then they are null and shown as placeholders.
/// </summary>
public sealed record Car(string Id, string Name)
{
    public CarStats? Stats { get; init; }
}

/// <summary>DIRT 5 car-card ratings (0..10). Null = not yet extracted.</summary>
public sealed record CarStats(int? Speed, int? Acceleration, int? Handling, int? Toughness)
{
    public bool HasAny => Speed is not null || Acceleration is not null ||
                          Handling is not null || Toughness is not null;
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

        var cars = ids
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Select(id => new Car(id, Naming.Prettify(id)))
            .OrderBy(c => c.Name, StringComparer.OrdinalIgnoreCase)
            .ToList();
        return new CarCatalog(cars);
    }
}
