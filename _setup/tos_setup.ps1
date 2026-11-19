# tos_setup.ps1 — TOS_RigTools 설치기 (작업자 PC용)  2026-11-13 TOS_RigTools 1.0 (GE 리깅 툴 설치기 v5.5 를 바탕으로, 설치 방식은 같음)
#   TOS_RigTools 와 GE 리그 툴(RigTools.ms 등)은 같은 함수 이름을 써서 한 Max 에 같이 켤 수 없음 → GE 리그 툴 파일이 있으면 원인을 보여 주고 Y/N 으로 물어 백업 폴더로 치움 (3_RESTORE.bat 로 되돌림)
#   부품: A = Max Bridge + VirusGuard (항상)  B = 리그 툴 (Max + 블렌더)  C = Claude Max 환경 (작업자 Max 와 분리)
#   1_INSTALL.bat = -Mode Install   2_CHECK.bat = -Mode Check   3_RESTORE.bat = -Mode Restore
#   -Parts AUTO : 지난번 설치한 부품 그대로 (처음이면 물음, INSTALL_ALL.bat)   -Parts ABC : 묻지 않고 부품 지정   -Yes : 묻는 곳 모두 '예'   -Root <빈 폴더> : 시험용 (실제 PC 대신 그 폴더 아래만 씀)
# 원칙
#   - 바꾸는 파일은 전부 %USERPROFILE%\tos_rig_backup\<시각>\ 에 먼저 백업 → 3_RESTORE.bat 로 되돌림
#   - 예전에 설치된 '우리' 파일: 최신으로 자동 갱신. 이름이 바뀐 옛 파일·백업 찌꺼기는 자동으로 치움(백업 폴더로 옮김)
#   - 우리 것인지 확실치 않은 파일, 작업자 Max 설정(3dsmax.ini) 수정은 원인을 보여 주고 Y/N
#   - 작업자 Max(포트 9877)·작업자 Max 설정은 Claude Max 환경 때문에 바뀌지 않는다 (Claude Max 는 따로 만든 설정 파일·포트 9878~)
param(
  [ValidateSet('Install','Check','Restore')][string]$Mode = 'Install',
  [string]$Parts = '',
  [string]$Root = '',
  [switch]$Yes
)
$ErrorActionPreference = 'Stop'
$here    = $PSScriptRoot
$payload = Join-Path $here 'payload'
$verFile = Join-Path (Split-Path $here) 'VERSION.txt'
$PORT    = 9877
$MINBLEND = [version]'4.2'
$TESTED   = '5.2'

if ($Root) {
  $Root = [IO.Path]::GetFullPath($Root)
  $APPDATA = Join-Path $Root 'AppData\Roaming'; $LOCAL = Join-Path $Root 'AppData\Local'; $UP = Join-Path $Root 'User'
  $CLAUDE  = Join-Path $Root 'claude'
} else {
  $APPDATA = $env:APPDATA; $LOCAL = $env:LOCALAPPDATA; $UP = $env:USERPROFILE
  $CLAUDE  = 'C:\claude'
}
$maxUser    = Join-Path $LOCAL 'Autodesk\3dsMax\2016 - 64bit'
$maxProg    = 'C:\Program Files\Autodesk\3ds Max 2016'
$maxSysStartup = "$maxProg\scripts\startup"
$blendRoot  = Join-Path $APPDATA 'Blender Foundation\Blender'
$mbRoot     = Join-Path $CLAUDE 'max_blender'
$profDir    = Join-Path $CLAUDE 'max_claude_profile'
$claudeIni  = Join-Path $profDir '3dsmax_claude.ini'
$backupRoot = Join-Path $UP 'tos_rig_backup'
$stateFile  = Join-Path $backupRoot 'installed.txt'
$PARTNAME   = @{ A = 'Max Bridge + VirusGuard'; B = 'TOS_RigTools (Max + 블렌더)'; C = 'Claude Max 환경' }

# 우리 도구의 이름 (지금 이름 + 예전 이름 앞부분). 여기에 맞고 묶음에 없는 파일 = 옛 파일 → 자동 정리
$OURS_MAX     = '^(!?MaxVirusGuard|MaxBridge|BipFit|BipConvert|TOS_RigTools|TOS_RigToolsStd|WeightToolPos)([ _.-].*)?\.(ms|mse|mcr|mzp)$'
# TOS_RigTools 는 전역 이름이 따로라(TosRig·TosRigStd·trts_*·tsbg_*·tos_*) GE 리그 툴·MTOS_RigTools 와 같이 켜도 됨 → 이 설치기는 그 파일을 치우지도·묻지도 않음 (아래 OTHER_TOOLS)
#   ($GE_MAX 는 이름만 남김: 아무 파일에도 맞지 않게)
$GE_MAX       = '^$^'
# 1.61: Fix Tools·MeshFix 는 QATool(animation_tool\QATool, 따로 설치) 로 분리 -> 리그툴 설치기는 이 파일을 옛 파일로 치우지도·묻지도 않음
$OTHER_TOOLS  = '(?i)^(ClaudeFixTools|ClaudeMeshFix|MTOS_RigTools|MTOS_RigToolsStd|FaceTools|RigTools|RigToolsKnee|RigToolsStd)([ _.-].*)?\.(ms|mse|mcr|mzp)$|^MTOS_RigTools$'
$OURS_RIGDIR  = '^(pc_[mf]_set_test|tos_skin|tos_bip|tos_twist|tos_secondary|tos_clavicle|tos_make_ref|rom_check|sbg_build|sbg_fingers|SecBoneGen|rts_blender|rts_tpl)'   # 1.71: ivelar_standard = 옛 이름(정리용)
$OURS_TPL     = '^(limb_helpers|ivelar_limb_helpers)'   # 1.71: C:\claude\max_blender\templates 의 팔다리 헬퍼 템플릿 (ivelar_ = 옛 이름, 정리용)
$OURS_ADDON   = '^(max_bridge|max_style_rig|object_bones|hair_bones|body_template|eye_template|biped_test_rig|blender_mcp_addon|parts_preset|clean_view|sbg_detect|ge_jobs|rig_template|secondary_weight_ref)([ _.-].*)?(\.py|\.json)?$'
$OURS_MODULE  = '^(accurig_prep|helper_template|rig_weights|standardize)([ _.-].*)?\.py$'
$OURS_LAUNCH  = '^Max_Claude.*\.(bat|ps1)$'
$LEFTOVER     = '(?i)\.bak|^버전\.txt$|^VERSION\.txt$'
# 이름은 다르지만 비슷해서 '확인 필요'로 묻는 것
$SIMILAR      = '(?i)rig|bridge|bip|bone|template|hair|weight|claude|knee|ivelar|virusguard|meshfix'

# ---------------------------------------------------------------- 공통
function Say($t, $c = 'Gray') { Write-Host $t -ForegroundColor $c }
function Stop-Here($t) { Say ''; Say "[멈춤] $t" Red; Say '결과: 멈춤 (아무것도 바꾸지 않았어요)' Red; exit 2 }
# 다른 프로그램(Max 등)이 쓰는 중인 파일도 읽을 수 있게 공유 모드로 연다. 못 읽으면 오류로 멈추지 않고 표시만
function Hash($p) {
  try {
    $fs = [IO.File]::Open($p, [IO.FileMode]::Open, [IO.FileAccess]::Read, ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
    try { $sha = [Security.Cryptography.SHA256]::Create(); return ([BitConverter]::ToString($sha.ComputeHash($fs)) -replace '-', '') } finally { $fs.Dispose() }
  } catch { return ('UNREADABLE:' + [guid]::NewGuid().ToString('N')) }
}
function Ask($q) { if ($Yes) { Say "$q -> 예 (-Yes)"; return $true }; $a = Read-Host "$q (Y/N)"; return ($a -match '^[yY]') }
function Short($p) {
  foreach ($r in @(@($maxUser, '[Max2016]'), @($blendRoot, '[Blender]'), @($UP, '[USERPROFILE]'))) {
    if ($p.StartsWith($r[0] + '\', [StringComparison]::OrdinalIgnoreCase) -or $p.StartsWith($r[0] + '/', [StringComparison]::OrdinalIgnoreCase)) { return ($r[1] + $p.Substring($r[0].Length)) }
  }
  $p
}
function SafeRel($full) { ($full -replace ':', '') -replace '^[\\/]+', '' }
function Head($t) { Say ''; Say "--- $t ---" Cyan }
$script:Results = @(); $script:JunkList = $null
function Result($st, $what, $why = '', $fix = '') {
  $script:Results += [pscustomobject]@{ St = $st; What = $what; Why = $why; Fix = $fix }
  $c = @{ 'OK' = 'Green'; 'WARN' = 'Yellow'; 'FAIL' = 'Red'; 'SKIP' = 'DarkGray' }[$st]
  Say ('[{0,-4}] {1}' -f $st, $what) $c
  if ($why) { Say "       원인: $why" $c }
  if ($fix) { Say "       해결: $fix" $c }
}

# ---------------------------------------------------------------- ini (UTF-16 / UTF-8 / ANSI)
function Read-IniText($path) {
  $b = [IO.File]::ReadAllBytes($path)
  if ($b.Length -ge 2 -and $b[0] -eq 0xFF -and $b[1] -eq 0xFE) { return @{ Text = [Text.Encoding]::Unicode.GetString($b, 2, $b.Length - 2); Enc = 'utf16' } }
  if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) { return @{ Text = [Text.Encoding]::UTF8.GetString($b, 3, $b.Length - 3); Enc = 'utf8bom' } }
  return @{ Text = [Text.Encoding]::Default.GetString($b); Enc = 'ansi' }
}
function Write-IniText($path, $text, $enc) {
  switch ($enc) {
    'utf16'   { [IO.File]::WriteAllBytes($path, [byte[]](0xFF, 0xFE) + [Text.Encoding]::Unicode.GetBytes($text)) }
    'utf8bom' { [IO.File]::WriteAllBytes($path, [byte[]](0xEF, 0xBB, 0xBF) + [Text.Encoding]::UTF8.GetBytes($text)) }
    default   { [IO.File]::WriteAllBytes($path, [Text.Encoding]::Default.GetBytes($text)) }
  }
}
function Get-IniValue($text, $key) { $m = [regex]::Match($text, "(?im)^\s*$([regex]::Escape($key))\s*=\s*(.*?)\s*$"); if ($m.Success) { $m.Groups[1].Value } else { $null } }
function Set-IniValue($text, $key, $val) { [regex]::Replace($text, "(?im)^(\s*$([regex]::Escape($key))\s*=\s*).*?(\s*)$", ('${1}' + $val.Replace('$', '$$') + '${2}')) }

# ---------------------------------------------------------------- 환경 찾기
function Get-MaxTargets {
  $res = @()
  foreach ($l in 'ENU', 'KOR') {
    $ld = Join-Path $maxUser $l
    if (-not (Test-Path $ld)) { continue }
    $def = Join-Path $ld 'scripts\startup'
    $ini = Join-Path $ld '3dsmax.ini'
    $cfg = $null; if (Test-Path -LiteralPath $ini) { $cfg = Get-IniValue (Read-IniText $ini).Text 'Additional Startup Scripts' }
    $state = 'default'
    if ($cfg -and ($cfg.TrimEnd('\') -ne $def.TrimEnd('\'))) { if (Test-Path -LiteralPath $cfg) { $state = 'custom' } else { $state = 'broken' } }
    $use = $def; if ($state -eq 'custom') { $use = $cfg }
    $res += [pscustomobject]@{ Lang = $l; Dir = $ld; Ini = $ini; Default = $def; Cfg = $cfg; State = $state; Use = $use; RigDir = (Join-Path $ld 'scripts\TOS_RigTools') }
  }
  $res
}
function Get-BlenderVersions {
  if (-not (Test-Path $blendRoot)) { return @() }
  Get-ChildItem $blendRoot -Directory | Where-Object { $_.Name -match '^\d+\.\d+$' } |
    ForEach-Object { [pscustomobject]@{ Ver = [version]$_.Name; Name = $_.Name; Dir = $_.FullName } } | Sort-Object Ver -Descending
}
function Find-BlenderExe($verName) {
  if ($Root) { return $null }
  $c = @()
  foreach ($base in @('C:\Program Files\Blender Foundation', 'C:\Program Files (x86)\Blender Foundation', (Join-Path $LOCAL 'Programs'))) {
    if (Test-Path $base) { $c += Get-ChildItem $base -Recurse -Filter blender.exe -ErrorAction SilentlyContinue }
  }
  $m = $c | Where-Object { Test-Path (Join-Path $_.DirectoryName $verName) } | Select-Object -First 1
  if (-not $m) { $m = $c | Where-Object { $_.DirectoryName -match [regex]::Escape($verName) } | Select-Object -First 1 }
  $m
}
function Choose-Blender($ask) {
  $vers = @(Get-BlenderVersions); $ok = @($vers | Where-Object { $_.Ver -ge $MINBLEND })
  if (-not $vers.Count) { return $null }
  $t = $ok | Where-Object { $_.Name -eq $TESTED } | Select-Object -First 1
  if (-not $t -and $ok.Count) {
    $t = $ok[0]
    if ($ask) {
      Say "[주의] 블렌더 $TESTED 이 없어요. 있는 버전: $(($vers | ForEach-Object { $_.Name }) -join ', ')" Yellow
      Say "       이 툴은 블렌더 $TESTED 에서 시험했어요. $($t.Name) 에서도 대부분 동작하지만 보장은 못 해요." Yellow
      if (-not (Ask "       블렌더 $($t.Name) 에 설치할까요? (아니오 = 블렌더 쪽은 건너뜀)")) { return $null }
    }
  }
  $t
}
function Get-BlendDirs($b) { @{ Addons = (Join-Path $b.Dir 'scripts\addons'); Modules = (Join-Path $b.Dir 'scripts\modules'); Pref = (Join-Path $b.Dir 'config\userpref.blend') } }
function Find-MaxExe {
  if ($Root) { return "$maxProg\3dsmax.exe" }
  $p = "$maxProg\3dsmax.exe"; if (Test-Path $p) { return $p }
  foreach ($k in 'HKLM:\SOFTWARE\Autodesk\3dsMax\18.0', 'HKLM:\SOFTWARE\Wow6432Node\Autodesk\3dsMax\18.0') {
    try { $d = (Get-ItemProperty $k -ErrorAction Stop).Installdir; if ($d -and (Test-Path (Join-Path $d '3dsmax.exe'))) { return (Join-Path $d '3dsmax.exe') } } catch { }
  }
  $null
}

# ---------------------------------------------------------------- 설치 목록
# 부품별 (Src, Dst). Dst 폴더는 대상 PC 에 맞춰 정함
function Get-Items($parts, $targets, $blend) {
  $items = @()
  # Seed = Claude Max 가 실행 중에 바꾸는 설정·캐시 파일: 없을 때만 넣고, 있으면 덮어쓰지도 비교하지도 않음
  function Add($src, $dstDir, $part, $recurse = $false) {
    if (-not (Test-Path $src)) { return }
    if ($recurse) {
      foreach ($f in Get-ChildItem $src -File -Recurse) {
        $rel = $f.FullName.Substring($src.Length).TrimStart('\', '/')
        $script:_items += [pscustomobject]@{ Src = $f.FullName; Dst = (Join-Path $dstDir $rel); Part = $part; Seed = $true }
      }
    } else {
      foreach ($f in Get-ChildItem $src -File) { $script:_items += [pscustomobject]@{ Src = $f.FullName; Dst = (Join-Path $dstDir $f.Name); Part = $part; Seed = $false } }
    }
  }
  $script:_items = @()
  $bd = $null; if ($blend) { $bd = Get-BlendDirs $blend }
  foreach ($p in $parts.ToCharArray()) {
    $pp = (Get-ChildItem $payload -Directory | Where-Object { $_.Name -like "$($p)_*" } | Select-Object -First 1).FullName
    foreach ($t in $targets) {
      Add (Join-Path $pp 'max_startup') $t.Use "$p"
      Add (Join-Path $pp 'max_RigTools') $t.RigDir "$p"
    }
    if ($bd) {
      Add (Join-Path $pp 'blender_addons') $bd.Addons "$p"
      Add (Join-Path $pp 'blender_modules') $bd.Modules "$p"
    }
    Add (Join-Path $pp 'templates') (Join-Path $mbRoot 'templates') "$p"
    Add (Join-Path $pp 'blender_mcp') (Join-Path $UP 'blender-mcp-lite') "$p"
    Add (Join-Path $pp 'launch') (Join-Path $mbRoot 'launch') "$p"
    Add (Join-Path $pp 'mcp') (Join-Path $mbRoot 'mcp') "$p"
    Add (Join-Path $pp 'claude_root') $CLAUDE "$p"
    $pe = Join-Path (Join-Path $pp 'profile') 'ENU'
    if (Test-Path $pe) { Add $pe (Join-Path $profDir 'ENU') "$p" $true }
  }
  $script:_items
}
# 묶음 전체(부품 상관없이)의 파일 이름 — 이 이름이면 '옛 파일' 이 아님
function Get-AllNames {
  $h = @{}; Get-ChildItem $payload -File -Recurse | ForEach-Object { $h[$_.Name.ToLower()] = 1 }
  $h['3dsmax_claude.ini'] = 1; $h
}
function Addons-For($parts) {
  $m = @('max_bridge'); if ($parts -match 'B') { $m += @('max_style_rig', 'biped_test_rig', 'sbg_detect', 'ge_jobs') }; if ($parts -match 'C') { $m += 'blender_mcp_addon' }; $m
}

# ---------------------------------------------------------------- 옛 파일 찾기
# 반환: Path, Why, Auto(우리 것 확실 → 자동 정리), System(Program Files)
function Get-OldFiles($targets, $blend) {
  $all = Get-AllNames
  $res = @()
  function Scan($dir, $nameRx, $kind, [bool]$sys = $false) {
    if (-not $dir -or -not (Test-Path -LiteralPath $dir)) { return }
    foreach ($e in Get-ChildItem -LiteralPath $dir -ErrorAction SilentlyContinue) {
      $n = $e.Name
      if ($n -match '^(__pycache__|_backup|_old_moved)$') { continue }
      if ($n -match $OTHER_TOOLS) { continue }      # 1.61: QATool 파일 (따로 설치) 은 건드리지 않음
      if (-not $e.PSIsContainer -and $all[$n.ToLower()] -and -not $sys) { continue }   # 지금 묶음에 있는 이름 = 갱신 대상
      $why = ''; $auto = $false
      if ($n -match $LEFTOVER) { $why = '예전 설치 때 남은 백업·버전 파일'; $auto = $true }
      elseif ($kind -eq 'max' -and $n -match $GE_MAX) { $why = 'GE 리그 툴 (Claude Rig Tools) - TOS_RigTools 와 같은 함수 이름이라 한 Max 에 같이 켜면 충돌. 치우면 백업 폴더로 옮김 (3_RESTORE.bat 로 되돌림)'; $auto = $false }
      elseif ($n -match $nameRx) { $why = '예전 이름의 우리 도구'; $auto = $true; if ($sys -and $all[$n.ToLower()]) { $why = 'Max 설치 폴더에도 같은 도구가 있음 (두 번 읽힘)' } }
      else {
        $txt = ''
        if (-not $e.PSIsContainer -and $e.Length -lt 3MB -and $e.Extension -match '^\.(ms|py)$') { try { $txt = [IO.File]::ReadAllText($e.FullName) } catch { } }
        if ($e.PSIsContainer -and (Test-Path (Join-Path $e.FullName '__init__.py'))) { try { $txt = [IO.File]::ReadAllText((Join-Path $e.FullName '__init__.py')) } catch { } }
        if ($txt -match 'MaxBridgeStruct|MVG_version\s*=|RigToolsStdTpl|BipFit_version\s*=|"author"\s*:\s*"Claude for|bl_idname\s*=\s*"maxbridge\.') { $why = '우리 도구의 옛 사본 (내용이 같은 기능)'; $auto = $true }
        elseif ($kind -ne 'launch' -and $n -match $SIMILAR -and ($e.PSIsContainer -or $e.Extension -match '^\.(ms|mse|mcr|mzp|py)$')) { $why = '이름이 비슷함 (우리 것인지 확실치 않음)' }
      }
      # Max·블렌더가 실제로 읽는 파일인가 (읽는 것만 '충돌'. 나머지는 동작에 영향 없는 찌꺼기)
      $load = $false
      if ($kind -eq 'max') { $load = (-not $e.PSIsContainer) -and ($e.Extension -match '^\.(ms|mse|mcr|mzp)$') }
      elseif ($kind -eq 'addon') { $load = ($e.PSIsContainer -and (Test-Path (Join-Path $e.FullName '__init__.py'))) -or ((-not $e.PSIsContainer) -and $e.Extension -eq '.py') }
      elseif ($kind -eq 'module') { $load = (-not $e.PSIsContainer) -and $e.Extension -eq '.py' }
      if ($why) { $script:_old += [pscustomobject]@{ Path = $e.FullName; Why = $why; Auto = $auto; System = $sys; Load = $load } }
    }
  }
  $script:_old = @()
  foreach ($t in $targets) {
    Scan $t.Use $OURS_MAX 'max'
    if ($t.Default -ne $t.Use) { Scan $t.Default $OURS_MAX 'max' }
    Scan $t.RigDir $OURS_RIGDIR 'rigdir'
  }
  if (-not $Root) { Scan $maxSysStartup $OURS_MAX 'max' $true }
  if ($blend) { $bd = Get-BlendDirs $blend; Scan $bd.Addons $OURS_ADDON 'addon'; Scan $bd.Modules $OURS_MODULE 'module' }
  Scan (Join-Path $UP 'blender-mcp-lite') '^blender_mcp_lite' 'mcp'
  Scan (Join-Path $mbRoot 'launch') $OURS_LAUNCH 'launch'
  Scan (Join-Path $mbRoot 'templates') $OURS_TPL 'templates'
  # 비슷한 이름이지만 우리 것인지 모르는 것: 이 목록에서 지금 묶음 이름은 이미 빠짐. 시스템 폴더의 우리 이름은 System 표시
  $script:_old | Where-Object { -not ($_.System -and -not $_.Auto) }
}

# ---------------------------------------------------------------- Max·포트
function Get-Procs($name) { if ($Root) { return @() }; @(Get-Process -Name $name -ErrorAction SilentlyContinue) }
function Get-PortOwner($port) {
  if ($Root) { return $null }
  try {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
    if ($c) { $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue; return [pscustomobject]@{ Pid = $c.OwningProcess; Name = $(if ($p) { $p.Name } else { '?' }) } }
  } catch {
    $line = netstat -ano -p tcp | Select-String -Pattern ("127\.0\.0\.1:$port\s+\S+\s+LISTENING\s+(\d+)") | Select-Object -First 1
    if ($line) { $id = [int]$line.Matches[0].Groups[1].Value; $p = Get-Process -Id $id -ErrorAction SilentlyContinue; return [pscustomobject]@{ Pid = $id; Name = $(if ($p) { $p.Name } else { '?' }) } }
  }
  $null
}
function Send-Max($code, $port = $PORT, $timeoutMs = 10000) {
  $c = New-Object Net.Sockets.TcpClient
  try {
    $iar = $c.BeginConnect('127.0.0.1', $port, $null, $null)
    if (-not $iar.AsyncWaitHandle.WaitOne(3000)) { return @{ Ok = $false; Err = 'connect-timeout' } }
    $c.EndConnect($iar)
    $s = $c.GetStream(); $s.ReadTimeout = $timeoutMs
    $b = [Text.Encoding]::UTF8.GetBytes($code)
    $s.Write($b, 0, $b.Length); $s.Flush()
    $c.Client.Shutdown([Net.Sockets.SocketShutdown]::Send)
    $r = New-Object IO.StreamReader($s, [Text.Encoding]::UTF8)
    return @{ Ok = $true; Text = $r.ReadToEnd() }
  } catch { return @{ Ok = $false; Err = $_.Exception.Message } }
  finally { $c.Close() }
}
function Run-Blender($exe, $py) {
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("ge_" + [guid]::NewGuid().ToString('N') + '.py')
  [IO.File]::WriteAllText($tmp, $py, (New-Object Text.UTF8Encoding $false))
  $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try { return (& $exe.FullName -b --python $tmp 2>&1 | ForEach-Object { "$_" } | Out-String) }
  finally { $ErrorActionPreference = $old; Remove-Item $tmp -ErrorAction SilentlyContinue }
}

# ---------------------------------------------------------------- 백업
$script:Bk = $null; $script:List = @()
function Begin-Backup {
  if ($script:Bk) { return }
  $script:Bk = Join-Path $backupRoot (Get-Date -Format 'yyyyMMdd_HHmmss')
  New-Item -ItemType Directory -Force -Path $script:Bk | Out-Null
  $script:List = @("# tos_setup 백업 목록", "# 상태`t위치`t백업 안 경로 (REPLACE=원래 파일, NEW=새로 생김, MOVED=치운 옛 파일, INI/PREF/CFG=설정)")
}
function Save-Backup { if ($script:Bk) { [IO.File]::WriteAllLines((Join-Path $script:Bk 'list.txt'), [string[]]$script:List, (New-Object Text.UTF8Encoding $true)) } }
function Backup-File($st, $path) {
  Begin-Backup
  if (Test-Path -LiteralPath $path) {
    $b = Join-Path $script:Bk (Join-Path 'files' (SafeRel $path))
    New-Item -ItemType Directory -Force -Path (Split-Path $b) | Out-Null
    Copy-Item -LiteralPath $path $b -Force
    $script:List += "$st`t$path`t$($b.Substring($script:Bk.Length + 1))"
  } else { $script:List += "$st`t$path`t" }
}
function Move-Old($path) {
  Begin-Backup
  $b = Join-Path $script:Bk (Join-Path '_old_moved' (SafeRel $path))
  New-Item -ItemType Directory -Force -Path (Split-Path $b) | Out-Null
  Move-Item -LiteralPath $path $b
  $script:List += "MOVED`t$path`t$($b.Substring($script:Bk.Length + 1))"
}

# ---------------------------------------------------------------- Claude Max 설정 파일 (이 PC 에 맞춰 만들기)
function Build-ClaudeIni($targets) {
  $tpl = Join-Path (Join-Path (Join-Path $payload 'C_claude') 'profile') '3dsmax_claude.ini.template'
  $ii = Read-IniText $tpl
  $t = $ii.Text
  # 템플릿을 만든 PC 의 사용자 폴더 → 이 PC 사용자 폴더
  $t = [regex]::Replace($t, '(?i)C:\\Users\\[^\\\r\n]+\\', ($UP.TrimEnd('\') + '\').Replace('$', '$$'))
  # 시작 스크립트·스크립트 폴더 = 작업자 Max 가 실제로 쓰는 폴더 (ENU 우선) → Claude Max 도 같은 도구를 읽음 (설정·UI 는 따로)
  $tg = $targets | Where-Object { $_.Lang -eq 'ENU' } | Select-Object -First 1; if (-not $tg) { $tg = $targets | Select-Object -First 1 }
  $t = Set-IniValue $t 'Additional Startup Scripts' $tg.Use
  $t = Set-IniValue $t 'Additional Scripts' (Join-Path $tg.Dir 'scripts')
  $t = Set-IniValue $t 'Additional Macros' (Join-Path $tg.Dir 'usermacros')
  $t = Set-IniValue $t 'Additional Icons' (Join-Path $tg.Dir 'usericons')
  # 설치 경로가 다르면 Program Files 경로도 맞춤
  $mx = Find-MaxExe
  if ($mx) { $dir = Split-Path $mx; if ($dir.TrimEnd('\') -ne $maxProg) { $t = $t.Replace($maxProg, $dir.TrimEnd('\')) } }
  $out = Join-Path ([IO.Path]::GetTempPath()) ('ge_claude_ini_' + [guid]::NewGuid().ToString('N') + '.ini')
  Write-IniText $out $t 'utf16'
  $out
}

# ---------------------------------------------------------------- 고치기
function Fix-Ini($t) {
  Backup-File 'INI' $t.Ini
  $ii = Read-IniText $t.Ini
  Write-IniText $t.Ini (Set-IniValue $ii.Text 'Additional Startup Scripts' $t.Default) $ii.Enc
  $t.Use = $t.Default; $t.State = 'default'
  Say "[고침] $($t.Lang) 3dsmax.ini 시작 스크립트 폴더 -> $(Short $t.Default)" Green
}
function Enable-Addons($exe, $blend, $mods) {
  Backup-File 'PREF' (Get-BlendDirs $blend).Pref
  $list = ($mods | ForEach-Object { "'$_'" }) -join ','
  $py = "import bpy, addon_utils`nfor m in ($list,):`n    try:`n        bpy.ops.preferences.addon_enable(module=m)`n    except Exception as e:`n        print('GE_ERR', m, e)`nbpy.ops.wm.save_userpref()`nfor m in ($list,):`n    print('GE_ON', m, bool(addon_utils.check(m)[1]))`n"
  $out = Run-Blender $exe $py
  $bad = @()
  foreach ($m in $mods) { if ($out -match "GE_ON $m True") { Say "[켬] 블렌더 애드온 $m" Green } else { $bad += $m } }
  if ($bad.Count) {
    Say "[실패] 애드온 자동 켜기 실패: $($bad -join ', ')  -> 블렌더 Edit > Preferences > Add-ons 에서 직접 켜세요." Red
    ($out -split "`n" | Where-Object { $_ -match 'GE_ERR|Traceback|Error' } | Select-Object -First 6) | ForEach-Object { Say "       $_" DarkGray }
  }
  return (-not $bad.Count)
}
function Register-Mcp($exe, $blend) {
  if ($Root) { Say '[시험] MCP 등록 건너뜀' DarkGray; return }
  $cl = Get-Command claude -ErrorAction SilentlyContinue
  if (-not $cl) { Say '[알림] 이 PC 에 Claude Code(claude 명령)가 없어요. Claude 를 쓸 때 CLAUDE_MAX_GUIDE_KO.txt 의 MCP 등록을 하세요.' Yellow; return }
  if (-not $exe) { Say '[알림] 블렌더 파이썬을 못 찾아 MCP 자동 등록을 건너뜀 (안내서 참고).' Yellow; return }
  $py = Join-Path (Split-Path $exe.FullName) "$($blend.Name)\python\bin\python.exe"
  if (-not (Test-Path $py)) { Say "[알림] 블렌더 파이썬이 없어요: $py (MCP 등록 건너뜀)" Yellow; return }
  if (-not (Ask 'Claude Code 에 Max·블렌더 MCP 를 등록할까요? (Claude Code 사용자 설정이 바뀜, 백업함)')) { return }
  Backup-File 'CFG' (Join-Path $UP '.claude.json')
  $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try {
    foreach ($m in @(@('max', (Join-Path $mbRoot 'mcp\max_mcp.py')), @('blender', (Join-Path $UP 'blender-mcp-lite\blender_mcp_lite.py')))) {
      & claude mcp remove --scope user $m[0] 2>&1 | Out-Null
      $o = & claude mcp add --scope user $m[0] -- $py $m[1] 2>&1 | ForEach-Object { "$_" } | Out-String
      if ($LASTEXITCODE -eq 0) { Say "[등록] MCP $($m[0])" Green } else { Say "[실패] MCP $($m[0]) 등록: $($o.Trim())" Red }
    }
  } finally { $ErrorActionPreference = $old }
}

# ---------------------------------------------------------------- 사전 검사·상태
function Pre-Check([bool]$forInstall) {
  if (-not (Test-Path $payload)) { Stop-Here "설치 파일 폴더가 없어요: $payload  (zip 을 모두 풀었는지 확인)" }
  if ($forInstall) {
    $on = @(Get-Procs '3dsmax') + @(Get-Procs 'blender')
    if ($on.Count) { Stop-Here "3ds Max 또는 블렌더가 켜져 있어요. 모두 끄고 다시 실행하세요. (켜진 것: $(($on | ForEach-Object { $_.Name } | Sort-Object -Unique) -join ', '))" }
  }
  if (-not (Test-Path $maxUser)) { Stop-Here "3ds Max 2016 사용자 폴더가 없어요: $maxUser`n       Max 2016 을 한 번 켰다 끈 뒤 다시 실행하세요." }
  $t = @(Get-MaxTargets)
  if (-not $t.Count) { Stop-Here "Max 2016 ENU/KOR 폴더가 없어요: $maxUser`n       Max 2016 을 한 번 켰다 끈 뒤 다시 실행하세요." }
  $t
}
function Save-State($parts, $blend) {
  New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
  $v = ''; if (Test-Path $verFile) { $v = Get-Content $verFile -Encoding UTF8 -TotalCount 1 }
  [IO.File]::WriteAllLines($stateFile, [string[]]@("parts=$parts", "blender=$(if ($blend) { $blend.Name } else { '' })", "version=$v", "date=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"), (New-Object Text.UTF8Encoding $true))
}
function Read-State {
  $h = @{ parts = ''; blender = '' }
  if (Test-Path $stateFile) { Get-Content $stateFile -Encoding UTF8 | ForEach-Object { if ($_ -match '^(\w+)=(.*)$') { $h[$Matches[1]] = $Matches[2] } } }
  $h
}

# ================================================================ Install
function Do-Install {
  Say '=== TOS_RigTools 설치 ===' Cyan
  if (Test-Path $verFile) { Say ('버전: ' + (Get-Content $verFile -Encoding UTF8 -TotalCount 1)) }
  $targets = Pre-Check $true

  Head '0. 설치할 부품'
  $parts = $Parts.ToUpper()
  if ($parts -eq 'AUTO') {
    $parts = (Read-State).parts
    if ($parts) { Say "  지난번에 설치한 부품 그대로: $parts (INSTALL_ALL)" }
  }
  if (-not $parts) {
    $prev = (Read-State).parts
    Say "  A. $($PARTNAME.A)  (항상 설치)"
    $parts = 'A'
    foreach ($p in 'B', 'C') {
      $q = "  $p. $($PARTNAME[$p]) 도 설치할까요?"; if ($prev -match $p) { $q += ' (지금 설치돼 있음 -> 예 = 최신으로 갱신)' }
      if (Ask $q) { $parts += $p }
    }
  }
  if ($parts -notmatch 'A') { $parts = 'A' + $parts }
  $parts = -join ($parts.ToCharArray() | Where-Object { 'ABC'.Contains([string]$_) } | Sort-Object -Unique)
  Say "  -> 설치: $(($parts.ToCharArray() | ForEach-Object { $PARTNAME[[string]$_] }) -join ' / ')" Green

  Head '1. Max 시작 스크립트 폴더 (작업자 Max 설정)'
  foreach ($t in $targets) {
    switch ($t.State) {
      'default' { Say "[OK]   $($t.Lang): $(Short $t.Use)" Green }
      'custom'  { Say "[알림] $($t.Lang): 3dsmax.ini 가 다른 폴더를 씀 -> 그 폴더에 설치: $($t.Use)" Yellow }
      'broken'  {
        Say "[문제] $($t.Lang): 3dsmax.ini 의 시작 스크립트 폴더가 없어요: $($t.Cfg)" Red
        Say '       이대로면 Max 가 도구를 읽지 못해요 (다른 PC 설정을 복사해 온 경우 흔함).' Red
        if (Ask "       기본 폴더($(Short $t.Default))로 고칠까요? 원래 ini 는 백업해요") { Fix-Ini $t }
        else { Say '       고치지 않음 -> 기본 폴더에 설치하지만 Max 가 못 읽을 수 있어요.' Yellow; $t.Use = $t.Default }
      }
    }
  }

  Head '2. 블렌더'
  $blend = Choose-Blender $true
  $exe = $null
  if ($blend) {
    Say "[OK]   블렌더 $($blend.Name): $(Short $blend.Dir)" Green
    $exe = Find-BlenderExe $blend.Name
    if (-not $exe -and -not $Root) { Say "[주의] 블렌더 $($blend.Name) 실행 파일을 못 찾음 -> 설치 뒤 애드온을 직접 켜야 해요." Yellow }
  } else {
    $vers = @(Get-BlenderVersions)
    if ($vers.Count) { Say "[건너뜀] 쓸 수 있는 블렌더 없음 (있는 버전: $(($vers | ForEach-Object { $_.Name }) -join ', '), $MINBLEND 이상 필요). Max 쪽만 설치해요." Yellow }
    else { Say '[건너뜀] 블렌더 사용자 폴더 없음 (블렌더를 한 번도 안 켰거나 없음). Max 쪽만 설치해요.' Yellow }
  }

  Head '3. 예전 파일 정리 (갱신·충돌 방지)'
  $old = @(Get-OldFiles $targets $blend)
  $nAuto = 0
  foreach ($o in $old) {
    if ($o.System) { Say "[문제] $(Short $o.Path)  ($($o.Why))" Red; Say '       Program Files 안이라 관리자 권한이 필요해요. IT 담당자에게 이 파일을 다른 곳으로 옮겨 달라고 하세요.' Yellow; continue }
    if ($o.Auto) { Move-Old $o.Path; $nAuto++; Say "[치움] $(Short $o.Path)  ($($o.Why))" Yellow; continue }
    Say "[확인] $(Short $o.Path)  ($($o.Why))" Yellow
    if (Ask '       우리 도구의 옛 파일이면 치울까요? (작업자가 따로 쓰는 파일이면 N)') { Move-Old $o.Path; Say '       치움' Yellow } else { Say '       그대로 둠' DarkGray }
  }
  if (-not $old.Count) { Say '[OK]   치울 옛 파일 없음' Green } elseif ($nAuto) { Say "       자동으로 치운 옛 파일 $nAuto 개 (백업 폴더에 보관 -> 되돌리기 가능)" DarkGray }
  # 설치 안 하는 부품이 예전 버전으로 남아 있으면 (새 Max Bridge 와 맞지 않을 수 있음) 갱신 여부를 물음
  foreach ($p in 'B', 'C') {
    if ($parts -match $p) { continue }
    $stale = @(Get-Items $p $targets $blend | Where-Object { -not $_.Seed -and (Test-Path -LiteralPath $_.Dst) -and ((Hash $_.Dst) -ne (Hash $_.Src)) })
    if ($stale.Count) {
      Say "[주의] $($PARTNAME[$p]) 의 예전 버전이 설치돼 있어요 ($($stale.Count)개 파일). 새 Max Bridge 와 맞지 않을 수 있어요." Yellow
      if (Ask "       $($PARTNAME[$p]) 도 최신으로 갱신할까요?") { $parts = -join (($parts + $p).ToCharArray() | Sort-Object -Unique) }
    }
  }

  Head "4. 포트 $PORT (작업자 Max 연결 통로)"
  if ($Root) { Say '[시험] 건너뜀' DarkGray }
  else {
    $own = Get-PortOwner $PORT
    if ($own) { Say "[문제] Max 가 꺼져 있는데 $PORT 포트를 '$($own.Name)'(PID $($own.Pid)) 가 쓰고 있어요 -> Max Bridge 연결이 막혀요. 그 프로그램을 끄거나 IT 담당자에게 문의하세요." Red }
    else { Say "[OK]   $PORT 포트 비어 있음" Green }
  }

  Head '5. 파일 설치·갱신'
  $dirs = @('exchange', 'standardized', 'templates')   # 1.61: fixtools_backup 은 QATool 설치기가 만듦
  foreach ($d in $dirs) {
    $p = Join-Path $mbRoot $d
    if (-not (Test-Path $p)) {
      try { New-Item -ItemType Directory -Force -Path $p | Out-Null; Say "[새 폴더] $p" Green }
      catch { Say "[문제] 폴더를 못 만들었어요: $p ($($_.Exception.Message))" Red }
    }
  }
  $items = @(Get-Items $parts $targets $blend)
  if ($parts -match 'C') {
    $gen = Build-ClaudeIni $targets
    $items += [pscustomobject]@{ Src = $gen; Dst = $claudeIni; Part = 'C'; Seed = $false }
    New-Item -ItemType Directory -Force -Path (Join-Path $profDir 'ENU\temp') | Out-Null
  }
  $cnt = @{ NEW = 0; REPLACE = 0; SAME = 0 }
  foreach ($i in $items) {
    $st = 'NEW'
    if (Test-Path -LiteralPath $i.Dst) { if ($i.Seed -or ((Hash $i.Dst) -eq (Hash $i.Src))) { $st = 'SAME' } else { $st = 'REPLACE' } }
    $cnt[$st]++
    if ($st -eq 'SAME') { continue }
    Backup-File $st $i.Dst
    New-Item -ItemType Directory -Force -Path (Split-Path $i.Dst) | Out-Null
    Copy-Item -LiteralPath $i.Src $i.Dst -Force
    $tag = '[새로]'; if ($st -eq 'REPLACE') { $tag = '[갱신]' }
    Say "$tag $(Short $i.Dst)" Green
  }
  Say "  새로 $($cnt.NEW) / 갱신 $($cnt.REPLACE) / 이미 최신 $($cnt.SAME)" Cyan
  if ($parts -match 'C') {
    $mx = Find-MaxExe; $mxt = Join-Path $profDir 'maxexe.txt'
    if ($mx -and ($mx -ne "$maxProg\3dsmax.exe")) { Backup-File 'CFG' $mxt; [IO.File]::WriteAllText($mxt, $mx, [Text.Encoding]::Default); Say "[설정] Claude Max 실행 파일 위치: $mx" Green }
    elseif (-not $mx) { Say "[주의] 3dsmax.exe 를 못 찾았어요. Claude Max 를 켜려면 $mxt 에 3dsmax.exe 전체 경로를 한 줄로 적으세요." Yellow }
  }

  Head '6. 블렌더 애드온 켜기'
  if ($blend -and $exe) { [void](Enable-Addons $exe $blend (Addons-For $parts)) }
  elseif ($blend -and -not $Root) { Say "[할 일] 블렌더 $($blend.Name) 를 켜고 Edit > Preferences > Add-ons 에서 켜기: $((Addons-For $parts) -join ', ')" Yellow }
  else { Say '[건너뜀]' DarkGray }

  if ($parts -match 'C') { Head '7. Claude Code MCP 등록 (선택)'; Register-Mcp $exe $blend }

  Save-Backup; Save-State $parts $blend
  if ($script:Bk) { Say ''; Say "백업 폴더: $($script:Bk)  (되돌리기 = 3_RESTORE.bat)" Cyan }
  Say ''; Say '=== 설치 확인 ===' Cyan
  return (Do-Check -AfterInstall)
}

# ================================================================ Check (진단)
function Do-Check([switch]$AfterInstall) {
  $script:Results = @()
  if (-not $AfterInstall) { Say '=== TOS_RigTools 점검 ===' Cyan; if (Test-Path $verFile) { Say ('버전: ' + (Get-Content $verFile -Encoding UTF8 -TotalCount 1)) } }
  $targets = Pre-Check $false
  $st = Read-State
  $parts = $st.parts
  if (-not $parts) {
    # 기록이 없으면 PC 에 있는 것으로 짐작 (예전 설치기로 깐 PC 등)
    $parts = 'A'
    if ($targets | Where-Object { Test-Path -LiteralPath (Join-Path $_.Use 'TOS_RigToolsStd.ms') }) { $parts += 'B' }
    if (Test-Path $claudeIni) { $parts += 'C' }
    Result 'WARN' '이 설치기의 설치 기록이 없음' "PC 에 있는 것으로 짐작해 점검: $parts" '1_INSTALL.bat 을 한 번 실행하면 기록이 생김'
  }
  Say "점검 부품: $(($parts.ToCharArray() | ForEach-Object { $PARTNAME[[string]$_] }) -join ' / ')" DarkGray
  $blend = $null; if ($st.blender) { $blend = Get-BlenderVersions | Where-Object { $_.Name -eq $st.blender } | Select-Object -First 1 }
  if (-not $blend) { $blend = Choose-Blender $false }

  Say ''; Say '[파일·설정]' Cyan
  $items = @(Get-Items $parts $targets $blend)
  foreach ($p in $parts.ToCharArray()) {
    $pi = @($items | Where-Object { $_.Part -eq [string]$p })
    $bad = @($pi | Where-Object { -not (Test-Path -LiteralPath $_.Dst) -or (-not $_.Seed -and ((Hash $_.Dst) -ne (Hash $_.Src))) })
    if (-not $bad.Count) { Result 'OK' "$($PARTNAME[[string]$p]): 파일 $($pi.Count)개 = 묶음" }
    else { Result 'FAIL' "$($PARTNAME[[string]$p]): $($bad.Count)/$($pi.Count)개 없거나 다름 ($((($bad | Select-Object -First 2) | ForEach-Object { Short $_.Dst }) -join ', '))" '설치가 덜 됐거나 다른 버전으로 덮어씀' 'Max·블렌더를 끄고 1_INSTALL.bat 다시 실행' }
  }
  foreach ($t in $targets) {
    if ($t.State -eq 'broken') { Result 'FAIL' "작업자 Max $($t.Lang) 시작 스크립트 폴더" "3dsmax.ini 가 없는 폴더를 가리킴: $($t.Cfg)" 'Max 를 끄고 1_INSTALL.bat -> 고칠지 물으면 Y' }
    elseif ($t.State -eq 'custom') { Result 'WARN' "작업자 Max $($t.Lang) 시작 스크립트 폴더 = $($t.Use)" '3dsmax.ini 가 기본이 아닌 폴더를 씀 (그 폴더에 설치함)' }
    else { Result 'OK' "작업자 Max $($t.Lang) 시작 스크립트 폴더 = 기본값" }
  }
  $old = @(Get-OldFiles $targets $blend)
  $junk = @($old | Where-Object { -not $_.Load -and -not $_.System })
  $live = @($old | Where-Object { $_.Load -or $_.System })
  if (-not $old.Count) { Result 'OK' '옛 파일·중복 파일 없음' }
  foreach ($o in $live) {
    $fx = 'Max·블렌더를 끄고 1_INSTALL.bat (우리 옛 파일은 자동으로 치움)'
    if ($o.System) { $fx = 'Program Files 안이라 IT 담당자에게 옮겨 달라고 요청' }
    if ($o.Why -like 'GE 리그 툴*') { Result 'FAIL' "GE 리그 툴이 같이 읽힘: $(Short $o.Path)" $o.Why 'Max·블렌더를 끄고 1_INSTALL.bat 에서 이 파일을 치우기(Y)' }
    elseif ($o.Auto -or $o.System) { Result 'FAIL' "중복으로 읽히는 파일: $(Short $o.Path)" "$($o.Why) -> 같은 도구가 두 번 읽혀 오류가 날 수 있음" $fx }
    else { Result 'WARN' "확인 필요: $(Short $o.Path)" $o.Why '우리 도구의 옛 파일이면 1_INSTALL.bat 에서 Y, 작업자가 따로 쓰는 파일이면 그대로 두면 됨' }
  }
  if ($junk.Count) {
    $ex3 = ($junk | Select-Object -First 3 | ForEach-Object { Split-Path $_.Path -Leaf }) -join ', '
    Result 'WARN' "예전 설치가 남긴 백업·찌꺼기 $($junk.Count)개 (예: $ex3)" 'Max·블렌더가 읽지 않는 파일이라 동작에는 영향 없음' '정리하려면 Max·블렌더를 끄고 1_INSTALL.bat (자동으로 치움, 백업 폴더에 보관)'
    $script:JunkList = $junk
  }
  $ex = Join-Path $mbRoot 'exchange'
  if (-not (Test-Path -LiteralPath $ex)) { Result 'FAIL' "주고받기 폴더 없음: $ex" '설치가 덜 됨' '1_INSTALL.bat 실행' }
  else { try { $tf = Join-Path $ex '_write_test.tmp'; [IO.File]::WriteAllText($tf, 'x'); Remove-Item $tf; Result 'OK' "주고받기 폴더 쓰기 가능: $ex" } catch { Result 'FAIL' "주고받기 폴더에 쓸 수 없음: $ex" $_.Exception.Message '블렌더 Max Bridge 설정의 Exchange folder 를 쓸 수 있는 폴더로 바꾸기' } }

  # C: Claude Max 환경 + 작업자 Max 보호
  if ($parts -match 'C') {
    if (-not (Test-Path $claudeIni)) { Result 'FAIL' 'Claude Max 설정 파일 없음' $claudeIni '1_INSTALL.bat 에서 C 선택' }
    else {
      $ct = (Read-IniText $claudeIni).Text
      $cs = Get-IniValue $ct 'Additional Startup Scripts'
      $foreign = [regex]::Matches($ct, '(?i)C:\\Users\\([^\\\r\n]+)\\') | ForEach-Object { $_.Groups[1].Value } | Where-Object { $UP -notmatch ("\\" + [regex]::Escape($_) + '$') } | Sort-Object -Unique
      if ($foreign) { Result 'FAIL' 'Claude Max 설정에 다른 PC 사용자 경로가 있음' "C:\Users\$($foreign -join ', ')" '1_INSTALL.bat 에서 C 를 다시 설치 (이 PC 에 맞춰 다시 만듦)' }
      elseif (-not $cs -or -not (Test-Path -LiteralPath (Join-Path $cs 'MaxBridge.ms'))) { Result 'FAIL' 'Claude Max 가 Max Bridge 를 못 읽음' "시작 스크립트 폴더: $cs" '1_INSTALL.bat 에서 C 를 다시 설치' }
      else { Result 'OK' 'Claude Max 설정 = 이 PC 경로, 작업자 Max 와 같은 도구를 읽음 (설정·UI 는 따로)' }
    }
    $mx = Find-MaxExe; $mxt = Join-Path $profDir 'maxexe.txt'
    if (Test-Path $mxt) { $mx = (Get-Content $mxt -TotalCount 1).Trim() }
    if (-not $Root) { if ($mx -and (Test-Path $mx)) { Result 'OK' "3dsmax.exe: $mx" } else { Result 'FAIL' '3dsmax.exe 를 찾을 수 없음' 'Max 가 기본 위치에 없음' "$mxt 에 3dsmax.exe 전체 경로를 한 줄로 적기" } }
    foreach ($t in $targets) {
      if (Test-Path -LiteralPath $t.Ini) { if ((Read-IniText $t.Ini).Text -match [regex]::Escape($profDir)) { Result 'FAIL' "작업자 Max $($t.Lang) 설정이 Claude Max 폴더를 가리킴" '설정이 섞임' '3_RESTORE.bat 또는 담당자 문의' } }
    }
    if (-not $Root) {
      $cl = Get-Command claude -ErrorAction SilentlyContinue
      if (-not $cl) { Result 'SKIP' 'Claude Code MCP 등록' '이 PC 에 claude 명령 없음' '' }
      else {
        $old2 = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        $ml = & claude mcp list 2>&1 | ForEach-Object { "$_" } | Out-String; $ErrorActionPreference = $old2
        foreach ($n in 'max', 'blender') { if ($ml -match "(?m)^$n\b") { Result 'OK' "Claude Code MCP '$n' 등록됨" } else { Result 'WARN' "Claude Code MCP '$n' 등록 안 됨" '' '1_INSTALL.bat 에서 MCP 등록 Y, 또는 CLAUDE_MAX_GUIDE_KO.txt 참고' } }
      }
    }
  }

  # 블렌더
  Say ''; Say '[블렌더]' Cyan
  $exe = $null; $on = @{}
  if (-not $blend) { Result 'WARN' '블렌더' "$MINBLEND 이상 블렌더 사용자 폴더 없음 -> 블렌더 쪽 미설치" '블렌더를 설치해 한 번 켰다 끈 뒤 1_INSTALL.bat' }
  else {
    if ($blend.Name -ne $TESTED) { Result 'WARN' "블렌더 $($blend.Name) 사용" "시험한 버전은 $TESTED" }
    $exe = Find-BlenderExe $blend.Name
    if (-not $exe) { if (-not $Root) { Result 'WARN' "블렌더 $($blend.Name) 실행 파일 못 찾음" '애드온 켜짐을 자동 확인 못 함' "블렌더 Edit > Preferences > Add-ons 에서 확인: $((Addons-For $parts) -join ', ')" } }
    else {
      $mods = Addons-For $parts; $list = ($mods | ForEach-Object { "'$_'" }) -join ','
      $out = Run-Blender $exe "import addon_utils`nfor m in ($list,):`n    print('GE_ON', m, bool(addon_utils.check(m)[1]))`n"
      $off = @()
      foreach ($m in $mods) { if ($out -match "GE_ON $m True") { $on[$m] = $true } else { $off += $m } }
      if (-not $off.Count) { Result 'OK' "블렌더 $($blend.Name) 애드온 켜짐: $($mods -join ', ')" }
      else {
        Result 'FAIL' "블렌더 애드온 꺼짐: $($off -join ', ')" '설치 뒤 안 켜졌거나 사용자가 끔' '아래에서 Y 또는 블렌더 Edit > Preferences > Add-ons 에서 켜기'
        if (@(Get-Procs 'blender').Count) { Say '       (블렌더가 켜져 있어 자동으로 켜지 않아요. 블렌더를 끄고 2_CHECK.bat 다시 실행)' Yellow }
        elseif (Ask '       지금 켤까요? (블렌더 설정은 백업해요)') { if (Enable-Addons $exe $blend $off) { $script:Results[-1].St = 'OK'; foreach ($m in $off) { $on[$m] = $true } }; Save-Backup }
      }
    }
  }

  # Max 연결
  Say ''; Say '[Max 연결]' Cyan
  if ($Root) { Result 'SKIP' 'Max 연결 시험 (시험 모드)' }
  else {
    $mp = @(Get-Procs '3dsmax')
    $own = Get-PortOwner $PORT
    if (-not $mp.Count) { Result 'SKIP' 'Max 연결 시험' 'Max 가 꺼져 있음' 'Max 를 켜고(파일 하나 열어도 됨) 2_CHECK.bat 을 다시 실행하면 연결·도구 로드까지 확인' }
    else {
      $markers = @('MVG_version')
      if ($parts -match 'B') { $markers += @('BipFit_version', 'BipConvert_version', 'TOS_RigTools_version', 'RigToolsTpl', 'RigToolsStd') }
      $arr = ($markers | ForEach-Object { '"' + $_ + '"' }) -join ','
      $code = "(local m = """"; for n in #($arr) do (if (execute n) == undefined do m += n + "" ""); ""pong "" + MaxBridge.version + "" |missing="" + m + ""|"" + MaxBridge.status())"
      $r = Send-Max $code
      if ($r.Ok -and $r.Text -match '^pong\s+(\S+)\s+\|missing=(.*?)\|(.*)$') {
        $ver = $Matches[1]; $miss = $Matches[2].Trim(); $status = $Matches[3]
        Result 'OK' "작업자 Max 연결 OK (MaxBridge v$ver, 포트 $PORT)"
        if ($status -match 'env=(\S+)' -and $Matches[1] -ne '(none)') { Result 'FAIL' "포트 $PORT 를 Claude Max 가 쓰고 있음" "MAXBRIDGE_PORT=$($Matches[1]) 인 Max 가 작업자 포트를 잡음" 'Claude Max 를 끄고 작업자 Max 를 다시 켜기' }
        if ($miss -match 'MVG_version') { Result 'FAIL' 'VirusGuard 안 켜짐' 'Max 시작 때 !MaxVirusGuard.ms 를 못 읽음' 'Max 리스너(F11)의 [VirusGuard] 줄·빨간 오류를 캡처해 담당자에게' } else { Result 'OK' 'VirusGuard 켜짐' }
        if ($parts -match 'B') {
          $mm = ($miss -split '\s+' | Where-Object { $_ -and $_ -ne 'MVG_version' })
          if ($mm) { Result 'FAIL' "리그 툴 일부가 Max 에 안 읽힘: $($mm -join ', ')" '시작 스크립트 오류 또는 파일 누락' 'Max 리스너(F11)의 빨간 오류 확인 -> 캡처해 담당자에게' } else { Result 'OK' 'Max 리그 툴 모두 읽힘' }
        }
      } elseif (-not $own) {
        Result 'FAIL' '작업자 Max 연결 안 됨' "Max 는 켜져 있는데 $PORT 포트를 연 곳이 없음 -> Max 가 MaxBridge.ms 를 못 읽음" "1) 위 '시작 스크립트 폴더'·'옛 파일' 항목 확인  2) Max 리스너(F11)에서 [MaxBridge] 줄·빨간 오류 확인  3) Max 다시 켜기"
      } elseif ($own.Name -ne '3dsmax') {
        Result 'FAIL' '작업자 Max 연결 안 됨' "$PORT 포트를 Max 가 아닌 '$($own.Name)'(PID $($own.Pid)) 가 씀" '그 프로그램을 끄고 Max 다시 켜기'
      } else {
        Result 'FAIL' 'Max 가 포트는 열었지만 답이 없음' "Max 에 대화상자가 떠 있거나 작업 중 ($($r.Err))" 'Max 의 열린 창(경고·저장 등)을 닫고 2_CHECK.bat 다시 실행'
      }
      if ($r.Ok -and $exe -and $on['max_bridge']) {
        $out = Run-Blender $exe "import addon_utils`naddon_utils.enable('max_bridge', default_set=False)`nimport max_bridge`ntry:`n    print('GE_PING', max_bridge.ping())`nexcept Exception as e:`n    print('GE_PING_ERR', e)`n"
        if ($out -match 'GE_PING pong') { Result 'OK' '블렌더 -> Max 연결 OK' }
        else { Result 'FAIL' '블렌더 -> Max 연결 실패' (($out -split "`n" | Where-Object { $_ -match 'GE_PING_ERR|Error' } | Select-Object -First 1) -as [string]) 'Windows 방화벽·보안 프로그램이 127.0.0.1 연결을 막는지 IT 담당자에게 확인' }
      }
    }
    if ($parts -match 'C') {
      $cm = @(); for ($p = 9878; $p -le 9899; $p++) { if (Get-PortOwner $p) { $cm += $p } }
      if (-not $cm.Count) { Result 'SKIP' 'Claude Max 연결 시험' 'Claude Max 가 꺼져 있음' 'C:\claude\max_blender\launch\Max_Claude_multi.bat 로 켠 뒤 2_CHECK.bat' }
      foreach ($p in $cm) {
        $r2 = Send-Max 'MaxBridge.status()' $p
        if ($r2.Ok -and $r2.Text -match "env=$p") { Result 'OK' "Claude Max 연결 OK (포트 $p, 작업자 Max 와 분리)" }
        else { Result 'FAIL' "포트 $p 응답 이상" (($r2.Text, $r2.Err) -join ' ') 'Claude Max 를 Max_Claude_multi.bat 으로만 켜기' }
      }
    }
  }

  # 요약
  $f = @($script:Results | Where-Object { $_.St -eq 'FAIL' }).Count
  $w = @($script:Results | Where-Object { $_.St -eq 'WARN' }).Count
  $rep = Join-Path $backupRoot ("check_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.txt')
  try {
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    $lines = @("TOS_RigTools 점검 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  PC=$env:COMPUTERNAME  USER=$env:USERNAME  부품=$parts")
    $lines += ($script:Results | ForEach-Object { "[$($_.St)] $($_.What)" + $(if ($_.Why) { " | 원인: $($_.Why)" } else { '' }) + $(if ($_.Fix) { " | 해결: $($_.Fix)" } else { '' }) })
    if ($script:JunkList) { $lines += ''; $lines += '# 백업·찌꺼기 목록 (동작 영향 없음)'; $lines += ($script:JunkList | ForEach-Object { "  $($_.Path)" }) }
    [IO.File]::WriteAllLines($rep, [string[]]$lines, (New-Object Text.UTF8Encoding $true))
  } catch { $rep = '' }
  Say ''
  if ($rep) { Say "점검 기록: $rep  (문제가 있으면 이 파일을 담당자에게 보내 주세요)" DarkGray }
  if ($f -eq 0) {
    if (@($script:Results | Where-Object { $_.St -eq 'SKIP' -and $_.What -eq 'Max 연결 시험' }).Count) { Say "결과: OK (파일·설정 정상, 주의 $w 개). Max 를 켠 상태에서 2_CHECK.bat 을 한 번 더 실행하면 연결·도구 로드까지 확인해요." Green }
    else { Say "결과: OK (주의 $w 개)" Green }
    return 0
  }
  Say "결과: FAIL ($f 개 문제, 위 '원인/해결' 참고)" Red
  return 1
}

# ================================================================ Restore
function Do-Restore {
  Say '=== 되돌리기 ===' Cyan
  if (@(Get-Procs '3dsmax').Count -or @(Get-Procs 'blender').Count) { Stop-Here '3ds Max 또는 블렌더가 켜져 있어요. 모두 끄고 다시 실행하세요.' }
  if (-not (Test-Path $backupRoot)) { Say '되돌릴 백업이 없어요.' Yellow; Say '결과: 할 것 없음'; return 0 }
  $bk = Get-ChildItem $backupRoot -Directory | Where-Object { (Test-Path (Join-Path $_.FullName 'list.txt')) -and -not (Test-Path (Join-Path $_.FullName '_restored.txt')) } | Sort-Object Name -Descending | Select-Object -First 1
  if (-not $bk) { Say '되돌릴 백업이 없어요 (모두 이미 되돌림).' Yellow; Say '결과: 할 것 없음'; return 0 }
  Say "백업: $($bk.FullName)"
  if (-not (Ask '이 백업 시점(그 설치 직전)으로 되돌릴까요?')) { Say '결과: 취소'; return 0 }
  $lines = @(Get-Content (Join-Path $bk.FullName 'list.txt') -Encoding UTF8 | Where-Object { $_ -and -not $_.StartsWith('#') })
  [array]::Reverse($lines)
  $bad = 0; $n = 0
  foreach ($ln in $lines) {
    $f = $ln -split "`t"; $st = $f[0]; $dst = $f[1]; $rel = ''; if ($f.Count -gt 2) { $rel = $f[2] }
    try {
      if ($rel -and $st -ne 'MOVED') { New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null; Copy-Item -LiteralPath (Join-Path $bk.FullName $rel) $dst -Force; Say "[복구]   $(Short $dst)" Green }
      elseif ($st -eq 'MOVED') { New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null; Move-Item -LiteralPath (Join-Path $bk.FullName $rel) $dst; Say "[제자리] $(Short $dst)" Green }
      elseif (Test-Path -LiteralPath $dst) {
        $t = Join-Path $bk.FullName (Join-Path '_new_files' (SafeRel $dst))
        New-Item -ItemType Directory -Force -Path (Split-Path $t) | Out-Null
        if (Test-Path -LiteralPath $t) { $t = $t + '.' + (Get-Date -Format 'HHmmss') }
        Move-Item -LiteralPath $dst $t; Say "[옮김]   $(Short $dst) -> 백업 폴더 _new_files" Yellow
      }
      $n++
    } catch { $bad++; Say "[실패]   $dst : $($_.Exception.Message)" Red }
  }
  [IO.File]::WriteAllText((Join-Path $bk.FullName '_restored.txt'), "되돌림 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`r`n", (New-Object Text.UTF8Encoding $true))
  # 설치 기록: 더 이전 설치 기록이 없으면 지움(옮김)
  if (Test-Path $stateFile) { Move-Item -LiteralPath $stateFile (Join-Path $bk.FullName 'installed.txt.after') -Force }
  Say ''
  if ($bad -eq 0) { Say "결과: OK ($n 개 되돌림. 새로 생겼던 파일은 지우지 않고 $($bk.FullName)\_new_files 로 옮김)" Green; return 0 }
  Say "결과: FAIL ($bad 개 실패)" Red; return 1
}

# ================================================================ main
if ($Root) { Say "[시험 모드] 대상 = $Root" Yellow }
try {
  switch ($Mode) {
    'Install' { $rc = Do-Install }
    'Check'   { $rc = Do-Check }
    'Restore' { $rc = Do-Restore }
  }
} catch {
  Save-Backup
  Say ''; Say "[오류] 예상하지 못한 문제: $($_.Exception.Message)" Red
  Say "       위치: $($_.InvocationInfo.ScriptLineNumber)행  $($_.InvocationInfo.Line.Trim())" DarkGray
  if ($script:Bk) { Say "       지금까지 바꾼 것은 백업돼 있어요 -> 3_RESTORE.bat 으로 되돌릴 수 있어요. ($($script:Bk))" Yellow }
  Say '결과: 오류 (이 화면을 캡처해 담당자에게 보내 주세요)' Red
  exit 3
}
exit ([int]($rc | Select-Object -Last 1))
