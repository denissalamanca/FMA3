# S0 feed probe — runbook (FABLEBOOKNATIVE_DESIGN.md, FABLE REVISION v2 item 4)

Go/no-go for the FableBookNative data path: can MT5 furnish, on a BTCUSD M1
clock chart, time-synchronized M1 data for the 33 Fable-book symbols + the
eurq EUR crosses (34 unique: only EURJPY is not already a book symbol), in
BOTH the 1m-OHLC Strategy Tester and on a live chart, with M1 depth to
2020-01-02 and a union grid + `has_bar` mask matching the frozen golden?

## Pieces (all built, compiled, installed)

| Piece | Where | Status |
|---|---|---|
| `FeedProbe.mq5` (EA, ZERO trading calls) | repo `mt5/ea/FeedProbe.mq5`; prefix `MQL5/Experts/FeedProbe.mq5` + `.ex5` | compiled 0 errors / 0 warnings |
| Golden exporter | `research/bpure/probe/export_probe_golden.py` | RUN — golden in Common Files |
| Judge | `research/bpure/probe/judge_feedprobe.py` | self-test judge(golden,golden)=PASS; negative test FAILs correctly |

Probe window (server time, fixed in both EA inputs and exporter):
**2024-03-02 00:00 → 2024-03-10 23:59** (Mon–Fri week 2024-03-04..08 + both
surrounding weekends for crypto bars). Depth reference: **2020-01-02** week.

Common Files dir (all CSVs land here):
`~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files/`

## Owner: run mode (i) — 1m-OHLC Strategy Tester

1. Terminal → Strategy Tester → Expert: **FeedProbe**, Symbol **BTCUSD**,
   Period **M1**, Model **"1 minute OHLC"**.
2. Date range: any short range AFTER the probe window — recommend
   **2024.03.11 → 2024.03.15** (the probe reads the window via CopyRates from
   history, so the range itself only needs to exist).
3. Deposit/leverage irrelevant (no trading calls). Run.
4. Journal shows `FEEDPROBE SYMBOL_SELECT <sym> ok=...` per symbol, then
   `FEEDPROBE DONE mode=tester file=FMA3_feedprobe_tester.csv ...`.
   The file is written even if some symbols never load (OnDeinit safety).

## Owner: run mode (ii) — live chart

1. Open a **BTCUSD M1** chart on ICMarketsEU-MT5-5, attach **FeedProbe**
   (Algo Trading can stay OFF — the EA never trades; it only needs timers).
2. It retries on a 5 s timer while lazy history downloads complete
   (up to `InpMaxTries`=60 ≈ 5 min), then prints
   `FEEDPROBE DONE mode=live file=FMA3_feedprobe_live.csv ...` in Experts log.
   Slow symbols show as `done=0` rows in the CSV — re-attach to retry.

## Judge (after each run)

```bash
CF="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
python3 research/bpure/probe/judge_feedprobe.py "$CF/FMA3_feedprobe_golden.csv" "$CF/FMA3_feedprobe_tester.csv"
python3 research/bpure/probe/judge_feedprobe.py "$CF/FMA3_feedprobe_golden.csv" "$CF/FMA3_feedprobe_live.csv"
```

Verdicts: SYMBOLS / GRID / HAS_BAR / DEPTH / OVERALL (exit 0 = PASS).
Divergences are listed minute-by-minute (first 10 grid, first 5 per symbol).

Re-export golden if the window is ever changed (must match the EA inputs):
`python3 research/bpure/probe/export_probe_golden.py`

## Known facts going in

- All 34 broker symbols exist on ICMarketsEU-MT5-5 — verified read-only via
  the terminal's `Bases/ICMarketsEU-MT5-5/history/<SYMBOL>/` folders (history
  already downloaded for every one, including DE40, US500, EURJPY, SOLUSD).
- Golden facts the judge already accounts for: SOLUSD cache starts
  2022-03-14 (depth is judged vs golden earliest + 1 day slack, not vs 2020);
  ETHUSD has only 5 bars in the 2020-01-02 depth week (thin early history);
  first bars: US30/US500/USTEC 08:00, DE40 03:16, XAU/XAG 01:00 on 2020-01-02.
- Window end (Sun 2024-03-10) straddles the US DST switch — if the broker
  clock shifted GMT+2→GMT+3 that day, expect any label drift to show as
  has_bar mismatches confined to 2024-03-10; that is a real finding, not a
  judge bug.
- Interpretation per FABLE REVISION v2 item 4: **tester-mode failure does NOT
  imply live failure** (deploy target is live CopyRates). Named fallback if
  tester mode fails: historical certification stays on the six-field frozen
  engine; R2 gets measured on a demo-forward run; the EA remains deployable.
