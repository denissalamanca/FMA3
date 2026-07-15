# RECON-9 — IC preset deploy-readiness adjudication

*Opus adjudication, 2026-07-15, **adversarially stress-tested and corrected.** Subject: the
IC preset — native EA `FableBookNative`, dial s=1.6, ICMarketsEU account, 1:30. This
synthesizes the full RECON-8 certification chain, an adversarial skeptic pass, and the
team's own forensic record into an honest go/no-go. It **corrects an error** in this
session's crisis-cert (below).*

---

## VERDICT

1. **Trade-DISABLED forward demo (compute + log, ZERO orders): GO now.** Zero capital risk,
   and it's the right plumbing shakedown + out-of-sample forward data collection. Unconditional.
2. **Trade-ENABLED demo: conditional on the dial.**
   - At the **safe/honest dial s≈0.7** (warm crisis DD ~18%, margin clears with room,
     red-team-robust) — **defensible.**
   - At **s=1.6** — only as a *deliberate aggressive-frontier* test, and only with a
     pre-registration that **states the ~38-40% warm crisis drawdown in writing** (not the
     10-22% this session first reported) and labels it aggressive-frontier, not certified-robust.
3. **Live capital: NO** — blocked until (i) a **real-tick crisis reconciliation** exists (the
   protocol's *mandatory, non-waivable* gate — needs external tick data, since the broker has
   no ticks before mid-2023), (ii) a **real-tick intra-bar min-ML > 110%** confirmation at the
   deployed dial, and ideally (iii) the **Task-17 aggregate-margin governor**.

The number to carry forward is a **heavily out-of-sample-discounted** net CAGR (§5b M1),
**not** +158% in-sample and **not** the frictionless +170% ceiling.

---

## 0. CORRECTION to this session's crisis-cert

Earlier this session I reported the crisis cert as **PASS** with **COVID DD 10.18%** and
**2022 DD 21.95%**. The **COVID figure is wrong for a deployment read** — it is the
**cold-start artifact.** My COVID run started fresh at 2020-01-01 with no pre-2020 warmup, so
the EA's indicators were cold and it *phantom-skipped the −€1,586 EURGBP short* that drives
the COVID loss — the identical artifact the record engine has (`record-engine-covid-warmup-
artifact`, `benchmark-cold-start-illusion`). A **warm** live account (indicators seeded from
broker history — the actual deployment condition) carries that short into the crash:
**warm COVID DD ≈ 40.61% worst-mark / 38.80% MT5-real at s=1.6.** The team's standing rule:
*"never quote 20.9%/8% as true worst-case; the true crisis DD is ~35-40%."* The **2022 warm
21.95%** figure stands (the native EA holds the model's margin-safe position, not V1's pyramid).
**The bias calibration (0.98) does NOT rescue the tail** — it was measured on Aug-2024, a
moderate 14.55% carry unwind, *not* a crisis; a calm-window bias cannot certify the crash tail.

## 1. The certification chain — the EXECUTOR is certified (this stands)

| Certification | Result | Verdict |
|---|---|---|
| Compute fidelity (R1) | live compute vs golden, full 2020-2025 | max\|diff\| 5.06e-13; Core seam 0.0 | **PASS** |
| Position fidelity | per-bar `book_frac→lots` self-check | **69 mismatches / 6 yr** | **PASS** |
| Sat port cert | Sat engine vs golden, record feed | 24/24 bit-exact | **PASS** |
| Full-window reconciliation | net €2.93M, worst *realized* DD 22.9% vs golden 22.2% | +0.7pp | **RECONCILED** |
| Friction decomposition | −12.9pp = swap 66% / spread 19% / comm 5% | quantified | — |

**And crucially, the native EA *fixes* the V1 over-leverage:** V1's 52%-DD / 90% ML / stop-out
May-2022 event was a cross-sleeve joint-equity double-count (an 8.23-lot USDJPY pyramid vs the
model's ~3.65). The native EA's position fidelity means it holds the **model's margin-safe
position** → s=1.6 at 1:30 runs the full window at **min ML 121% (1m-OHLC)**, no stop-out. This
is a real, load-bearing achievement — the executor is sound and margin-safe *as modelled*.

## 2. But the model, the dial, and the tail are in-sample-flattering

- **The tail is ~40%, not 22.9%.** The 22.9% "worst DD" is a *warm-era 2022 realized* event;
  the true crisis tail is the **~40% warm COVID** (worst-mark), close to the 50% stop-out
  (~10pp buffer on close-mark), and **real-tick intra-bar crisis microstructure is UNTESTED**
  (broker has no pre-2023 ticks; generated ticks smooth the stop-out wicks).
- **s=1.6 is an aggressive dial.** The v1.0 red-team certified **s=1.1** as probe-robust and
  labelled s=1.2-1.4 *"aggressive frontier, not probe-robust."* s=1.6 ships only because a
  later adjudication **relaxed the pre-registered breach cap 0.15→0.20** (`VALIDATION.md`: the
  0.15 gate ships none at s=1.6). The team's own honest-frontier read: *"the honest product is
  the SAFE IC (s≈0.7)."* At s≈0.7, warm COVID DD ~18%, margin clears, red-team-robust.
- **In-sample selection.** 2020-2025 is the design/mining window (pre-mined by both parent
  programs). +158% is an in-sample number.

## 3. What certification cannot do

RECONCILED = same model, same data, faithful — **structurally blind to overfitting** and
silent on live generalization. The *one* OOS datum (2026-H1 forward, "4/4") tests almost
nothing the demo deploys: **s=1.1 not 1.6, record engine not the native EA, Duka feed with
USTEC proxied, 14 symbols not 33, ~85 days** the pre-registration itself calls statistically
weak — and it realized **+12.34% / Sharpe 1.17** against a pre-stated +40-70%/yr band.

## 4. Residual-risk register (ranked; corrected for the V1-vs-native distinction)

| # | Risk | Tag |
|---|---|---|
| **B1** | **Crisis tail ~38-40% warm at s=1.6** (not 22.9%), close to the 50% stop-out, real-tick-crisis UNTESTED. The dominant risk. | **BLOCKER for live capital** — needs real-tick crisis reconciliation |
| **B2** | **s=1.6 is above the red-team-robust ceiling (s=1.1)** and ~2.3× the honest dial (s≈0.7); shipped via a relaxed breach cap. | **BLOCKER for trade-enabled demo at s=1.6** unless deliberately disclosed |
| **B3** | **No aggregate-margin governor (Task-17)** + the live blender is validated **in-sample only** (this cycle's 3 defects were caught only by golden divergence — forward there is no golden). Native EA is margin-safe *as modelled* (min ML 121% 1m-OHLC), but real-tick intra-bar min-ML is unconfirmed. | MONITOR-ON-DEMO / fix before live |
| M1 | OOS evidence thin (see §3); honest live CAGR heavily discounted. | ACCEPTED-RISK (disclose) |
| M2 | Diversification thins when leaned on: ρ=0.109 *monthly* but *daily* 0.35 (0.42-0.46 in 24-25); both sleeves long XAUUSD 86% of the time — co-directional pile-in. | MONITOR-ON-DEMO |
| M3 | Concentration structural: XAU+USTEC = 61.6% of net; 2025 = 71%. A joint gold+tech reversal (untested by the window) hits both sleeves, both big legs, the biggest swap payers at once. | ACCEPTED-RISK (disclose + position limits) |
| A1 | Live friction likely worse than 0.76× (1m-OHLC hides slippage/crisis-spread; swap is 66% of the gap, modelled as flat 2025 rates, grows with the book). | ACCEPTED-RISK |
| A2 | Margin headroom shrinks at a larger live account (volume caps de-lever winners while swap/losers bind). | MONITOR at small-live |

## 5. The demo-forward plan + graduation gates

**Demo (authorized now, trade-disabled; trade-enabled per the Verdict's dial rule):** real IC
feed; the refuse-latch + daily-state serializer active; a **pre-committed** forward window
(≥3 months, target 6+); no mid-run dial changes. Watch: live DD vs the **~40% warm crisis
reality** (not 22.9%); min ML vs the ≥110% line; per-bar position fidelity; swap accrual; the
concentration legs; zero refuse fires.

**Graduation to live capital (owner-ratified, all mandatory):**
1. A **real-tick crisis reconciliation** exists (external tick data for a COVID/2022-class
   event) showing survival within the ~40% band and min ML > 110% — the protocol's
   non-waivable gate. A calm demo **cannot** substitute.
2. The **Task-17 aggregate-margin governor** shipped (the runtime enforcer of the ML≥110% line).
3. A dial decision: **s≈0.7 (recommended, honest/robust)** or a documented aggressive-frontier
   s with the ~40% tail disclosed.
4. Start small, scale slowly.

## 6. Bottom line

The **executor is genuinely certified and fixes V1's over-leverage** — real, hard-won. But
the **certification headline oversold the tail** (my crisis-cert error): the honest crisis
drawdown at s=1.6 is **~40% warm**, the dial is **above the robust ceiling**, and the
**real-tick crisis test that would falsify the failure mode does not exist**. A trade-disabled
demo is GO; a trade-enabled demo belongs at **s≈0.7** (or s=1.6 only with the tail disclosed);
**live capital is blocked** until the real-tick crisis reconciliation and the margin governor
exist. The demo will likely print money in a calm 2026 tape — that is exactly why it must not
be read as evidence on the question it cannot answer.
