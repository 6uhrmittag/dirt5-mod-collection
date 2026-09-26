param([Parameter(ValueFromRemainingArguments=$true)][string[]]$A)

$Dir       = if ($env:DIRT5_HUNT_DIR) { $env:DIRT5_HUNT_DIR } else { Join-Path $env:TEMP 'dirt5-memhunt' }
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$CandFile  = Join-Path $Dir "hunt_cands.bin"
$SampFile  = Join-Path $Dir "hunt_samples.bin"
$ShotDir   = Join-Path $Dir "hunt_shots"
New-Item -ItemType Directory -Force -Path $ShotDir | Out-Null

$src = @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

public static class Hunt {
    [StructLayout(LayoutKind.Sequential)]
    struct MBI { public IntPtr BaseAddress; public IntPtr AllocationBase; public uint AllocationProtect; public uint pad1; public IntPtr RegionSize; public uint State; public uint Protect; public uint Type; public uint pad2; }
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint a, bool i, int p);
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr VirtualQueryEx(IntPtr h, IntPtr a, out MBI m, IntPtr l);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr s, out IntPtr r);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool WriteProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr s, out IntPtr r);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr h);

    const uint MEM_COMMIT=0x1000, PAGE_GUARD=0x100, QUERY=0x0400, VM_READ=0x0010, VM_WRITE=0x0020, VM_OP=0x0008;
    static bool Writable(uint p){ if((p & PAGE_GUARD)!=0) return false; uint b=p & 0xFF; return b==0x04||b==0x40; }
    static IntPtr Open(int pid, bool w){ uint acc=QUERY|VM_READ|(w?(VM_WRITE|VM_OP):0); return OpenProcess(acc,false,pid); }

    static List<long[]> Regions(IntPtr h){ var l=new List<long[]>(); IntPtr sz=(IntPtr)Marshal.SizeOf(typeof(MBI)); long a=0,max=0x7FFFFFFFFFFF;
        while(a<max){ MBI m; if(VirtualQueryEx(h,(IntPtr)a,out m,sz)==IntPtr.Zero) break; long rs=(long)m.RegionSize; if(rs<=0) break;
            if(m.State==MEM_COMMIT && Writable(m.Protect)) l.Add(new long[]{(long)m.BaseAddress,rs}); a+=rs; } return l; }

    static float[] BulkRead(IntPtr h, long[] addrs){
        int N=addrs.Length; float[] res=new float[N];
        for(int i=0;i<N;){
            long start=addrs[i]; int j=i; long spanEnd=start+4;
            while(j+1<N){ long ne=addrs[j+1]+4; if(addrs[j+1]-spanEnd<65536 && (ne-start)<=64L*1024*1024){ j++; spanEnd=ne; } else break; }
            long len=spanEnd-start; byte[] buf=new byte[len]; IntPtr rd;
            long got = ReadProcessMemory(h,(IntPtr)start,buf,(IntPtr)len,out rd) ? (long)rd : 0;
            for(int k=i;k<=j;k++){ long off=addrs[k]-start; res[k]=(off+4<=got)?BitConverter.ToSingle(buf,(int)off):float.NaN; }
            i=j+1;
        }
        return res;
    }

    static void SaveCand(string f, List<long> a){ using(var bw=new BinaryWriter(File.Open(f,FileMode.Create))){ bw.Write(a.Count); foreach(var x in a) bw.Write(x); } }
    static long[] LoadCand(string f){ using(var br=new BinaryReader(File.Open(f,FileMode.Open))){ int n=br.ReadInt32(); long[] a=new long[n]; for(int i=0;i<n;i++) a[i]=br.ReadInt64(); return a; } }

    public static string DiffSeed(int pid, string candFile, double min, double max, int sleepMs){
        IntPtr h=Open(pid,false); if(h==IntPtr.Zero) return "OpenProcess failed err="+Marshal.GetLastWin32Error();
        var regs=Regions(h);
        var addrsA=new List<long>(); var valsA=new List<float>();
        int chunk=4*1024*1024; byte[] buf=new byte[chunk]; float fmin=(float)min,fmax=(float)max; long cap=20000000; bool capped=false;
        foreach(var reg in regs){ long baseA=reg[0],size=reg[1],off=0;
            while(off<size){ int want=(int)Math.Min(chunk,size-off); IntPtr rd;
                if(ReadProcessMemory(h,(IntPtr)(baseA+off),buf,(IntPtr)want,out rd) && (long)rd>=4){
                    int nf=(int)rd/4; var span=MemoryMarshal.Cast<byte,float>(new ReadOnlySpan<byte>(buf,0,nf*4));
                    for(int i=0;i<nf;i++){ float f=span[i]; if(f>=fmin && f<=fmax){ addrsA.Add(baseA+off+(long)i*4); valsA.Add(f); if(addrsA.Count>=cap){capped=true;break;} } }
                }
                if(capped) break; off+=want;
            } if(capped) break;
        }
        Thread.Sleep(sleepMs);
        float[] cur=BulkRead(h, addrsA.ToArray());
        var cand=new List<long>();
        for(int k=0;k<cur.Length;k++){ float c=cur[k]; if(!float.IsNaN(c) && c>=fmin && c<=fmax && c!=valsA[k]) cand.Add(addrsA[k]); }
        CloseHandle(h); SaveCand(candFile, cand);
        return "DiffSeed band=["+min+","+max+"] plausible="+addrsA.Count+(capped?"(CAPPED)":"")+"  changed-> "+cand.Count+" candidates";
    }

    public static string Sample(int pid, string candFile, string sampFile){
        long[] a=LoadCand(candFile); IntPtr h=Open(pid,false); if(h==IntPtr.Zero) return "OpenProcess failed";
        float[] cur=BulkRead(h,a); CloseHandle(h);
        using(var fs=new FileStream(sampFile,FileMode.Append)) using(var bw=new BinaryWriter(fs)){ foreach(var v in cur) bw.Write(v); }
        long ns = new FileInfo(sampFile).Length / ((long)a.Length*4);
        return "sample #"+ns+" appended  ("+a.Length+" candidates)";
    }

    public static string Correlate(string candFile, string sampFile, double[] labels){
        long[] a=LoadCand(candFile); int N=a.Length;
        byte[] all=File.ReadAllBytes(sampFile); int S=(int)(all.Length/((long)N*4));
        if(S!=labels.Length) return "label count "+labels.Length+" != sample count "+S;
        int usedTot=0; for(int s=0;s<S;s++) if(labels[s]>=0) usedTot++;
        var errs=new double[N]; var hyp=new byte[N];
        for(int j=0;j<N;j++){ double ek=0,em=0; int used=0;
            for(int s=0;s<S;s++){ if(labels[s]<0) continue; float v=BitConverter.ToSingle(all,((s*N)+j)*4); if(float.IsNaN(v)){errs[j]=1e9;used=0;break;} ek+=Math.Abs(v-labels[s]); em+=Math.Abs(v*3.6-labels[s]); used++; }
            if(used==0){ errs[j]=1e9; hyp[j]=0; continue; }
            ek/=used; em/=used; if(ek<=em){errs[j]=ek;hyp[j]=0;} else {errs[j]=em;hyp[j]=1;} }
        int[] idx=new int[N]; for(int j=0;j<N;j++) idx[j]=j; Array.Sort(idx,(x,y)=>errs[x].CompareTo(errs[y]));
        var sb=new StringBuilder(); sb.AppendLine("labels(km/h): "+string.Join(",",labels)); sb.AppendLine("top candidates (low mean-error = tracks speed):");
        int top=Math.Min(20,N);
        for(int t=0;t<top;t++){ int j=idx[t]; var vals=new double[S]; for(int s=0;s<S;s++) vals[s]=BitConverter.ToSingle(all,((s*N)+j)*4);
            sb.AppendLine("0x"+a[j].ToString("X")+"  err="+errs[j].ToString("F2")+"  unit="+(hyp[j]==0?"km/h":"m/s")+"  vals=["+string.Join(",",Array.ConvertAll(vals,v=>v.ToString("F1")))+"]"); }
        return sb.ToString();
    }

    public static string Dump(int pid, long addr, int count){
        IntPtr h=Open(pid,false); int n=count*4; byte[] b=new byte[n]; IntPtr r;
        bool ok=ReadProcessMemory(h,(IntPtr)addr,b,(IntPtr)n,out r); CloseHandle(h);
        if(!ok) return "read failed err="+Marshal.GetLastWin32Error();
        var sb=new StringBuilder();
        for(int i=0;i<count;i++){ float f=BitConverter.ToSingle(b,i*4); int iv=BitConverter.ToInt32(b,i*4);
            sb.AppendLine("0x"+(addr+i*4).ToString("X")+"  f="+f.ToString("0.###")+"   i="+iv); }
        return sb.ToString();
    }

    public static string RegionInfo(int pid, long addr){
        IntPtr h=Open(pid,false); IntPtr sz=(IntPtr)Marshal.SizeOf(typeof(MBI)); MBI m;
        IntPtr r=VirtualQueryEx(h,(IntPtr)addr,out m,sz); CloseHandle(h);
        if(r==IntPtr.Zero) return "VirtualQueryEx failed";
        string ty = m.Type==0x1000000?"IMAGE(module)":m.Type==0x40000?"MAPPED":m.Type==0x20000?"PRIVATE(heap)":("0x"+m.Type.ToString("X"));
        return "addr=0x"+addr.ToString("X")+"  allocBase=0x"+((long)m.AllocationBase).ToString("X")+"  regionBase=0x"+((long)m.BaseAddress).ToString("X")+"  type="+ty+"  protect=0x"+m.Protect.ToString("X")+"  offsetFromAllocBase=0x"+(addr-(long)m.AllocationBase).ToString("X");
    }

    public static string ReadA(int pid, long addr){ IntPtr h=Open(pid,false); byte[] b=new byte[4]; IntPtr r; bool ok=ReadProcessMemory(h,(IntPtr)addr,b,(IntPtr)4,out r); CloseHandle(h);
        return ok?("0x"+addr.ToString("X")+" f="+BitConverter.ToSingle(b,0)+" i="+BitConverter.ToInt32(b,0)):"unreadable"; }

    public static string Poke(int pid, long addr, bool isFloat, double val){
        IntPtr h=Open(pid,true); if(h==IntPtr.Zero) return "OpenProcess(write) FAILED err="+Marshal.GetLastWin32Error();
        byte[] before=new byte[4]; IntPtr rb; ReadProcessMemory(h,(IntPtr)addr,before,(IntPtr)4,out rb);
        byte[] b= isFloat?BitConverter.GetBytes((float)val):BitConverter.GetBytes((int)val);
        IntPtr wr; bool ok=WriteProcessMemory(h,(IntPtr)addr,b,(IntPtr)4,out wr); int e=Marshal.GetLastWin32Error();
        byte[] after=new byte[4]; IntPtr ra; ReadProcessMemory(h,(IntPtr)addr,after,(IntPtr)4,out ra); CloseHandle(h);
        return "Poke 0x"+addr.ToString("X")+" write="+ok+" err="+e+" before(f="+BitConverter.ToSingle(before,0)+") after(f="+BitConverter.ToSingle(after,0)+")";
    }
}
'@
Add-Type -TypeDefinition $src -Language CSharp

function Capture-Primary([string]$path){
  Add-Type -Namespace Win2 -Name Dpi -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool SetProcessDpiAwarenessContext(System.IntPtr value);
'@ -ErrorAction SilentlyContinue
  try { [void][Win2.Dpi]::SetProcessDpiAwarenessContext([IntPtr](-4)) } catch {}
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing
  $p = [System.Windows.Forms.Screen]::AllScreens | Where-Object { $_.Primary } | Select-Object -First 1
  $b = $p.Bounds
  $bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size)
  $g.Dispose()
  $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Jpeg)
  $bmp.Dispose()
}

$p = Get-Process game_release -ErrorAction Stop
$procId = $p.Id
switch ($A[0]) {
  'diffseed'  { if (Test-Path $SampFile) { Remove-Item $SampFile -Force }; $s = if($A[3]){[int]$A[3]}else{3000}; [Hunt]::DiffSeed($procId,$CandFile,[double]$A[1],[double]$A[2],$s) }
  'sample'    { $idx = if(Test-Path $SampFile){ [int]((Get-Item $SampFile).Length / 4) } else { 0 }
                $shot = Join-Path $ShotDir ("sample_{0}.jpg" -f (Get-Date -Format 'HHmmss'))
                Capture-Primary $shot
                $r = [Hunt]::Sample($procId,$CandFile,$SampFile)
                "$r  shot=$shot" }
  'correlate' { $labels = @(); for($k=1;$k -lt $A.Count;$k++){ $labels += [double]$A[$k] }; [Hunt]::Correlate($CandFile,$SampFile,$labels) }
  'read'      { [Hunt]::ReadA($procId,[Convert]::ToInt64($A[1],16)) }
  'regioninfo'{ [Hunt]::RegionInfo($procId,[Convert]::ToInt64($A[1],16)) }
  'dump'      { [Hunt]::Dump($procId,[Convert]::ToInt64($A[1],16),[int]$A[2]) }
  'poke'      { $isF = ($A[3] -ne 'int'); [Hunt]::Poke($procId,[Convert]::ToInt64($A[1],16),$isF,[double]$A[2]) }
  default     { "commands: diffseed <min> <max> [sleepMs] | sample | correlate <label0> <label1> ... | read <hex> | poke <hex> <val> [float|int]" }
}

