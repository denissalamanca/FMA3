"""Build the FMA3 V1.0 stable-version scorecard dashboard (self-contained HTML).
Template mirrors NSF5 docs/v7/DASHBOARD.html (built by NSF5/mt5/reconcile/v8/build_dashboard.py)
— regenerate per stable version by swapping the DATA/GATES/LEVERS blocks.
All series and figures come from the engine-free writer data pack
research/outputs/package_data.json (itself pinned to fma3_v1_pin.json /
fma3_v1_pin_curve.parquet). Output: archive/docs-v1.0/DASHBOARD.html
"""
import json, pathlib

ROOT = pathlib.Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
PACK = json.load(open(ROOT / "research/outputs/package_data.json"))

# ---- weekly equity (close-mark, EUR 10k base) — three record curves ----
we = PACK["weekly_equity"]
dates = [d for d, _ in we["fma3_v1"]]
fma3  = [v for _, v in we["fma3_v1"]]
v7p   = [v for _, v in we["v7_r8_record"]]
v34p  = [v for _, v in we["v34_s10_record"]]
assert len(dates) == len(fma3) == len(v7p) == len(v34p) == 314
assert abs(fma3[-1] - 665776.69) < 0.005, "hero equity must be the pin to the cent"

# ---- daily worst-mark drawdown -> weekly max (keeps size in the v7 ballpark) ----
import pandas as pd
dd_daily = PACK["daily_drawdown_worst"]["series"]
s = pd.Series([v for _, v in dd_daily],
              index=pd.to_datetime([d for d, _ in dd_daily]))
wk = s.resample("W-SUN").max().dropna()
dd_dates = [d.strftime("%Y-%m-%d") for d in wk.index]
dd = [round(-100.0 * v, 2) for v in wk.values]
assert min(dd) == -15.73, "weekly-max DD must preserve the pinned worst-mark 15.73%"

# ---- headline / gate cross-checks against the pack ----
h = PACK["headline"]
assert round(h["cagr"] * 100, 1) == 101.4
assert round(h["maxdd_worst"] * 100, 2) == 15.73
assert round(h["sharpe"], 3) == 2.467
assert round(h["crisis_tail"] * 100, 2) == 5.36
assert h["neg_years"] == 0 and h["neg_quarters"] == 0
assert all(g["pass"] for g in PACK["gates"]["owner"]) and len(PACK["gates"]["owner"]) == 6
assert PACK["gates"]["composite"]["all_dominant"]
assert PACK["forward"]["verdict"] == "CONFIRM"
assert all(b["pass"] for b in PACK["forward"]["bars"]) and len(PACK["forward"]["bars"]) == 4
assert PACK["meta"]["config_hash"] == "51a7541cc2aaa593"
# worst quarter (all 24 positive) — shown on the negQ tile
worst_q = min(PACK["returns"]["quarterly"], key=PACK["returns"]["quarterly"].get)
assert round(PACK["returns"]["quarterly"][worst_q] * 100, 1) == 2.9 and worst_q == "2022Q4"

DATA = {
    "dates": dates, "fma3": fma3, "v7": v7p, "v34": v34p,
    "ddDates": dd_dates, "dd": dd,
    # honest floor + owner gate ceiling (annotation lines on the DD chart)
    "worstDD": -15.73, "gateDD": -20.9,
}

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FMA3 V1.0 — Portfolio Scorecard</title>
<style>
  :root{
    color-scheme: dark;
    --bg:#0a0e14; --panel:#111823; --panel-2:#0d131c; --line:#1f2836; --line-2:#2a3547;
    --ink:#e8eef6; --muted:#83909f; --faint:#5a6576;
    --accent:#57d7cc; --accent-soft:rgba(87,215,204,.12);
    --good:#46c977; --good-soft:rgba(70,201,119,.10);
    --warn:#e2a83c; --warn-soft:rgba(226,168,60,.10);
    --crit:#ef5f5f; --crit-soft:rgba(239,95,95,.10);
    --sans:-apple-system,"Segoe UI",Roboto,system-ui,"Helvetica Neue",Arial,sans-serif;
    --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{
    background:
      radial-gradient(1200px 600px at 80% -10%, rgba(87,215,204,.06), transparent 60%),
      var(--bg);
    color:var(--ink); font-family:var(--sans);
    font-size:15px; line-height:1.5; -webkit-font-smoothing:antialiased;
    padding:clamp(16px,4vw,40px);
  }
  .dash{max-width:1140px; margin:0 auto; display:flex; flex-direction:column; gap:26px}
  .mono{font-family:var(--mono); font-variant-numeric:tabular-nums}

  /* ---- header / hero ---- */
  .top{display:flex; flex-wrap:wrap; align-items:flex-end; justify-content:space-between; gap:20px}
  .chip{
    display:inline-flex; align-items:center; gap:8px; font-family:var(--mono); font-size:12px;
    letter-spacing:.06em; color:var(--accent); background:var(--accent-soft);
    border:1px solid rgba(87,215,204,.25); padding:5px 11px; border-radius:999px;
  }
  .chip .dot{width:6px;height:6px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}
  .hero-eq{font-family:var(--mono); font-weight:600; font-size:clamp(40px,8vw,72px);
    line-height:.98; letter-spacing:-.02em; margin:14px 0 6px}
  .hero-sub{color:var(--muted); font-size:14px; max-width:60ch}
  .hero-sub b{color:var(--ink); font-weight:600}
  .verdict{text-align:right}
  .verdict .score{font-family:var(--mono); font-size:clamp(30px,6vw,44px); font-weight:600; letter-spacing:-.02em}
  .verdict .score b{color:var(--good)}
  .verdict .note{color:var(--muted); font-size:12.5px; max-width:22ch; margin-left:auto}

  /* ---- gate tiles ---- */
  .gates{display:grid; grid-template-columns:repeat(6,1fr); gap:12px}
  @media(max-width:900px){.gates{grid-template-columns:repeat(3,1fr)}}
  @media(max-width:520px){.gates{grid-template-columns:repeat(2,1fr)}}
  .tile{background:var(--panel); border:1px solid var(--line); border-top-width:2px;
    border-radius:11px; padding:14px 14px 13px; display:flex; flex-direction:column; gap:3px; min-height:118px}
  .tile.g{border-top-color:var(--good)} .tile.w{border-top-color:var(--warn)} .tile.c{border-top-color:var(--crit)} .tile.a{border-top-color:var(--accent)}
  .tile .lab{font-size:10.5px; letter-spacing:.09em; text-transform:uppercase; color:var(--muted); display:flex; align-items:center; gap:6px}
  .tile .val{font-family:var(--mono); font-size:27px; font-weight:600; letter-spacing:-.01em; margin-top:2px}
  .tile.g .val{color:var(--good)} .tile.w .val{color:var(--warn)} .tile.c .val{color:var(--crit)} .tile.a .val{color:var(--accent)}
  .tile .val.sm{font-size:17px; margin-top:9px}
  .tile .gate{font-size:11.5px; color:var(--faint); margin-top:auto}
  .tile .path{font-family:var(--mono); font-size:12px; line-height:1.55; color:var(--ink); margin-top:4px}
  .mk{margin-left:auto; font-family:var(--mono); font-size:12px; font-weight:600}
  .mk.g{color:var(--good)} .mk.w{color:var(--warn)} .mk.c{color:var(--crit)}

  /* ---- charts ---- */
  .charts{display:grid; grid-template-columns:1.55fr 1fr; gap:16px}
  @media(max-width:820px){.charts{grid-template-columns:1fr}}
  .card{background:var(--panel); border:1px solid var(--line); border-radius:13px; padding:16px 18px 12px}
  .card h3{margin:0; font-size:13px; font-weight:600; letter-spacing:.01em}
  .card .csub{color:var(--faint); font-size:11.5px; margin:2px 0 8px}
  svg{display:block; width:100%; height:auto; max-height:320px; overflow:visible}
  .ax{fill:var(--faint); font-family:var(--mono); font-size:10px}
  .grid{stroke:var(--line); stroke-width:1}
  .reflab{fill:var(--muted); font-family:var(--mono); font-size:9.5px}

  /* ---- decision trail ---- */
  .trail h2, .rej h2, .fwd h2{font-size:12px; letter-spacing:.11em; text-transform:uppercase; color:var(--muted); margin:0 0 12px; font-weight:600}
  .fwd h2 b{color:var(--good)}
  .levers{display:grid; grid-template-columns:repeat(4,1fr); gap:12px}
  @media(max-width:820px){.levers{grid-template-columns:repeat(2,1fr)}}
  @media(max-width:480px){.levers{grid-template-columns:1fr}}
  .lever{background:var(--panel-2); border:1px solid var(--line); border-radius:11px; padding:14px; display:flex; flex-direction:column; gap:7px}
  .lever .st{display:inline-flex; align-items:center; gap:7px; font-family:var(--mono); font-size:11px; letter-spacing:.04em; font-weight:600}
  .lever.ad .st{color:var(--good)} .lever.de .st{color:var(--crit)} .lever.no .st{color:var(--warn)}
  .lever .st .ic{width:15px;height:15px;border-radius:4px;display:grid;place-items:center;font-size:10px;line-height:1}
  .lever.ad .st .ic{background:var(--good-soft);color:var(--good)}
  .lever.de .st .ic{background:var(--crit-soft);color:var(--crit)}
  .lever.no .st .ic{background:var(--warn-soft);color:var(--warn)}
  .lever .nm{font-size:14px; font-weight:600; letter-spacing:-.01em}
  .lever .ds{font-size:12px; color:var(--muted); line-height:1.45}

  /* ---- rejected strip ---- */
  .rej-list{display:flex; flex-wrap:wrap; gap:8px}
  .rej-item{font-family:var(--mono); font-size:11.5px; color:var(--muted); background:var(--panel-2);
    border:1px solid var(--line); border-radius:7px; padding:6px 10px}
  .rej-item s{color:var(--crit); text-decoration:none; opacity:.85; margin-right:7px}
  .rej-item b{color:var(--ink); font-weight:600}

  /* ---- forward strip ---- */
  .fwd-note{color:var(--faint); font-size:11.5px; margin-top:10px; line-height:1.5}
  .fwd-note b{color:var(--muted); font-weight:600}

  footer{border-top:1px solid var(--line); padding-top:14px; color:var(--faint); font-size:11.5px;
    display:flex; flex-wrap:wrap; justify-content:space-between; gap:10px}
  footer .mono{color:var(--muted)}
  a{color:var(--accent); text-decoration:none}
</style>
</head>
<body>
<main class="dash">

  <div class="top">
    <div>
      <span class="chip"><span class="dot"></span>FMA3 V1.0 &middot; LATEST STABLE</span>
      <div class="hero-eq">&euro;665,777</div>
      <div class="hero-sub"><b>&euro;10,000 &rarr;</b> over 2020&ndash;2025 &middot; blend book &middot; w70/30 &middot; s=1.1 &middot; single account &middot; <b>1m worst-mark accounting</b>. Both shipped parents in one account &mdash; the pinned record, not a paper blend.</div>
    </div>
    <div class="verdict">
      <div class="score"><b>6</b> / 6 gates</div>
      <div class="note">clears every owner gate and dominates both parents on all 7 composite dimensions</div>
    </div>
  </div>

  <section class="gates">
    <div class="tile g"><div class="lab">CAGR &middot; &ge;96.1%<span class="mk g">&check;</span></div><div class="val">+101.4%</div><div class="gate">annualised, crash-inclusive &mdash; beats the best parent</div></div>
    <div class="tile g"><div class="lab">Max DD &middot; &lt;20.9%<span class="mk g">&check;</span></div><div class="val">15.73%</div><div class="gate">worst-mark, 1m marks &mdash; below both parents</div></div>
    <div class="tile g"><div class="lab">COVID tail &middot; &le;35.6%<span class="mk g">&check;</span></div><div class="val">5.36%</div><div class="gate">the 2020 event &mdash; the parent&rsquo;s &ldquo;accepted&rdquo; bar, cleared 6&times; over</div></div>
    <div class="tile g"><div class="lab">Sharpe &middot; &gt;2.03<span class="mk g">&check;</span></div><div class="val">2.467</div><div class="gate">daily, annualised &mdash; the diversification dividend</div></div>
    <div class="tile g"><div class="lab">Neg years &middot; 0<span class="mk g">&check;</span></div><div class="val">0 / 6</div><div class="gate">every year positive; worst +48.8% (2022)</div></div>
    <div class="tile g"><div class="lab">Neg qtrs &middot; &le;1<span class="mk g">&check;</span></div><div class="val">0 / 24</div><div class="gate">every quarter positive; worst +2.9% (2022Q4)</div></div>
  </section>

  <section class="charts">
    <div class="card">
      <h3>Equity &mdash; &euro;10,000 account</h3>
      <div class="csub">log scale &middot; blend book, close-mark weekly &middot; parents&rsquo; record curves faint (v7 &euro;532k, v3.4 &euro;450k)</div>
      <div id="eq"></div>
    </div>
    <div class="card">
      <h3>Drawdown</h3>
      <div class="csub">worst-mark at 1m marks, weekly max &middot; 15.73% floor and 20.9% owner gate marked</div>
      <div id="dd"></div>
    </div>
  </section>

  <section class="trail">
    <h2>How V1.0 was reached &mdash; four levers, each tested against pre-committed bars</h2>
    <div class="levers">
      <div class="lever ad"><div class="st"><span class="ic">&check;</span>ADOPTED</div><div class="nm">Static blend, w = 0.70</div><div class="ds">Pre-registered grid w = .30&ndash;.70: w50/w60/w70 pass every H-FED-1 bar; winner by rule (max Sharpe among passers). Friction &minus;2.7pp, already in the pin.</div></div>
      <div class="lever de"><div class="st"><span class="ic">&times;</span>DECLINED</div><div class="nm">Cross-book rebalance</div><div class="ds">All four cadences (quarterly + 3 band rules) miss the &le;+0.3pp DD bar &mdash; rebalancing couples the disjoint troughs it harvests. Static w70 stands.</div></div>
      <div class="lever no"><div class="st"><span class="ic">&#9675;</span>NO-OP</div><div class="nm">Joint exposure caps</div><div class="ds">Verified, not assumed: overnight joint gold p99 1.97&times; / max 2.03&times; equity = exactly entitlement, 0 hours over. Per-book caps compose; no joint cap added.</div></div>
      <div class="lever ad"><div class="st"><span class="ic">&check;</span>ADOPTED</div><div class="nm">Global scale s = 1.1</div><div class="ds">The ceiling rule alone said s=1.4; the w+20% probe broke it (DD +3.59pp). Probe-robust re-pick &rArr; s=1.1 &mdash; the only fully parent-dominant point (7/7).</div></div>
    </div>
  </section>

  <section class="rej">
    <h2>Stress-tested after V1.0 &mdash; every richer variant rejected with cause, so static w70 @ s=1.1 is the frontier</h2>
    <div class="rej-list">
      <span class="rej-item"><s>&times;</s><b>Quarterly rebalance (F2a)</b> &mdash; +1.1pp CAGR costs +0.43pp DD</span>
      <span class="rej-item"><s>&times;</s><b>Band rebalance .60/.65 (F2b)</b> &mdash; degenerate at w70: 418 events &asymp; every 5d</span>
      <span class="rej-item"><s>&times;</s><b>Band rebalance .70 (F2b)</b> &mdash; &minus;0.34pp CAGR, pays nothing</span>
      <span class="rej-item"><s>&times;</s><b>s = 1.2&ndash;1.3 aggressive frontier</b> &mdash; DD fits at locked w, not probe-robust at w+20%</span>
      <span class="rej-item"><s>&times;</s><b>s = 1.4 ceiling pick</b> &mdash; +141% CAGR mirage; perturbation FAIL (w+20% dDD +3.6pp)</span>
      <span class="rej-item"><s>&times;</s><b>w &plusmn;20% probe surface</b> &mdash; w_up20 DD 17.97% binds the ceiling &rArr; s=1.1 (FMA3-RT)</span>
      <span class="rej-item"><s>&times;</s><b>Off-grid w80</b> &mdash; Sharpe still rising at the grid edge; NOT tested, the grid is binding</span>
    </div>
  </section>

  <section class="fwd">
    <h2>Forward confirmation &mdash; 2026H1 one-shot, consumed 2026-07-10 &middot; <b>CONFIRM 4 / 4</b></h2>
    <div class="gates">
      <div class="tile g"><div class="lab">F1 &middot; DD &lt; 20.9%<span class="mk g">&check;</span></div><div class="val">17.67%</div><div class="gate">window worst-mark, fresh &euro;10k seed</div></div>
      <div class="tile g"><div class="lab">F2 &middot; Return &gt; &minus;10%<span class="mk g">&check;</span></div><div class="val">+12.34%</div><div class="gate">Jan&ndash;Apr 2026, &euro;10,000 &rarr; &euro;11,234</div></div>
      <div class="tile g"><div class="lab">F3 &middot; No stop-out<span class="mk g">&check;</span></div><div class="val">0 / 0</div><div class="gate">stop-outs / margin-cap binds in the window</div></div>
      <div class="tile g"><div class="lab">F4 &middot; Sub-books &gt; &minus;20%<span class="mk g">&check;</span></div><div class="val sm">+15.99 / +13.59%</div><div class="gate">v7 / v3.4 native window return</div></div>
      <div class="tile a"><div class="lab">Window Sharpe</div><div class="val">1.17</div><div class="gate">4 months, daily annualised &mdash; not a gate</div></div>
      <div class="tile a"><div class="lab">Monthly path</div><div class="path">Jan&nbsp;+14.9%<br>Feb&nbsp;&minus;0.2%<br>Mar&nbsp;+0.4%<br>Apr&nbsp;&minus;2.4%</div><div class="gate">front-loaded, then flat</div></div>
    </div>
    <div class="fwd-note"><b>Margin envelope:</b> max margin/balance 32.4% vs the 90% cap &middot; min margin level 3.11 vs 0.50 stop-out. <b>Read honestly:</b> Duka feed (not IC, ~8pp documented divergence), USA500 proxied by USTEC (corr 0.89), 14-symbol coverage for v3.4 &mdash; four months is a breakdown detector, not proof.</div>
  </section>

  <footer>
    <span>Portfolio scorecard &middot; regenerated at each stable version &middot; gates from <span class="mono">archive/docs-v1.0/PERFORMANCE.md</span> &middot; all numbers in-sample (IC 2020&ndash;25); the 2026H1 one-shot is consumed; MT5 real-tick + live demo are the remaining falsification tests</span>
    <span class="mono">FMA3 V1.0 &middot; strategy_fma3.py &middot; config 51a7541cc2aaa593</span>
  </footer>
</main>

<script>
const D = __DATA__;
const NS="http://www.w3.org/2000/svg";
function el(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;}
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

function yearTicks(dates){const out=[];let last=null;dates.forEach((d,i)=>{const y=d.slice(0,4);if(y!==last){out.push([i,y]);last=y;}});return out;}

function equityChart(){
  const W=560,H=250,pl=44,pr=40,pt=10,pb=22, iw=W-pl-pr, ih=H-pt-pb;
  const eq=D.fma3, n=eq.length;
  const lo=Math.log10(10000), hi=Math.log10(1000000);
  const x=i=>pl+iw*i/(n-1);
  const y=v=>pt+ih*(1-(Math.log10(v)-lo)/(hi-lo));
  const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,role:"img","aria-label":"Equity curve, ten thousand euros growing to over six hundred sixty-five thousand, above both parent curves"});
  const defs=el("defs",{}); const g=el("linearGradient",{id:"eqg",x1:0,y1:0,x2:0,y2:1});
  g.append(el("stop",{offset:0,"stop-color":"#57d7cc","stop-opacity":.28}),el("stop",{offset:1,"stop-color":"#57d7cc","stop-opacity":0}));
  defs.append(g); svg.append(defs);
  [10000,30000,100000,300000,900000].forEach(v=>{
    const yy=y(v); svg.append(el("line",{class:"grid",x1:pl,y1:yy,x2:W-pr,y2:yy}));
    const lab=el("text",{class:"ax",x:pl-7,y:yy+3,"text-anchor":"end"}); lab.textContent=(v>=1e6?"€1M":"€"+(v/1000)+"k"); svg.append(lab);
  });
  yearTicks(D.dates).forEach(([i,yr])=>{const t=el("text",{class:"ax",x:x(i),y:H-6,"text-anchor":"middle"});t.textContent=yr;svg.append(t);});
  // parents' record curves, faint reference lines
  [[D.v7,"v7","1.1",null],[D.v34,"v3.4","1.1","3 3"]].forEach(([ser,lab,wdt,dash])=>{
    let pd=`M${x(0)},${y(ser[0])}`;
    for(let i=1;i<n;i++)pd+=` L${x(i)},${y(ser[i])}`;
    const attrs={d:pd,fill:"none",stroke:"#83909f","stroke-width":wdt,"stroke-opacity":.55,"stroke-linejoin":"round"};
    if(dash)attrs["stroke-dasharray"]=dash;
    svg.append(el("path",attrs));
    const t=el("text",{class:"reflab",x:x(n-1)+5,y:y(ser[n-1])+3}); t.textContent=lab; svg.append(t);
  });
  let dline=`M${x(0)},${y(eq[0])}`, darea=`M${x(0)},${pt+ih} L${x(0)},${y(eq[0])}`;
  for(let i=1;i<n;i++){dline+=` L${x(i)},${y(eq[i])}`;darea+=` L${x(i)},${y(eq[i])}`;}
  darea+=` L${x(n-1)},${pt+ih} Z`;
  svg.append(el("path",{d:darea,fill:"url(#eqg)"}));
  const p=el("path",{d:dline,fill:"none",stroke:"#57d7cc","stroke-width":2,"stroke-linejoin":"round"}); svg.append(p);
  svg.append(el("circle",{cx:x(n-1),cy:y(eq[n-1]),r:3.5,fill:"#57d7cc",stroke:"#0a0e14","stroke-width":1.5}));
  if(!reduce){const L=p.getTotalLength();p.style.strokeDasharray=L;p.style.strokeDashoffset=L;p.animate([{strokeDashoffset:L},{strokeDashoffset:0}],{duration:1400,easing:"ease-out",fill:"forwards"});}
  document.getElementById("eq").append(svg);
}

function ddChart(){
  const W=540,H=250,pl=34,pr=64,pt=10,pb=22, iw=W-pl-pr, ih=H-pt-pb;
  const dd=D.dd, n=dd.length, lo=-25, hi=0;
  const x=i=>pl+iw*i/(n-1);
  const y=v=>pt+ih*(v-hi)/(lo-hi);
  const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,role:"img","aria-label":"Drawdown, floor at minus fifteen point seven percent, inside the minus twenty point nine percent gate"});
  const defs=el("defs",{}); const g=el("linearGradient",{id:"ddg",x1:0,y1:0,x2:0,y2:1});
  g.append(el("stop",{offset:0,"stop-color":"#ef5f5f","stop-opacity":.30}),el("stop",{offset:1,"stop-color":"#ef5f5f","stop-opacity":.02}));
  defs.append(g); svg.append(defs);
  [0,-5,-10,-15,-20,-25].forEach(v=>{
    const yy=y(v); svg.append(el("line",{class:"grid",x1:pl,y1:yy,x2:W-pr,y2:yy,"stroke-opacity":v===0?.9:.5}));
    const lab=el("text",{class:"ax",x:pl-6,y:yy+3,"text-anchor":"end"}); lab.textContent=v+"%"; svg.append(lab);
  });
  yearTicks(D.ddDates).forEach(([i,yr])=>{const t=el("text",{class:"ax",x:x(i),y:H-6,"text-anchor":"middle"});t.textContent="'"+yr.slice(2);svg.append(t);});
  let area=`M${x(0)},${y(0)}`;
  for(let i=0;i<n;i++)area+=` L${x(i)},${y(dd[i])}`;
  area+=` L${x(n-1)},${y(0)} Z`;
  svg.append(el("path",{d:area,fill:"url(#ddg)",stroke:"#ef5f5f","stroke-width":1.2,"stroke-linejoin":"round"}));
  // honest floor + pre-committed owner gate ceiling
  [[D.worstDD,"Worst −15.73%","#e2a83c"],[D.gateDD,"Gate −20.9%","#ef5f5f"]].forEach(([v,txt,col])=>{
    const yy=y(v);
    svg.append(el("line",{x1:pl,y1:yy,x2:W-pr,y2:yy,stroke:col,"stroke-width":1,"stroke-dasharray":"3 3","stroke-opacity":.8}));
    const t=el("text",{class:"reflab",x:W-pr+4,y:yy+3,fill:col}); t.textContent=txt.split(" ")[0]; svg.append(t);
    const t2=el("text",{class:"reflab",x:W-pr+4,y:yy+13,fill:col,"fill-opacity":.75}); t2.textContent=txt.split(" ")[1]; svg.append(t2);
  });
  document.getElementById("dd").append(svg);
}
equityChart(); ddChart();
</script>
</body>
</html>
"""

out = HTML.replace("__DATA__", json.dumps(DATA, separators=(",", ":")))
p = ROOT / "archive/docs-v1.0/DASHBOARD.html"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(out)
print("wrote", p, len(out), "bytes")
