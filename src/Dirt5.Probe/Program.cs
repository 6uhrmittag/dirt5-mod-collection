// Dirt5.Probe — the project's "hello world" that proves the toolchain works.
//
// Two things happen here:
//   1. NATIVE PROBE  — we read the DIRT 5 EGO/EVO container ourselves (reversed
//      FourCC tag + u32 length) and enumerate the top-level tags. This is the
//      real, working read of a game archive from a compiled C# tool.
//   2. NEFSLIB PROBE — we point the EGO community's NefsLib at the same file to
//      empirically confirm whether it understands DIRT 5's container. We expect a
//      rejection (DIRT 5 packs are NOT "NefS" magic), and we capture the exact
//      failure. A clean, documented failure is a valid result for this RE project.
//
// Usage:
//   Dirt5.Probe <path-to-sample.dat|.head.bin> [--tags N]

using System.IO.Abstractions;
using VictorBush.Ego.NefsLib.IO;
using VictorBush.Ego.NefsLib.Progress;

int maxTags = 24;
string? samplePath = null;
for (var i = 0; i < args.Length; i++)
{
    if (args[i] == "--tags" && i + 1 < args.Length && int.TryParse(args[i + 1], out var n)) { maxTags = n; i++; }
    else samplePath = args[i];
}

if (samplePath is null)
{
    // Default to the ARC header sample if present (relative to repo root when run
    // from the solution dir).
    var guess = Path.Combine("samples", "5_DISC_ARC.head.bin");
    samplePath = File.Exists(guess) ? guess : null;
}

if (samplePath is null || !File.Exists(samplePath))
{
    Console.Error.WriteLine("usage: Dirt5.Probe <sample.dat|.head.bin> [--tags N]");
    Console.Error.WriteLine("  (or place samples/5_DISC_ARC.head.bin and run with no args)");
    return 2;
}

Console.WriteLine($"== DIRT 5 probe ==");
Console.WriteLine($"sample: {Path.GetFullPath(samplePath)}");
Console.WriteLine();

NativeProbe(samplePath, maxTags);
Console.WriteLine();
await NefsLibProbeAsync(samplePath);
return 0;

// ---------------------------------------------------------------------------
// 1. Native EGO/EVO chunk-header reader
// ---------------------------------------------------------------------------
static void NativeProbe(string path, int maxTags)
{
    const int window = 1 * 1024 * 1024; // 1 MiB header window
    byte[] data;
    using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
    {
        var take = (int)Math.Min(window, fs.Length);
        data = new byte[take];
        var read = 0;
        while (read < take)
        {
            var got = fs.Read(data, read, take - read);
            if (got == 0) break;
            read += got;
        }
    }

    Console.WriteLine("-- native EGO/EVO probe --");
    Console.WriteLine($"read {data.Length:N0} bytes, entropy {Entropy(data):0.000} bits/byte");

    // Container tags are stored byte-reversed; enumerate printable 4-byte runs.
    var tags = new List<(int off, string rev, uint len)>();
    var seen = new HashSet<string>();
    for (var i = 0; i + 8 <= data.Length && tags.Count < maxTags; )
    {
        if (IsTag(data, i))
        {
            var rev = new string(new[] { (char)data[i + 3], (char)data[i + 2], (char)data[i + 1], (char)data[i] });
            var len = BitConverter.ToUInt32(data, i + 4);
            if (seen.Add(rev)) tags.Add((i, rev, len));
            i += 4;
        }
        else i++;
    }

    var hasMaster = tags.Any(t => t.rev is "MHDR" or "MAST");
    Console.WriteLine($"container: {(hasMaster ? "EGO/EVO chunk container (MHDR/MAST present) — RECOGNIZED" : "no MHDR/MAST anchor found in window")}");
    Console.WriteLine("top tags (reversed->readable):");
    foreach (var (off, rev, len) in tags)
        Console.WriteLine($"    0x{off:X6}  {rev,-4}  next-u32={len:N0}");
}

static bool IsTag(byte[] d, int i)
{
    for (var k = 0; k < 4; k++)
    {
        var c = d[i + k];
        var ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                 (c >= '0' && c <= '9') || c == ' ' || c == '_' || c == '-' ||
                 c == '/' || c == '.';
        if (!ok) return false;
    }
    return true;
}

static double Entropy(byte[] d)
{
    if (d.Length == 0) return 0;
    var counts = new int[256];
    foreach (var b in d) counts[b]++;
    double e = 0;
    foreach (var c in counts)
        if (c > 0) { var p = (double)c / d.Length; e -= p * Math.Log2(p); }
    return e;
}

// ---------------------------------------------------------------------------
// 2. NefsLib empirical probe
// ---------------------------------------------------------------------------
static async Task NefsLibProbeAsync(string path)
{
    Console.WriteLine("-- NefsLib probe (EGO community lib) --");
    try
    {
        var reader = new NefsReader(new FileSystem());
        var archive = await reader.ReadArchiveAsync(Path.GetFullPath(path), new NefsProgress());
        Console.WriteLine($"NefsLib OPENED it: {archive.Items.Count} item(s). (unexpected — investigate!)");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"NefsLib REJECTED it: {ex.GetType().Name}: {ex.Message}");
        Console.WriteLine("=> Expected. DIRT 5 packs are a custom EGO/EVO chunk container, not a");
        Console.WriteLine("   'NefS'-magic archive. Extraction needs a custom parser (native probe above)");
        Console.WriteLine("   or a QuickBMS comtype scan for the compressed FPX/INIT packs.");
    }
}
