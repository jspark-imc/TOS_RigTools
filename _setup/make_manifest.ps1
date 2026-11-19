# make_manifest.ps1 — _setup\payload 의 파일 목록(manifest.txt)을 다시 만든다  2026-10-28
#   payload 를 고친 뒤 실행 (powershell -File _setup\make_manifest.ps1). 손으로 manifest.txt 를 고치지 않는다.
#   형식: relative path<TAB>size<TAB>SHA256 (tos_setup.ps1 Check-Payload 가 읽음). UTF-8 BOM, CRLF
#   -Check : 쓰지 않고 지금 manifest.txt 가 payload 와 맞는지만 확인 (맞으면 exit 0, 다르면 1)
param([switch]$Check)
$ErrorActionPreference = 'Stop'
$here     = $PSScriptRoot
$payload  = Join-Path $here 'payload'
$manifest = Join-Path $here 'manifest.txt'
$verFile  = Join-Path (Split-Path $here) 'VERSION.txt'
if (-not (Test-Path $payload)) { Write-Host "[멈춤] payload 폴더가 없어요: $payload" -ForegroundColor Red; exit 2 }

$ver = if (Test-Path $verFile) { (Get-Content $verFile -Encoding UTF8 -TotalCount 1).Trim() } else { '(VERSION.txt 없음)' }
$sha = [Security.Cryptography.SHA256]::Create()
$lines = @("# $ver payload manifest: relative path<TAB>size<TAB>SHA256")
$files = Get-ChildItem $payload -File -Recurse | Where-Object { $_.FullName -notmatch '\\__pycache__\\' -and $_.Name -notmatch '(?i)\.bak' }
foreach ($f in ($files | Sort-Object { $_.FullName.Substring($payload.Length + 1) })) {
  $rel = $f.FullName.Substring($payload.Length + 1)
  $fs = [IO.File]::OpenRead($f.FullName)
  try { $h = [BitConverter]::ToString($sha.ComputeHash($fs)) -replace '-', '' } finally { $fs.Dispose() }
  $lines += "$rel`t$($f.Length)`t$h"
}
$text = ($lines -join "`r`n") + "`r`n"

if ($Check) {
  $old = if (Test-Path $manifest) { (Get-Content $manifest -Encoding UTF8 | Where-Object { $_ -and -not $_.StartsWith('#') }) } else { @() }
  $diff = @(Compare-Object @($old) @($lines | Select-Object -Skip 1))
  if ($diff.Count) { Write-Host "manifest 가 payload 와 달라요 ($($diff.Count)줄)" -ForegroundColor Yellow; $diff | ForEach-Object { Write-Host "  $($_.SideIndicator) $($_.InputObject)" }; exit 1 }
  Write-Host "manifest OK ($($files.Count)개)" -ForegroundColor Green; exit 0
}
[IO.File]::WriteAllText($manifest, $text, (New-Object Text.UTF8Encoding $true))
Write-Host "manifest.txt 다시 만듦: $($files.Count)개" -ForegroundColor Green
