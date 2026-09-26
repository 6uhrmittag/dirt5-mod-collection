using Windows.Globalization;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;

namespace Dirt5.TrackCompanion;

public readonly record struct OcrWord(string Text, RectangleF Box);
public sealed record OcrOutput(string Text, IReadOnlyList<OcrWord> Words);

/// <summary>
/// Thin wrapper over Windows' built-in OCR (Windows.Media.Ocr) — offline, no external
/// dependency. Reads text (and word boxes) from a Bitmap.
/// </summary>
public sealed class Ocr
{
    private readonly OcrEngine _engine;

    public Ocr()
    {
        _engine = OcrEngine.TryCreateFromUserProfileLanguages()
                  ?? OcrEngine.TryCreateFromLanguage(new Language("en-US"))
                  ?? throw new InvalidOperationException(
                      "No OCR language pack available. Install an OCR language in Windows Settings.");
    }

    public string Language => _engine.RecognizerLanguage.DisplayName;

    public async Task<OcrOutput> ReadAsync(Bitmap bmp)
    {
        using var sw = await ScreenCapture.ToSoftwareBitmapAsync(bmp);
        // OCR requires Bgra8; convert if the decoder handed us something else.
        using var bgra = sw.BitmapPixelFormat == BitmapPixelFormat.Bgra8
            ? sw
            : SoftwareBitmap.Convert(sw, BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied);

        var result = await _engine.RecognizeAsync(bgra);
        var words = new List<OcrWord>();
        foreach (var line in result.Lines)
            foreach (var w in line.Words)
                words.Add(new OcrWord(w.Text,
                    new RectangleF((float)w.BoundingRect.X, (float)w.BoundingRect.Y,
                                   (float)w.BoundingRect.Width, (float)w.BoundingRect.Height)));
        return new OcrOutput(result.Text, words);
    }

    public static int MaxImageDimension => (int)OcrEngine.MaxImageDimension;
}
