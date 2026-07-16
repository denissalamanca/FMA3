# FMA v4 — kickstart brief (for a fresh session)

*The conversation-initiation context for opening FMA v4 in a **separate** session,
per the standing decision that v4 work does not happen inside FMA3. Paste the block
at the bottom to start; this page is the durable version of it.*

---

## Where things stand (so the new session has the picture)

- **FMA3 (the parent) is validated and in demo-launch prep** — a blended NSF5-Core (w=0.70)
  × FMA2-Satellite (0.30) book, 33 netted symbols, executed by the live-computing
  `FableBookNative` EA. Dials decided (IC s=1.6, FTMO s≈0.70), executor certified, on-broker
  real-tick crisis cert passed (RECON-12). It has an **open demo-readiness thread of its own**
  (see `docs/v3.0/DEMO_GO_NOGO.md` — an OPEX-calendar code fix + measurability gaps). **That is
  FMA3 work; v4 does not touch it.**
- **The v4 backlog is [`OPPORTUNITIES.md`](OPPORTUNITIES.md)** — hypotheses mined from the FMA3
  deep-dive, prioritised:
  - **B1 (HIGH, risk):** home-run dependence — 25 of 5,008 trades = 95% of net; median trade −€0.
  - **B2 (HIGH, risk):** diversification decays under stress — Core-Sat corr −0.16 (COVID) → +0.76 (Apr-25).
  - B3 swap-killed legs · B4 margin reallocation · B5 dynamic tilt (naive fails) — MED/LOW.
  - A1 historical-regime robustness (Dukascopy/synthetic) · A2 symbol cull via LOO ablation — test-methods.

## The strategic steer (the "much higher ROI" framing)

Everything in FMA3 has been *validating* a fixed, capacity-capped (~€2M/account) edge. The
value multiplier now is **not** more validation — it's **a new, uncorrelated edge**. Two
altitudes to choose between as the v4 opener:

1. **Hunt the next edge (new-alpha research sprint)** — highest ceiling; the only direction that
   *grows* the book's Sharpe + capacity rather than measuring it. Mine the two parents' DNA, the
   regimes 2020-25 didn't contain, and untraded markets → a ranked, pre-screened slate of novel
   uncorrelated edge candidates with falsifiable tests.
2. **"Where's the 10x?" — a strategic program review** across NSF5 / FMA2 / FMA3 / the CVE
   validation-engine spinoff → decide whether the next dollar goes to new alpha, productising the
   validation engine, capital-scaling architecture (break the ~€2M cap), or de-fragilizing the
   current edge (B1/B2).

Recommendation: if you want a *concrete* first swing, do **#1**; if you want to *aim* the whole
program before firing, do **#2** first (it decides where all subsequent v4 effort goes).

## Constraints (read the memory: `MEMORY.md`)
- v4 is a **fresh program**. FMA3 and its parents (`../NewStrategyFable5`, `../FableMultiAssets2`)
  are **read-only references**, not edit targets, unless v4 explicitly forks something.
- **First decision to settle with the owner:** where v4 lives — kept here under `docs/v4.0/` +
  a v4 working area, or spun out into its own repo (like the CVE engine). Don't assume.
- Never deploy/trade/move money; any EA ships trade-disabled.

---

## ▶ Paste this to open the v4 session

> Kickstart **FMA v4**, the next program after FMA3. Start by reading
> `docs/v4.0/KICKSTART.md`, `docs/v4.0/OPPORTUNITIES.md`, and `MEMORY.md`. FMA3 (the
> parent blended book) is validated and in its own demo-launch prep — it's a separate
> program; do not work on FMA3 here.
>
> Your first task is **not to execute** — it's to **propose the v4 roadmap**: which
> direction to open with (a new-alpha "hunt the next edge" research sprint · a strategic
> "where's the 10x" program review across NSF5/FMA2/FMA3/CVE · or the risk-findings B1/B2
> de-fragilization), with your reasoning and a rough scope for each. Also surface the one
> decision I need to make first: whether v4 lives in this repo or spins out into its own.
> Give me the proposal, then we pick a direction together before any build.
