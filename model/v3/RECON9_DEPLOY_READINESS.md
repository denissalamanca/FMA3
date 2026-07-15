# RECON-9 — IC preset deploy-readiness adjudication

*Opus adjudication, 2026-07-15. Subject: the IC preset — native EA `FableBookNative`, dial
s=1.6, ICMarketsEU account, 1:30. Grounded in **our own full-window run #36** (the 2020-2025
IC 1m-OHLC test) and our docs/REGISTRY — not memory notes. Question: is IC ready to advance
to a live forward demo?*

> **Provenance note.** An earlier draft of this doc quoted a ~40% "warm COVID drawdown" from
> an *old, different account* (52949549). That was memory creep — substituting a stale figure
> for the run we actually did and processed. **Removed.** Every number below is from run #36
> or a cited repo artifact.

---

## VERDICT

1. **Trade-DISABLED forward demo (compute + log, zero orders): GO now.** Zero risk; the right
   plumbing shakedown + out-of-sample forward data collection.
2. **Trade-ENABLED demo at s=1.6: defensible.** s=1.6 is the owner's *documented* aggressive
   dial (30% DD risk appetite, breach cap 0.20; REGISTRY FMA3-004/004c), and **our full-window
   run measured worst DD ~22.9% and survived** — well inside that appetite. A lower dial (s≈0.7-1.1)
   is the owner's option, not a requirement imposed by the data.
3. **Live capital: a separate owner decision *after* the demo**, weighing the in-sample discount
   (§3) and the concentration tail (§2). Recommend demo-forward first, then decide.

The honest **live** expectation is **well below the in-sample +158%**, but it is *unquantified*:
there is **no valid OOS forward** yet (the earlier 2026-H1 one-shot was not properly conducted
and is not usable for decisions). Anchor on the **risk envelope**, not the in-sample headline or
the frictionless ceiling — the **demo-forward will produce the first valid OOS read.**

---

## 1. The certification chain — the executor is certified

| Certification | Result (run #36 / cited) | Verdict |
|---|---|---|
| Compute fidelity (R1) | max\|diff\| 5.06e-13 vs golden, full window; Core seam 0.0 | **PASS** |
| Position fidelity | **69 self-check mismatches over 6 years** | **PASS** |
| Sat port cert | 24/24 quarters bit-exact | **PASS** |
| Full-window reconciliation | net €2.93M, worst DD 22.9% vs golden 22.2% (+0.7pp), retention 95.2% | **RECONCILED** |
| Friction decomposition | −12.9pp = swap 66% / spread 19% / comm 5% | quantified |

The native EA also **fixes V1's over-leverage** — it holds the model's margin-safe position
(min ML 121% at 1m-OHLC, no stop-out), whereas the V1 EA's cross-sleeve double-count produced
an over-levered pyramid. The executor is sound.

## 2. The performance read (our run #36)

- **Worst drawdown ~22.9%** — a **2022** warm-crisis event (realized-balance −21.5% Jan-2022;
  M2M ~25% Oct-Dec 2022; report Equity-DD-Relative 23.27%). **The book survived it** (positive
  year, no breach). This is a real warm-crisis stress test, and it cleared.
- **COVID drawdown ~10.8%** (regime analysis on the deals balance path). *Footnote:* our run
  cold-starts through COVID (the book holds zero EURGBP and runs 0.46× gross vs ~4.3× normal
  through the March crash), so COVID is not the binding drawdown in our data — 2022 is.
- Net €2.93M (0.76× the frictionless ceiling); CAGR +158.0% (**in-sample**); Sharpe 2.07.
- **Concentration:** XAUUSD (40%) + USTEC (21%) = **61.6%** of net; 2025 = 71%
  (`SLEEVE_REGIME_ANALYSIS.md`). The book is a levered-long gold + Nasdaq trend with a
  diversifying overlay.

## 3. Honest deploy considerations (verified against our docs, not memory)

1. **s=1.6 is a deliberate aggressive dial.** REGISTRY: the red-team battery certified **s=1.1**
   as probe-robust (FMA3-RT); s=1.2-1.4 = "aggressive frontier, not probe-robust"; s=1.6 ships
   under **H-RISK-1**, the owner's risk revision to a **30% DD appetite** with the breach cap
   relaxed **0.15→0.20** (FMA3-004c). It is a *documented owner risk choice*, not a hidden flaw
   — but it *is* the top of the tested frontier, so the tail sensitivity is real.
2. **In-sample selection.** 2020-2025 is the design/mining window (pre-mined by both parent
   programs; DSR n=20). **+158% is an in-sample number**, and **there is no valid out-of-sample
   forward** to anchor a live expectation on (the earlier 2026-H1 one-shot was not conducted
   properly and is not usable). So discount the in-sample headline heavily; **the demo is the
   load-bearing — and first valid — OOS test.**
3. **Concentration tail.** A simultaneous gold **and** tech reversal — a regime the 2020-2025
   window did not contain — would hit both big legs, both sleeves, and the biggest swap payers
   at once. Real, undiversified, and untested.
4. **Plumbing.** Native EA is margin-safe *as modelled* (min ML 121% 1m-OHLC); the Task-17
   aggregate-margin governor is deferred; real-tick intra-bar min-ML is unconfirmed (broker has
   no pre-2023 ticks). Fine for a demo; worth the governor before scaling live.
5. **Friction is likely worse live** than the measured 0.76× (1m-OHLC hides slippage/crisis
   spread; swap is 66% of the gap, modelled flat, grows with the book).

## 4. Demo-forward plan + graduation

**Demo (authorized; trade-disabled unconditionally, trade-enabled at the owner's dial):** real
IC feed; refuse-latch + state serializer active; a pre-committed window (≥3 months, target 6+);
no mid-run dial changes. Watch: live DD vs the ~22.9% measured band; min ML vs the ≥110% line;
per-bar position fidelity; swap accrual; the concentration legs.

**Graduation to live capital (owner decision):** the demo clears the watch criteria; the owner
accepts the **in-sample discount** (expect live well below +158%) and the **concentration tail**;
start small and scale slowly. Ship the Task-17 governor before meaningful size.

## 5. Bottom line

The **executor is genuinely certified**, and **our own full-window run measured a ~22.9% worst
drawdown that survived** — within the owner's stated risk appetite. The honest cautions are
about **generalization** (in-sample +158% with no valid OOS forward yet — the demo produces the
first), the **aggressive s=1.6 dial** (owner's documented choice, top of the tested frontier),
and **concentration** — not a hidden crash tail. **GO for demo-forward**; the live-capital step
is a downstream owner decision, made with the in-sample discount and concentration in full view.
