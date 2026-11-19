# make_zip.ps1 (2026-11-13, TOS_RigTools) - this tool folder -> Desktop\TOS_RigTools_<version>.zip
#   One top folder TOS_RigTools_<version> inside, so unzipping never meets an old folder (no renaming).
#   Left out: _logs, .git, *.bak*, Thumbs.db. If _setup\manifest.txt exists, stops when a payload file differs from it.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$ver = Get-Content (Join-Path $root 'VERSION.txt') -Encoding UTF8 -TotalCount 1
$tag = if ($ver -match 'TOS_RigTools (\d+\.\d+)') { 'v' + $Matches[1] } elseif ($ver -match '\d{4}-\d{2}-\d{2}\w*') { $Matches[0] } else { Get-Date -Format 'yyyy-MM-dd' }
$man = Join-Path $PSScriptRoot 'manifest.txt'
if (Test-Path $man) {
  $payload = Join-Path $PSScriptRoot 'payload'; $bad = @(); $n = 0
  foreach ($ln in Get-Content $man -Encoding UTF8) {
    if ($ln -match '^#' -or -not $ln.Trim()) { continue }
    $p = $ln -split "`t"; $f = Join-Path $payload $p[0]; $n++
    if (-not (Test-Path -LiteralPath $f)) { $bad += "없음 $($p[0])"; continue }
    if ((Get-Item -LiteralPath $f).Length -ne [int64]$p[1] -or (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash -ne $p[2]) { $bad += "다름 $($p[0])" }
  }
  if ($bad.Count) { Write-Host "[멈춤] manifest 와 다른 파일 $($bad.Count)개:" -ForegroundColor Red; $bad | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }; exit 2 }
  Write-Host "[OK] 묶음 파일 $n 개 = manifest" -ForegroundColor Green
}
$dest = [Environment]::GetFolderPath('Desktop'); if (-not $dest) { $dest = $root }
$name = "TOS_RigTools_$tag"
$out = Join-Path $dest "$name.zip"; $i = 2
while (Test-Path -LiteralPath $out) { $out = Join-Path $dest "${name}_$i.zip"; $i++ }
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::Open($out, 'Create'); $cnt = 0
try {
  foreach ($f in Get-ChildItem -LiteralPath $root -Recurse -File -Force) {
    $rel = $f.FullName.Substring($root.Length + 1)
    if ($rel -match '^(_logs|\.git)(\\|$)' -or $f.Name -match '(?i)\.bak|^Thumbs\.db$') { continue }
    [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $f.FullName, ($name + '/' + ($rel -replace '\\', '/')), 'Optimal'); $cnt++
  }
} finally { $zip.Dispose() }
Write-Host ("[OK] {0}  (파일 {1}개, {2:N1} MB)" -f $out, $cnt, ((Get-Item -LiteralPath $out).Length / 1MB)) -ForegroundColor Green
Write-Host '다른 PC 에서: 아무 곳에나 압축 풀기 -> 새로 생긴 폴더의 INSTALL_ALL.bat 더블클릭 (Max·블렌더 끄고)' -ForegroundColor Cyan
exit 0
