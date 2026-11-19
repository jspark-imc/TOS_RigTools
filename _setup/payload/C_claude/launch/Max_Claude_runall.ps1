# Run one .ms script in every running Claude Max (MaxBridge ports 9878-9899).
# The user's Max (port 9877) is never touched.
param([Parameter(Mandatory = $true)][string]$Script)

if (-not (Test-Path -LiteralPath $Script)) { Write-Host "[ERROR] file not found: $Script"; exit 1 }
$full = (Resolve-Path -LiteralPath $Script).Path
if ($full -notmatch '\.(ms|mse|mcr)$') { Write-Host "[ERROR] not a MAXScript file (.ms / .mse / .mcr): $full"; exit 1 }
if ($full.Contains('"')) { Write-Host "[ERROR] the file path contains a quote character"; exit 1 }

function Get-Listening {
  $out = @()
  foreach ($p in 9878..9899) {
    if (netstat -ano -p tcp | Select-String (":$p\s.*LISTENING")) { $out += $p }
  }
  return $out
}

function Send-Max([int]$port, [string]$code) {
  $c = New-Object System.Net.Sockets.TcpClient
  $c.ReceiveTimeout = 30000
  $c.Connect("127.0.0.1", $port)
  $st = $c.GetStream()
  $b = [System.Text.Encoding]::UTF8.GetBytes($code)
  $st.Write($b, 0, $b.Length)
  $c.Client.Shutdown([System.Net.Sockets.SocketShutdown]::Send)
  $ms = New-Object System.IO.MemoryStream
  $buf = New-Object byte[] 65536
  while (($n = $st.Read($buf, 0, $buf.Length)) -gt 0) { $ms.Write($buf, 0, $n) }
  $c.Close()
  return [System.Text.Encoding]::UTF8.GetString($ms.ToArray()).Trim()
}

$ports = @()
foreach ($p in @(Get-Listening)) {
  # only a Max started by Max_Claude_multi.bat (env MAXBRIDGE_PORT = its port) is a Claude Max
  $who = ""
  try { $who = (Send-Max $p 'systemTools.getEnvVariable "MAXBRIDGE_PORT"').Trim('"') } catch {}
  if ($who -eq "$p") { $ports += $p } else { Write-Host ("  {0}  SKIP: not a Claude Max (MAXBRIDGE_PORT='{1}')" -f $p, $who) }
}
if ($ports.Count -eq 0) { Write-Host "No Claude Max is running (ports 9878-9899). Start them with Max_Claude_multi.bat first."; exit 1 }

# SafePruneBatch: each window gets its own share of the files (window number 1..N of N), same folder
$isPrune = ([IO.Path]::GetFileName($full) -like "SafePrune*")
$folder = ""
if ($isPrune) {
  Write-Host ""
  Write-Host "SafePruneBatch: drag the folder to clean into this window and press Enter (Enter only = fill it in yourself)."
  $folder = (Read-Host "Folder").Trim().Trim('"')
  if ($folder -ne "" -and -not (Test-Path -LiteralPath $folder -PathType Container)) { Write-Host "[WARN] folder not found, leaving it empty: $folder"; $folder = "" }
  if ($folder.Contains('"')) { $folder = "" }
}

Write-Host ("Script : {0}" -f $full)
Write-Host ("Targets: Claude Max on ports {0}" -f ($ports -join ", "))
Write-Host ""
$ok = 0
foreach ($p in $ports) {
  try {
    $r = Send-Max $p ('try (fileIn @"' + $full + '"; "OK") catch ("ERROR: " + (getCurrentException()))')
    Write-Host ("  {0}  {1}" -f $p, $r)
    if ($r -like "*OK*") {
      $ok++
      if ($isPrune) {
        $idx = [array]::IndexOf($ports, $p) + 1
        $set = 'if SafePruneBatchRoll != undefined and SafePruneBatchRoll.open then (SafePruneBatchRoll.spnParts.value = ' + $ports.Count + '; SafePruneBatchRoll.spnPart.value = ' + $idx
        if ($folder -ne "") { $set += '; SafePruneBatchRoll.edtDir.text = @"' + $folder + '"' }
        $set += '; "set") else "no window"'
        $r2 = Send-Max $p $set
        Write-Host ("        window {0} / {1}  ({2})" -f $idx, $ports.Count, $r2)
      }
    }
  } catch {
    Write-Host ("  {0}  no answer ({1})" -f $p, $_.Exception.Message)
  }
}
Write-Host ""
Write-Host ("Opened in {0} of {1} Claude Max window(s)." -f $ok, $ports.Count)
if ($isPrune) {
  Write-Host ""
  Write-Host "Next: in EACH window check the options, then press the run button. (v1.7 has no test-only mode: files are cleaned for real.)"
  Write-Host "Window numbers are already split, so no file is processed twice."
}
