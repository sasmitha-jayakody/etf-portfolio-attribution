"""ETF Portfolio Construction & Risk Attribution dashboard.

    streamlit run streamlit_app.py

Reads the res_* tables written by scripts/run_pipeline.py from
data/results.db (small, committed) or data/etf_lab.db (full, local).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from portfolio_lab import viz  # noqa: E402

st.set_page_config(page_title="ETF Portfolio Risk & Attribution", layout="wide")

# Dark mode: follow whatever theme Streamlit is showing (the app's own setting,
# which itself follows the operating system unless the reader overrides it).
# viz.use_dark() has to run before the names below are bound, because it swaps
# the module palette rather than passing a mode through twenty call sites.
try:
    DARK = (st.context.theme.type or "light") == "dark"
except Exception:                                   # older Streamlit: stay light
    DARK = False
viz.use_dark(DARK)

from portfolio_lab.viz import (COLORS, FONT, MUTED, NAMES, NAVY, ORDER,  # noqa: E402
                               SEGMENT_COLORS, style)

# Two palettes, one set of rules. Only the values change; every selector below
# reads these tokens, so nothing is hard-coded to a light background.
LIGHT_TOKENS = {
    "--pb-navy": "#102f52", "--pb-accent": "#2a5f9e", "--pb-thead": "#102f52",
    "--pb-surface": "#ffffff", "--pb-panel": "#f3f6f9", "--pb-rule": "#dde3ea",
    "--pb-rule-soft": "#eef2f6", "--pb-row": "#fafcfd", "--pb-rowhead": "#f7f9fb",
    "--pb-hover": "#eaf1f8", "--pb-ink": "#14202e", "--pb-ink2": "#44556a",
    "--pb-ink3": "#5d6e82", "--pb-muted": "#78889b", "--pb-head-ink": "#ffffff",
    "--pb-head-sub": "#c3d6e8", "--pb-head-meta": "#8fabc9", "--pb-pos": "#14733f",
    "--pb-neg": "#a32b23", "--pb-bench": "#737b85", "--pb-sb-ink": "#eaf2fa",
    "--pb-sb-accent": "#9dc3ea", "--pb-sb-cap": "#b3c8de", "--pb-sb-hover": "#1b436f",
    "--pb-sb-on": "#1d4a7c", "--pb-sb-focus": "#173d66", "--pb-cell-bar": "#dbe4ef",
    "--pb-heading": "#102f52", "--pb-rule-hd": "#102f52",
}
DARK_TOKENS = {
    "--pb-navy": "#16283c", "--pb-accent": "#5b9ae0", "--pb-thead": "#1b2c3e",
    "--pb-surface": "#101c29", "--pb-panel": "#17273a", "--pb-rule": "#23364b",
    "--pb-rule-soft": "#1b2c3e", "--pb-row": "#13202e", "--pb-rowhead": "#17273a",
    "--pb-hover": "#1e3247", "--pb-ink": "#e7edf4", "--pb-ink2": "#a9b7c6",
    "--pb-ink3": "#93a3b5", "--pb-muted": "#7e8d9e", "--pb-head-ink": "#eef3f9",
    "--pb-head-sub": "#a9c3dd", "--pb-head-meta": "#8296ab", "--pb-pos": "#3fae6b",
    "--pb-neg": "#e0665a", "--pb-bench": "#8e98a5", "--pb-sb-ink": "#dbe6f2",
    "--pb-sb-accent": "#7fb2e4", "--pb-sb-cap": "#9fb1c5", "--pb-sb-hover": "#1a2c40",
    "--pb-sb-on": "#213951", "--pb-sb-focus": "#1b2f45", "--pb-cell-bar": "#24384f",
    "--pb-heading": "#cfe0f2", "--pb-rule-hd": "#5b9ae0",
}
T = DARK_TOKENS if DARK else LIGHT_TOKENS
CELL_BAR = T["--pb-cell-bar"]

# The level at which a 60/40's bond sleeve stops paying for the equity risk it is
# meant to offset. Set here rather than in the chart so the monitor table and the
# line on the chart can never disagree.
CORR_TRIGGER = 0.30

# Streamlit renamed the full-width argument in 1.49; support both so the app
# runs on whatever version is installed locally or on Streamlit Cloud.
_VER = tuple(int(p) for p in st.__version__.split(".")[:2] if p.isdigit())
FULL = {"width": "stretch"} if _VER >= (1, 49) else {"use_container_width": True}

CSS = """
<style>
  .block-container { padding-top: 1.1rem; padding-bottom: 3rem; max-width: 1520px; }

  /* ---------------------------------------------------------- masthead */
  .pb-head { background:var(--pb-navy); color:var(--pb-head-ink); padding:18px 24px 16px; margin:0 0 16px;
             border-bottom:3px solid var(--pb-accent); }
  .pb-head h1 { font-size:1.75rem; font-weight:900; letter-spacing:-0.015em; margin:0; color:var(--pb-head-ink); }
  .pb-head .sub { font-size:0.92rem; color:var(--pb-head-sub); margin-top:5px; }
  .pb-head .meta { font-size:0.74rem; color:var(--pb-head-meta); margin-top:11px; letter-spacing:0.07em;
                   text-transform:uppercase; }

  /* ---------------------------------------------------------- sections */
  .pb-sec { border-top:2px solid var(--pb-rule-hd); margin:26px 0 10px; padding-top:7px; }
  .pb-sec .t { font-size:0.82rem; font-weight:900; letter-spacing:0.1em; text-transform:uppercase;
               color:var(--pb-heading); }
  .pb-sec .n { font-size:0.84rem; color:var(--pb-ink3); margin-top:3px; max-width:110ch; }

  /* ---------------------------------------------------------- tabs */
  [role="tab"] { padding:11px 18px !important; }
  [role="tab"] p { font-size:0.8rem !important; font-weight:900; letter-spacing:0.09em;
                   text-transform:uppercase; color:var(--pb-ink2); }
  [role="tab"][aria-selected="true"] p { color:var(--pb-heading); }
  [role="tab"]:hover p { color:var(--pb-accent); }
  .stTabs [data-baseweb="tab-highlight"] { background-color:var(--pb-accent) !important; height:3px; }

  /* ---------------------------------------------------------- KPI strip */
  .pb-kpi { display:grid; grid-template-columns:repeat(4,1fr); gap:0; border:1px solid var(--pb-rule);
            border-top:3px solid var(--pb-rule-hd); border-left:none; margin-bottom:8px; background:var(--pb-surface); }
  .pb-kpi > div { border-left:1px solid var(--pb-rule); padding:13px 18px 15px; position:relative;
                  overflow:hidden; }
  .pb-kpi .nm { font-size:0.7rem; font-weight:900; letter-spacing:0.1em; text-transform:uppercase;
                color:var(--pb-ink3); display:flex; align-items:center; gap:8px; }
  .pb-kpi .nm i { width:16px; height:3px; display:inline-block; }
  .pb-kpi .v { font-size:3.3rem; font-weight:900; color:var(--pb-heading); line-height:1; margin-top:6px;
               letter-spacing:-0.035em; font-variant-numeric:tabular-nums; position:relative; z-index:1; }
  .pb-kpi .v small { font-size:0.95rem; font-weight:700; letter-spacing:0.02em; margin-left:4px;
                     color:var(--pb-muted); }
  .pb-kpi .d { font-size:0.84rem; font-weight:700; font-variant-numeric:tabular-nums; position:relative; z-index:1; }
  .pb-kpi .s { font-size:0.78rem; color:var(--pb-muted); margin-top:6px; font-variant-numeric:tabular-nums;
               position:relative; z-index:1; }
  .pb-kpi .s.ir { margin-top:2px; }
  .pb-kpi .s.ir em { font-style:normal; padding:1px 5px; margin-left:4px; border:1px solid var(--pb-rule);
                     font-size:0.72rem; }
  .pb-kpi .spark { position:absolute; right:0; bottom:0; width:62%; height:54%; opacity:0.16; z-index:0; }
  /* the focused portfolio is called out here too, so 'Now showing X' is one system */
  .pb-kpi > div.on { background:var(--pb-panel); box-shadow:inset 0 3px 0 0 var(--c); }
  .pb-kpi > div.off .v, .pb-kpi > div.off .nm i { opacity:0.62; }
  .pb-kpi > div.off .spark { opacity:0.09; }
  .pos { color:var(--pb-pos); } .neg { color:var(--pb-neg); }

  /* ---------------------------------------------------------- tables */
  .pb-tbl-wrap { overflow-x:auto; border:1px solid var(--pb-rule); background:var(--pb-surface); }
  table.pb-tbl { border-collapse:collapse; width:100%; font-size:0.82rem; }
  table.pb-tbl th, table.pb-tbl td { padding:7px 12px; text-align:right; white-space:nowrap;
                                     border-bottom:1px solid var(--pb-rule-soft); }
  table.pb-tbl thead th { background:var(--pb-thead); color:var(--pb-head-ink); font-weight:900; font-size:0.7rem;
                          letter-spacing:0.08em; text-transform:uppercase; border-bottom:0;
                          position:sticky; top:0; }
  table.pb-tbl th.blank, table.pb-tbl th.index_name { background:var(--pb-thead); }
  table.pb-tbl tbody th { text-align:left; font-weight:700; color:var(--pb-heading); background:var(--pb-rowhead);
                          font-size:0.8rem; }
  table.pb-tbl tbody td { color:var(--pb-ink); font-variant-numeric:tabular-nums; }
  table.pb-tbl tbody tr:nth-child(even) td { background:var(--pb-row); }
  table.pb-tbl tbody tr:hover td, table.pb-tbl tbody tr:hover th { background:var(--pb-hover); }
  table.pb-tbl tbody tr { transition:background 0.12s ease; }

  /* ---------------------------------------------------------- chart frames */
  [data-testid="stPlotlyChart"] { border:1px solid var(--pb-rule); border-top:2px solid var(--pb-accent);
                                  padding:10px 12px 4px; background:var(--pb-surface); }
  [data-testid="stCaptionContainer"] p { font-size:0.8rem; color:var(--pb-muted); }

  /* ---------------------------------------------------------- sidebar */
  section[data-testid="stSidebar"] h2 { font-size:0.85rem; letter-spacing:0.1em;
                                        text-transform:uppercase; color:var(--pb-sb-accent); font-weight:900; }
  section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color:var(--pb-sb-cap); font-size:0.79rem; }
  section[data-testid="stSidebar"] label p { color:var(--pb-sb-accent); font-size:0.76rem; font-weight:900;
                                             letter-spacing:0.09em; text-transform:uppercase; }
  /* the portfolio list is the filter: it has to look pressable */
  section[data-testid="stSidebar"] .stButton button { width:100%; justify-content:flex-start;
      background:transparent; border:0; border-left:3px solid var(--pf, var(--pb-sb-accent)); border-radius:0;
      padding:7px 10px; color:var(--pb-sb-ink); font-weight:700; font-size:0.93rem; text-align:left;
      transition:background .15s ease, transform .15s ease, padding-left .15s ease; }
  section[data-testid="stSidebar"] .stButton button:hover { background:var(--pb-sb-hover); padding-left:14px; }
  section[data-testid="stSidebar"] .stButton button:active { transform:translateX(2px); }
  section[data-testid="stSidebar"] .stButton button:focus-visible { outline:2px solid var(--pb-sb-accent); outline-offset:-2px; }
  section[data-testid="stSidebar"] [class*="st-key-pfrow-on-"] .stButton button { background:var(--pb-sb-on);
      color:var(--pb-head-ink); padding-left:14px; }
  section[data-testid="stSidebar"] [class*="st-key-pfrow-on-"] .stButton button::after { content:"\\2713";
      margin-left:auto; font-size:0.85rem; opacity:0.9; }
  section[data-testid="stSidebar"] [class*="st-key-pfrow-"] .stButton button p { font-weight:700;
      font-size:0.93rem; margin:0; }
  .pb-note { margin-top:14px; padding:12px 15px; border-left:3px solid var(--pb-rule-hd);
              background:var(--pb-panel); font-size:0.83rem; line-height:1.55; color:var(--pb-ink3);
              max-width:118ch; }
  .pb-note b { color:var(--pb-heading); }
  .pb-note ul { margin:0; padding-left:18px; }
  .pb-note li + li { margin-top:7px; }
  .pb-hint { font-size:0.74rem; color:var(--pb-head-meta); letter-spacing:0.02em; margin:-4px 0 10px; }
  .pb-pf { display:flex; align-items:center; gap:9px; font-weight:700; font-size:0.93rem; color:var(--pb-sb-ink);
           padding:7px 10px 1px; border-left:3px solid var(--pb-bench); }
  .pb-pf i { width:16px; height:3px; display:inline-block; flex:none; }
  .pb-pf em { font-style:normal; font-size:0.68rem; letter-spacing:0.08em; text-transform:uppercase;
              color:var(--pb-head-meta); margin-left:auto; }
  .pb-focus { margin-top:10px; padding:9px 12px; border-left:3px solid var(--c); background:var(--pb-sb-focus);
              font-size:0.78rem; letter-spacing:0.07em; text-transform:uppercase; font-weight:900;
              color:var(--pb-sb-ink); animation:focusIn 0.45s cubic-bezier(.2,.8,.2,1) both; }
  @keyframes focusIn { from { opacity:0; transform:translateX(-8px); } to { opacity:1; transform:none; } }

  /* ---------------------------------------------------------- motion
     One entrance per tab. Everything re-runs when a tab is opened or the
     focus portfolio changes, which is what makes these replay. */
  @keyframes drawLine { from { stroke-dashoffset:5000; } to { stroke-dashoffset:0; } }
  @keyframes growX { from { transform:scaleX(0); } to { transform:scaleX(1); } }
  @keyframes growY { from { transform:scaleY(0); } to { transform:scaleY(1); } }
  @keyframes riseIn { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:none; } }

  .st-key-anim-growth .js-plotly-plot .scatterlayer .js-line,
  .st-key-anim-cost .js-plotly-plot .scatterlayer .js-line {
      stroke-dasharray:5000; animation:drawLine 1.5s cubic-bezier(.25,.8,.3,1) forwards; }
  .st-key-anim-risk .js-plotly-plot .barlayer,
  .st-key-anim-expo .js-plotly-plot .barlayer {
      transform-box:fill-box; transform-origin:left center;
      animation:growX 0.85s cubic-bezier(.2,.85,.25,1) both; }
  .st-key-anim-stress .js-plotly-plot .barlayer {
      transform-box:fill-box; transform-origin:right center;
      animation:growX 0.85s cubic-bezier(.2,.85,.25,1) both; }
  .st-key-anim-turn .js-plotly-plot .barlayer {
      transform-box:fill-box; transform-origin:center bottom;
      animation:growY 0.8s cubic-bezier(.2,.85,.25,1) both; }
  .anim-rise { animation:riseIn 0.5s cubic-bezier(.2,.8,.2,1) both; }
  .pb-kpi > div { animation:riseIn 0.5s cubic-bezier(.2,.8,.2,1) both; }
  .pb-kpi > div:nth-child(2) { animation-delay:0.07s; }
  .pb-kpi > div:nth-child(3) { animation-delay:0.14s; }
  .pb-kpi > div:nth-child(4) { animation-delay:0.21s; }
  .anim-stagger > div > div:nth-child(1) { animation:riseIn 0.5s cubic-bezier(.2,.8,.2,1) both; }
  .anim-stagger > div > div:nth-child(2) { animation:riseIn 0.5s cubic-bezier(.2,.8,.2,1) 0.09s both; }
  .anim-stagger > div > div:nth-child(3) { animation:riseIn 0.5s cubic-bezier(.2,.8,.2,1) 0.18s both; }

  @media (prefers-reduced-motion: reduce) {
    .st-key-anim-growth .js-plotly-plot .scatterlayer .js-line,
    .st-key-anim-cost .js-plotly-plot .scatterlayer .js-line,
    .st-key-anim-risk .js-plotly-plot .barlayer, .st-key-anim-expo .js-plotly-plot .barlayer,
    .st-key-anim-stress .js-plotly-plot .barlayer, .st-key-anim-turn .js-plotly-plot .barlayer,
    .anim-rise, .pb-kpi > div,
    .anim-stagger > div > div, .pb-focus { animation:none !important; stroke-dasharray:none !important; }
  }
</style>
"""
st.markdown("<style>:root, .stApp {" + "".join(f"{k}:{v};" for k, v in T.items()) + "}</style>",
            unsafe_allow_html=True)
st.markdown(CSS, unsafe_allow_html=True)

# One accent rule per portfolio, so the sidebar rows carry the same colour the
# charts use. Generated because the palette lives in one place.
st.markdown(
    "<style>" + "".join(
        f'section[data-testid="stSidebar"] [class*="st-key-pfrow-on-{c}"] .stButton button,'
        f'section[data-testid="stSidebar"] [class*="st-key-pfrow-off-{c}"] .stButton button'
        f"{{ border-left-color:{COLORS[c]}; }}"
        for c in ORDER
    ) + "</style>", unsafe_allow_html=True)

# Paint the masthead before touching the database, so the page is never blank
# while the script is still starting up.
header = st.empty()
header.markdown(
    "<div class='pb-head'><h1>ETF Portfolio Construction &amp; Risk Attribution</h1>"
    "<div class='sub'>Three multi-asset ETF portfolios against a 60/40 benchmark</div></div>",
    unsafe_allow_html=True)


def table(obj, index: bool = True, colour_by_code: list[str] | None = None) -> None:
    """Render a frame or Styler as HTML, so the header is readable and rows respond to hover.

    Streamlit's own dataframe draws to a canvas, which means no control over
    header contrast and no row hover. These tables are small and static, so
    plain HTML is the better tool.
    """
    styler = obj if hasattr(obj, "to_html") else pd.DataFrame(obj).style
    styles = [{"selector": "", "props": [("border-collapse", "collapse")]}]
    if colour_by_code:
        for i, code in enumerate(colour_by_code):
            styles.append({"selector": f"th.col_heading.col{i}",
                           "props": [("border-bottom", f"3px solid {COLORS[code]}")]})
    styler = (styler.set_table_attributes('class="pb-tbl"')
                    .set_table_styles(styles, overwrite=False)
                    .hide(axis="index", names=True)      # axis names are noise here,
                    .hide(axis="columns", names=True))   # and pandas gives them a whole row
    if not index:
        styler = styler.hide(axis="index")
    st.markdown(f"<div class='pb-tbl-wrap'>{styler.to_html()}</div>", unsafe_allow_html=True)


def sparkline(values, colour: str, w: int = 150, h: int = 40) -> str:
    """Tiny area chart drawn straight into the KPI cell."""
    vals = [float(v) for v in values if pd.notna(v)]
    if len(vals) < 3:
        return ""
    step = max(1, len(vals) // 90)
    vals = vals[::step]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    pts = [(i * w / (len(vals) - 1), h - (v - lo) / rng * (h - 3) - 1.5) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return (f"<svg class='spark' viewBox='0 0 {w} {h}' preserveAspectRatio='none' aria-hidden='true'>"
            f"<polygon points='0,{h} {line} {w},{h}' fill='{colour}'/>"
            f"<polyline points='{line}' fill='none' stroke='{colour}' stroke-width='1.6'/></svg>")


def section(title: str, note: str = "") -> None:
    """Uppercase section label over a navy rule."""
    st.markdown(f"<div class='pb-sec'><div class='t'>{title}</div>"
                + (f"<div class='n'>{note}</div>" if note else "") + "</div>",
                unsafe_allow_html=True)

def signed_text(styler, subset=None):
    """Sign by ink colour, not by a filled block: the numbers stay the loudest thing."""
    def paint(v):
        if pd.isna(v):
            return ""
        return f"color:{viz.POS};font-weight:700" if v >= 0 else f"color:{viz.NEG};font-weight:700"
    return styler.map(paint) if subset is None else styler.map(paint, subset=subset)


def tint(colour: str, alpha: float) -> str:
    """The same hue, washed out. Used so one portfolio keeps one colour everywhere."""
    h = colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def signed(values, colour: str, width: float = 1.3) -> dict:
    """Marker for a bar chart that carries both sign and portfolio identity.

    Colour says which portfolio; a solid fill says positive and a hollow fill
    says negative, on top of the direction the bar already points. Red and green
    would introduce a second colour language for no extra information.
    """
    vals = [0.0 if pd.isna(v) else float(v) for v in values]
    return dict(color=[colour if v >= 0 else tint(colour, 0.16) for v in vals],
                line=dict(color=colour, width=width))


def annotate_peak(fig, frame: pd.DataFrame, label: str, lo: str, hi: str,
                  value: str = "value", when: str = "date", at: str = "max") -> None:
    """Point at the tallest reading inside a window, so the rest of the chart reads relative to it.

    The March 2020 spike dominates both rolling charts. Without a label a reader
    has to hover to find out what it is.
    """
    w = frame[(frame[when] >= pd.Timestamp(lo)) & (frame[when] <= pd.Timestamp(hi))]
    w = w.dropna(subset=[value])
    if w.empty:
        return
    row = w.loc[w[value].idxmax() if at == "max" else w[value].idxmin()]
    fig.add_annotation(
        x=row[when], y=float(row[value]), text=f"<b>{label}</b>", showarrow=True, arrowhead=0,
        arrowwidth=1, arrowcolor=viz.MUTED, ax=34, ay=-26 if at == "max" else 26, xanchor="left",
        font=dict(size=10.5, color=viz.INK, family=FONT), bgcolor=tint(viz.SURFACE, 0.88),
        bordercolor=viz.AXIS, borderwidth=1, borderpad=3)


DB_CANDIDATES = [ROOT / "data" / "results.db", ROOT / "data" / "etf_lab.db", ROOT / "data" / "synthetic.db"]


def seg_of(ticker: str) -> str:
    """Asset-class segment of a ticker (kept here so the app does not import scipy)."""
    from portfolio_lab.config import SEGMENT_OF
    return {"ACWI": "Global Equity"}.get(ticker, SEGMENT_OF.get(ticker, ticker))


@st.cache_data(show_spinner="Loading results...")
def load() -> dict[str, pd.DataFrame]:
    path = next((p for p in DB_CANDIDATES if p.exists()), None)
    if path is None:
        return {}
    con = sqlite3.connect(path)
    names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'res_%'")]
    out = {n[4:]: pd.read_sql(f"SELECT * FROM {n}", con) for n in names}
    con.close()
    for k in ("nav", "rolling", "stock_bond_corr", "weights", "factor_rolling", "acwi_mix"):
        if k in out and "date" in out[k]:
            out[k]["date"] = pd.to_datetime(out[k]["date"])
    out["_path"] = str(path)
    return out


D = load()
if not D or "summary" not in D:
    st.error("No results found. Run `python scripts/fetch_data.py` then `python scripts/run_pipeline.py`.")
    st.stop()

meta = dict(zip(D["meta"]["key"], D["meta"]["value"]))
specs = json.loads(meta["portfolios"])
S = D["summary"].set_index("code")


def pct(x, d=1):
    return "n/a" if pd.isna(x) else f"{x * 100:.{d}f}%"


def bps(x):
    return "n/a" if pd.isna(x) else f"{x:.1f} bp"


def num(x, d=2):
    return "n/a" if pd.isna(x) else f"{x:.{d}f}"


YEARS = (pd.Timestamp(meta["backtest_end"]) - pd.Timestamp(meta["backtest_start"])).days / 365.25


def pp(x, d=2):
    """Percentage points, with negative zero printed as zero."""
    v = x * 100
    return f"{0.0 if abs(v) < 0.5 * 10 ** -d else v:+.{d}f}pp"


def t_of_ir(ir):
    """A t statistic for an information ratio: IR times the root of the sample length.

    Thirteen years is a short sample. Quoting the t beside the IR is the honest
    way to say how much of the active return could be luck.
    """
    return float("nan") if pd.isna(ir) else ir * (YEARS ** 0.5)


# ------------------------------------------------------------------ header
header.markdown(
    "<div class='pb-head'><h1>ETF Portfolio Construction &amp; Risk Attribution</h1>"
    "<div class='sub'>Three multi-asset ETF portfolios against a 60/40 benchmark, "
    "decomposed into allocation, selection and factor effects</div>"
    f"<div class='meta'>Backtest {meta['backtest_start']} to {meta['backtest_end']} &nbsp;|&nbsp; "
    f"daily &nbsp;|&nbsp; USD &nbsp;|&nbsp; total return, net of trading costs &nbsp;|&nbsp; "
    f"source: {meta['data']}</div></div>",
    unsafe_allow_html=True)
if meta["data"] == "SYNTHETIC":
    st.warning("These results come from SYNTHETIC test data, not market data.")

PFS = [c for c in ORDER if c != "BENCH"]
st.session_state.setdefault("focus", PFS[0])

with st.sidebar:
    st.header("Portfolios")
    st.markdown("<div class='pb-hint'>Pick one to highlight it across every exhibit</div>",
                unsafe_allow_html=True)
    for c in PFS:
        state = "on" if st.session_state["focus"] == c else "off"
        with st.container(key=f"pfrow-{state}-{c}"):
            if st.button(specs[c]["name"], key=f"pf-{c}"):
                st.session_state["focus"] = c
                st.rerun()
            st.caption(specs[c]["description"])
    st.markdown(
        f"<div class='pb-pf'><i style='background:{COLORS['BENCH']}'></i>{specs['BENCH']['name']}"
        "<em>reference</em></div>", unsafe_allow_html=True)
    st.caption(specs["BENCH"]["description"])

focus = st.session_state["focus"]


def emph(code: str, width: float = 1.6) -> dict:
    """Line styling for a series, given which portfolio the page is focused on.

    The focused line keeps its full colour and gains weight; the others stay in
    their own colour but step back, so 'Now showing X' means the same thing on
    every exhibit rather than only in the sidebar.
    """
    on = code == focus
    col = COLORS[code] if on else tint(COLORS[code], 0.38 if code != "BENCH" else 0.5)
    return dict(line=dict(color=col, width=width + 1.0 if on else width))


def bar_emph(code: str) -> dict:
    """The bar-chart twin of `emph`: focused bars fill solid, the rest keep only their outline."""
    on = code == focus
    return dict(color=COLORS[code] if on else tint(COLORS[code], 0.34),
                line=dict(color=COLORS[code], width=0 if on else 1.1))


with st.sidebar:
    st.markdown(f"<div class='pb-focus' style='--c:{COLORS[focus]}'>Now showing {NAMES[focus]}</div>",
                unsafe_allow_html=True)

tabs = st.tabs(["Overview", "Risk", "Exposures", "Attribution", "Stress tests", "Costs & turnover", "Method"])

# ------------------------------------------------------------------ overview
with tabs[0]:
    nav = D["nav"]

    # The growth chart is the headline: it gets the height and the top of the page.
    fig = go.Figure()
    for c in ORDER:
        x = nav[nav.code == c]
        fig.add_trace(go.Scatter(x=x.date, y=100 * x.nav, name=NAMES[c], **emph(c, 2.0),
                                 hovertemplate="%{y:.1f}"))
    fig.update_layout(title="Growth of $100 (net of transaction costs)")
    with st.container(key="anim-growth"):        # the one motion moment on this tab
        st.plotly_chart(style(fig, 470), **FULL)

    cells = []
    for c in ORDER:
        r = S.loc[c]
        delta = ("<div class='d' style='color:var(--pb-muted)'>benchmark</div>" if c == "BENCH" else
                 f"<div class='d {'pos' if r.excess_cagr >= 0 else 'neg'}'>"
                 f"{'▲' if r.excess_cagr >= 0 else '▼'} {abs(r.excess_cagr) * 100:.2f}pp vs benchmark</div>")
        val = pct(r.cagr)
        cells.append(
            f"<div class='{'on' if c == focus else 'off'}' style='--c:{COLORS[c]}'>"
            f"{sparkline(nav[nav.code == c].nav, COLORS[c])}"
            f"<div class='nm'><i style='background:{COLORS[c]}'></i>{NAMES[c]}</div>"
            f"<div class='v' style='color:{COLORS[c]}'>{val[:-1]}<small>% p.a.</small></div>{delta}"
            f"<div class='s'>Vol {pct(r.vol)} &nbsp;·&nbsp; Sharpe {r.sharpe:.2f} "
            f"&nbsp;·&nbsp; Max DD {pct(r.max_dd)}</div>"
            + ("" if c == "BENCH" else
               f"<div class='s ir'>Info ratio {num(r.info_ratio)} "
               f"<em>t {num(t_of_ir(r.info_ratio), 1)}</em></div>")
            + "</div>")
    st.markdown("<div class='pb-kpi'>" + "".join(cells) + "</div>", unsafe_allow_html=True)

    # What the headline is, and what it is not. A reader who stops here should
    # still leave with the right impression of how big these differences are.
    def _ir(c):
        return S.loc[c, "info_ratio"]
    st.markdown(
        "<div class='pb-note'><b>How big are these differences, really.</b> "
        f"The strategic portfolio earns {pct(S.loc['SAA', 'excess_cagr'], 2)} a year over the benchmark "
        f"at {pct(S.loc['SAA', 'tracking_error'], 2)} tracking error, an information ratio of "
        f"{num(_ir('SAA'))}. Over {YEARS:.1f} years that is a t of about {num(t_of_ir(_ir('SAA')), 1)}, "
        "so it clears the bar for being real, but only just. "
        f"Quality-Value earns {pct(S.loc['QV', 'excess_cagr'], 2)} a year at an information ratio of "
        f"{num(_ir('QV'))}, a t of about {num(t_of_ir(_ir('QV')), 1)}: that is indistinguishable from zero "
        "and should be read as noise, not as a factor premium being captured. "
        f"Minimum variance is {pct(abs(S.loc['MINVAR', 'excess_cagr']), 2)} a year behind "
        f"(t {num(t_of_ir(_ir('MINVAR')), 1)}). "
        "The Attribution tab shows where each of these came from, and almost none of it is fund selection."
        "</div>", unsafe_allow_html=True)

    fig = go.Figure()
    for c in ORDER:
        x = nav[nav.code == c]
        fig.add_trace(go.Scatter(x=x.date, y=x.drawdown, name=NAMES[c], **emph(c, 1.4),
                                 hovertemplate="%{y:.1%}"))
    fig.update_layout(title="Drawdown from previous peak")
    annotate_peak(fig, nav.assign(value=nav.drawdown), "COVID crash, Mar 2020",
                  "2020-02-15", "2020-05-31", at="min")
    st.plotly_chart(style(fig, 260, pct_y=True), **FULL)

    section("Key statistics", "Annualised unless stated. Risk-free rate is SHV.")
    rows = {
        "Annualised return": S.cagr.map(pct), "Volatility": S.vol.map(pct), "Sharpe ratio": S.sharpe.map(num),
        "Sortino ratio": S.sortino.map(num), "Maximum drawdown": S.max_dd.map(pct),
        "Drawdown trough": S.dd_trough, "Recovered": S.dd_recovery.fillna("not yet"),
        "Tracking error": S.tracking_error.map(pct), "Information ratio": S.info_ratio.map(num),
        "Beta to benchmark": S.beta.map(num), "Down-capture": S.down_capture.map(lambda v: pct(v, 0)),
        "Daily VaR 95%": S.var95_daily.map(lambda v: pct(v, 2)), "Annual turnover (one-way)": S.turnover_ann.map(pct),
        "Trading costs / yr": S.cost_bps_ann.map(bps), "Rebalance rule": S.rule,
    }
    table(pd.DataFrame(rows).T[ORDER].rename(columns=NAMES).style, colour_by_code=ORDER)

    cal = D["calendar"].pivot(index="year", columns="code", values="return")[ORDER].rename(columns=NAMES)
    section("Calendar-year returns")
    table(signed_text(cal.style.format("{:.1%}")), colour_by_code=ORDER)
    per = D["periods"].pivot(index="period", columns="code", values="cagr")[ORDER].rename(columns=NAMES)
    section("Return by market regime", "Annualised within each window.")
    table(signed_text(per.style.format("{:.1%}")), colour_by_code=ORDER)

    section("What this does not prove")
    st.markdown(
        "<div class='pb-note'><ul>"
        "<li><b>One rates shock, and the crisis is borrowed.</b> The window starts in August 2013 because that "
        "is when QUAL listed, so it contains a single genuine rates and inflation shock, 2022. The 2008 crisis "
        "sits outside it and appears only as a stress replay built from proxy funds, which is an estimate rather "
        "than something these portfolios lived through.</li>"
        "<li><b>The factor sleeve was chosen with hindsight.</b> QUAL and VLUE are in here because quality and "
        "value are the factors people talk about today. A fair test would have had to pick them in 2013, and "
        "would have had to accept whatever the next thirteen years did to them.</li>"
        "<li><b>The allocation stance was never re-decided.</b> Most of the strategic portfolio's active return "
        "comes from a fixed asset allocation that was set once and rebalanced back to, not from a repeated "
        "judgement that could be scored. It was right on this one path. One path is not evidence of a process.</li>"
        "</ul></div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ risk
with tabs[1]:
    rl = D["rolling"]
    c1, c2 = st.columns(2)
    fig = go.Figure()
    for c in ORDER:
        x = rl[(rl.code == c) & (rl.metric == "vol_63d")]
        fig.add_trace(go.Scatter(x=x.date, y=x.value, name=NAMES[c], **emph(c), hovertemplate="%{y:.1%}"))
    fig.update_layout(title="Rolling 3-month volatility (annualised)")
    annotate_peak(fig, rl[rl.metric == "vol_63d"], "COVID crash, Mar 2020", "2020-02-15", "2020-06-30")
    c1.plotly_chart(style(fig, 320, pct_y=True), **FULL)
    fig = go.Figure()
    for c in ORDER[:-1]:
        x = rl[(rl.code == c) & (rl.metric == "te_252d")]
        fig.add_trace(go.Scatter(x=x.date, y=x.value, name=NAMES[c], **emph(c), hovertemplate="%{y:.1%}"))
    fig.update_layout(title="Rolling 1-year tracking error vs benchmark")
    annotate_peak(fig, rl[rl.metric == "te_252d"], "COVID crash carried for a year", "2020-03-01", "2021-03-31")
    c2.plotly_chart(style(fig, 320, pct_y=True), **FULL)

    sb = D["stock_bond_corr"]
    fig = go.Figure(go.Scatter(x=sb.date, y=sb.value, line=dict(color=NAVY, width=2), name="IVV vs AGG",
                               hovertemplate="%{y:.2f}"))
    fig.update_layout(title="Stock-bond correlation, IVV vs AGG, rolling 6 months")
    # The level that matters is not zero, it is the level at which bonds stop paying
    # for the equity risk they are supposed to offset.
    fig.add_hline(y=CORR_TRIGGER, line=dict(color=viz.NEG, width=1.2, dash="dash"),
                  annotation_text=f"trigger {CORR_TRIGGER:+.1f}", annotation_position="top left",
                  annotation_font=dict(size=10.5, color=viz.NEG))
    st.plotly_chart(style(fig, 280, legend=False), **FULL)
    corr_now = float(sb.value.iloc[-1])
    st.caption("Below zero, bonds cushion equity drawdowns. Above zero, the diversification argument in a "
               f"60/40 stops working, which is what 2022 looked like. It reads {corr_now:+.2f} today, "
               f"above the {CORR_TRIGGER:+.1f} line, so on this measure the 60/40 is not currently "
               "diversified the way the policy assumes.")

    section("What would change the portfolio",
            "Fixed levels, set in advance, so the decision is not made in the middle of a drawdown.")
    saa, mv, qvr = S.loc["SAA"], S.loc["MINVAR"], S.loc["QV"]
    du_now = D["duration"].set_index("code")
    monitors = pd.DataFrame([
        ["Tracking error vs policy, 1y rolling (Strategic)", pct(saa.tracking_error, 2), "above 2.0%",
         "Drift is no longer the 2.5pp band at work. Rebalance to policy or re-underwrite the tilt."],
        ["One-way turnover a year (Strategic)", pct(saa.turnover_ann), "above 15%",
         "The band is too tight for the volatility regime. Widen it or move to a calendar rule."],
        ["Stock-bond correlation, 6 months", f"{corr_now:+.2f}", f"above {CORR_TRIGGER:+.1f} for two quarters",
         "Bonds are no longer the equity hedge. Shift part of the defence to TIPS, gold or cash."],
        ["Bond sleeve DV01 per $1m (Strategic)", f"${du_now.loc['SAA', 'dv01_per_1m']:,.0f}", "above $300",
         "Duration is doing more than intended. Shorten the sleeve or cut the weight."],
        ["Quality-Value information ratio since inception", num(qvr.info_ratio)
         + f" (t {num(t_of_ir(qvr.info_ratio), 1)})", "still under 0.30 at twenty years",
         "The factor sleeve has not paid for its tracking error. Fold it back into the core."],
        ["Minimum variance turnover a year", pct(mv.turnover_ann), "above 50%",
         "The optimiser is chasing the covariance estimate. Add a turnover penalty inside it."],
    ], columns=["Monitor", "Today", "Trigger", "What I would do"])
    table(monitors.style.set_properties(subset=["Monitor", "What I would do"],
                                        **{"text-align": "left", "white-space": "normal"})
                       .set_properties(subset=["What I would do"], **{"color": viz.INK}),
          index=False)

    section("Where the risk comes from", "Ex-ante volatility split by Euler decomposition at today\u2019s weights.")
    window = st.radio("Covariance window", ["1y", "full"], horizontal=True,
                      format_func=lambda w: "Last 12 months" if w == "1y" else "Full backtest")
    rc = D["risk_contrib"][D["risk_contrib"].window == window]
    agg = rc.groupby(["code", "segment"], as_index=False)[["weight", "pct_risk"]].sum()
    fig = go.Figure()
    seen = set()
    for c in ORDER:
        x = agg[agg.code == c]
        for seg in SEGMENT_COLORS:
            y = x[x.segment == seg]
            if y.empty or (y.weight.abs().sum() < 1e-6):
                continue
            fig.add_trace(go.Bar(y=[f"{NAMES[c]} · capital", f"{NAMES[c]} · risk"],
                                 x=[float(y.weight.iloc[0]), float(y.pct_risk.iloc[0])], orientation="h",
                                 name=seg, marker_color=SEGMENT_COLORS[seg], legendgroup=seg,
                                 showlegend=seg not in seen,
                                 hovertemplate=seg + ": %{x:.1%}<extra></extra>"))
            seen.add(seg)
    fig.update_layout(barmode="stack", title="Capital allocation vs contribution to volatility")
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(autorange="reversed")
    with st.container(key="anim-risk"):
        st.plotly_chart(style(fig, 420).update_layout(hovermode="closest"), **FULL)
    st.caption("Risk contributions are Euler decompositions of ex-ante volatility using a Ledoit-Wolf "
               "shrunk covariance matrix and today's weights.")

# ------------------------------------------------------------------ exposures
with tabs[2]:
    w = D["weights"]
    w = w[w.code == focus].copy()
    w["segment"] = w.ticker.map(seg_of)
    ws = w.groupby(["date", "segment"], as_index=False).weight.sum()
    fig = go.Figure()
    for seg in SEGMENT_COLORS:
        x = ws[ws.segment == seg]
        if x.empty or x.weight.max() < 1e-4:
            continue
        fig.add_trace(go.Scatter(x=x.date, y=x.weight, name=seg, stackgroup="one", mode="lines",
                                 line=dict(width=1, color=SEGMENT_COLORS[seg]),
                                 fillcolor=SEGMENT_COLORS[seg], hovertemplate="%{y:.1%}"))
    fig.update_layout(title=f"{NAMES[focus]}: asset allocation through time (month-end, after drift)")
    st.plotly_chart(style(fig, 340, pct_y=True), **FULL)

    ex = D["exposures"]
    dim = st.radio("Look-through exposure", ["sector", "country", "currency"], horizontal=True,
                   format_func=str.title)
    p = ex[(ex.code == focus) & (ex.dimension == dim)].set_index("bucket").weight
    b = ex[(ex.code == "BENCH") & (ex.dimension == dim)].set_index("bucket").weight
    df = pd.concat([p.rename("port"), b.rename("bench")], axis=1).fillna(0.0)
    df["active"] = df.port - df.bench
    top = df.sort_values("port", ascending=False).head(14 if dim != "sector" else 20)
    c1, c2 = st.columns([3, 2])
    fig = go.Figure()
    fig.add_trace(go.Bar(y=top.index, x=top.port, orientation="h", name=NAMES[focus],
                         marker=dict(color=COLORS[focus]),
                         hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
    fig.add_trace(go.Bar(y=top.index, x=top.bench, orientation="h", name=NAMES["BENCH"], marker_color=COLORS["BENCH"],
                         hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
    fig.update_layout(barmode="group", title=f"{dim.title()} exposure, % of total portfolio")
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(autorange="reversed")
    with c1.container(key="anim-expo"):
        st.plotly_chart(style(fig, 520).update_layout(hovermode="closest"), **FULL)
    act = top.sort_values("active")
    fig = go.Figure(go.Bar(y=act.index, x=act.active, orientation="h",
                           marker=signed(act.active, COLORS[focus]),
                           text=[f"{v:+.1%}" for v in act.active], textposition="outside",
                           textfont=dict(size=10, color=viz.INK2), cliponaxis=False,
                           hovertemplate="%{y}: %{x:+.1%}<extra></extra>"))
    fig.update_layout(title="Active weight vs benchmark")
    lo, hi = float(act.active.min()), float(act.active.max())
    pad = (hi - lo) * 0.22 or 0.01
    fig.update_xaxes(tickformat="+.0%", range=[lo - pad, hi + pad])
    c2.plotly_chart(style(fig, 520, legend=False).update_layout(hovermode="closest"), **FULL)
    c2.caption("Solid bars are overweights, hollow bars underweights, both in the colour of "
               f"{NAMES[focus]}.")

    if "top_holdings" in D and len(D["top_holdings"]):
        th = D["top_holdings"]
        th = th[th.code == focus]
        section("Largest single issuers, looked through")
        h1, h2 = st.columns([3, 2])
        with h1:
            tb = (th[["name", "ticker", "weight", "via"]]
                  .rename(columns={"name": "Issuer", "ticker": "Ticker", "weight": "% of portfolio",
                                   "via": "Held through"}))
            table(tb.style.format({"% of portfolio": "{:.2%}"})
                    .bar(subset=["% of portfolio"], color=tint(COLORS[focus], 0.30),
                         align="left", vmin=0.0, vmax=float(tb["% of portfolio"].max())),
                  index=False)
        with h2:
            # the table answers "which names"; the donut answers "how concentrated, and where"
            sec = (ex[(ex.code == focus) & (ex.dimension == "sector")]
                   .sort_values("weight", ascending=False))
            keep = sec.head(6)
            rest = float(sec.weight.iloc[6:].sum())
            labels = list(keep.bucket) + (["Other sectors"] if rest > 1e-4 else [])
            values = list(keep.weight) + ([rest] if rest > 1e-4 else [])
            base = COLORS[focus]
            shades = [tint(base, a) for a in (1.0, 0.82, 0.66, 0.52, 0.4, 0.3)][:len(keep)]
            shades += [viz.PANEL if DARK else "#dfe5ec"] * (len(labels) - len(shades))
            fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.62, sort=False,
                                   marker=dict(colors=shades, line=dict(color=viz.SURFACE, width=1.5)),
                                   textinfo="none", hovertemplate="%{label}: %{value:.1%}<extra></extra>"))
            fig.update_layout(title=f"Equity sector mix, {NAMES[focus]}")
            fig.add_annotation(text=f"<b>{float(keep.weight.sum()) * 100:.0f}%</b><br>top 6", showarrow=False,
                               font=dict(size=15, color=viz.NAVY_DEEP, family=FONT))
            st.plotly_chart(
                style(fig, 340).update_layout(
                    hovermode="closest", margin=dict(l=8, r=8, t=58, b=8),
                    legend=dict(orientation="v", x=0.98, y=0.5, yanchor="middle", xanchor="left",
                                font=dict(size=10.5, color=viz.INK2))), **FULL)

    section("Interest-rate and credit exposure",
            "Bar length is the row read across the four portfolios, so the outliers stand out "
            "without reading every digit.")
    du = D["duration"].set_index("code").loc[ORDER]
    tbl = pd.DataFrame({
        "Bond weight": du.bond_weight,
        "Nominal duration (yrs, portfolio)": du.nominal_duration,
        "Real duration via TIPS (yrs)": du.real_duration,
        "Bond sleeve duration (yrs)": du.bond_sleeve_duration,
        "IG spread duration": du.ig_spread_duration,
        "HY / EM spread duration": du.hy_spread_duration,
        "DV01 per $1m": du.dv01_per_1m,
    }).T.rename(columns=NAMES)
    lead = {"Bond weight", "DV01 per $1m"}                 # the two rows that drive the risk story
    sty = (tbl.style
              .format({c: "{:.1%}" for c in tbl.columns}, subset=pd.IndexSlice[["Bond weight"], :])
              .format({c: "${:,.0f}" for c in tbl.columns}, subset=pd.IndexSlice[["DV01 per $1m"], :])
              .format("{:.2f}", subset=pd.IndexSlice[[i for i in tbl.index if i not in lead], :])
              .bar(subset=pd.IndexSlice[sorted(lead), :], axis=1, color=CELL_BAR, align="left")
              .set_properties(subset=pd.IndexSlice[sorted(lead), :],
                              **{"font-weight": "800", "color": viz.NAVY_DEEP}))
    code_of = {NAMES[c]: c for c in ORDER}
    for row in sorted(lead):                                # underline the single largest reading in each
        hi = tbl.loc[row].idxmax()
        sty = sty.set_properties(subset=pd.IndexSlice[[row], [hi]],
                                 **{"border-bottom": f"2px solid {COLORS[code_of[hi]]}"})
    table(sty, colour_by_code=ORDER)
    du_s = D["duration"].set_index("code")
    st.markdown(
        "<div class='pb-note'><b>Why minimum variance sits in bonds.</b> It is specified as long-only "
        "variance minimisation over eleven ETFs with a 25% cap on any one fund and a 20% floor on equities, "
        "and no return target at all. An optimiser given those constraints will walk into the lowest "
        f"volatility assets and stay there, so {pct(du_s.loc['MINVAR', 'bond_weight'])} in bonds and a DV01 of "
        f"${du_s.loc['MINVAR', 'dv01_per_1m']:,.0f} per $1m, about double the other three, is the specification "
        "doing exactly what it was told rather than a surprise in the data. It is also why the portfolio lost "
        "to a 60/40 in a thirteen-year equity bull market, and why its tracking error is "
        f"{pct(S.loc['MINVAR', 'tracking_error'])}. What I would change: give it a return or equity-risk floor "
        "instead of a bare weight floor, cap portfolio duration directly, and put a turnover penalty inside the "
        "optimisation rather than skipping small trades after the fact."
        "</div>", unsafe_allow_html=True)
    bc = D["bond_characteristics"]
    st.caption("Fund durations: " + "; ".join(
        f"{r.fund} {max(r.duration, r.real_duration):.2f}y ({r.dur_source})" for r in bc.itertuples()))

# ------------------------------------------------------------------ attribution
with tabs[3]:
    tot = D["brinson_totals"]
    full = tot[tot.period == "Full period"].set_index("code")
    section("Active return versus benchmark, decomposed",
            "Brinson-Fachler, computed daily and linked with Carino. Allocation is segment over and "
            "underweights; selection is what the chosen ETFs did inside each segment against its core ETF; "
            "the benchmark residual is ACWI/AGG against the IVV/IEFA/IEMG/AGG composite.")
    st.markdown("<div class='anim-stagger'>", unsafe_allow_html=True)
    cols = st.columns(3)
    for col, c in zip(cols, ["SAA", "MINVAR", "QV"]):
        r = full.loc[c]
        items = [("Allocation", r.allocation), ("Selection", r.selection), ("Costs", r.costs),
                 ("Residual", r.bench_residual)]
        col_c = COLORS[c]
        ys = [i[1] for i in items] + [r.active]
        fig = go.Figure(go.Waterfall(
            x=[i[0] for i in items] + ["Total"], y=ys,
            measure=["relative"] * 4 + ["total"],
            # one colour per portfolio, everywhere. A solid bar adds, a hollow bar
            # subtracts, which the +/- label and the bar direction already say.
            increasing=dict(marker=dict(color=col_c, line=dict(color=col_c, width=1.4))),
            decreasing=dict(marker=dict(color=tint(col_c, 0.22), line=dict(color=col_c, width=1.4))),
            totals=dict(marker=dict(color=tint(col_c, 0.55), line=dict(color=viz.INK, width=1.6))),
            text=[f"{v:+.1%}" for v in ys], textposition="outside",
            textfont=dict(size=10.5, color=viz.INK2, family=FONT),
            connector=dict(mode="between", line=dict(color=viz.MUTED, width=1.3, dash="dot")),
            hovertemplate="%{x}: %{y:+.1%}<extra></extra>"))
        fig.update_layout(title=f"{NAMES[c]}: {r.active * 100:+.1f}pp cumulative",
                          uniformtext=dict(mode="show", minsize=9))
        fig.update_yaxes(tickformat="+.0%")
        fig.update_xaxes(tickfont=dict(size=10))
        fig.update_traces(opacity=1.0 if c == focus else 0.6)
        col.plotly_chart(style(fig, 340, legend=False).update_layout(hovermode="closest"), **FULL)
    st.markdown("</div>", unsafe_allow_html=True)
    st.caption("Each bridge runs left to right from the benchmark return to the portfolio return. Solid bars add, "
               "hollow bars subtract, and the outlined bar is the total. The highlighted panel is the portfolio "
               f"selected in the sidebar ({NAMES[focus]}).")

    # Say the uncomfortable part out loud, with the numbers behind it, rather than
    # leaving the reader to work out that none of this came from picking funds.
    segs_full = D["brinson_segments"]
    segs_full = segs_full[segs_full.period == "Full period"]
    sa = segs_full[segs_full.code == "SAA"].set_index("segment")

    def _seg(name, col="allocation"):
        return float(sa.loc[name, col]) if name in sa.index else 0.0

    eq_alloc = _seg("US Equity") + _seg("Dev ex-US Equity") + _seg("EM Equity")
    r_saa, r_qv = full.loc["SAA"], full.loc["QV"]
    st.markdown(
        "<div class='pb-note'><b>Where the strategic portfolio's edge actually came from.</b> "
        f"Of the {r_saa.active * 100:+.1f}pp cumulative, {r_saa.allocation * 100:+.1f}pp is asset allocation and "
        f"{r_saa.bench_residual * 100:+.1f}pp is a benchmark construction residual, which is ACWI and AGG "
        "measured against the IVV/IEFA/IEMG/AGG composite rather than any decision I made. Selection is "
        f"{pp(r_saa.selection)} and costs are {pp(r_saa.costs)}. Nothing came from picking "
        "better funds. Inside allocation the two largest lines are the lighter US aggregate bond sleeve, "
        f"{_seg('US Aggregate') * 100:+.1f}pp, against the cost of the TIPS sleeve the benchmark does not hold, "
        f"{_seg('TIPS') * 100:+.1f}pp, with the regional equity tilts adding {eq_alloc * 100:+.1f}pp between them. "
        "That is one asset allocation stance, fixed in advance and held for thirteen years, in a sample where "
        "equities beat bonds by a wide margin. It was right; that is not the same as being skilful. "
        f"Quality-Value tells the same story from the other side: allocation {r_qv.allocation * 100:+.1f}pp with "
        f"selection {r_qv.selection * 100:+.1f}pp, so the quality and value sleeve lost to plain IVV over this "
        "window and the portfolio's small lead is inherited from the same allocation stance."
        "</div>", unsafe_allow_html=True)

    # Item 9: the allocation effect broken out, so the driver is a bar and not an inference.
    asg = segs_full[segs_full.code == focus].copy()
    asg = asg[(asg.port_weight.abs() > 1e-9) | (asg.bench_weight.abs() > 1e-9)]
    asg = asg.sort_values("allocation")
    fig = go.Figure(go.Bar(
        y=asg.segment, x=asg.allocation, orientation="h", marker=signed(asg.allocation, COLORS[focus]),
        customdata=(asg.port_weight - asg.bench_weight),
        text=[f"{v:+.1%}" for v in asg.allocation], textposition="outside",
        textfont=dict(size=10, color=viz.INK2), cliponaxis=False,
        hovertemplate="%{y}: %{x:+.1%} from a %{customdata:+.1%} active weight<extra></extra>"))
    lo, hi = float(asg.allocation.min()), float(asg.allocation.max())
    pad = (hi - lo) * 0.22 or 0.01
    fig.update_layout(title=f"{NAMES[focus]}: which allocation calls produced the allocation effect")
    fig.update_xaxes(tickformat="+.0%", range=[lo - pad, hi + pad])
    st.plotly_chart(style(fig, 300, legend=False).update_layout(hovermode="closest"), **FULL)
    st.caption("Brinson-Fachler allocation by segment, cumulative over the full period. Solid bars added to the "
               "active return, hollow bars subtracted; the hover shows the active weight behind each one.")

    seg = D["brinson_segments"]
    seg = seg[(seg.code == focus) & (seg.period == "Full period")].copy()
    seg["selection+interaction"] = seg.selection + seg.interaction
    seg = seg[(seg.port_weight > 0) | (seg.bench_weight > 0)]
    fig = go.Figure()
    fc = COLORS[focus]
    fig.add_trace(go.Bar(x=seg.segment, y=seg.allocation, name="Allocation",
                         marker=dict(color=fc, line=dict(color=fc, width=1.2)),
                         hovertemplate="%{x}: %{y:+.2%}<extra>Allocation</extra>"))
    fig.add_trace(go.Bar(x=seg.segment, y=seg["selection+interaction"], name="Selection",
                         marker=dict(color=tint(fc, 0.28), line=dict(color=fc, width=1.2)),
                         hovertemplate="%{x}: %{y:+.2%}<extra>Selection</extra>"))
    fig.update_layout(barmode="group",
                      title=f"{NAMES[focus]}: allocation against selection, by segment (cumulative)")
    fig.update_yaxes(tickformat="+.1%")
    st.plotly_chart(style(fig, 340).update_layout(hovermode="closest"), **FULL)
    yr = tot[(tot.code == focus) & (tot.period != "Full period")].set_index("period")
    st.caption(f"{NAMES[focus]}: attribution by calendar year")
    table(yr[["port_return", "bench_return", "active", "allocation", "selection", "costs", "bench_residual"]]
          .rename(columns={"port_return": "Portfolio", "bench_return": "Benchmark", "active": "Active",
                           "allocation": "Allocation", "selection": "Selection", "costs": "Costs",
                           "bench_residual": "Residual"})
          .style.pipe(signed_text).format("{:+.2%}"))

    section("Factor exposures", "Weekly regression on ETF-built factor spreads.")
    mode = st.radio("Explain", ["absolute", "active"], horizontal=True,
                    format_func=lambda m: "Excess return over cash" if m == "absolute" else "Active return vs benchmark")
    ft = D["factor"]
    fm = D["factor_meta"].set_index(["code", "mode"])
    x = ft[(ft.code == focus) & (ft["mode"] == mode)]
    c1, c2 = st.columns(2)
    xb = x[x.factor != "Alpha / residual"]
    fig = go.Figure(go.Bar(x=xb.factor, y=xb.beta, marker=signed(xb.beta, COLORS[focus]),
                           customdata=xb.t_stat, hovertemplate="%{x}: β %{y:.2f} (t %{customdata:.1f})<extra></extra>"))
    fig.update_layout(title=f"Factor betas · R² {fm.loc[(focus, mode), 'r2']:.2f}")
    c1.plotly_chart(style(fig, 320, legend=False).update_layout(hovermode="closest"), **FULL)
    fig = go.Figure(go.Bar(x=x.factor, y=x.return_contrib, marker=signed(x.return_contrib, COLORS[focus]),
                           hovertemplate="%{x}: %{y:+.2%} a year<extra></extra>"))
    fig.update_layout(title="Contribution to annual return (β × factor premium)")
    fig.update_yaxes(tickformat="+.1%")
    c2.plotly_chart(style(fig, 320, legend=False).update_layout(hovermode="closest"), **FULL)
    show = x.set_index("factor")[["beta", "t_stat", "factor_ann_return", "return_contrib", "risk_share"]]
    table(show.rename(columns={"beta": "Beta", "t_stat": "t", "factor_ann_return": "Factor premium p.a.",
                               "return_contrib": "Return contribution p.a.", "risk_share": "Share of variance"})
          .style.format({"Beta": "{:.2f}", "t": "{:.1f}", "Factor premium p.a.": "{:+.1%}",
                         "Return contribution p.a.": "{:+.2%}", "Share of variance": "{:.0%}"}, na_rep="n/a"))
    fr = D["factor_rolling"]
    fr = fr[fr.code == focus]
    fig = go.Figure()
    fcol = {"Equity": "#2a78d6", "Rates": "#eb6834", "Value": "#1baf7a", "Quality": "#eda100", "USD": "#e87ba4"}
    for f, colr in fcol.items():
        y = fr[fr.factor == f]
        fig.add_trace(go.Scatter(x=y.date, y=y.beta, name=f, line=dict(color=colr, width=2), hovertemplate="%{y:.2f}"))
    fig.update_layout(title="Rolling 52-week factor betas")
    st.plotly_chart(style(fig, 320), **FULL)

# ------------------------------------------------------------------ stress
with tabs[4]:
    rp = D["stress_replay"]
    section("Historical replay",
            "Today's weights held through each past episode, no rebalancing. ETFs launched after an episode "
            "are proxied (IEFA to EFA, IEMG to EEM, QUAL to IVV, VLUE to IWD, ACWI to IVV/EFA/EEM, "
            "EMB to LQD/HYG).")
    piv = rp.pivot(index="window", columns="code", values="replay_return")[ORDER]
    piv = piv.reindex([w for w in rp.window.unique()])
    # Say on the axis which episodes are estimates rather than history.
    prox = rp.groupby("window").proxy_share.max().fillna(0.0)
    piv.index = [w + (f"  ({prox.get(w, 0):.0%} proxied)" if prox.get(w, 0) > 0.01 else "") for w in piv.index]
    fig = go.Figure()
    for c in ORDER:
        fig.add_trace(go.Bar(y=piv.index, x=piv[c], orientation="h", name=NAMES[c], marker=bar_emph(c),
                             hovertemplate="%{y}: %{x:.1%}<extra>" + NAMES[c] + "</extra>"))
    fig.update_layout(barmode="group", title="Loss in each historical episode, current weights")
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(autorange="reversed")
    with st.container(key="anim-stress"):
        st.plotly_chart(style(fig, 560).update_layout(hovermode="closest"), **FULL)
    st.caption("The proxy share is the weight of the portfolio represented by a stand-in fund in that episode. "
               f"The 2008 replay is {prox.max():.0%} proxied at its worst, so read it as an estimate of how "
               "these weights would have behaved, not as something these portfolios lived through. The episodes "
               "with no label are held in the actual funds.")
    real = rp.pivot(index="window", columns="code", values="realised_return") if "realised_return" in rp else None
    if real is not None:
        real = real.reindex(rp.window.unique())[ORDER].dropna(how="all")
        st.caption("Realised during the backtest (weights at the time, net of costs)")
        table(signed_text(real.rename(columns=NAMES).style.format("{:.1%}", na_rep="n/a")),
              colour_by_code=ORDER)

    section("Hypothetical shocks",
            "Bonds by duration, convexity and spread duration; equities by their betas to ACWI and to the "
            "dollar from 3-year weekly regressions; gold as specified.")
    sc = D["stress_scenarios"].pivot(index="scenario", columns="code", values="return")[ORDER]
    table(signed_text(sc.rename(columns=NAMES).style.format("{:.1%}")), colour_by_code=ORDER)

    section("Build your own scenario")
    c1, c2, c3 = st.columns(3)
    rates = c1.slider("10y Treasury yield change (pp)", -2.0, 2.0, 1.0, 0.25)
    be = c1.slider("Breakeven inflation change (pp)", -1.5, 1.5, 0.0, 0.25)
    eq_on = c2.checkbox("Specify equity move", True)
    eq = c2.slider("ACWI move", -0.5, 0.3, -0.15, 0.05, disabled=not eq_on)
    usd = c2.slider("US dollar move", -0.15, 0.15, 0.0, 0.01)
    ig = c3.slider("IG spread change (pp)", -1.0, 3.0, 0.0, 0.25)
    hy = c3.slider("HY / EM spread change (pp)", -2.0, 8.0, 0.0, 0.5)
    gold = c3.slider("Gold move", -0.3, 0.3, 0.0, 0.05)
    from portfolio_lab import stress  # imported here: it pulls in scipy
    sens = D["sensitivities"].set_index("ticker")
    implied = {"eq_per_1pp_rates": float(meta["implied_eq_per_1pp_rates"]), "eq_per_usd": float(meta["implied_eq_per_usd"])}
    shock = stress.shock_returns(sens, implied, rates=rates, breakeven=be, equity=eq if eq_on else None,
                                 usd=usd, ig=ig, hy=hy, gold=gold)
    wts = D["weights"]
    last = wts[wts.date == wts.date.max()]
    res = {c: float((last[last.code == c].set_index("ticker").weight * shock).dropna().sum()) for c in ORDER}
    cols = st.columns(4)
    for col, c in zip(cols, ORDER):
        col.metric(NAMES[c], pct(res[c]))
    st.caption("Per-ETF shock: " + ", ".join(f"{t} {v:+.1%}" for t, v in shock.items()))

# ------------------------------------------------------------------ costs
with tabs[5]:
    rs = D["rebalance_study"]
    section("Rebalancing rules", "Tested on the Strategic 60/40: same targets, same costs, different rule.")
    table(rs.set_index("rule")[["cagr", "vol", "sharpe", "max_dd", "tracking_error", "turnover_ann",
                               "n_rebalances", "cost_bps_ann"]]
          .rename(columns={"cagr": "Return p.a.", "vol": "Volatility", "sharpe": "Sharpe",
                           "max_dd": "Max drawdown", "tracking_error": "Tracking error",
                           "turnover_ann": "Turnover p.a.", "n_rebalances": "Trades",
                           "cost_bps_ann": "Cost p.a."})
          .style.format({"Return p.a.": "{:.2%}", "Volatility": "{:.2%}", "Sharpe": "{:.2f}",
                         "Max drawdown": "{:.1%}", "Tracking error": "{:.2%}", "Turnover p.a.": "{:.1%}",
                         "Trades": "{:.0f}", "Cost p.a.": "{:.2f} bp"}))
    st.markdown(
        "<div class='pb-note'><b>What size this is true at.</b> Costs here are a one-way charge in basis "
        "points per ETF, covering half the quoted spread plus a fixed impact allowance, applied to the weight "
        "actually traded. There is no market impact that grows with the size of the order. At a few million "
        "dollars that is about right. At a few billion it is not: the trade would move the book, the band rule "
        "would need a participation limit and a multi-day schedule, and the minimum variance portfolio's "
        f"{pct(S.loc['MINVAR', 'turnover_ann'])} of annual turnover would be the first thing to break. Read the "
        "finding as costs did not matter at this size and this turnover, not as costs do not matter."
        "</div>", unsafe_allow_html=True)

    cs = D["cost_sensitivity"]
    fig = go.Figure()
    for c in ["SAA", "MINVAR", "QV"]:
        x = cs[cs.code == c]
        fig.add_trace(go.Scatter(x=x.cost_multiplier, y=x.cagr, name=NAMES[c], mode="lines+markers",
                                 **emph(c, 2.0), marker=dict(size=9 if c == focus else 7, color=COLORS[c],
                                                             opacity=1.0 if c == focus else 0.45),
                                 hovertemplate="%{x}× costs: %{y:.2%}<extra></extra>"))
    fig.update_layout(title="Annual return as trading costs are scaled up (1× = base case)")
    fig.update_xaxes(title="Cost multiplier", tickvals=[0, 1, 3, 5])
    fig.update_yaxes(tickformat=".1%")
    with st.container(key="anim-cost"):
        st.plotly_chart(style(fig, 320).update_layout(hovermode="closest"), **FULL)
    ty = D["turnover_year"].pivot(index="year", columns="code", values="turnover")[ORDER]
    fig = go.Figure()
    for c in ORDER:
        fig.add_trace(go.Bar(x=ty.index, y=ty[c], name=NAMES[c], marker=bar_emph(c),
                             hovertemplate="%{x}: %{y:.1%}<extra>" + NAMES[c] + "</extra>"))
    fig.update_layout(barmode="group", title="One-way turnover by year")
    with st.container(key="anim-turn"):
        st.plotly_chart(style(fig, 300, pct_y=True).update_layout(hovermode="closest"), **FULL)

# ------------------------------------------------------------------ method
with tabs[6]:
    # The version you would say out loud, before the reader meets Ledoit-Wolf.
    st.markdown(
        "<div class='pb-note'><b>The three minute version.</b> I built three multi-asset portfolios out of "
        "fourteen US-listed iShares ETFs and ran them against a 60/40 ACWI and AGG benchmark on daily data "
        f"from {meta['backtest_start']} to {meta['backtest_end']}. One is a plain strategic 60/40 with a fixed "
        "regional split and a TIPS sleeve, rebalanced quarterly inside a 2.5 point band. One is a long-only "
        "minimum variance portfolio re-optimised monthly on a shrunk covariance matrix. One is the strategic "
        "portfolio with its US equity sleeve split into quality and value factor funds, so the only difference "
        "between the two is the factor tilt. Weights drift with the market, trades happen a day after the "
        "signal, and every trade pays a spread. Then I took the difference between each portfolio and the "
        "benchmark apart three ways: Brinson-Fachler attribution into allocation, selection and cost, a "
        "ten-factor regression, and a set of stress tests that either replay past episodes or apply a shock "
        "through duration and beta. I cared more about the decomposition than the backtest: I wanted "
        "to be able to say which decision produced which basis point, and to be able to prove the pieces add "
        "up, which the daily identity check does."
        "</div>", unsafe_allow_html=True)
    md = ROOT / "docs" / "methodology.md"
    st.markdown(md.read_text(encoding="utf-8") if md.exists() else "See docs/methodology.md")
    st.markdown("<div class='pb-note'>Built as a personal education project, to practise portfolio construction and risk attribution on real data. It is not investment advice and not a recommendation to buy or sell any security. Past performance says nothing about future returns.</div>", unsafe_allow_html=True)
