# FMA3 Hypothesis Slate — pre-registered 2026-07-10

Committed before any merged-book simulation. Each hypothesis is structurally
distinct; each is evaluated one lever at a time per PROTOCOL.md. The slate
deliberately contains ZERO sleeve-level changes — both parents' alpha is
frozen; the merge alpha is structural.

## The core structural thesis

The two books were built firewalled from each other and monetize different
regimes with different mechanics:

- **Core** is a convergent high-vol trend/momentum book whose ~26–32pp
  re-split premium is vol-harvesting across ~0-corr high-vol sleeves; its
  weakness is the crisis tail (COVID −35.6% on MT5 tick; 2020Q1 −21.8%) and
  chop quarters (3/24 negQ on tick).
- **Satellite** is a consistency-first book (1/24 negQ, worst quarter −1.4%) whose
  crisis/meanrev/seasonal seats PAY during stress (2020 was its best year,
  +127.6%); its weakness is lower Sharpe (1.85) and a leverage ceiling set by
  its own 30% DD wall (breach 0.121 at scale 10).

They are structurally complementary — Satellite's stress-payers should cushion
exactly the tail that caps Core's leverage, and Core's explosive trend capture
should lift exactly the CAGR/Sharpe ceiling that Satellite's reweighting studies
proved unreachable from inside (allocator study: Sharpe tops 1.94). Neither
program could test this: the firewall forbade it, and both single-book import
channels are dead (H8/H14/H15). The blend level is genuinely untested.

**Falsifiable precondition (H0):** if daily-return correlation between the two
book curves is high (ρ ≥ 0.6) or their drawdowns are co-timed (COVID, 2022Q4),
the thesis is materially weakened and gates below will show it. Measured
first, before any blend is run — see M-0.

## M-0 — Measurements (not experiments; no adoption decision)

On the two parent curves in the engine of record: daily-return ρ (full, and
per-year), co-drawdown profile (each book's DD on the other's 10 worst days /
worst month), per-quarter M2M return matrix, gross-exposure overlap by
instrument (XAUUSD, USTEC, JPY, ETH/BTC, EURGBP stacking), combined margin
headroom at candidate scales. Also ρ(BOOK_USTEC leg, FMA2 intraday) on shared
active days — the duplicate-edge check.

## H-FED-1 — Static blend (no cross-book rebalance)

One account, capital split w to Core book / (1−w) to Satellite book at t0; each
book compounds its own sub-capital with its native mechanics (Core band
re-splits operate on Core slot equities only; Satellite fractions size on Satellite
sub-equity only). Combined account = sum of sub-books; margin/stop-out joint.

- Pre-registered grid: w ∈ {0.30, 0.40, 0.50, 0.60, 0.70} at each book's
  native scale (Core @ R8-anchor extraction, Satellite @ scale 10). No off-grid picks.
- **Selection rule (amended 2026-07-10 12:29, before any grid result was
  read; FMA3-001 was mid-first-point):** the winning w is the grid point that
  passes ALL bars and maximizes Sharpe among passers. If no point passes all
  bars, the static mechanism FAILS and H-FED-2 is only run if ≥1 point passed
  the DD and negQ bars (the risk half) — rebalancing may add the return half,
  but may not rescue a config that failed on risk.
- **Bars (ALL must pass for the mechanism to survive to H-FED-3):** at ≥1 grid
  point: combined worst-mark DD < min(parent DDs in record engine) − 0.5pp;
  combined Sharpe > max(parent Sharpes) + 0.05; negY 0; negQ ≤ min(parents).
  (CAGR is NOT a bar here — it is bought later with scale; DD/Sharpe/negQ are
  the structural evidence.)

## H-FED-2 — Rebalanced blend (cross-book vol-harvesting)

As H-FED-1 plus periodic re-split of TOTAL account equity back to (w, 1−w)
between the books. Variants (each a separate ledger entry, same bars as
H-FED-1 plus): rebalanced variant must beat static H-FED-1 at the same w by
> +0.5pp CAGR at ≤ +0.3pp DD, else DECLINE (cadence complexity not paid for).

- F2a: calendar-quarterly re-split (the v13-REBAL medicine at book level).
- F2b: band-triggered re-split — book share > B_up or < B_dn, daily close
  decision, act next server midnight, 5d min-gap (exact BAND_SYM_25 semantics,
  N=2 slots). Pre-registered: B_up ∈ {0.60, 0.65, 0.70} with B_dn = 1−B_up.
- Mandatory: fixed-schedule ablation on any F2 winner; coupling perturbation
  (±€128) on sub-book seeds; the re-split must respect both books' internal
  state (Core band gap clock does NOT reset on blend re-splits).

## H-FED-3 — Scale re-pick on the winning structure (LAST lever)

Mechanical rule, committed now: on the winning blend config, sweep global
scale multiplier s over a fixed grid {0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4} ×
native, and **ship the largest s such that: worst-mark DD < 20.9%, negQ ≤ 1,
negY = 0, breach P(DD>30%) ≤ 0.12, crisis tail ≤ 35.6%.** If no s clears the
user's CAGR gate (>96.1%) under those ceilings, the highest-CAGR compliant s
is the honest frontier and is shipped as such. Both fraction matrices scale
linearly; caps that bind at higher s (gold overnight, managed-cross, margin
cap 0.9) bind naturally inside the engine.

## H-CAPS-1 — Combined-book structural limits (safety lever, evaluated on the
winning config BEFORE scale re-pick)

Re-derive the two Satellite hard limits for the combined book: overnight |XAUUSD|
cap must count BOOK_XAU + seasonal + mag_xau + crisis gold stacking; managed-
cross 0.5×E unchanged; add a combined |USTEC| sanity check (BOOK_USTEC +
intraday). Bars: caps must not cost > 3pp CAGR at equal DD (if they do, the
stacking they prevent wasn't occurring — keep the rule anyway if free, per
the Satellite "structural rule beats fitted pin" doctrine). This lever can only
REDUCE exposure — it is a guard, not alpha; adoption is default-YES unless
it costs > 3pp.

## H-TAIL-1 (conditional, only if H-FED-1 bars fail on the DD dimension)

If the books' drawdowns prove co-timed, test the one asymmetry the M-0 data
would then justify: Satellite's crisis sleeve weight ×{1.5, 2.0} INSIDE the Satellite
sub-book (weight moved from cash-park, NOT from other sleeves; total Satellite
gross unchanged ≤ its own convention). This touches a parent weight — it is
the ONLY such lever licensed, it is conditional, and it uses Satellite's own
freed-weight mechanism. Bars: combined crisis tail improves ≥ 2pp at ≤ 0.5pp
CAGR cost; DECLINE otherwise.

## Explicitly out of scope (graveyard-adjacent, will not be tested)

New sleeves; re-tuned sleeve params; regime switching between the books
(both registries: dead); DD-throttles/vol-targeting at any level (inverts);
weight optimization beyond the fixed w grid (1/N doctrine + allocator-study
kill); carrying FMA2 sleeves as band slots or the band inside Satellite (closed
channels); anything on either kill list.

## Evaluation order

M-0 → H-FED-1 → H-FED-2 (only if H-FED-1 mechanism survives) → H-CAPS-1 →
H-FED-3 (scale, last) → red-team battery (PROTOCOL §6) → lock → whitepaper →
2026H1 one-shot.
