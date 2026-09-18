"""Shared chart styling so the app, the figures and the web dashboard agree.

Palette: an institutional navy / rust / teal set, checked for colour-vision
separation against a white surface (worst adjacent pair dE 9.5 simulated,
18.5 unsimulated; every slot clears 3:1 contrast).
"""
from __future__ import annotations

import plotly.graph_objects as go

# Portfolio identity: the benchmark is a neutral reference, the three
# portfolios take the first three categorical slots.
COLORS = {"BENCH": "#737b85", "SAA": "#2a5f9e", "MINVAR": "#c1571d", "QV": "#0f8f6f"}
NAMES = {"BENCH": "Benchmark 60/40", "SAA": "Strategic 60/40", "MINVAR": "Minimum Variance", "QV": "Quality-Value"}
ORDER = ["SAA", "MINVAR", "QV", "BENCH"]

# Asset-class segments: eight slots in fixed order.
SEGMENT_COLORS = {
    "US Equity": "#2a5f9e", "Dev ex-US Equity": "#c1571d", "EM Equity": "#0f8f6f",
    "US Aggregate": "#b8860b", "TIPS": "#9c5c8f", "Treasuries": "#2f7a2f",
    "Credit": "#4a3aa7", "Gold": "#c0392b", "Cash": "#737b85", "Global Equity": "#5a6b7d",
}

NAVY, NAVY_DEEP = "#2a5f9e", "#102f52"
POS, NEG = "#14733f", "#a32b23"          # gain and loss, not chart series
INK, INK2, MUTED = "#14202e", "#44556a", "#78889b"
GRID, AXIS, SURFACE, PANEL = "#e7ecf1", "#c3ccd6", "#ffffff", "#f3f6f9"
FONT = 'Lato, "Segoe UI", system-ui, sans-serif'

# ---------------------------------------------------------------- dark mode
# Same palette logic on a dark surface: the portfolio hues are lifted so each
# one still clears 4.5:1 against the panel, and the greys are inverted rather
# than simply darkened. Light stays the default; the Streamlit app calls
# use_dark() before it imports these names, and the print figures never do.
MODE = "light"

_LIGHT = {
    "COLORS": dict(COLORS), "SEGMENT_COLORS": dict(SEGMENT_COLORS),
    "NAVY": NAVY, "NAVY_DEEP": NAVY_DEEP, "POS": POS, "NEG": NEG,
    "INK": INK, "INK2": INK2, "MUTED": MUTED,
    "GRID": GRID, "AXIS": AXIS, "SURFACE": SURFACE, "PANEL": PANEL,
}
_DARK = {
    "COLORS": {"BENCH": "#8e98a5", "SAA": "#5b9ae0", "MINVAR": "#e08040", "QV": "#1db894"},
    "SEGMENT_COLORS": {
        "US Equity": "#5b9ae0", "Dev ex-US Equity": "#e08040", "EM Equity": "#1db894",
        "US Aggregate": "#d2a521", "TIPS": "#c084b4", "Treasuries": "#52a852",
        "Credit": "#8a80e8", "Gold": "#e0655a", "Cash": "#8e98a5", "Global Equity": "#93a3b5",
    },
    "NAVY": "#5b9ae0", "NAVY_DEEP": "#cfe0f2", "POS": "#3fae6b", "NEG": "#e0665a",
    "INK": "#e7edf4", "INK2": "#a9b7c6", "MUTED": "#7e8d9e",
    "GRID": "#22354a", "AXIS": "#3c5771", "SURFACE": "#101c29", "PANEL": "#17273a",
}


def use_dark(dark: bool = True) -> None:
    """Swap the module palette. Call before `from viz import COLORS, ...` binds names."""
    global MODE
    MODE = "dark" if dark else "light"
    globals().update(_DARK if dark else _LIGHT)
    # dicts are rebound, not mutated, so callers that kept a reference are safe
    globals()["COLORS"] = dict((_DARK if dark else _LIGHT)["COLORS"])
    globals()["SEGMENT_COLORS"] = dict((_DARK if dark else _LIGHT)["SEGMENT_COLORS"])


def style(fig: go.Figure, height: int = 360, pct_y: bool = False, legend: bool = True) -> go.Figure:
    # exhibit titles are set in uppercase, like the section labels around them
    title = (fig.layout.title.text or "")
    if title:
        fig.update_layout(title_text=title.upper())
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=20, t=58, b=48),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=12.5, color=INK2),
        title=dict(font=dict(size=12, color=NAVY_DEEP, weight=700), y=1, yanchor="top", pad=dict(t=4)),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=PANEL if MODE == "dark" else "white", bordercolor=AXIS,
                        font=dict(size=12, family=FONT, color=INK)),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title=None,
                    font=dict(size=11.5, color=INK2)),
        bargap=0.34,
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, linewidth=1, tickcolor=AXIS, ticks="outside",
                     tickfont=dict(size=11, color=MUTED), zeroline=False)
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, zeroline=True, zerolinecolor=AXIS, zerolinewidth=1,
                     tickfont=dict(size=11, color=MUTED))
    if pct_y:                       # never clobber a format the caller already set
        fig.update_yaxes(tickformat=".0%")
    return fig
