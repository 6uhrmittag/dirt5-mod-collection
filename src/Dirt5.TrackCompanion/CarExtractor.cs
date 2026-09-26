using System.Text;
using System.Text.RegularExpressions;

namespace Dirt5.TrackCompanion;

/// <summary>
/// Extracts the real DIRT 5 car roster from the game's plaintext asset index
/// (dat.ndx) / packs by scanning for vehicle model paths, e.g.
///   data:ao/models/vehicles/alfa_romeo_giulia_gtam/...
/// The segment right after "models/vehicles/" is the car id.
/// </summary>
public static class CarExtractor
{
    // "models/vehicles/<id>/" — id is a slug. Anchored on "models/vehicles/" so we
    // ignore "models/objects/vehicles/" props like mining_truck.
    private static readonly Regex CarPath = new(
        @"models/vehicles/([a-z0-9][a-z0-9_]{2,50})/",
        RegexOptions.Compiled);

    // Dev/placeholder/non-player ids to drop.
    private static readonly string[] NoisePrefixes = { "blockout_", "test_", "dev_", "template_" };
    private static readonly HashSet<string> NoiseExact = new(StringComparer.OrdinalIgnoreCase)
    {
        "generic", "default", "shared", "common",
    };

    public static IReadOnlyList<string> Extract(string path)
    {
        var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var file in EnumerateFiles(path))
        {
            try { ScanFile(file, ids); }
            catch { /* unreadable — best effort */ }
        }
        return ids.OrderBy(x => x, StringComparer.OrdinalIgnoreCase).ToList();
    }

    private static IEnumerable<string> EnumerateFiles(string path)
    {
        if (Directory.Exists(path))
        {
            foreach (var f in Directory.EnumerateFiles(path))
                if (f.EndsWith(".ndx", StringComparison.OrdinalIgnoreCase) ||
                    f.EndsWith(".dat", StringComparison.OrdinalIgnoreCase) ||
                    f.EndsWith(".bin", StringComparison.OrdinalIgnoreCase))
                    yield return f;
        }
        else if (File.Exists(path))
        {
            yield return path;
        }
    }

    private static void ScanFile(string file, HashSet<string> ids)
    {
        const int chunk = 8 * 1024 * 1024;
        const int overlap = 128;
        using var fs = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        var buffer = new byte[chunk + overlap];
        var carry = 0;
        int read;
        while ((read = fs.Read(buffer, carry, chunk)) > 0)
        {
            var total = carry + read;
            var text = Encoding.Latin1.GetString(buffer, 0, total);
            foreach (Match m in CarPath.Matches(text))
            {
                var id = m.Groups[1].Value.ToLowerInvariant();
                if (IsNoise(id)) continue;
                ids.Add(id);
            }
            carry = Math.Min(overlap, total);
            Array.Copy(buffer, total - carry, buffer, 0, carry);
        }
    }

    private static bool IsNoise(string id)
    {
        if (NoiseExact.Contains(id)) return true;
        if (id.EndsWith("_test", StringComparison.Ordinal) ||
            id.EndsWith("_blockout", StringComparison.Ordinal)) return true;
        foreach (var p in NoisePrefixes)
            if (id.StartsWith(p, StringComparison.Ordinal)) return true;
        // Ids that are just a body-part token, not a car.
        if (id is "chassis" or "wheel" or "wheels" or "interior" or "driver") return true;
        return false;
    }
}
