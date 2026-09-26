using System.Globalization;
using System.Text.RegularExpressions;

namespace Dirt5.TrackCompanion;

/// <summary>Parses lap/finish times out of noisy OCR text, e.g. "1:30.882", "90.88".</summary>
public static class LapTime
{
    // Optional H:, required M(:)?, S with fractional. Accept ' or : or . as separators.
    private static readonly Regex Rx = new(
        @"(?:(?<h>\d{1,2})[:'])?(?<m>\d{1,2})[:'](?<s>\d{1,2})[.,](?<f>\d{1,3})",
        RegexOptions.Compiled);
    // Fallback: bare seconds like "90.882".
    private static readonly Regex RxSec = new(@"(?<s>\d{1,3})[.,](?<f>\d{1,3})", RegexOptions.Compiled);

    public static double? TryParse(string ocr)
    {
        // OCR commonly confuses O/o->0, l/I->1, S->5 in numeric fields.
        var t = ocr.Replace('O', '0').Replace('o', '0').Replace('l', '1')
                   .Replace('I', '1').Replace('S', '5').Replace('B', '8');

        var m = Rx.Match(t);
        if (m.Success)
        {
            var h = m.Groups["h"].Success ? int.Parse(m.Groups["h"].Value) : 0;
            var min = int.Parse(m.Groups["m"].Value);
            var sec = int.Parse(m.Groups["s"].Value);
            var frac = double.Parse("0." + m.Groups["f"].Value, CultureInfo.InvariantCulture);
            var total = h * 3600 + min * 60 + sec + frac;
            return Plausible(total) ? total : null;
        }
        var ms = RxSec.Match(t);
        if (ms.Success)
        {
            var sec = int.Parse(ms.Groups["s"].Value);
            var frac = double.Parse("0." + ms.Groups["f"].Value, CultureInfo.InvariantCulture);
            var total = sec + frac;
            return Plausible(total) ? total : null;
        }
        return null;
    }

    // A single stage/lap in DIRT 5 is seconds..a few minutes; reject nonsense.
    private static bool Plausible(double seconds) => seconds is > 3 and < 3600;
}
