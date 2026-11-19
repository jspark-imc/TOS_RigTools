# Arrange Claude Max windows (MaxBridge ports 9878-9899) in a grid on the primary screen.
# -Ports "9878,9879"  : wait until these ports are listening (Max finished starting), then arrange them
# (no -Ports)         : arrange every Claude Max that is already running
# The user's Max (port 9877) is never touched.
# -NoTile             : do not arrange, only close the Welcome Screen
# Also closes the Welcome Screen of those Claude Max windows (only their own process, never the user's Max).
param([string]$Ports = "", [int]$Timeout = 240, [switch]$NoTile)

Add-Type @"
using System; using System.Runtime.InteropServices;
public class CMW {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int w, int hh, uint f);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SystemParametersInfo(int a, int b, ref RECT r, int c);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr v);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] static extern int GetWindowThreadProcessId(IntPtr h, out int pid);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
  // visible top-level windows of one process whose title contains "Welcome" -> WM_CLOSE. returns count
  public static int CloseWelcome(int pid) {
    int n = 0;
    EnumWindows(delegate (IntPtr h, IntPtr l) {
      int p; GetWindowThreadProcessId(h, out p);
      if (p == pid && IsWindowVisible(h)) {
        var sb = new System.Text.StringBuilder(256); GetWindowText(h, sb, 256);
        if (sb.ToString().IndexOf("Welcome", StringComparison.OrdinalIgnoreCase) >= 0) { PostMessage(h, 0x0010, IntPtr.Zero, IntPtr.Zero); n++; }
      }
      return true;
    }, IntPtr.Zero);
    return n;
  }
  [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out RECT r, int size);
}
"@
# work in real screen pixels (otherwise Windows display scaling 125%/150% shifts the grid)
try { [CMW]::SetProcessDpiAwarenessContext([IntPtr](-4)) | Out-Null } catch { try { [CMW]::SetProcessDPIAware() | Out-Null } catch {} }

function Get-PortPid([int]$p) {
  $m = netstat -ano -p tcp | Select-String (":$p\s.*LISTENING")
  if ($m) { return [int](($m[0].ToString().Trim() -split '\s+')[-1]) }
  return 0
}

function Send-Max([int]$port, [string]$code) {
  $c = New-Object System.Net.Sockets.TcpClient
  $c.ReceiveTimeout = 5000
  $c.Connect("127.0.0.1", $port)
  $st = $c.GetStream()
  $b = [System.Text.Encoding]::UTF8.GetBytes($code)
  $st.Write($b, 0, $b.Length)
  $c.Client.Shutdown([System.Net.Sockets.SocketShutdown]::Send)
  $ms = New-Object System.IO.MemoryStream
  $buf = New-Object byte[] 4096
  while (($n = $st.Read($buf, 0, $buf.Length)) -gt 0) { $ms.Write($buf, 0, $n) }
  $c.Close()
  return [System.Text.Encoding]::UTF8.GetString($ms.ToArray()).Trim().Trim('"')
}
# only a Max started by Max_Claude_multi.bat (env MAXBRIDGE_PORT = its port) counts as a Claude Max
# returns "yes", "no", or "busy" (no answer yet - Max still starting)
function Is-ClaudeMax([int]$p) {
  try { if ((Send-Max $p 'systemTools.getEnvVariable "MAXBRIDGE_PORT"') -eq "$p") { return "yes" } else { return "no" } } catch { return "busy" }
}

$want = @()
if ($Ports -ne "") { $want = $Ports.Split(",") | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ } | Where-Object { $_ -ge 9878 -and $_ -le 9899 } }
else { $want = 9878..9899 | Where-Object { (Get-PortPid $_) -ne 0 } }
$want = @($want | Sort-Object)
if ($want.Count -eq 0) { Write-Host "No Claude Max windows to arrange."; exit 0 }

# wait for every wanted port to listen and its window to exist
$t0 = Get-Date
$wins = @{}
while ($wins.Count -lt $want.Count -and ((Get-Date) - $t0).TotalSeconds -lt $Timeout) {
  foreach ($p in $want) {
    if ($wins.ContainsKey($p)) { continue }
    $pid2 = Get-PortPid $p
    if ($pid2 -eq 0) { continue }
    $who = Is-ClaudeMax $p
    if ($who -eq "busy") { continue }
    if ($who -eq "no") { Write-Host ("  port {0}: not a Claude Max (no matching MAXBRIDGE_PORT) - left alone" -f $p); $wins[$p] = 0; continue }
    $pr = Get-Process -Id $pid2 -ErrorAction SilentlyContinue
    if ($pr -and $pr.MainWindowHandle -ne 0 -and $pr.MainWindowTitle -like "*3ds Max*") { $wins[$p] = $pr.MainWindowHandle }
  }
  if ($wins.Count -lt $want.Count) { Start-Sleep -Seconds 2 }
}
if ($wins.Count -eq 0) { Write-Host "No Max window became ready within $Timeout s."; exit 1 }

# drop ports that are not Claude Max (never touch the user's Max)
foreach ($k in @($wins.Keys)) { if ($wins[$k] -eq 0) { $wins.Remove($k) } }
if ($wins.Count -eq 0) { Write-Host "No Claude Max windows to arrange."; exit 0 }

# close the Welcome Screen. It shows up only after Max has fully loaded (later than the port),
# so watch each Max for up to 2 minutes and stop as soon as every one has had its Welcome Screen closed.
$pids = @(); foreach ($p in $wins.Keys) { $pids += (Get-PortPid $p) }
$done = @{}
$t1 = Get-Date
while ($done.Count -lt $pids.Count -and ((Get-Date) - $t1).TotalSeconds -lt 120) {
  foreach ($pp in $pids) {
    if ($done.ContainsKey($pp)) { continue }
    if ([CMW]::CloseWelcome($pp) -gt 0) { $done[$pp] = 1; Write-Host ("  Welcome Screen closed (process {0})" -f $pp) }
  }
  if ($done.Count -lt $pids.Count) { Start-Sleep -Milliseconds 700 }
}
Write-Host ("Welcome Screen closed: {0} of {1}" -f $done.Count, $pids.Count)
if ($NoTile) { exit 0 }

$order = @($wins.Keys | Sort-Object)   # not $ports: PowerShell names ignore case, $ports == the [string] param $Ports
$n = $order.Count
$wa = New-Object CMW+RECT
[CMW]::SystemParametersInfo(0x30, 0, [ref]$wa, 0) | Out-Null     # SPI_GETWORKAREA: primary screen minus taskbar
$area = @{ X = $wa.L; Y = $wa.T; Width = $wa.R - $wa.L; Height = $wa.B - $wa.T }
$cols = [int][math]::Ceiling([math]::Sqrt($n))
$rows = [int][math]::Ceiling($n / $cols)
$w = [int][math]::Floor($area.Width / $cols)
$h = [int][math]::Floor($area.Height / $rows)

function Place {
  for ($i = 0; $i -lt $n; $i++) {
    $c = $i % $cols; $r = [int][math]::Floor($i / $cols)
    $hwnd = [IntPtr]$wins[$order[$i]]
    [CMW]::ShowWindow($hwnd, 9) | Out-Null            # restore (un-minimize / un-maximize)
    $x = $area.X + $c * $w; $y = $area.Y + $r * $h
    [CMW]::SetWindowPos($hwnd, [IntPtr]::Zero, $x, $y, $w, $h, 0x0044) | Out-Null
    # Windows 10/11 windows have an invisible border; grow by it so the visible edges meet exactly
    $wr = New-Object CMW+RECT; $vr = New-Object CMW+RECT
    [CMW]::GetWindowRect($hwnd, [ref]$wr) | Out-Null
    if ([CMW]::DwmGetWindowAttribute($hwnd, 9, [ref]$vr, 16) -eq 0) {
      $bl = $vr.L - $wr.L; $bt = $vr.T - $wr.T; $br = $wr.R - $vr.R; $bb = $wr.B - $vr.B
      [CMW]::SetWindowPos($hwnd, [IntPtr]::Zero, $x - $bl, $y - $bt, $w + $bl + $br, $h + $bt + $bb, 0x0044) | Out-Null
    }
  }
}
function Report {
  for ($i = 0; $i -lt $n; $i++) {
    $c = $i % $cols; $r = [int][math]::Floor($i / $cols)
    $vr = New-Object CMW+RECT
    if ([CMW]::DwmGetWindowAttribute([IntPtr]$wins[$order[$i]], 9, [ref]$vr, 16) -ne 0) { [CMW]::GetWindowRect([IntPtr]$wins[$order[$i]], [ref]$vr) | Out-Null }
    Write-Host ("  port {0}: wanted x={1} y={2} {3}x{4}  ->  now x={5} y={6} {7}x{8}" -f $order[$i], ($area.X + $c * $w), ($area.Y + $r * $h), $w, $h, $vr.L, $vr.T, ($vr.R - $vr.L), ($vr.B - $vr.T))
  }
}
Write-Host ("Screen work area: {0}x{1} at {2},{3}" -f $area.Width, $area.Height, $area.X, $area.Y)
Place
Start-Sleep -Seconds 4
Place   # Max may re-maximize itself while finishing startup
Report
Write-Host ("Arranged {0} window(s) in {1}x{2} grid: ports {3}" -f $n, $cols, $rows, ($order -join ","))
