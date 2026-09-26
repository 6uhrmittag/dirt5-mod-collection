// Dirt5.SaveInspector — READ-ONLY catalog of DIRT 5's Xbox save data (WGS format).
//
// DIRT 5 (Microsoft Store) stores saves via Xbox "connected storage" / WGS under
//   %LOCALAPPDATA%\Packages\CodemastersSoftwareCompan.DiRT5_...\SystemAppData\wgs\
// as: containers.index  +  per-container folders each with container.NNN manifests
// that map friendly blob names -> on-disk GUID blob files.
//
// This tool ONLY READS. It never writes, moves, or deletes anything under wgs — a
// corrupt save is unrecoverable and could also trip Xbox integrity. It exists to
// scout whether best-times / ghosts could later be auto-read per player.
//
// Usage: Dirt5.SaveInspector [--wgs <path>] [--report <file.md>]

using System.Text;

string? wgsOverride = null, reportPath = null;
for (var i = 0; i < args.Length; i++)
{
    if (args[i] == "--wgs" && i + 1 < args.Length) wgsOverride = args[++i];
    else if (args[i] == "--report" && i + 1 < args.Length) reportPath = args[++i];
}

var wgs = wgsOverride ?? DefaultWgsPath();
var sb = new StringBuilder();
void Line(string s = "") { Console.WriteLine(s); sb.AppendLine(s); }

Line("## DIRT 5 save inspector (WGS, read-only)");
if (wgs is null || !Directory.Exists(wgs))
{
    Line($"- WGS folder not found: {wgs ?? "(package data dir missing)"}");
    return 1;
}
Line($"- WGS root: `{wgs}`");

// --- containers.index (lenient string/GUID harvest) -------------------------
var indexPath = Directory.EnumerateFiles(wgs, "containers.index", SearchOption.AllDirectories).FirstOrDefault();
if (indexPath is not null)
{
    var bytes = ReadAll(indexPath);
    var version = BitConverter.ToUInt32(bytes, 0);
    var count = BitConverter.ToUInt32(bytes, 4);
    Line($"- containers.index: version={version}, container-count={count}");
    var strings = HarvestUtf16(bytes, minLen: 3).Distinct().Take(12).ToList();
    Line("  strings: " + string.Join(" · ", strings));
}
else Line("- no containers.index found");

// --- per-container manifests (exact parse) ----------------------------------
long totalBytes = 0; int totalBlobs = 0;
// Structure is wgs/<account>/<containerGUID>/container.NNN — find manifests at any
// depth, then keep the highest generation per container folder.
var manifests = Directory.EnumerateFiles(wgs, "container.*", SearchOption.AllDirectories)
    .Where(f => ParseGen(f) >= 0)
    .GroupBy(f => Path.GetDirectoryName(f)!)
    .Select(grp => grp.OrderByDescending(ParseGen).First());
foreach (var manifest in manifests)
{
    var dir = Path.GetDirectoryName(manifest)!;
    var blobs = ParseContainer(ReadAll(manifest));
    Line($"\n### container `{Path.GetFileName(dir)}`  (manifest {Path.GetFileName(manifest)}, {blobs.Count} blobs)");
    foreach (var (name, guid) in blobs)
    {
        var blobFile = Path.Combine(dir, guid);
        long size = File.Exists(blobFile) ? new FileInfo(blobFile).Length : -1;
        if (size >= 0) { totalBytes += size; totalBlobs++; }
        Line($"    {name,-46} {guid}  {(size >= 0 ? $"{size,10:N0} B" : "MISSING")}");
    }
}
Line($"\n- totals: {totalBlobs} blobs, {totalBytes:N0} bytes");
Line("- NOTE: read-only inspection; nothing under wgs was modified.");
Line("- Ghost blobs (`ghosts/...`) are per-track lap data — a future path to auto-read");
Line("  best times per player. Decoding blob *contents* is out of scope for now.");

if (reportPath is not null)
{
    File.AppendAllText(reportPath, "\n---\n\n" + sb + "\n");
    Console.WriteLine($"[appended to {reportPath}]");
}
return 0;

// ---------------------------------------------------------------------------
static string? DefaultWgsPath()
{
    var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
    var pkg = Path.Combine(local, "Packages", "CodemastersSoftwareCompan.DiRT5_4cfye3zbe1gaw",
                           "SystemAppData", "wgs");
    return Directory.Exists(pkg) ? pkg : null;
}

// Always open read-only, sharing so we never lock the game's own file handles.
static byte[] ReadAll(string path)
{
    using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
    var buf = new byte[fs.Length];
    var read = 0;
    while (read < buf.Length)
    {
        var got = fs.Read(buf, read, buf.Length - read);
        if (got == 0) break;
        read += got;
    }
    return buf;
}

static int ParseGen(string path)
{
    var ext = Path.GetExtension(path).TrimStart('.');
    return int.TryParse(ext, out var n) ? n : -1;
}

// container.NNN: u32 version, u32 blobCount, then blobCount ×
//   { UTF-16 name padded to 128 bytes; GUID(16); GUID(16) }   (160 bytes each)
static List<(string Name, string Guid)> ParseContainer(byte[] b)
{
    var result = new List<(string, string)>();
    if (b.Length < 8) return result;
    var count = BitConverter.ToUInt32(b, 4);
    var pos = 8;
    const int nameLen = 128, rec = 128 + 16 + 16;
    for (var i = 0; i < count && pos + rec <= b.Length; i++, pos += rec)
    {
        var name = Encoding.Unicode.GetString(b, pos, nameLen).TrimEnd('\0');
        var guidBytes = new byte[16];
        Array.Copy(b, pos + nameLen, guidBytes, 0, 16);           // first GUID = on-disk file
        var guid = new Guid(guidBytes).ToString("N").ToUpperInvariant();
        result.Add((name, guid));
    }
    return result;
}

static IEnumerable<string> HarvestUtf16(byte[] b, int minLen)
{
    var cur = new StringBuilder();
    for (var i = 0; i + 1 < b.Length; i += 2)
    {
        var ch = (char)(b[i] | (b[i + 1] << 8));
        if (ch >= ' ' && ch < 0x7f) cur.Append(ch);
        else { if (cur.Length >= minLen) yield return cur.ToString(); cur.Clear(); }
    }
    if (cur.Length >= minLen) yield return cur.ToString();
}
