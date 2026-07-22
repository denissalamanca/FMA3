<#
  Validate-FMA3Telemetry.ps1  -- FMA3 live-telemetry data-quality gate (RECON-DQ 1..8)
  PURE PowerShell (no Python/pandas). Run ON THE VPS where the two MT5 terminals live.
  Read-only: it never writes to Common\Files. Safe to run anytime.

  Usage:   powershell -ExecutionPolicy Bypass -File .\Validate-FMA3Telemetry.ps1
#>

$ErrorActionPreference = 'Stop'
$Common = Join-Path $env:APPDATA 'MetaQuotes\Terminal\Common\Files'

# Expected hourly schema (26 cols) and column indices (0-based, verified vs FableBookNative.mq5:215/622)
$EXP_HDR = 'ts,rec,sym,val,a_h,b_h,j,core_seed,n_segs,fires,lead_hold,sc_mm,unready,skipped,balance,equity,margin_level,trading,warm,n_stops,worst_eq,day_anchor,want,held,defer,snap_ts'
$NCOL      = 26
$IX = @{ ts=0; rec=1; sym=2; val=3; a_h=4; b_h=5; j=6; balance=14; equity=15; ml=16; trading=17; warm=18; n_stops=19; worst_eq=20; day_anchor=21; want=22; held=23; defer=24; snap_ts=25 }

$Accounts = @(
  @{ name='IC';   initial=10000.0; absent=$null;     ftmo=$false },
  @{ name='FTMO'; initial=80000.0; absent='EURSEK';  ftmo=$true  }
)

# ------------------------------------------------------------------ helpers
function Detect-Encoding([byte[]]$b) {
  if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) { return 'UTF-8-BOM' }
  if ($b.Length -ge 2 -and $b[0] -eq 0xFF -and $b[1] -eq 0xFE)                     { return 'UTF-16LE' }
  if ($b.Length -ge 2 -and $b[0] -eq 0xFE -and $b[1] -eq 0xFF)                     { return 'UTF-16BE' }
  return 'ANSI/UTF-8'   # no BOM: EA writes FILE_ANSI (cp1252) for CSV, CP_UTF8 for JSON; ASCII-identical
}
function Decode-Bytes([byte[]]$b, [string]$enc) {
  switch ($enc) {
    'UTF-8-BOM'  { return [Text.Encoding]::UTF8.GetString($b, 3, $b.Length-3) }
    'UTF-16LE'   { return [Text.Encoding]::Unicode.GetString($b) }
    'UTF-16BE'   { return [Text.Encoding]::BigEndianUnicode.GetString($b) }
    default      { return [Text.Encoding]::GetEncoding(1252).GetString($b) }  # ANSI/cp1252 lossless for high bytes
  }
}
function ReadBytesShared([string]$path) {
  # Open share-tolerant (FileShare.ReadWrite) so a file the EA holds OPEN for writing
  # (the hourly + decisions CSVs are held continuously) still copies. ReadAllBytes uses
  # FileShare.Read, which conflicts with the EA's write handle -> "used by another process".
  $fs = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
  $ms = New-Object System.IO.MemoryStream
  try { $fs.CopyTo($ms); return $ms.ToArray() }
  finally { $fs.Dispose(); $ms.Dispose() }
}
function Read-TextFile([string]$path) {
  # returns @{ ok; enc; lines; highBytes; hasBOM; err }
  $r = @{ ok=$false; enc='?'; lines=@(); highBytes=0; hasBOM=$false; err=$null }
  try {
    $b = ReadBytesShared $path
    if ($b.Length -eq 0) { $r.err='empty file'; $r.enc='empty'; return $r }
    $r.enc = Detect-Encoding $b
    $r.hasBOM = ($r.enc -like '*BOM*') -or ($r.enc -like 'UTF-16*')
    # count bytes > 0x7F only meaningful for single-byte streams
    if ($r.enc -eq 'ANSI/UTF-8' -or $r.enc -eq 'UTF-8-BOM') { $r.highBytes = ($b | Where-Object {$_ -gt 127} | Measure-Object).Count }
    $txt = Decode-Bytes $b $r.enc
    $r.lines = $txt -split "`r?`n"
    $r.ok = $true
  } catch { $r.err = $_.Exception.Message }
  return $r
}
function Is-Finite([string]$v) {
  if ($null -eq $v -or $v.Trim() -eq '') { return $false }
  if ($v -match '(?i)(1\.#|inf|nan)') { return $false }   # 1.#INF/1.#IND/1.#QNAN, inf, -inf, nan
  $d = 0.0
  return [double]::TryParse($v, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$d)
}
function AsD([string]$v) { $d=0.0; [void][double]::TryParse($v,[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$d); return $d }

$script:pass=0; $script:fail=0; $script:warn=0
function Chk([bool]$ok,[string]$label,[string]$detail='') {
  if ($ok) { $script:pass++; Write-Host ("  [PASS] {0}" -f $label) -ForegroundColor Green }
  else     { $script:fail++; Write-Host ("  [FAIL] {0}{1}" -f $label, $(if($detail){"  -> $detail"})) -ForegroundColor Red }
}
function Wrn([string]$label,[string]$detail='') { $script:warn++; Write-Host ("  [WARN] {0}{1}" -f $label, $(if($detail){"  -> $detail"})) -ForegroundColor Yellow }
function Info([string]$s) { Write-Host ("  [info] {0}" -f $s) -ForegroundColor Cyan }

# ------------------------------------------------------------------ per-account
function Validate-Account($acct) {
  $name = $acct.name
  Write-Host ""
  Write-Host ("==================== ACCOUNT: {0} (initial EUR {1:N0}) ====================" -f $name, $acct.initial) -ForegroundColor White

  $hourly = Join-Path $Common ("FMA3_native_hourly_{0}.csv"   -f $name)
  $decis  = Join-Path $Common ("fma3native_decisions_{0}.csv" -f $name)
  $stateF = Join-Path $Common ("FMA3_native_state_{0}.json"   -f $name)
  $coreF  = "$stateF.coredrive"

  # ---------- HOURLY CSV ----------
  Write-Host "-- hourly telemetry CSV --"
  if (-not (Test-Path $hourly)) {
    Chk $false "hourly CSV present" "missing: $hourly"
  } else {
    $fi = Get-Item $hourly
    $rd = Read-TextFile $hourly
    Info ("path       : {0}" -f $hourly)
    Info ("encoding   : {0}   (cockpit reader MUST match this; BOM={1}, high-bytes={2})" -f $rd.enc, $rd.hasBOM, $rd.highBytes)
    Info ("file mtime : {0}   size={1}B" -f $fi.LastWriteTime, $fi.Length)

    if (-not $rd.ok) {
      Chk $false "hourly CSV readable" $rd.err
    } else {
      Chk ($rd.enc -notlike 'UTF-16*') "encoding is single-byte (not UTF-16)" ("detected $($rd.enc) - a UTF-16 file means the writer changed; naive readers see NUL garbage")
      if ($rd.highBytes -gt 0) { Wrn "high bytes (>0x7F) present" "$($rd.highBytes) bytes - reader must use latin-1/ANSI, not strict UTF-8" }

      $rawLines = @($rd.lines | Where-Object { $_ -ne '' })
      Chk ($rawLines.Count -ge 1) "file has content" "no lines"
      $hdr = $rawLines[0]
      Chk ($hdr -eq $EXP_HDR) "header matches 26-col schema" "got: $hdr"

      # torn-last-row robustness: keep only well-formed rows (correct col count)
      $data = @($rawLines | Select-Object -Skip 1)
      $lastRaw = if ($data.Count) { $data[-1] } else { '' }
      $lastCols = ($lastRaw -split ',').Count
      if ($data.Count -and $lastCols -ne $NCOL) {
        Wrn "last row torn (half-written current row)" "cols=$lastCols expected=$NCOL - using previous complete row (soft, not a crash)"
      }
      $good = @($data | Where-Object { ($_ -split ',').Count -eq $NCOL })
      Chk ($good.Count -ge 1) "at least one complete data row" "0 well-formed rows"

      if ($good.Count -ge 1) {
        $Hrows = @($good | Where-Object { ($_ -split ',')[$IX.rec] -eq 'H' })
        $Prows = @($good | Where-Object { ($_ -split ',')[$IX.rec] -eq 'P' })
        Chk ($Hrows.Count -ge 1) "at least one H (hourly) row" "none"

        # (A) no non-finite token anywhere in the file  [RECON-DQ-4]
        $infHit = @($good | Where-Object { $_ -match '(?i)(1\.#|[,]inf|[,]-inf|[,]nan|infinity)' })
        Chk ($infHit.Count -eq 0) "no inf/nan/1.# tokens in file (absent-symbol regression sentinel)" ("{0} poisoned row(s); first: {1}" -f $infHit.Count, ($infHit | Select-Object -First 1))

        if ($Hrows.Count -ge 1) {
          $H = $Hrows[-1] -split ','
          $tsH = [int64]$H[$IX.ts]
          Info ("last H ts  : {0}  ({1} UTC-naive)" -f $tsH, ([DateTimeOffset]::FromUnixTimeSeconds($tsH).UtcDateTime))

          # (B) key numeric fields finite  [RECON-DQ-4]
          foreach ($k in 'a_h','b_h','j','balance','equity','worst_eq','day_anchor') {
            Chk (Is-Finite $H[$IX[$k]]) ("H.$k finite") ("value='{0}'" -f $H[$IX[$k]])
          }

          # (C) balance / equity sane and > 0  [RECON-DQ-1 sanity]
          $bal = AsD $H[$IX.balance]; $eq = AsD $H[$IX.equity]; $we = AsD $H[$IX.worst_eq]
          $lo = 0.30 * $acct.initial; $hi = 5.0 * $acct.initial
          Chk ($bal -gt 0 -and $bal -ge $lo -and $bal -le $hi) "balance in sane band" ("balance=$bal band=[$lo,$hi]")
          Chk ($eq  -gt 0 -and $eq  -ge $lo -and $eq  -le $hi) "equity in sane band"  ("equity=$eq band=[$lo,$hi]")

          # (D) FTMO 10% kill-line on worst-mark equity  (VACUOUS if compute-only - see below)
          if ($acct.ftmo -and $we -gt 0) {
            $ddPct = (($acct.initial - $we) / $acct.initial) * 100.0
            Info ("worst-mark DD = {0:N2}%  (FTMO hard limit 10%)" -f $ddPct)
            Chk ($ddPct -lt 10.0) "FTMO worst-mark DD < 10% (kill-line)" ("DD={0:N2}% worst_eq={1}" -f $ddPct, $we)
            if ($ddPct -ge 5.0) { Wrn "worst-mark DD >= 5% (half the FTMO limit)" ("DD={0:N2}%" -f $ddPct) }
          }

          # (E) timestamps advancing across H rows
          if ($Hrows.Count -ge 2) {
            $tPrev = [int64](($Hrows[-2] -split ',')[$IX.ts])
            Chk ($tsH -gt $tPrev) "H timestamps advancing" ("last=$tsH prev=$tPrev")
          }

          # (F) cadence / liveness -- authoritative signal is file mtime (local clock, tz-free)
          $ageMin = ((Get-Date) - $fi.LastWriteTime).TotalMinutes
          if ($ageMin -le 90) {
            Chk $true "fresh row within 90 min (file mtime)" ""
          } else {
            Wrn "hourly file stale (mtime age > 90 min)" ("age={0:N0} min - if a session is OPEN this is a FREEZE/refuse-latch (RECON-DQ-3), NOT a benign weekend HOLD; confirm with the HB scan below, treat >3h open-session gap as data loss" -f $ageMin)
          }
          # secondary ts-derived age (biased by broker server-time ~UTC+2..+3; informational only)
          $ageTsMin = ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $tsH)/60.0
          Info ("ts-derived age = {0:N0} min (add ~120-180 min for broker server-time bias; use mtime above as truth)" -f $ageTsMin)

          # (G) compute-only detection  [RECON-DQ-1] -- flip the verdict-labelling, do NOT fail
          $trading = $H[$IX.trading].Trim()
          $balEqEqual = ([math]::Abs($bal - $eq) -lt 0.01)
          if ($trading -eq '0' -and $balEqEqual) {
            Wrn "COMPUTE-ONLY MODE (trading=0, balance==equity)" "BY DESIGN. position-fidelity AND the FTMO kill-line above are VACUOUS in this mode - a green board proves plumbing + the COMPUTE cross-check (a_h/b_h/j), not execution/drawdown. Coverage choice (not a defect): either LABEL fidelity/kill-line 'not exercised' in the cockpit, or (only if you want execution coverage) enable demo trading before FTMO expires ~2026-08-04. Per the settled plan FTMO is a compute cross-check, so labelling is the default."
          } else {
            Info ("trading flag = {0}, balance==equity: {1}" -f $trading, $balEqEqual)
          }
        }

        # (H) absent-symbol (EURSEK) P-row flat-not-broken  [RECON-DQ-4]
        if ($acct.absent) {
          $ab = @($Prows | Where-Object { ($_ -split ',')[$IX.sym] -eq $acct.absent })
          if ($ab.Count -eq 0) {
            Wrn "no P-row for absent symbol $($acct.absent)" "cannot confirm flat (may be pre-fix or no P rows yet)"
          } else {
            $abc = $ab[-1] -split ','
            $w = $abc[$IX.want].Trim(); $hld = $abc[$IX.held].Trim()
            Chk ($w -eq '0.00' -and $hld -eq '0.00') "$($acct.absent) forced flat (want=held=0.00)" ("want=$w held=$hld defer=$($abc[$IX.defer]) - nonzero => absent-symbol guard REGRESSED")
            Info ("$($acct.absent) defer col = $($abc[$IX.defer]) (0=none,1=legDefer,2=unsized; informational)")
          }
        }

        # (I) snap_ts freshness rate on P-rows  [RECON-DQ-8]  (INFO under compute-only)
        if ($Prows.Count -ge 1) {
          $tot=0; $fresh=0; $nzWant=0
          foreach ($p in $Prows) {
            $c = $p -split ','
            if ($c.Count -lt $NCOL) { continue }
            $t=[int64]$c[$IX.ts]; $s=[int64]$c[$IX.snap_ts]; $a=$s-$t; $tot++
            if ($s -gt 0 -and $a -ge 0 -and $a -lt 3600) { $fresh++ }
            if ($c[$IX.want].Trim() -ne '0.00' -or $c[$IX.held].Trim() -ne '0.00') { $nzWant++ }
          }
          Info ("P-rows: {0}  fresh-snap(0<=snap-ts<3600): {1}  nonzero want/held: {2}" -f $tot, $fresh, $nzWant)
          if ($nzWant -eq 0) { Info "all P-rows want=held=0.00 => positions never taken (compute-only) => fidelity is vacuous, snap freshness moot" }
          elseif ($tot -gt 0 -and ($fresh/$tot) -lt 0.5) { Wrn "fresh-snap rate < 50% while positions ARE held" "possible snap_ts/ts unit or semantics drift (PR#39 inversion class)" }
        }
      }
    }
  }

  # ---------- STATE JSON ----------
  Write-Host "-- warm-state JSON --"
  if (-not (Test-Path $stateF)) {
    Chk $false "state JSON present" "missing: $stateF"
  } else {
    $sfi = Get-Item $stateF
    $sb  = ReadBytesShared $stateF
    $senc = Detect-Encoding $sb
    Info ("path     : {0}" -f $stateF)
    Info ("encoding : {0}  (EA writes CP_UTF8/no-BOM via FILE_BIN)" -f $senc)
    Info ("mtime    : {0}  size={1}B" -f $sfi.LastWriteTime, $sfi.Length)
    $sJson = Decode-Bytes $sb $senc

    # integrity trailer written by BookState.mqh Save(): ..., "fnv64": "...", "eof": true}
    Chk ($sJson -match '"eof":\s*true') "state JSON has eof:true trailer (complete, not torn)" "no eof trailer - file half-written or truncated"
    Chk ($sJson -match '"fnv64":\s*"[0-9a-fA-F]{16}"') "state JSON has fnv64 integrity tag" "missing fnv64"
    # BookState.mqh Save() DELIBERATELY writes NaN/Infinity/-Infinity tokens for non-finite
    # ledger slots (python-json non-strict; the loader's SatParseDouble is NaN-aware). So their
    # presence is NORMAL, not poison. The real integrity signals are eof+fnv64+finite continuity
    # (checked below) + the EA's own reload continuity guard (rel_jump). Report the count as INFO.
    $nfTokens = ([regex]::Matches($sJson, '(?<![\w.])(-?Infinity|NaN)(?![\w])')).Count
    if ($nfTokens -gt 0) { Info ("state carries {0} NaN/Infinity token(s) - NORMAL for this non-strict format (NaN-aware loader); a large jump vs prior runs would be worth a look" -f $nfTokens) }
    else { Info "state has no NaN/Infinity tokens" }

    # parse (ConvertFrom-Json handles the whole object; fails on NaN/Infinity non-strict tokens)
    $parsed = $null
    try { $parsed = $sJson | ConvertFrom-Json } catch { }
    if ($null -eq $parsed) {
      Wrn "state JSON did not parse via ConvertFrom-Json" "likely NaN/Infinity tokens (non-strict) - inspect manually; integrity tags above still indicate completeness"
    } else {
      # b-sleeve equity proxy (the state has no account 'balance'; b_eqc is the closest finite>0 value)
      $beqc = $null
      if ($parsed.PSObject.Properties.Name -contains 'b_eqc') { $beqc = $parsed.b_eqc }
      elseif ($null -ne $parsed.continuity) { $beqc = $parsed.continuity.j }
      if ($null -ne $beqc) {
        # coerce via TryParse (ConvertFrom-Json may return [decimal]/[double]/string) instead of a brittle -is gate
        $dv = 0.0
        $isNum = [double]::TryParse([string]$beqc, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$dv)
        $ok = $isNum -and -not [double]::IsNaN($dv) -and -not [double]::IsInfinity($dv) -and $dv -gt 0
        Chk $ok "state equity proxy finite & > 0" ("value=$beqc")
      } else { Wrn "no b_eqc / continuity.j in state" "cannot check equity proxy; rely on integrity + freshness" }
      if ($null -ne $parsed.continuity) {
        foreach ($k in 'a_h','b_h','j') {
          $v = $parsed.continuity.$k
          $fin = ($null -ne $v) -and -not [double]::IsNaN([double]$v) -and -not [double]::IsInfinity([double]$v)
          Chk $fin "continuity.$k finite" ("value=$v")
        }
      }
    }
    # freshness by mtime (~90 min)
    $sAge = ((Get-Date) - $sfi.LastWriteTime).TotalMinutes
    if ($sAge -le 90) { Chk $true "state JSON fresh (mtime <= 90 min)" "" }
    else { Wrn "state JSON stale (mtime age > 90 min)" ("age={0:N0} min - SaveStateFiles no-ops under refuse-latch (RECON-DQ-3) or market closed" -f $sAge) }

    if (Test-Path $coreF) { $cfi=Get-Item $coreF; Info ("coredrive: present  mtime={0}  size={1}B" -f $cfi.LastWriteTime, $cfi.Length) }
    else { Wrn "coredrive sidecar absent" "$coreF missing - state save may be partial" }
  }

  # ---------- DECISIONS CSV (informational under compute-only) ----------
  Write-Host "-- decisions CSV (informational) --"
  if (-not (Test-Path $decis)) {
    Wrn "decisions CSV absent" "$decis - expected empty/absent while compute-only (no fills logged)"
  } else {
    $dfi=Get-Item $decis; $dr=Read-TextFile $decis
    Info ("path={0}  encoding={1}  mtime={2}  size={3}B" -f $decis, $dr.enc, $dfi.LastWriteTime, $dfi.Length)
    $dlines=@($dr.lines | Where-Object {$_ -ne ''})
    if ($dlines.Count -ge 1) { Chk ($dlines[0] -like 'time,symbol,event,net_frac,want,held,after,balance,equity,margin_level*') "decisions header present" ("got: $($dlines[0])") }
    Info ("decisions data rows (fills): {0}" -f [math]::Max(0,$dlines.Count-1))
  }
}

# ------------------------------------------------------------------ collision guard [RECON-DQ-2]
function Check-Collision {
  Write-Host ""
  Write-Host "==================== SHARED-FILE COLLISION GUARD (RECON-DQ-2) ====================" -ForegroundColor White
  $def = Join-Path $Common 'FMA3_native_hourly.csv'   # un-suffixed default
  if (Test-Path $def) {
    $dfi=Get-Item $def; $age=((Get-Date)-$dfi.LastWriteTime).TotalHours
    if ($age -lt 2) { Chk $false "no un-suffixed default telemetry growing" ("COLLISION: $def is live (mtime age {0:N1}h) - a preset OMITTED InpTelemetryFile; IC+FTMO rows are interleaving into one file with no account column. Redeploy the mis-set preset NOW." -f $age) }
    else { Wrn "un-suffixed default telemetry exists but stale" ("$def age={0:N1}h - old artifact, not currently colliding" -f $age) }
  } else { Chk $true "no un-suffixed default telemetry file (no collision)" "" }
  Get-ChildItem $Common -Filter 'FMA3_native_hourly*.csv' -ErrorAction SilentlyContinue | ForEach-Object { Info ("{0,-34} {1,10}B  {2}" -f $_.Name, $_.Length, $_.LastWriteTime) }
}

# ------------------------------------------------------------------ main
Write-Host "########################################################################"
Write-Host "#  FMA3 LIVE TELEMETRY VALIDATOR  --  $(Get-Date)"
Write-Host "#  Common\Files: $Common"
Write-Host "########################################################################"
if (-not (Test-Path $Common)) { Write-Host "FATAL: Common\Files not found. Run this ON THE VPS, not the dev laptop." -ForegroundColor Red; exit 2 }

foreach ($a in $Accounts) { Validate-Account $a }
Check-Collision

Write-Host ""
Write-Host "==================== SUMMARY ====================" -ForegroundColor White
Write-Host ("  PASS={0}  FAIL={1}  WARN={2}" -f $script:pass, $script:fail, $script:warn) -ForegroundColor $(if($script:fail){'Red'}else{'Green'})
Write-Host "  Heartbeat/liveness (not scored here): scan Experts logs for the loop pulse ->"
Write-Host "    Get-ChildItem (Join-Path `$env:APPDATA 'MetaQuotes\Terminal') -Recurse -Filter '*.log' |"
Write-Host "      ? { `$_.FullName -match 'MQL5\\Logs' } |"
Write-Host "      % { Select-String `$_.FullName -Pattern 'FMA3 NATIVE HB:|REFUSE|refuse-to-trade' } | Select -Last 8"
Write-Host "    Missing/old 'FMA3 NATIVE HB:' during an OPEN session => EA loop not running (Algo-Trading off / crashed / refuse-latch)."
if ($script:fail -gt 0) { exit 1 } else { exit 0 }