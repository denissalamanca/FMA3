# Archive-FMA3-Logs.ps1 — copy the FMA3 demos' MT5 logs before they rotate.
# The GO_NOGO #4 weekend heartbeat (`FMA3 NATIVE HB: ...`) lives in the Experts
# log, which MT5 rotates daily; this preserves it (and the Journal logs).
#
# The two terminal data folders are PINNED explicitly (from File -> Open Data
# Folder in each terminal). Auto-discovery was dropped on purpose: MT5 holds the
# current-day log OPEN and writes UTF-16, so grepping it from outside is
# unreliable. We never need to READ the logs here — only COPY them — so this uses
# a share-tolerant byte copy that also captures the still-open current log.
#
# RUN:      powershell -ExecutionPolicy Bypass -File .\Archive-FMA3-Logs.ps1
# SCHEDULE: see the schtasks block at the end (run ONCE, elevated).

$ErrorActionPreference = 'Stop'
$archiveRoot  = 'C:\FMA3_log_archive'
$lookbackDays = 14                       # only (re)copy logs this recent -> fast daily runs

# acct -> terminal data folder (File -> Open Data Folder in each running terminal)
$terminals = [ordered]@{
  '52963578'   = 'C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\ECBBF30105B5FC8F8DF407DFE4160A9B'  # IC demo
  '1514016754' = 'C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\05F73DEE2D5A1BF4E1592EF2E3F40113'  # FTMO demo
}

# Copy one file with FileShare.ReadWrite on the source, so a log MT5 currently
# holds open still copies. Byte copy -> encoding-agnostic.
function Copy-Shared($src, $dstDir) {
  $dst = Join-Path $dstDir (Split-Path $src -Leaf)
  $in = $null; $out = $null
  try {
    $in  = [System.IO.File]::Open($src, 'Open',   'Read',  'ReadWrite')
    $out = [System.IO.File]::Open($dst, 'Create', 'Write', 'None')
    $in.CopyTo($out)
    return $true
  } catch {
    return $false
  } finally {
    if ($out) { $out.Dispose() }
    if ($in)  { $in.Dispose() }
  }
}

New-Item -ItemType Directory -Force -Path $archiveRoot | Out-Null
$cutoff = (Get-Date).AddDays(-$lookbackDays)
Write-Host "=== FMA3 log archive @ $((Get-Date).ToString('yyyy-MM-dd HH:mm'))  ->  $archiveRoot ==="

foreach ($acct in $terminals.Keys) {
  $term = $terminals[$acct]
  if (-not (Test-Path $term)) { Write-Host "  acct ${acct}: MISSING terminal folder -> $term"; continue }

  $srcDirs = @{ journal = (Join-Path $term 'logs'); experts = (Join-Path $term 'MQL5\Logs') }
  foreach ($kind in 'journal','experts') {
    $srcDir = $srcDirs[$kind]
    $dstDir = Join-Path $archiveRoot "$acct\$kind"
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null

    $ok = 0; $skip = 0
    if (Test-Path $srcDir) {
      Get-ChildItem $srcDir -Filter '*.log' -EA SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $cutoff } | ForEach-Object {
          if (Copy-Shared $_.FullName $dstDir) { $ok++ } else { $skip++ }
        }
    }
    $note = if ($skip) { " ($skip locked/skipped)" } else { "" }
    Write-Host ("  acct {0} {1}: {2} copied{3}  ->  {4}" -f $acct, $kind, $ok, $note, $dstDir)
  }
}
Write-Host "=== done ==="

# ---------------------------------------------------------------------------
# Schedule it daily at 23:50 (run ONCE, in an ELEVATED PowerShell):
#
#   $p = "C:\FMA3_ops\Archive-FMA3-Logs.ps1"
#   schtasks /Create /SC DAILY /ST 23:50 /TN "FMA3 Log Archive" /RL HIGHEST /F `
#     /TR "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$p`""
#
# Verify:  schtasks /Query /TN "FMA3 Log Archive"
# Run now: schtasks /Run   /TN "FMA3 Log Archive"
# ---------------------------------------------------------------------------
