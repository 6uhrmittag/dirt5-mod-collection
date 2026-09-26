using System.Globalization;

namespace Dirt5.TrackCompanion;

/// <summary>Shared slug -> display-name helper (used by track and car catalogs).</summary>
public static class Naming
{
    private static readonly TextInfo Ti = CultureInfo.InvariantCulture.TextInfo;

    // Words that should render upper-cased, not title-cased (marque / class acronyms).
    private static readonly HashSet<string> Upper = new(StringComparer.OrdinalIgnoreCase)
    {
        "gt", "gt4", "gtam", "rx", "eks", "dbx", "tt", "s1", "gtr", "rs", "sx",
        "ai", "v8", "4x4", "usa", "gg", "nc",
    };

    public static string Prettify(string slug)
    {
        var words = slug.Replace('_', ' ').Split(' ', StringSplitOptions.RemoveEmptyEntries);
        return string.Join(' ', words.Select(w =>
            Upper.Contains(w) ? w.ToUpperInvariant() : Ti.ToTitleCase(w.ToLowerInvariant())));
    }
}
