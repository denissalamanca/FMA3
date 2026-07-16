# RUNSHEET — VPS setup + the live-resume test (one-time, owner-executed)

*Gets `FableBookNative` running on the Windows VPS against the two demo accounts, and
proves the warm blob resumes on a live feed (DEMO_FORWARD_PLAN §6A Step 2 — the last
technical gate). Ends with the **Week-0 trade-disabled shakedown** running.*

> **⚠ NEVER attach this EA to account 11078280 / ICMarketsEU-MT5-5 — that is a REAL,
> LIVE-FUNDED account.** The EA runs on the **VPS**, against **DEMO** logins, only. The
> laptop's MT5 stays research + Strategy-Tester only. Nothing in this runsheet touches it.

**Time:** ~1h of setup + ~15 min of backfill watching. **Trades placed: ZERO** (Week-0 is
trade-disabled by preset default).

---

## Step 0 — What you need before starting

| | |
|---|---|
| VPS | Windows Server, always-on, no sleep |
| IC demo | **`52963578`** — €10,000, leverage **1:30** ✅ created 2026-07-16 |
| FTMO demo | €100,000, leverage **1:100** ← provision the leverage at creation |
| Warm blob | `FMA3_native_state.json` + `.coredrive` from this laptop's `Common\Files` |

**Leverage is not cosmetic.** Both dials (IC s=1.6, FTMO s=0.70) were decided *at* those
leverages; a different one silently changes the margin path and the drawdown that follows.
Set it when you create the account — changing it later resets things.

**Two accounts = two MT5 installations.** MT5 allows one login per terminal, so install MT5
twice on the VPS (separate directories, e.g. `C:\MT5-IC\` and `C:\MT5-FTMO\`) — one login each.

**Do NOT use `/portable`.** Two *normal* installs each get their own data folder under
`%APPDATA%\MetaQuotes\Terminal\<hash>\` while **sharing** one `…\Terminal\Common\Files` — which
is what Step 3's blob path and the `_IC`/`_FTMO` namespacing assume. Portable installs keep
data under the install directory and break that assumption.

---

## Step 1 — Grab the warm blob OFF this laptop (do this first)

It is the deliverable of three tester runs and it lives in a folder the tester overwrites.

**On the laptop**, copy these two files somewhere durable (then to the VPS):

```
~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/crossover/
    AppData/Roaming/MetaQuotes/Terminal/Common/Files/
        FMA3_native_state.json              7,876,336 B   sha256 2f3a2c40…
        FMA3_native_state.json.coredrive        8,334 B   sha256 8574a2bf…
```

**⚠ Any future Strategy-Tester run with `InpSaveInTester=true` overwrites these.** Copy them
now, before anything else.

Verify after copying (PowerShell on the VPS):
```powershell
Get-FileHash FMA3_native_state.json -Algorithm SHA256
# must start 2F3A2C40...
```
A blob that does not match is not the certified one — stop and re-copy.

---

## Step 2 — Install MT5 twice, log into the demos

1. Install MT5 into `C:\MT5-IC\` → log into the **IC demo**.
2. Install MT5 into `C:\MT5-FTMO\` → log into the **FTMO demo**.
3. In **each**: `Tools → Options → Charts → Max bars in chart = Unlimited`.
   *The EA backfills ~6.5 months of M1 across 33 symbols; a bar cap starves it.*
4. In **each**: `Tools → Options → Expert Advisors → Allow algorithmic trading` ✔.
   *Week-0 still places zero orders — that's enforced by `InpAllowLiveTrading=false` in the
   preset, not by this checkbox. The checkbox only lets the EA run at all.*
5. In **each**: Market Watch → right-click → **Show All** (the EA needs all 33 symbols).
6. Set the VPS to never sleep; set MT5 to start on login.

---

## Step 3 — Copy the EA + presets into BOTH terminals

Into **each** of `C:\MT5-IC\MQL5\` and `C:\MT5-FTMO\MQL5\`:

| From (this repo / laptop terminal) | To |
|---|---|
| `mt5/ea/FableBookNative.mq5` | `MQL5\Experts\` |
| `mt5/ea/Include\` (**all** headers: Core, Book, Sat, FMA3) | `MQL5\Include\` |
| `mt5/ea/presets/FABLE_IC_LIVE.set` | `MQL5\Presets\` (IC terminal) |
| `mt5/ea/presets/FABLE_FTMO_LIVE.set` | `MQL5\Presets\` (FTMO terminal) |

Then **compile on the VPS** (MetaEditor → open `FableBookNative.mq5` → F7). Expect
**`0 errors, 0 warnings`**. Compile there rather than copying the `.ex5` — it guarantees the
binary matches the VPS's MT5 build.

### The blob goes in the SHARED folder — under TWO names

`Common\Files` is **shared by every MT5 install of the same Windows user** — both terminals
see one folder. So each account needs its **own** state file, or the two EAs overwrite each
other's warm state every hour for three months.

Copy the blob **twice**, into the shared folder — paste this literally into Explorer's
address bar (`%APPDATA%` expands itself, so you needn't unhide `AppData`):

```
%APPDATA%\MetaQuotes\Terminal\Common\Files
```

which resolves to `C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\Common\Files\`.
Note `Common` is a **sibling** of the per-terminal hex-named folders, not inside one — that is
exactly why both installs see it. If `Files` doesn't exist, create it.
Can't find it? `File → Open Data Folder`, then go **up one level** to `…\Terminal\` — `Common`
sits alongside the hex-named folder. (This assumes the non-portable install from Step 2.)

```
FMA3_native_state.json            ->  FMA3_native_state_IC.json
FMA3_native_state.json.coredrive  ->  FMA3_native_state_IC.json.coredrive
FMA3_native_state.json            ->  FMA3_native_state_FTMO.json
FMA3_native_state.json.coredrive  ->  FMA3_native_state_FTMO.json.coredrive
```

The same blob serves both: it holds the **sleeve curves** (a_h/b_h, seeded at 10,000 by
construction), which are dial-independent. `InpScale` scales the *target lots*, not the
sleeve state — so IC (1.6) and FTMO (0.70) legitimately resume from identical state.

The presets already point at these names. Nothing else in `Common\Files` is shared: telemetry
and the decisions CSV are namespaced `_IC` / `_FTMO` too.

---

## Step 4 — Attach to the IC demo (the live-resume test)

1. In the **IC** terminal, open a **BTCUSD, M1** chart (24/7 clock — every RECON run used it).
2. Drag `FableBookNative` onto it.
3. In the dialog → **Inputs** tab → **Load** → `FABLE_IC_LIVE.set`.
4. **Confirm before clicking OK:**

```
InpScale             = 1.6
InpInitial           = 10000.0
InpDailyStopX        = 0.0
InpAllowLiveTrading  = false        <-- MUST be false
InpStateFile         = FMA3_native_state_IC.json
InpSaveStateFrom     =              <-- MUST be empty (tester-only)
```

5. OK.

### What you should see in the Experts tab

```
FMA3 NATIVE WARM START: blob validated (j=… at hour …); resuming from 2025-12-31 22:00
FMA3 NATIVE init: s=1.60 initial=10000 … symbols=33 trade=ON warm=yes refuse=no
```

**`warm=yes` is the whole point of this step.** It means the blob loaded and validated.

| If you see | It means | Do |
|---|---|---|
| `warm=yes` | ✅ the blob resumed — **this is the gate passing** | continue to Step 5 |
| `warm=cold` | the blob wasn't found — wrong filename or wrong folder | re-check Step 3 |
| `REFUSE: state blob present but core-drive sidecar missing` | you copied the `.json` but not the `.coredrive` | copy both |
| `REFUSE: state incoherence…` | the pair is mismatched | re-copy both from the same source |
| any other `REFUSE:` | the EA is *correctly* refusing a doubted state | **stop, send me the line** |

`trade=ON` here is expected and safe — it reflects the internal gate, not order permission.
`InpAllowLiveTrading=false` is what guarantees zero orders. Confirm with the **Trade** tab:
it must stay empty all week.

### Then: the backfill (~15 min)

The blob is at 2025-12-31 22:00 and today is ~6.5 months later, so the EA replays ~283,000
minutes to catch up — about 14 passes. **It cannot trade during this**: the catch-up gate
holds `FED_Reconcile` until the compute clock reaches the wall clock. Watch the Experts tab
tick forward. When it reaches now, the hourly telemetry starts appending to
`FMA3_native_hourly_IC.csv`.

*Note: those 6.5 months are genuinely out-of-sample data the model has never seen. The EA
computes across them without trading — a free OOS read we can look at afterwards.*

---

## Step 5 — Attach to the FTMO demo

Identical, in the **FTMO** terminal, with `FABLE_FTMO_LIVE.set`. Confirm:

```
InpScale             = 0.7
InpInitial           = 100000.0
InpDailyStopX        = 3.0          <-- the breaker is ARMED here (it is NOT on IC)
InpAllowLiveTrading  = false
InpStateFile         = FMA3_native_state_FTMO.json
```

---

## Step 6 — Week-0: let it run trade-disabled for one week

Zero orders. What we're proving: it survives a week unattended, resumes cleanly across at
least one restart, and the telemetry is complete.

**Restart test (do this once, deliberately):** close MT5, reopen. Expect `warm=yes` again —
now resuming from a blob the EA wrote *itself*, not the one we shipped. That's restart
continuity, and it's what keeps a 3-month demo alive through a VPS reboot.

**Watch for (DEMO_GO_NOGO #4 — the one thing we could not test in the tester):** the
**weekend/holiday clock-stall**. The RECON-8j/8k fix was tester-only. The live question is
whether this broker's `CopyRates` returns `n=0` (fine) or `n<0` (stalls the book) for a
closed symbol. **The first weekend is the test.** If the book stops advancing Saturday and
doesn't resume Monday, send me the Experts log.

Also: set up the daily log archival + weekly deal export from
[`RUNBOOK_VPS.md`](RUNBOOK_VPS.md) §1–2 — logs rotate daily and are lost otherwise.

---

## Step 7 — The Week-1 gate (do NOT skip)

Before flipping to trade-enabled, **all** must hold:

- [ ] `warm=yes` on every start, including after the deliberate restart
- [ ] zero unexplained `REFUSE:` latches
- [ ] the book advanced through a **weekend** without stalling
- [ ] hourly telemetry complete for both accounts, no gaps
- [ ] `Trade` tab empty all week (proves `InpAllowLiveTrading=false` held)
- [ ] **owner decision on GO_NOGO #1b** (policy rates expired — carry/swap drift, needs the
      real USD/JPY path or explicit acceptance as a known caveat)

Then Week-1 = change **one input**, `InpAllowLiveTrading=false → true`, on the **demo**
accounts only. The 3-month clock starts.

---

## Appendix — why the odd bits are the way they are

- **`InpSaveStateFrom` must stay empty live.** It is a *tester* throttle. Live saves the blob
  at every completed hour; that is the only legal save point (the core-drive sidecar needs
  drained queues — `CoreLiveDrive.mqh:712`) and restart continuity depends on it.
- **Every output is account-namespaced** because `Common\Files` is shared across installs.
  Un-namespaced, the two EAs clobber each other's state, telemetry and decisions CSV.
- **The blob's hour is 22:00, not 23:00** (RECON-13, accepted). The EA resumes from
  `last_emit_hour` and backfills, so the exact hour is cosmetic. Don't chase 23:00.
