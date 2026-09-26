using System.Globalization;

namespace Dirt5.TrackCompanion;

public sealed record Track(string Id, string Name, string Region, string Environment);

/// <summary>
/// The list of DIRT 5 maps the overlay shows. It is grounded in real data:
/// a curated baseline of the game's actual locations, merged with track ids
/// extracted live from the game's .dat packs (<see cref="TrackExtractor"/>).
/// </summary>
public sealed class TrackCatalog
{
    // Curated real DIRT 5 regions (country slug -> display + typical environment).
    private static readonly Dictionary<string, (string Region, string Env)> Regions = new(StringComparer.OrdinalIgnoreCase)
    {
        ["china"]     = ("China", "Urban / River"),
        ["italy"]     = ("Italy", "Marble Quarry"),
        ["greece"]    = ("Greece", "Coastal Cliffs"),
        ["morocco"]   = ("Morocco", "Desert"),
        ["nepal"]     = ("Nepal", "Ice / Mountain"),
        ["norway"]    = ("Norway", "Snow / Forest"),
        ["brazil"]    = ("Brazil", "Favela / Rio"),
        ["usa"]       = ("USA", "Mixed"),
        ["arizona"]   = ("USA — Arizona", "Red Rock Desert"),
        ["new_york"]  = ("USA — New York", "Ice / City"),
        ["cape_town"] = ("South Africa — Cape Town", "Coastal"),
    };

    // Friendly names for track ids we recognise; others are prettified from the slug.
    private static readonly Dictionary<string, string> FriendlyTrack = new(StringComparer.OrdinalIgnoreCase)
    {
        ["guilin_yulong"] = "Guilin — Yulong River",
        ["carrara"]       = "Carrara Marble Mountains",
    };

    public IReadOnlyList<Track> Tracks { get; }

    private TrackCatalog(IReadOnlyList<Track> tracks) => Tracks = tracks;

    /// <summary>
    /// Build the catalog. If <paramref name="scanPath"/> is a real game install /
    /// samples dir, extracted track ids are merged in; otherwise the curated
    /// baseline is used so the overlay always shows the correct real locations.
    /// </summary>
    public static TrackCatalog Build(string? scanPath)
    {
        var byId = new Dictionary<string, Track>(StringComparer.OrdinalIgnoreCase);

        void Add(string country, string trackId)
        {
            var (region, env) = Regions.TryGetValue(country, out var r)
                ? r : (Prettify(country), "—");
            var name = FriendlyTrack.TryGetValue(trackId, out var f) ? f : Prettify(trackId);
            var id = $"{country}/{trackId}";
            byId[id] = new Track(id, name, region, env);
        }

        // Curated baseline — the real DIRT 5 locations (confirmed against the game's
        // own asset paths where possible: guilin_yulong, carrara, meteora, cape_town…).
        Add("china", "guilin_yulong");
        Add("china", "shanghai");
        Add("italy", "carrara");
        Add("greece", "meteora");
        Add("morocco", "desert");
        Add("nepal", "himalaya");
        Add("norway", "fjord");
        Add("brazil", "rio");
        Add("arizona", "red_rock");
        Add("new_york", "roosevelt");
        Add("cape_town", "waterfront");

        // Merge in whatever we can extract from the real game files.
        if (!string.IsNullOrWhiteSpace(scanPath) && (File.Exists(scanPath) || Directory.Exists(scanPath)))
        {
            foreach (var (country, trackId) in TrackExtractor.Extract(scanPath))
                Add(country, trackId);
        }

        var tracks = byId.Values
            .OrderBy(t => t.Region, StringComparer.OrdinalIgnoreCase)
            .ThenBy(t => t.Name, StringComparer.OrdinalIgnoreCase)
            .ToList();
        return new TrackCatalog(tracks);
    }

    private static string Prettify(string slug) => Naming.Prettify(slug);
}
