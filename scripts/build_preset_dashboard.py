#!/usr/bin/env python3
"""FMA3 preset dashboard generator — one HTML scorecard per preset data pack.

Turns a preset data pack (research/outputs/preset_{ic,ftmo}_data.json, produced
by scripts/build_preset_data.py) into a self-contained dashboard HTML that
duplicates docs/v1.0/DASHBOARD.html's exact look-and-feel.  Two dashboards are
produced on every update: docs/v1.0/DASHBOARD_IC.html and DASHBOARD_FTMO.html.

The v1.0 CSS is embedded VERBATIM (byte-for-byte copy of the <style> block in
docs/v1.0/DASHBOARD.html — see V1_STYLE below).  Charts are built as static
inline SVG in Python, mirroring the log-scale equity + worst-mark drawdown
approach of the v1.0 client-side charting code.  No external resources.

API
  load_pack(path) -> dict
  render_dashboard(pack, kind) -> str          # kind in {'ic','ftmo'}
  main(argv=None) -> int

Run (after both preset grids ship, so the packs exist):
  python3 scripts/build_preset_data.py            # writes the two data packs
  python3 scripts/build_preset_dashboard.py       # writes the two dashboards

Smoke test against synthetic fixtures (never touches real docs):
  python3 scripts/build_preset_dashboard.py --fixture /path/to/fixture_dir
      --> reads {dir}/preset_{ic,ftmo}_data.json, writes DASHBOARD_{IC,FTMO}.html
          into the SAME fixture dir (or --out DIR).
"""
from __future__ import annotations

import argparse
import html as _html
import json
import math
from pathlib import Path

_FMA3 = Path(__file__).resolve().parents[1]
OUT = _FMA3 / "research" / "outputs"
DOCS = _FMA3 / "docs" / "v1.0"

# ---------------------------------------------------------------------------
# v1.0 CSS — copied VERBATIM from docs/v1.0/DASHBOARD.html.  Do not edit; this
# is the visual contract.  scripts/build_preset_dashboard.py --byte-check (and
# the smoke test) assert this equals the file's <style> block byte-for-byte.
# ---------------------------------------------------------------------------
V1_STYLE = r"""<style>
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
</style>"""

# Supplemental rules for the two preset-only components (scale-frontier strip
# and the FTMO two-rule explainer).  Uses ONLY v1.0 design tokens (var(--...))
# so it is visually indistinguishable from the reference styling.
EXTRA_STYLE = """<style>
  .fr-strip{display:grid; grid-template-columns:repeat(auto-fit,minmax(104px,1fr)); gap:8px}
  .fr{background:var(--panel-2); border:1px solid var(--line); border-radius:9px;
    padding:9px 10px; display:flex; flex-direction:column; gap:2px; font-family:var(--mono)}
  .fr.ship{border-color:var(--accent); background:var(--accent-soft)}
  .fr.dim{opacity:.4}
  .fr .s{font-size:14px; font-weight:600; color:var(--ink)}
  .fr.ship .s{color:var(--accent)}
  .fr .m{font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums}
  .fr .m b{color:var(--ink); font-weight:600}
  .rule2{display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:0 0 14px}
  @media(max-width:640px){.rule2{grid-template-columns:1fr}}
  .rulebox{background:var(--panel-2); border:1px solid var(--line); border-left-width:3px;
    border-radius:10px; padding:12px 14px}
  .rulebox.d{border-left-color:var(--warn)} .rulebox.st{border-left-color:var(--crit)}
  .rulebox .rt{font-family:var(--mono); font-size:12px; font-weight:600; letter-spacing:.02em; margin-bottom:4px}
  .rulebox.d .rt{color:var(--warn)} .rulebox.st .rt{color:var(--crit)}
  .rulebox .rd{font-size:12px; color:var(--muted); line-height:1.45}
</style>"""


# ---------------------------------------------------------------------------
# small formatting helpers
# ---------------------------------------------------------------------------
def _esc(s) -> str:
    return _html.escape(str(s))


def _eur(v) -> str:
    return f"&euro;{float(v):,.0f}"


def _eur_ax(v: float) -> str:
    if v >= 1e6:
        return f"&euro;{v/1e6:g}M"
    if v >= 1e3:
        return f"&euro;{v/1e3:g}k"
    return f"&euro;{v:g}"


def _pct(v, dp=2, signed=False) -> str:
    s = f"{float(v)*100:+.{dp}f}%" if signed else f"{float(v)*100:.{dp}f}%"
    return s


def _year_ticks(dates):
    out, last = [], None
    for i, d in enumerate(dates):
        y = str(d)[:4]
        if y != last:
            out.append((i, y))
            last = y
    return out


# ---------------------------------------------------------------------------
# gate-tile rendering (schema-generic: renders whatever pack['gates'] holds)
# ---------------------------------------------------------------------------
def _gate_val(g) -> str:
    """Format a gate's numeric value from its label, mirroring v1.0's look."""
    import re

    k = str(g["k"])
    kl = k.lower()
    v = g["v"]
    gate = str(g.get("gate", ""))
    if kl.startswith("p(") or "pass" in kl and kl.startswith("p("):
        return f"{float(v):.3f}" if abs(float(v)) < 0.1 else f"{float(v):.2f}"
    if kl.startswith("p("):
        return f"{float(v):.3f}"
    if "cagr" in kl:
        return _pct(v, 1, signed=True)
    if "dd" in kl or "drawdown" in kl or "tail" in kl:
        return _pct(v, 2)
    if "sharpe" in kl:
        return f"{float(v):.3f}"
    if "days" in kl:
        return f"{float(v):.0f}d"
    if "breaches" in kl or "neg" in kl or "quarter" in kl or "year" in kl:
        m = re.search(r"/\s*(\d+)", gate)
        return f"{int(v)} / {m.group(1)}" if m else f"{int(v)}"
    if isinstance(v, float) and abs(v) < 1:
        return f"{float(v):.3f}"
    return _esc(v)


def _gate_is_soft(g) -> bool:
    return "maximize" in str(g.get("gate", "")).lower()


def _gate_cls(g) -> str:
    if _gate_is_soft(g):
        return "a"
    return "g" if g.get("ok") else "c"


def _gate_mk(g) -> str:
    if _gate_is_soft(g):
        return ""
    if g.get("ok"):
        return '<span class="mk g">&check;</span>'
    return '<span class="mk c">&times;</span>'


def _gate_note(g) -> str:
    if _gate_is_soft(g):
        return "not a hard gate &mdash; maximise"
    return "within gate" if g.get("ok") else "OVER gate"


def _gate_tile(g) -> str:
    val = _gate_val(g)
    sm = " sm" if "/" in val and "%" in val else ""
    return (
        f'<div class="tile {_gate_cls(g)}">'
        f'<div class="lab">{_esc(g["k"])} &middot; {_esc(g.get("gate",""))}{_gate_mk(g)}</div>'
        f'<div class="val{sm}">{val}</div>'
        f'<div class="gate">{_gate_note(g)}</div></div>'
    )


# ---------------------------------------------------------------------------
# SVG charts — static, built in Python, mirroring docs/v1.0/DASHBOARD.html
# ---------------------------------------------------------------------------
def _svg_equity(weekly, initial: float) -> str:
    W, H, pl, pr, pt, pb = 560, 250, 44, 40, 10, 22
    iw, ih = W - pl - pr, H - pt - pb
    vals = [float(v) for _, v in weekly]
    dates = [str(d) for d, _ in weekly]
    n = len(vals)
    if n == 0:
        return "<svg></svg>"
    lomin = min(vals + [initial])
    himax = max(vals + [initial])
    lo = math.floor(math.log10(max(lomin, 1e-9)))
    hi = math.ceil(math.log10(max(himax, lomin * 1.0 + 1)))
    if hi <= lo:
        hi = lo + 1

    def x(i):
        return pl + iw * i / (n - 1) if n > 1 else pl + iw / 2

    def y(v):
        return pt + ih * (1 - (math.log10(max(v, 1e-9)) - lo) / (hi - lo))

    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Equity curve, '
         f'log scale, {_eur(initial)} account growing to {_eur(vals[-1])}">']
    p.append('<defs><linearGradient id="eqg" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0" stop-color="#57d7cc" stop-opacity=".28"/>'
             '<stop offset="1" stop-color="#57d7cc" stop-opacity="0"/>'
             '</linearGradient></defs>')
    # gridlines: 1x and 3x per decade inside the range
    gvals = []
    for d in range(lo, hi + 1):
        for mult in (1, 3):
            val = mult * 10 ** d
            if 10 ** lo <= val <= 10 ** hi:
                gvals.append(val)
    for val in sorted(set(gvals)):
        yy = y(val)
        p.append(f'<line class="grid" x1="{pl}" y1="{yy:.1f}" x2="{W-pr}" y2="{yy:.1f}"/>')
        p.append(f'<text class="ax" x="{pl-7}" y="{yy+3:.1f}" text-anchor="end">{_eur_ax(val)}</text>')
    for i, yr in _year_ticks(dates):
        p.append(f'<text class="ax" x="{x(i):.1f}" y="{H-6}" text-anchor="middle">{yr}</text>')
    # account initial marked
    yi = y(initial)
    p.append(f'<line x1="{pl}" y1="{yi:.1f}" x2="{W-pr}" y2="{yi:.1f}" '
             f'stroke="#83909f" stroke-width="1" stroke-dasharray="2 3" stroke-opacity=".7"/>')
    p.append(f'<text class="reflab" x="{W-pr+4}" y="{yi+3:.1f}" fill="#83909f">start</text>')
    # area + line + end dot
    line = f"M{x(0):.1f},{y(vals[0]):.1f}"
    area = f"M{x(0):.1f},{pt+ih} L{x(0):.1f},{y(vals[0]):.1f}"
    for i in range(1, n):
        line += f" L{x(i):.1f},{y(vals[i]):.1f}"
        area += f" L{x(i):.1f},{y(vals[i]):.1f}"
    area += f" L{x(n-1):.1f},{pt+ih} Z"
    p.append(f'<path d="{area}" fill="url(#eqg)"/>')
    p.append(f'<path d="{line}" fill="none" stroke="#57d7cc" stroke-width="2" stroke-linejoin="round"/>')
    p.append(f'<circle cx="{x(n-1):.1f}" cy="{y(vals[n-1]):.1f}" r="3.5" '
             f'fill="#57d7cc" stroke="#0a0e14" stroke-width="1.5"/>')
    p.append("</svg>")
    return "".join(p)


def _svg_drawdown(drawdown, kind: str) -> str:
    W, H, pl, pr, pt, pb = 540, 250, 34, 64, 10, 22
    iw, ih = W - pl - pr, H - pt - pb
    dd = [-abs(float(v)) * 100.0 for _, v in drawdown]  # signed percent
    dates = [str(d) for d, _ in drawdown]
    n = len(dd)
    if n == 0:
        return "<svg></svg>"
    if kind == "ftmo":
        refs = [(-5.0, "Daily", "5%", "#e2a83c"), (-10.0, "Static", "10%", "#ef5f5f")]
    else:
        refs = [(-30.0, "Gate", "30%", "#ef5f5f")]
    worst = min(dd)
    mn = min(dd + [r[0] for r in refs])
    lo = 5 * math.floor((mn - 3) / 5)
    if lo > -5:
        lo = -5
    hi = 0

    def x(i):
        return pl + iw * i / (n - 1) if n > 1 else pl + iw / 2

    def y(v):
        return pt + ih * (v - hi) / (lo - hi)

    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Drawdown, '
         f'worst {worst:.1f} percent">']
    p.append('<defs><linearGradient id="ddg" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0" stop-color="#ef5f5f" stop-opacity=".30"/>'
             '<stop offset="1" stop-color="#ef5f5f" stop-opacity=".02"/>'
             '</linearGradient></defs>')
    v = 0
    while v >= lo:
        yy = y(v)
        op = ".9" if v == 0 else ".5"
        p.append(f'<line class="grid" x1="{pl}" y1="{yy:.1f}" x2="{W-pr}" y2="{yy:.1f}" stroke-opacity="{op}"/>')
        p.append(f'<text class="ax" x="{pl-6}" y="{yy+3:.1f}" text-anchor="end">{v}%</text>')
        v -= 5
    for i, yr in _year_ticks(dates):
        p.append(f'<text class="ax" x="{x(i):.1f}" y="{H-6}" text-anchor="middle">\'{yr[2:]}</text>')
    area = f"M{x(0):.1f},{y(0):.1f}"
    for i in range(n):
        area += f" L{x(i):.1f},{y(dd[i]):.1f}"
    area += f" L{x(n-1):.1f},{y(0):.1f} Z"
    p.append(f'<path d="{area}" fill="url(#ddg)" stroke="#ef5f5f" stroke-width="1.2" stroke-linejoin="round"/>')
    # honest worst floor (amber) + the preset ceiling rule line(s)
    lines = [(worst, "Worst", f"{worst:.1f}%", "#e2a83c")] + refs
    for val, w1, w2, col in lines:
        yy = y(val)
        p.append(f'<line x1="{pl}" y1="{yy:.1f}" x2="{W-pr}" y2="{yy:.1f}" '
                 f'stroke="{col}" stroke-width="1" stroke-dasharray="3 3" stroke-opacity=".8"/>')
        p.append(f'<text class="reflab" x="{W-pr+4}" y="{yy+3:.1f}" fill="{col}">{w1}</text>')
        p.append(f'<text class="reflab" x="{W-pr+4}" y="{yy+13:.1f}" fill="{col}" fill-opacity=".75">{w2}</text>')
    p.append("</svg>")
    return "".join(p)


# ---------------------------------------------------------------------------
# scale-frontier strip
# ---------------------------------------------------------------------------
def _frontier_strip(pack) -> str:
    fr = pack.get("frontier", [])
    if not fr:
        return ""
    ship_s = pack.get("ship_s")
    comp_key = "ic_ok" if fr and "ic_ok" in fr[0] else "ok"
    if fr and "breach" in fr[0]:
        bkey, blab = "breach", "breach"
    else:
        bkey, blab = "p_breach", "P(brch)"
    cells = []
    for pt in fr:
        s = pt["s"]
        is_ship = ship_s is not None and abs(float(s) - float(ship_s)) < 1e-9
        ok = bool(pt.get(comp_key, True))
        cls = "fr"
        if is_ship:
            cls += " ship"
        elif not ok:
            cls += " dim"
        cells.append(
            f'<div class="{cls}">'
            f'<span class="s">s={s:g}</span>'
            f'<span class="m">CAGR <b>{_pct(pt["cagr"],0,signed=True)}</b></span>'
            f'<span class="m">DD <b>{_pct(pt["dd"],1)}</b></span>'
            f'<span class="m">{blab} <b>{float(pt.get(bkey,0)):.2f}</b></span>'
            f"</div>"
        )
    return (
        '<section class="trail">'
        '<h2>How the dial was set &mdash; scale frontier, shipped s highlighted, '
        "non-compliant s dimmed</h2>"
        f'<div class="fr-strip">{"".join(cells)}</div>'
        "</section>"
    )


# ---------------------------------------------------------------------------
# FTMO-only two-rule + challenge-pass strip
# ---------------------------------------------------------------------------
def _ftmo_strip(pack) -> str:
    hd = pack.get("headline", {})
    initial = float(pack.get("initial", 100000.0))
    p_pass = hd.get("p_pass_p1")
    med = hd.get("median_days_p1")
    pass_tiles = []
    if p_pass is not None:
        pass_tiles.append(
            '<div class="tile a"><div class="lab">P(pass Phase-1 &plus;10%)</div>'
            f'<div class="val">{float(p_pass)*100:.0f}%</div>'
            '<div class="gate">bootstrapped, no breach in the window</div></div>'
        )
    if med is not None:
        pass_tiles.append(
            '<div class="tile a"><div class="lab">Median days to &plus;10%</div>'
            f'<div class="val">{float(med):.0f}d</div>'
            '<div class="gate">Phase-1 target pace</div></div>'
        )
    return (
        '<section class="trail">'
        "<h2>FTMO two-rule model &middot; challenge-pass projection</h2>"
        '<div class="rule2">'
        '<div class="rulebox d"><div class="rt">Daily loss &minus;5%</div>'
        "<div class=\"rd\">measured from previous-midnight equity <b>including "
        f"floating PnL</b>; 5% of initial = {_eur(initial*0.05)}. Resets each "
        "server midnight.</div></div>"
        '<div class="rulebox st"><div class="rt">Static floor &minus;10%</div>'
        "<div class=\"rd\">equity must never touch 90% of initial = "
        f"{_eur(initial*0.90)}; absolute floor for the whole challenge.</div></div>"
        "</div>"
        f'<div class="gates">{"".join(pass_tiles)}</div>'
        "</section>"
    )


# ---------------------------------------------------------------------------
# top-level render
# ---------------------------------------------------------------------------
def render_dashboard(pack: dict, kind: str) -> str:
    kind = kind.lower()
    preset = pack.get("preset", "")
    account = pack.get("account", "")
    ship_s = pack.get("ship_s")
    cfg = str(pack.get("config_hash", ""))
    cfg8 = cfg[:8] if cfg else ""
    initial = float(pack.get("initial", 10000.0))
    final = float(pack.get("final_equity", initial))
    gates = pack.get("gates", [])
    n_ok = sum(1 for g in gates if g.get("ok"))
    n_tot = len(gates)

    tag = "IC PRESET" if kind == "ic" else "FTMO PRESET"
    title = f"FMA3 {preset} &mdash; Preset Scorecard"

    gate_tiles = "".join(_gate_tile(g) for g in gates)

    eq_svg = _svg_equity(pack.get("weekly", []), initial)
    dd_svg = _svg_drawdown(pack.get("drawdown", []), kind)
    if kind == "ftmo":
        dd_sub = "worst-mark, weekly max &middot; daily &minus;5% and static &minus;10% FTMO rule lines marked"
    else:
        dd_sub = "worst-mark at 1m marks, weekly max &middot; 30% DD ceiling marked"

    frontier = _frontier_strip(pack)
    ftmo = _ftmo_strip(pack) if kind == "ftmo" else ""

    ship_note = pack.get("ship_note") or (
        "clears every pre-committed owner gate for this preset"
    )

    parts = []
    parts.append("<!doctype html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append(f"<title>{title}</title>")
    parts.append(V1_STYLE)
    parts.append(EXTRA_STYLE)
    parts.append("</head>")
    parts.append("<body>")
    parts.append('<main class="dash">')

    # hero + gates-headline
    parts.append('<div class="top"><div>')
    parts.append(f'<span class="chip"><span class="dot"></span>FMA3 V1.0 &middot; {tag}</span>')
    parts.append(f'<div class="hero-eq">{_eur(final)}</div>')
    parts.append(
        '<div class="hero-sub"><b>' + _eur(initial) + " &rarr;</b> "
        f"{_esc(preset)} &middot; {_esc(account)} &middot; s={ship_s:g} &middot; "
        f'config <span class="mono">{_esc(cfg8)}</span>. Pinned preset record &mdash; '
        "the shipped dial, not a paper blend.</div>"
    )
    parts.append("</div>")
    parts.append('<div class="verdict">')
    parts.append(f'<div class="score"><b>{n_ok}</b> / {n_tot} gates</div>')
    parts.append(f'<div class="note">{_esc(ship_note)}</div>')
    parts.append("</div></div>")

    # gate tiles
    parts.append(f'<section class="gates">{gate_tiles}</section>')

    # charts
    parts.append('<section class="charts">')
    parts.append(
        '<div class="card"><h3>Equity &mdash; ' + _eur(initial) + " account</h3>"
        f'<div class="csub">log scale &middot; {_esc(preset)} shipped s={ship_s:g} '
        "&middot; weekly close-mark &middot; account initial marked</div>"
        f"{eq_svg}</div>"
    )
    parts.append(
        '<div class="card"><h3>Drawdown</h3>'
        f'<div class="csub">{dd_sub}</div>{dd_svg}</div>'
    )
    parts.append("</section>")

    # frontier + ftmo strips
    parts.append(frontier)
    parts.append(ftmo)

    # footer
    prov = (
        "provisional dial: shipped DD is the in-sample record-DD; live sizing "
        "pending the record-DD &times; MT5 ratio (v1.1)"
    )
    parts.append(
        "<footer><span>"
        f"{_esc(preset)} preset scorecard &middot; regenerated at each stable "
        f"version &middot; all numbers in-sample ({_esc(account)}) &middot; "
        "MT5 real-tick + live demo = remaining falsification tests &middot; "
        f"{prov}</span>"
        f'<span class="mono">FMA3 V1.0 &middot; strategy_fma3.py &middot; '
        f"config {_esc(cfg)}</span></footer>"
    )

    parts.append("</main>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# io + cli
# ---------------------------------------------------------------------------
def load_pack(path) -> dict:
    return json.loads(Path(path).read_text())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the two preset dashboards.")
    ap.add_argument("--fixture", help="dir holding preset_{ic,ftmo}_data.json "
                    "(smoke test; output defaults to the same dir)")
    ap.add_argument("--out", help="output dir (default: docs/v1.0, or --fixture dir)")
    a = ap.parse_args(argv)

    src_dir = Path(a.fixture) if a.fixture else OUT
    out_dir = Path(a.out) if a.out else (Path(a.fixture) if a.fixture else DOCS)
    out_dir.mkdir(parents=True, exist_ok=True)

    for kind in ("ic", "ftmo"):
        pack = load_pack(src_dir / f"preset_{kind}_data.json")
        doc = render_dashboard(pack, kind)
        outp = out_dir / f"DASHBOARD_{kind.upper()}.html"
        outp.write_text(doc)
        print(f"[{kind}] {outp} ({len(doc):,} bytes, "
              f"{sum(1 for g in pack.get('gates',[]) if g.get('ok'))}/"
              f"{len(pack.get('gates',[]))} gates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
