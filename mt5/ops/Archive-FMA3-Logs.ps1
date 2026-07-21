# Archive-FMA3-Logs.ps1 — capture the daily-rotating MT5 logs for the FMA3 demos
# before they roll over. The GO_NOGO #4 weekend heartbeat (FMA3 NATIVE HB: ...)
# lives in the Experts log, which MT5 rotates daily; this preserves it.
#
# WHAT IT DOES: finds each running FMA3 terminal by account number, copies its
#   Journal logs   (<terminal>\logs\*.log)
#   Experts logs   (<terminal>\MQL5\Logs\*.log)
# into C:\FMA3_log_archive\<account>\{journal,experts}\.  COPIES (never moves),
# overwrites same-name, so it is safe to run repeatedly and on a schedule.
#
# RUN MANUALLY:   powershell -ExecutionPolicy Bypass -File .\Archive-FMA3-Logs.ps1
# SCHEDULE DAILY: see the Register block printed at the end (run once, as admin).

$ErrorActionPreference = 'Stop'
$accounts    = @('52963578', '1514016754')     # IC demo, FTMO demo
$archiveRoot = 'C:\FMA3_log_archive'
$termRoot    = Join-Path $env:APPDATA 'MetaQuotes\Terminal'

New-Item -ItemType Directory -Force -Path $archiveRoot | Out-Null
$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm')
Write-Host "=== FMA3 log archive @ $stamp  ->  $archiveRoot ==="

if (-not (Test-Path $termRoot)) {
  Write-Host "  ERROR: $termRoot not found. Is MT5 installed for this user?"; return
}

$done = @{}
Get-ChildItem $termRoot -Directory | Where-Object { $_.Name -ne 'Common' } | ForEach-Object {
  $term       = $_.FullName
  $journalDir = Join-Path $term 'logs'
  $expertsDir = Join-Path $term 'MQL5\Logs'
  if (-not (Test-Path $journalDir)) { return }

  # identify the account from the newest journal log
  $newest = Get-ChildItem $journalDir -Filter '*.log' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $newest) { return }

  $acct = $null
  foreach ($a in $accounts) {
    if (Select-String -Path $newest.FullName -Pattern $a -Quiet -ErrorAction SilentlyContinue) { $acct = $a; break }
  }
  if (-not $acct)            { return }   # not one of our demos
  if ($done.ContainsKey($acct)) { return } # already archived this account
  $done[$acct] = $true

  $dstJ = Join-Path $archiveRoot "$acct\journal"
  $dstE = Join-Path $archiveRoot "$acct\experts"
  New-Item -ItemType Directory -Force -Path $dstJ, $dstE | Out-Null

  $nj = 0; $ne = 0
  Get-ChildItem $journalDir -Filter '*.log' -ErrorAction SilentlyContinue |
    ForEach-Object { Copy-Item $_.FullName $dstJ -Force; $nj++ }
  if (Test-Path $expertsDir) {
    Get-ChildItem $expertsDir -Filter '*.log' -ErrorAction SilentlyContinue |
      ForEach-Object { Copy-Item $_.FullName $dstE -Force; $ne++ }
  }
  Write-Host ("  acct {0}: {1} journal + {2} experts logs  ->  {3}\{0}" -f $acct, $nj, $ne, $archiveRoot)
}

if ($done.Count -eq 0) {
  Write-Host "  WARNING: no terminal matched accounts $($accounts -join ', '). Are both demos running?"
} else {
  Write-Host "=== done: $($done.Count) demo(s) archived ==="
}

# ---------------------------------------------------------------------------
# To schedule it daily at 23:50 (run ONCE, in an ELEVATED PowerShell):
#
#   $p = "$PWD\Archive-FMA3-Logs.ps1"
#   schtasks /Create /SC DAILY /ST 23:50 /TN "FMA3 Log Archive" /RL HIGHEST /F `
#     /TR "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$p`""
#
# Verify:  schtasks /Query /TN "FMA3 Log Archive"
# Run now: schtasks /Run   /TN "FMA3 Log Archive"
# ---------------------------------------------------------------------------
