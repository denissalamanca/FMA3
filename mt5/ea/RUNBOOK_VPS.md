# RUNBOOK — running the demo on the Windows VPS (operations)

*The operational setup for the 3-month demo (DEMO_FORWARD_PLAN §6C.2–3, §6E, §6F).
Covers what must be in place so the demo **captures everything and loses nothing**
over 3 months of unattended running. Owner-executed on the VPS.*

---

## 0. One-time setup on the VPS

**→ [`RUNSHEET_VPS_SETUP.md`](RUNSHEET_VPS_SETUP.md)** — the full step-by-step (install,
blob transfer, attach, the live-resume test, the Week-1 gate). Superseded the 4-step sketch
that used to live here, which was wrong on three counts now worth remembering:

- it named the **tester** presets (`FABLE_*_REALTICK_P1.set`); live needs
  **`FABLE_IC_LIVE.set` / `FABLE_FTMO_LIVE.set`** (trade-disabled by default);
- it said copy the `.ex5` — **compile on the VPS** instead, so the binary matches its build;
- it copied the warm blob under **one** name. `Common\Files` is **shared by every MT5 install
  of a Windows user**, and MT5 allows one login per terminal — so the two demos would have
  overwritten each other's state every hour. The blob is copied under **two** names, and
  state/telemetry/decisions are all account-namespaced.

**Power/sleep:** VPS never sleeps; MT5 auto-starts on login. Warm-blob auto-resume
(`InpSaveState=true`) covers restarts, but a *gap* loses live telemetry — keep it always-on.

> **⚠ NEVER attach the EA to account 11078280 / ICMarketsEU-MT5-5 — it is REAL and
> LIVE-FUNDED.** VPS + demo logins only.

## 1. Log + data archival (CRITICAL — logs rotate daily and are lost otherwise)

MT5 rotates the **Journal** and **Experts** logs daily (`…\MQL5\Logs\`,
`…\Tester\…\logs\` for agents) and **overwrites** the telemetry each restart is a
risk if `InpSaveState` isn't on (it is). Set a **daily Task Scheduler job** that
copies everything to a retained, dated folder:

```bat
:: archive_demo.bat  — schedule DAILY (Task Scheduler)
set SRC="%APPDATA%\MetaQuotes\Terminal\Common\Files"
set LOGS="%APPDATA%\MetaQuotes\Terminal\<TERMINAL_HASH>\MQL5\Logs"
set DEST="D:\demo_archive\%date:~-4%%date:~4,2%%date:~7,2%"
robocopy %SRC%  %DEST%\common  FMA3_native_hourly.csv fma3native_decisions.csv /R:2 /W:5
robocopy %LOGS% %DEST%\logs    *.log /R:2 /W:5
```
- Replace `<TERMINAL_HASH>` (find it via MT5 → File → *Open Data Folder*).
- `D:\demo_archive\` = any retained drive/folder.
- **Why daily:** the telemetry CSV is appended live but the *logs* rotate — a daily
  copy guarantees the refuse / feed-gap / warm-resume events survive.

## 2. Deal-history export (weekly — the friction / native-`k` input)

Once trading is enabled, **weekly** export the deal history so the reconciliation
harness can decompose swap/spread/commission and the native `k`:
- Strategy Tester isn't running live, so export from the **account history**:
  Toolbox → *History* tab → right-click → *Report* → save `.xlsx` (or *Save as Detailed Report*).
- Drop it next to that week's telemetry in the archive folder.

## 3. Monitoring (§6E) — automated eye on the kill criteria

Run **`research/demo/demo_watch.py`** (daily or on a schedule) against the live
telemetry — it prints current min-ML / worst-mark DD / fidelity / breaker + **flags
any §5 kill-criterion breach**, and exits non-zero on a KILL so it can drive an alert:

```
python demo_watch.py --telemetry "%APPDATA%\MetaQuotes\Terminal\Common\Files\FMA3_native_hourly.csv" \
                     --journal "<...>\MQL5\Logs\<today>.log" --preset ic
```
- `--preset ic` or `ftmo` (per account).
- Exit code **1 = a KILL criterion is breached** → wire it to an email/notification
  in the scheduled task if you want push alerts.
- **Weekly**, run the deeper `reconcile_demo.py` (retention, friction, per-window
  DD) on the archived telemetry + deal export.

## 4. Kill / restart discipline (pre-committed — DEMO_FORWARD_PLAN §5)

**Halt + investigate** on: a refuse-latch on non-corruption · min ML < 105% · live
DD > 28% (IC) / any 10% breach (FTMO) · fidelity < 95% over a day. `demo_watch.py`
surfaces all of these. On a VPS restart, confirm the **`WARM START: blob validated`**
line appears (not COLD) before leaving it — a silent cold-start would quietly stop
trading.

---

## The daily / weekly cadence at a glance
| When | Do |
|---|---|
| **Daily** (auto) | `archive_demo.bat` + `demo_watch.py` (alert on exit 1) |
| **Weekly** | export deal history · run `reconcile_demo.py` on the archive · read the §3 criteria |
| **Month 1.5** | mid-read against the success bands |
| **On any restart** | confirm `WARM START` (not COLD) |
| **Month 3** | final reconciliation → the deploy decision |
