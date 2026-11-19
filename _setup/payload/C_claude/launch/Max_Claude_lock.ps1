# Claude Max window reservation (lock) for several Claude threads at once.
# Each thread reserves ONE Claude Max window (MaxBridge port 9878-9899) before using Max,
# and releases it when done, so two threads never overwrite each other's scene.
# If every running Claude Max is reserved, a new Claude Max is started automatically
# (same way as Max_Claude_multi.bat: own settings file, env MAXBRIDGE_PORT = its port).
# The user's Max (port 9877) is never touched.
#
#   claim   -Owner "eye"                 reserve a free Claude Max (start a new one if needed). Last line: PORT=98xx
#   claim   -Owner "eye" -File x.max     same; a newly started Max opens x.max (an existing one is NOT changed)
#   claim   -Owner "eye" -Wait 600       if the window limit is reached, wait up to 600 s for one to be released
#   renew   -Owner "eye" -Port 9879      still working: refresh the time on my reservation
#   release -Owner "eye" -Port 9879      done: SAVE FIRST, then free the window. The scene is reset to empty
#                                        (unsaved changes are dropped). Add -Close to quit that Max instead (never 9878)
#   status                               show every Claude Max port, who holds it, since when
#
# Only an UNLOCKED Claude Max with an EMPTY scene (no file, 0 objects) is ever taken; a window with a scene but no lock
# (a thread using it the old way) is left alone. Locked ports get no message at all.
# Lock files: C:\claude\max_blender\exchange\max_lock\<port>.lock (JSON). A lock counts as stale (free) when
# its Max is gone, or nobody renewed it for -StaleHours (default 6).
# Exit codes: 0 ok, 1 error, 2 limit reached and nothing became free (claim), 3 not your lock (release/renew).
param(
  [Parameter(Position = 0)][ValidateSet("claim", "release", "renew", "status")][string]$Action = "status",
  [string]$Owner = "",
  [int]$Port = 0,
  [string]$File = "",
  [int]$Wait = 0,
  [int]$MaxWindows = 3,
  [double]$StaleHours = 6,
  [switch]$Close,
  [switch]$Force
)

$BASE = 9878; $LAST = 9899
$LOCKDIR = "C:\claude\max_blender\exchange\max_lock"
$CLAUDEINI = "C:\claude\max_claude_profile\3dsmax_claude.ini"
$MAXEXE = "C:\Program Files\Autodesk\3ds Max 2014\3dsmax.exe"
if (Test-Path "C:\claude\max_claude_profile\maxexe.txt") { $MAXEXE = (Get-Content "C:\claude\max_claude_profile\maxexe.txt" -TotalCount 1).Trim() }
$UTF8 = New-Object System.Text.UTF8Encoding($false)
if (-not (Test-Path $LOCKDIR)) { New-Item -ItemType Directory -Path $LOCKDIR | Out-Null }

function Get-Listening {
  $set = @{}
  foreach ($line in (netstat -ano -p tcp | Select-String "LISTENING")) {
    $f = $line.ToString().Trim() -split '\s+'
    if ($f[1] -match ':(\d+)$') { $p = [int]$matches[1]; if ($p -ge $BASE -and $p -le $LAST) { $set[$p] = [int]$f[-1] } }
  }
  return $set   # port -> pid
}

function Send-Max([int]$p, [string]$code, [int]$ms = 5000) {
  $c = New-Object System.Net.Sockets.TcpClient
  $c.ReceiveTimeout = $ms
  $c.Connect("127.0.0.1", $p)
  $st = $c.GetStream()
  $b = [System.Text.Encoding]::UTF8.GetBytes($code)
  $st.Write($b, 0, $b.Length)
  $c.Client.Shutdown([System.Net.Sockets.SocketShutdown]::Send)
  $mem = New-Object System.IO.MemoryStream
  $buf = New-Object byte[] 4096
  while (($n = $st.Read($buf, 0, $buf.Length)) -gt 0) { $mem.Write($buf, 0, $n) }
  $c.Close()
  return [System.Text.Encoding]::UTF8.GetString($mem.ToArray()).Trim().Trim('"')
}

# "yes" = Claude Max (started with MAXBRIDGE_PORT = its port), "no" = something else, "busy" = no answer (starting or running a long job)
function Is-ClaudeMax([int]$p) {
  try { if ((Send-Max $p 'systemTools.getEnvVariable "MAXBRIDGE_PORT"') -eq "$p") { "yes" } else { "no" } } catch { "busy" }
}

# read-only look at an unlocked Max: "empty" = Claude Max with no file and no objects (safe to take),
# "inuse" = Claude Max with a scene (a thread may be using it without a lock - never taken), "no" / "busy" as above
function Probe-Free([int]$p) {
  try { $r = Send-Max $p '(systemTools.getEnvVariable "MAXBRIDGE_PORT") + "|" + maxFileName + "|" + (objects.count as string)' } catch { return "busy" }
  $f = $r.Split("|")
  if ($f.Count -lt 3 -or $f[0] -ne "$p") { return "no" }
  if ($f[1] -eq "" -and $f[2] -eq "0") { return "empty" }
  return "inuse"
}

function Read-Lock([int]$p) {
  $f = Join-Path $LOCKDIR "$p.lock"
  if (-not (Test-Path $f)) { return $null }
  try { return ([IO.File]::ReadAllText($f, $UTF8) | ConvertFrom-Json) } catch { return [pscustomobject]@{ port = $p; owner = "?"; since = ""; renewed = ""; state = "unreadable" } }
}

# a lock is live while its Max is up (or still starting, 6 min grace) and it was renewed within StaleHours
function Lock-Live($lk, $listen) {
  if ($null -eq $lk) { return $false }
  $t = [datetime]::MinValue
  if (-not [datetime]::TryParse([string]$lk.renewed, [ref]$t)) { return $false }
  $age = ((Get-Date) - $t).TotalHours
  if ($age -gt $StaleHours) { return $false }
  if ($listen.ContainsKey([int]$lk.port)) { return $true }
  return ($lk.state -eq "starting" -and $age -lt 0.1)
}

# create the lock file only if it does not exist (atomic: two threads can never both get it)
function New-Lock([int]$p, [string]$state) {
  $now = (Get-Date).ToString("s")
  $obj = [ordered]@{ port = $p; owner = $Owner; since = $now; renewed = $now; state = $state; host_pid = $PID }
  $f = Join-Path $LOCKDIR "$p.lock"
  try { $fs = [IO.File]::Open($f, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None) } catch { return $false }
  $b = $UTF8.GetBytes(($obj | ConvertTo-Json -Compress)); $fs.Write($b, 0, $b.Length); $fs.Close()
  return $true
}

function Set-Lock([int]$p, $lk) { [IO.File]::WriteAllText((Join-Path $LOCKDIR "$p.lock"), ($lk | ConvertTo-Json -Compress), $UTF8) }

function Clear-Stale($listen) {
  foreach ($f in (Get-ChildItem $LOCKDIR -Filter "*.lock" -ErrorAction SilentlyContinue)) {
    $p = 0; if (-not [int]::TryParse($f.BaseName, [ref]$p)) { continue }
    $lk = Read-Lock $p
    if (-not (Lock-Live $lk $listen)) {
      Write-Host ("  stale lock removed: {0} (owner '{1}', renewed {2})" -f $p, $lk.owner, $lk.renewed)
      Remove-Item $f.FullName -Force -ErrorAction SilentlyContinue
    }
  }
}

function Show-Status {
  $listen = Get-Listening
  Write-Host "Claude Max windows (9877 = user's Max, never used):"
  $any = $false
  foreach ($p in $BASE..$LAST) {
    $lk = Read-Lock $p
    if (-not $listen.ContainsKey($p) -and $null -eq $lk) { continue }
    $any = $true
    $run = if ($listen.ContainsKey($p)) { "running pid " + $listen[$p] } else { "not running" }
    if ($null -eq $lk) { $who = "FREE" }
    elseif (Lock-Live $lk $listen) { $who = "held by '" + $lk.owner + "' since " + $lk.since + " (renewed " + $lk.renewed + ")" }
    else { $who = "stale lock of '" + $lk.owner + "' (counts as free)" }
    Write-Host ("  {0}  {1,-18} {2}" -f $p, $run, $who)
  }
  if (-not $any) { Write-Host "  none running" }
}

function Wait-Ready([int]$p, [int]$sec) {
  $t0 = Get-Date
  while (((Get-Date) - $t0).TotalSeconds -lt $sec) {
    $l = Get-Listening
    if ($l.ContainsKey($p) -and (Is-ClaudeMax $p) -eq "yes") { return $true }
    Start-Sleep -Seconds 3
  }
  return $false
}

# ---------------------------------------------------------------- actions
if ($Action -eq "status") { Show-Status; exit 0 }

if ($Owner.Trim() -eq "") { Write-Host "[ERROR] -Owner is required (who is using the window, e.g. the thread name)"; exit 1 }

if ($Action -eq "release" -or $Action -eq "renew") {
  if ($Port -lt $BASE -or $Port -gt $LAST) { Write-Host "[ERROR] -Port must be $BASE-$LAST (9877 is the user's Max)"; exit 1 }
  $lk = Read-Lock $Port
  if ($null -eq $lk) { Write-Host "No lock on $Port (already free)."; if ($Action -eq "renew") { exit 3 } else { exit 0 } }
  if ($lk.owner -ne $Owner -and -not $Force) { Write-Host ("[STOP] {0} is held by '{1}', not '{2}'. Nothing changed." -f $Port, $lk.owner, $Owner); exit 3 }
  if ($Action -eq "renew") {
    $lk.renewed = (Get-Date).ToString("s"); Set-Lock $Port $lk
    Write-Host "Renewed $Port for '$Owner'."; Write-Host "PORT=$Port"; exit 0
  }
  if (-not $Close -and (Is-ClaudeMax $Port) -eq "yes") {
    # leave an empty scene behind so the next claim can take this window (save your work BEFORE release)
    # resetMaxFile is NOT run inside the MaxBridge request (that broke MaxBridge on 9878, 2026-10-27):
    # a one-shot timer runs it 0.5 s after MaxBridge has answered
    $ms = 'global ClaudeLock_resetTimer; fn ClaudeLock_onReset s a = (s.Stop(); resetMaxFile #noPrompt); ' +
          'ClaudeLock_resetTimer = dotNetObject "System.Windows.Forms.Timer"; ClaudeLock_resetTimer.Interval = 500; ' +
          'dotNet.addEventHandler ClaudeLock_resetTimer "Tick" ClaudeLock_onReset; dotNet.setLifetimeControl ClaudeLock_resetTimer #mxs; ' +
          'ClaudeLock_resetTimer.Start(); "scheduled"'
    try { Send-Max $Port $ms 10000 | Out-Null; Write-Host "  scene on $Port will be reset to empty." } catch { Write-Host "  [WARN] could not reset the scene on $Port" }
  }
  if ($Close) {
    if ($Port -eq $BASE) { Write-Host "  -Close ignored for $BASE (the first Claude Max stays open)." }
    elseif ((Is-ClaudeMax $Port) -eq "yes") {
      try { Send-Max $Port 'quitMax #noPrompt; "bye"' 3000 | Out-Null } catch {}
      Write-Host "  asked Max $Port to quit (unsaved changes there are dropped)."
    }
  }
  Remove-Item (Join-Path $LOCKDIR "$Port.lock") -Force
  Write-Host "Released $Port."; exit 0
}

# ---- claim
if ($File -ne "" -and -not (Test-Path -LiteralPath $File)) { Write-Host "[ERROR] file not found: $File"; exit 1 }
$mutex = New-Object System.Threading.Mutex($false, "Global\ClaudeMaxLockClaim")
$t0 = Get-Date
$launched = 0
while ($true) {
  $got = $false
  try { $got = $mutex.WaitOne(60000) } catch [System.Threading.AbandonedMutexException] { $got = $true }
  if (-not $got) { Write-Host "[ERROR] another claim is stuck (waited 60 s)"; exit 1 }
  try {
    $listen = Get-Listening
    Clear-Stale $listen
    # same owner already holds one: give it back (renewed)
    foreach ($p in $BASE..$LAST) {
      $lk = Read-Lock $p
      if ($lk -and $lk.owner -eq $Owner -and (Lock-Live $lk $listen)) {
        $lk.renewed = (Get-Date).ToString("s"); Set-Lock $p $lk
        Write-Host "'$Owner' already holds $p (renewed)."; Write-Host "PORT=$p"; exit 0
      }
    }
    # 1) a running Claude Max nobody holds and that has an empty scene
    #    locked ports get NO message at all; unlocked ones get one read-only query
    $claude = 0
    foreach ($p in ($listen.Keys | Sort-Object)) {
      if (Test-Path (Join-Path $LOCKDIR "$p.lock")) { $claude++; continue }
      $who = Probe-Free $p
      if ($who -eq "no") { continue }
      $claude++
      if ($who -ne "empty") { Write-Host "  $p has no lock but is $who (scene open or working) - left alone"; continue }
      if (New-Lock $p "held") { Write-Host "Reserved running Claude Max $p for '$Owner'."; Write-Host "PORT=$p"; exit 0 }
    }
    # 2) start a new one if under the limit
    if ($claude -lt $MaxWindows) {
      $free = $BASE..$LAST | Where-Object { -not $listen.ContainsKey($_) -and -not (Test-Path (Join-Path $LOCKDIR "$_.lock")) } | Select-Object -First 1
      if ($null -eq $free) { Write-Host "[ERROR] no free port left in $BASE-$LAST"; exit 1 }
      foreach ($need in @($CLAUDEINI, $MAXEXE)) { if (-not (Test-Path $need)) { Write-Host "[ERROR] not found: $need"; exit 1 } }
      if (-not (New-Lock $free "starting")) { continue }
      $env:MAXBRIDGE_PORT = "$free"
      $args2 = @("/Language=ENU", "-i", "`"$CLAUDEINI`"")
      if ($File -ne "") { $args2 += "`"$File`"" }
      Start-Process -FilePath $MAXEXE -ArgumentList $args2 -WindowStyle Minimized | Out-Null
      Remove-Item Env:MAXBRIDGE_PORT
      $launched = $free
      Write-Host "Starting a new Claude Max on $free for '$Owner' (up to 4 min)..."
    }
  } finally { $mutex.ReleaseMutex() }

  if ($launched -ne 0) {
    if (-not (Wait-Ready $launched 240)) {
      Remove-Item (Join-Path $LOCKDIR "$launched.lock") -Force -ErrorAction SilentlyContinue
      Write-Host "[ERROR] the new Max on $launched did not answer within 4 min (lock removed)."; exit 1
    }
    $lk = Read-Lock $launched; $lk.state = "held"; $lk.renewed = (Get-Date).ToString("s"); Set-Lock $launched $lk
    $tile = Join-Path $PSScriptRoot "Max_Claude_tile.ps1"
    # close its Welcome Screen in the background (does not delay the claim)
    if (Test-Path $tile) { Start-Process powershell -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$tile`"", "-Ports", "$launched", "-NoTile", "-Timeout", "30") -WindowStyle Hidden | Out-Null }
    Write-Host "Reserved new Claude Max $launched for '$Owner'."; Write-Host "PORT=$launched"; exit 0
  }
  if (((Get-Date) - $t0).TotalSeconds -ge $Wait) {
    Write-Host "[FULL] $MaxWindows Claude Max windows are all reserved. Try again later or use -Wait."
    Show-Status; exit 2
  }
  Start-Sleep -Seconds 10
}
