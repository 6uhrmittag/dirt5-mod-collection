namespace Dirt5.TrackCompanion;

public readonly record struct Match<T>(T Value, string Display, double Score);

/// <summary>
/// Matches noisy OCR text against a finite candidate list (the car roster / track
/// locations). Because the candidate set is small and fixed, fuzzy matching is very
/// reliable even when OCR mangles a few characters.
/// </summary>
public static class FuzzyMatch
{
    /// <summary>Best candidate for the OCR text, or null if below <paramref name="minScore"/>.</summary>
    public static Match<T>? Best<T>(string ocrText, IEnumerable<T> candidates,
        Func<T, string> nameOf, double minScore = 0.55)
    {
        var q = Normalize(ocrText);
        if (q.Length == 0) return null;

        return Best(ocrText, candidates, c => new[] { nameOf(c) }, minScore);
    }

    /// <summary>As <see cref="Best{T}(string,IEnumerable{T},Func{T,string},double)"/> but each
    /// candidate can offer several aliases; the best-scoring alias wins.</summary>
    public static Match<T>? Best<T>(string ocrText, IEnumerable<T> candidates,
        Func<T, IEnumerable<string>> namesOf, double minScore = 0.55)
    {
        var q = Normalize(ocrText);
        if (q.Length == 0) return null;

        Match<T>? best = null;
        foreach (var c in candidates)
        {
            double score = 0; var disp = "";
            foreach (var name in namesOf(c))
            {
                var s = Score(q, Normalize(name));
                if (s > score) { score = s; disp = name; }
            }
            if (best is null || score > best.Value.Score)
                best = new Match<T>(c, disp, score);
        }
        return best is { } b && b.Score >= minScore ? b : null;
    }

    /// <summary>Best match plus the runner-up score, for margin-based confidence checks.</summary>
    public static (Match<T>? Best, double SecondScore) Ranked<T>(string ocrText,
        IEnumerable<T> candidates, Func<T, string> nameOf)
    {
        var q = Normalize(ocrText);
        if (q.Length == 0) return (null, 0);

        Match<T>? best = null; double second = 0;
        foreach (var c in candidates)
        {
            var score = Score(q, Normalize(nameOf(c)));
            if (best is null || score > best.Value.Score)
            {
                second = best?.Score ?? 0;
                best = new Match<T>(c, nameOf(c), score);
            }
            else if (score > second) second = score;
        }
        return (best, second);
    }

    public static string Normalize(string s)
    {
        Span<char> buf = stackalloc char[s.Length];
        var n = 0;
        var prevSpace = false;
        foreach (var ch in s.ToLowerInvariant())
        {
            if (char.IsLetterOrDigit(ch)) { buf[n++] = ch; prevSpace = false; }
            else if (!prevSpace && n > 0) { buf[n++] = ' '; prevSpace = true; }
        }
        return new string(buf[..n]).Trim();
    }

    /// <summary>
    /// Combined score: token overlap (order-independent) blended with a whole-string
    /// Levenshtein ratio. Both are 0..1; the blend rewards "most words right" and
    /// "few characters off".
    /// </summary>
    public static double Score(string a, string b)
    {
        if (a == b) return 1.0;
        var lev = 1.0 - (double)Levenshtein(a, b) / Math.Max(a.Length, b.Length);

        var ta = a.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        var tb = b.Split(' ', StringSplitOptions.RemoveEmptyEntries).ToHashSet();
        var hit = ta.Count(t => tb.Contains(t));
        var overlap = tb.Count == 0 ? 0 : (double)hit / Math.Max(ta.Length, tb.Count);

        return 0.5 * lev + 0.5 * overlap;
    }

    public static int Levenshtein(string a, string b)
    {
        var d = new int[a.Length + 1, b.Length + 1];
        for (var i = 0; i <= a.Length; i++) d[i, 0] = i;
        for (var j = 0; j <= b.Length; j++) d[0, j] = j;
        for (var i = 1; i <= a.Length; i++)
            for (var j = 1; j <= b.Length; j++)
            {
                var cost = a[i - 1] == b[j - 1] ? 0 : 1;
                d[i, j] = Math.Min(Math.Min(d[i - 1, j] + 1, d[i, j - 1] + 1), d[i - 1, j - 1] + cost);
            }
        return d[a.Length, b.Length];
    }
}
