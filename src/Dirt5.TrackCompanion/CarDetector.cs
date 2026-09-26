namespace Dirt5.TrackCompanion;

/// <summary>
/// Identifies the selected car from OCR of the brand wordmark + the (stylised, hard-to-
/// OCR) car-name bar. Because the brush font is unreliable, this is deliberately
/// CONSERVATIVE: it only returns a car when confident, so it never auto-logs the wrong
/// one. Two confident paths:
///   1. Brand wordmark OCRs cleanly (e.g. "BENTLEY") AND that brand has exactly one car.
///   2. The brand+name text matches a single car with a clear margin over the runner-up.
/// Otherwise it returns null and the overlay keeps the manual selection.
/// </summary>
public sealed class CarDetector
{
    private readonly IReadOnlyList<Car> _cars;
    private readonly Dictionary<string, List<Car>> _byBrand;

    public CarDetector(IReadOnlyList<Car> cars)
    {
        _cars = cars;
        _byBrand = cars
            .GroupBy(c => Brand(c.Name), StringComparer.OrdinalIgnoreCase)
            .ToDictionary(g => g.Key, g => g.ToList(), StringComparer.OrdinalIgnoreCase);
    }

    private static string Brand(string name) => name.Split(' ', 2)[0];

    /// <summary>Confident car for this player's brand+name OCR, or null.</summary>
    public Match<Car>? Detect(string brandText, string nameText)
    {
        // Path 1 — clean brand wordmark that uniquely identifies a car.
        var brand = FuzzyMatch.Best(brandText, _byBrand.Keys, b => b, minScore: 0.75);
        if (brand is { } bm && _byBrand[bm.Value].Count == 1)
            return new Match<Car>(_byBrand[bm.Value][0], _byBrand[bm.Value][0].Name, 0.95);

        // Path 2 — brand+name text with a decisive margin over the second-best car.
        var combined = $"{brandText} {nameText}".Trim();
        var (best, second) = FuzzyMatch.Ranked(combined, _cars, c => c.Name);
        if (best is { } b && b.Score >= 0.35 && b.Score - second >= 0.12)
            return b;

        // If a brand was recognised, restrict to that brand and retry the name only.
        if (brand is { } bm2)
        {
            var (b2, s2) = FuzzyMatch.Ranked(nameText, _byBrand[bm2.Value], c => c.Name);
            if (b2 is { } bb && bb.Score >= 0.30 && bb.Score - s2 >= 0.10)
                return bb;
        }
        return null;
    }
}
