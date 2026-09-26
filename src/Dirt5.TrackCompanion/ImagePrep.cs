using System.Drawing.Drawing2D;
using System.Drawing.Imaging;

namespace Dirt5.TrackCompanion;

/// <summary>
/// Image preprocessing to make DIRT 5's stylised UI text OCR-friendlier.
/// The car-name bar is white text on a light-cyan strip — very low contrast for OCR.
/// Cyan has low red, white has high red, so mapping (1 - red) to all channels turns it
/// into near-black text on a light background. We also upscale, which OCR prefers.
/// </summary>
public static class ImagePrep
{
    // Per channel: out = 1 - inputRed  → white(text)→0, cyan(bg)→light.
    private static readonly ColorMatrix RedInvert = new(new[]
    {
        new float[] { -1, -1, -1, 0, 0 },
        new float[] {  0,  0,  0, 0, 0 },
        new float[] {  0,  0,  0, 0, 0 },
        new float[] {  0,  0,  0, 1, 0 },
        new float[] {  1,  1,  1, 0, 1 },
    });

    public static Bitmap RedInvertUpscale(Bitmap src, int scale = 4)
        => Draw(src, scale, RedInvert);

    public static Bitmap Upscale(Bitmap src, int scale = 4)
        => Draw(src, scale, null);

    private static Bitmap Draw(Bitmap src, int scale, ColorMatrix? cm)
    {
        var dst = new Bitmap(src.Width * scale, src.Height * scale, PixelFormat.Format32bppArgb);
        using var g = Graphics.FromImage(dst);
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        var rect = new Rectangle(0, 0, dst.Width, dst.Height);
        if (cm is null)
        {
            g.DrawImage(src, rect, 0, 0, src.Width, src.Height, GraphicsUnit.Pixel);
        }
        else
        {
            using var ia = new ImageAttributes();
            ia.SetColorMatrix(cm);
            g.DrawImage(src, rect, 0, 0, src.Width, src.Height, GraphicsUnit.Pixel, ia);
        }
        return dst;
    }
}
