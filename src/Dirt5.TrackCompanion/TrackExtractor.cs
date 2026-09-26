using System.Text;
using System.Text.RegularExpressions;

namespace Dirt5.TrackCompanion;

/// <summary>
/// Extracts real DIRT 5 world/track identifiers from the game's readable .dat
/// packs by scanning for the engine's asset paths, e.g.
///   .../models/worlds/china/guilin_yulong...
///   .../environments/worlds/italy/carrara...
/// We stream the file in chunks (packs are up to 2 GB) with an overlap so paths
/// that straddle a chunk boundary are not missed.
/// </summary>
public static class TrackExtractor
{
    // worlds/<country>/<track>  — country is alphabetic, track is a slug.
    private static readonly Regex WorldPath = new(
        @"worlds/([a-z_]{3,20})/([a-z0-9][a-z0-9_]{2,40})",
        RegexOptions.Compiled);

    // Known DIRT 5 country/region slugs — used to reject shader-path noise like
    // "shaders/MayaDX11/worlds/track_array".
    private static readonly HashSet<string> KnownCountries = new(StringComparer.OrdinalIgnoreCase)
    {
        "china", "italy", "greece", "morocco", "nepal", "norway", "brazil",
        "usa", "cape_town", "arizona", "new_york",
    };

    // Slugs that are environment/technical, not real track names.
    private static readonly HashSet<string> NoiseTracks = new(StringComparer.OrdinalIgnoreCase)
    {
        "track", "track_a", "track_array", "terrain_array", "distant_trees",
        "river_alpha", "distant_terrain", "ice", "river", "beach", "beach_l",
    };

    /// <summary>Scan a file or directory; returns unique (country, trackId) pairs.</summary>
    public static IReadOnlyList<(string Country, string TrackId)> Extract(string path)
    {
        var found = new HashSet<(string, string)>();
        foreach (var file in EnumerateFiles(path))
        {
            try { ScanFile(file, found); }
            catch { /* unreadable pack — skip, best-effort */ }
        }
        return found
            .OrderBy(t => t.Item1, StringComparer.OrdinalIgnoreCase)
            .ThenBy(t => t.Item2, StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    private static IEnumerable<string> EnumerateFiles(string path)
    {
        if (Directory.Exists(path))
        {
            foreach (var f in Directory.EnumerateFiles(path))
                if (f.EndsWith(".dat", StringComparison.OrdinalIgnoreCase) ||
                    f.EndsWith(".bin", StringComparison.OrdinalIgnoreCase))
                    yield return f;
        }
        else if (File.Exists(path))
        {
            yield return path;
        }
    }

    private static void ScanFile(string file, HashSet<(string, string)> found)
    {
        const int chunk = 8 * 1024 * 1024;   // 8 MiB
        const int overlap = 256;             // longer than any path we match
        using var fs = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        var buffer = new byte[chunk + overlap];
        var carry = 0;
        int read;
        while ((read = fs.Read(buffer, carry, chunk)) > 0)
        {
            var total = carry + read;
            // Decode bytes as latin1 so every byte maps to a char; paths are ASCII.
            var text = Encoding.Latin1.GetString(buffer, 0, total);
            foreach (Match m in WorldPath.Matches(text))
            {
                var country = m.Groups[1].Value.ToLowerInvariant();
                var track = m.Groups[2].Value.ToLowerInvariant();
                if (!KnownCountries.Contains(country)) continue;
                if (NoiseTracks.Contains(track)) continue;
                found.Add((country, NormalizeTrack(track)));
            }
            // Carry the tail so a path split across chunks is still matched next round.
            carry = Math.Min(overlap, total);
            Array.Copy(buffer, total - carry, buffer, 0, carry);
        }
    }

    // Trailing layout/version tokens that mark route variants of the same location:
    // _lr (long route) _rr (rally) _nc (national circuit) _hr _or, _v1/_v2/_v1r,
    // _layers, _areaN, bare numbers. Collapse them so 17 "guilin_yulong_*" -> one.
    private static readonly Regex VariantToken = new(
        @"^(lr|rr|nc|hr|or|r|layers|v\d+r?|area\d+|\d+)$", RegexOptions.Compiled);

    /// <summary>Collapse a route slug to its base location (strip variant suffixes).</summary>
    private static string NormalizeTrack(string track)
    {
        var parts = track.Split('_', StringSplitOptions.RemoveEmptyEntries).ToList();
        while (parts.Count > 1 && VariantToken.IsMatch(parts[^1]))
            parts.RemoveAt(parts.Count - 1);
        return string.Join('_', parts);
    }
}
