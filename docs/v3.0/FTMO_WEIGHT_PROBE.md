# FTMO ±20% weight-probe — record-engine parity of *mechanism*, not of *assurance*

*Run 2026-07-15 (FMA3-011, `scripts/run_ftmo_weight_probe.py`). Adversarially
adjudicated (workflow `wf_be8760a7-dce`, 4 skeptic lenses + synthesis). This
document gives FTMO the same ±20% weight-probe treatment IC has — and is honest
about what that probe does and does not certify.*

---

## The one-line finding

The ±20% **weight** probe ran the *identical machinery* IC used (FMA3-004c):
same `static_blend` perturbation, same ±20% drifts around w=0.70, same
cold-start record engine, same "base + both probes must clear" gate. All six
cells pass. **But that is parity of mechanism, not of assurance** — the weight
probe is *pass-by-construction* and *frame-blind* for FTMO, so it certifies far
less than IC's did. The lever that actually binds FTMO is the **exposure dial
s**, and there the margin is thin and asymmetric.

## The probe grid (record engine, breaker x=3%, €100k, w=0.70 base ±20%)

Two frames per cell: **static** peak-to-trough max-DD (the honest, base-relative
frame that sees the 10% Max-Loss rule) and **`score_v3`** (the monthly-payout-
reset frame that gates the ship). `f` = `worst_month_floor_touch` (reset frame).

| dial | w | **static max-DD** | `score_v3` `f` | `P(breach12m)` | CAGR | `score_v3` |
|---|---:|---:|---:|---:|---:|:--|
| **s=0.70** ship | 0.56 | 11.57% | 0.9010 | 0.0 | +53.6% | compliant |
| | **0.70** | **13.33%** | 0.9088 | 0.0 | +54.0% | compliant |
| | 0.84 | 13.20% | 0.9020 | 0.0 | +54.4% | compliant |
| **s=0.65** crisis | 0.56 | 10.38% | 0.9077 | 0.0 | +48.9% | compliant |
| | **0.70** | 10.84% | 0.9149 | 0.0 | +50.3% | compliant |
| | 0.84 | **12.55%** | 0.9064 | 0.0 | +49.3% | compliant |

**Drift-guard:** the three s=0.70 cells reproduce the archived FMA3-008/010
numbers **bit-exact** (`Δstatic = 0`, `ΔP = 0`) — the record engine is
deterministic and the 2026-07-10 result stands. The s=0.65 dial was never
probed before; it is added here.

## Why "all six compliant" is much weaker than it looks

Three independent reasons (all four adjudication lenses converge; only the COVID
lens returned "sound", and only as a *scoped* parity claim):

1. **Pass-by-construction (weight axis).** At s=0.70 the base w=0.70 is a
   **local drawdown *maximum*** (static DD w56/w70/w84 = 11.57 / 13.33 / 13.20%)
   — both ±20% arms *reduce* DD, so a probe centred there cannot surface a worse
   config. Contrast IC, whose +20% arm *drove* worst-mark DD to **27.55%** of a
   30% cap and *set* the shipped s=1.6. FTMO's arms all sit pinned at
   `P(breach12m)=0.0` with zero headroom consumed. *(At s=0.65 the +20% w arm is
   the local worst, 12.55%, a modest +1.7pp — still within policy.)*

2. **Frame-blind / laundering (the crux).** `score_v3` rebases every calendar
   month to base (modelling the monthly-withdrawal payout cycle), so a sustained
   multi-month drawdown never accumulates toward the absolute €90k floor. The
   result: **every s=0.70 cell shows an 11.6–13.3% *static* drawdown — above the
   10% Max-Loss rule — yet still reports `P(breach12m)=0.0` and `compliant`.**
   The compliance gate never tests static max-DD. That single reset is exactly
   why the record engine reads 0.0 while the native-EA static frame (this repo,
   `FTMO_DIAL_DECISION.md`) reads **~0.73 breaches/yr** at s=0.70. Not a
   contradiction — two frames, and only the static one sees the binding rule.
   *(The scorer fix is tracked separately: task_03aba9d3.)*

3. **Wrong axis.** The binding FTMO lever is the exposure **dial s**, not the
   blend weight w. From the native-EA breach table:

   | dial s | breaches/yr | vs ≤1/yr policy |
   |---:|---:|:--|
   | 0.56 (−20% of ship) | ≲0.15 | safe |
   | 0.65 (crisis-margin) | 0.36 | ~2.8× headroom |
   | **0.70 (ship)** | **0.73** | **top of the band, no upside margin** |
   | 0.73 (ceiling) | ~0.9 | ≤1/yr edge |
   | **0.84 (+20% of ship)** | **~2.0** | **breaches decisively** |

   A **±20% move in the *dial*** straddles the breach cliff (−20% safe, +20%
   ~2/yr); a ±20% move in the *weight* never approaches it. The record-engine
   static DD across the dial at w=0.70 corroborates: s=0.60 / 0.65 / 0.70 / 0.80
   = 10.28 / 10.84 / 13.33 / 14.09% — rising with s and ≥10% across the whole
   deployable band.

## What this means for the dial

- **s=0.70 passes the owner's ≤1-breach/year policy at nominal (0.73/yr)** — the
  ship dial is *not* overturned. But it sits at the **top** of its ≤1/yr band
  with **no upside margin**: a +20% dial overshoot, a friction surprise, or a
  crisis all push it over.
- **This is an independent, robustness-based reason to prefer s≈0.65** (0.36/yr,
  ~2.8× headroom; static DD 10.4–12.6% under the same ±20% w probe) — not just
  the crisis intuition already in the dial doc.
- The weight axis is genuinely w-robust (≤~2.2pp static-DD spread under ±20% w),
  which is a real, if minor, reassurance: a config-level split error of ±20%
  does not blow up the FTMO risk.

## Parity verdict + the residual bar

**Parity of mechanism: YES.** Identical procedure to IC's FMA3-004c; it ran and
did not fail. **Parity of assurance: NO** — IC's probe *bound* and set its dial;
FTMO's passes by construction on a frame that cannot see the rule that binds.

**The higher bar neither preset has cleared** is a *native-EA-grade* probe —
over both the weight **and the dial s** — run on the owner's real MT5 equity
curve, scored on the **raw, non-reset static frame** against the absolute €90k
floor, over a **crisis-inclusive / real-tick window** that contains a true
COVID-class month. On the record engine both COVID-blindness (cold-start holds
~zero through March-2020) and frictionlessness are shared symmetrically with IC,
so they don't break *parity* — but they bite FTMO harder: the shared ~18% warm-
crisis tail at s≈0.7 clears IC's 30% ceiling yet **breaches FTMO's 10% floor**.
Real-tick crisis certification remains the open arbiter.

## Caveats (so nothing is oversold)

1. **Record engine, not native EA.** Frictionless-optimistic and COVID cold-
   start blind — the same caveats IC's probe carries, but more consequential for
   FTMO's tighter floor.
2. **`score_v3` launders the binding axis.** The `P(breach12m)=0.0` headline is
   *not* the honest metric; read the static max-DD column and the native-EA
   ~0.73/yr instead. Fix tracked: task_03aba9d3.
3. **The dial breach-table is a native-EA linear-scale** of one pass (Run A),
   not a per-s re-sim — directional, not exact.
4. **±20% w is a weak lever for FTMO.** Do not headline "weight-robust" as
   evidence the dial is hardened; the informative probes are ±20% *s*, a serial/
   block bootstrap, a missed-withdrawal (no-reset) month, and a real-tick crisis
   window.

## Bottom line

FTMO now has the ±20% weight-probe IC has, run and adjudicated honestly: the
dial is robust to ±20% *weight* drift, but the probe is pass-by-construction and
frame-blind, so it is **not** the assurance IC's probe delivered. The real
robustness signal is the **dial margin** — s=0.70 is at the top of its ≤1/yr
band, **s≈0.65 restores headroom** — and the deploy-grade arbiter is the native-
EA static-frame crisis probe, owner-MT5, still open.
