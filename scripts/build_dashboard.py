"""Render the standalone HTML dashboard from the results database.

    python scripts/build_dashboard.py            # -> outputs/dashboard.html
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from portfolio_lab import reports  # noqa: E402


def font_faces() -> str:
    """Inline the Lato faces as data URIs: the page then needs no font host."""
    import base64
    css = []
    for name, weight, style in [("Lato-Regular", 400, "normal"), ("Lato-Italic", 400, "italic"),
                                ("Lato-Bold", 700, "normal"), ("Lato-Black", 900, "normal")]:
        f = ROOT / "static" / "fonts" / f"{name}.woff2"
        if not f.exists():
            continue
        b64 = base64.b64encode(f.read_bytes()).decode()
        css.append(f"@font-face{{font-family:Lato;font-style:{style};font-weight:{weight};"
                   f"font-display:swap;src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "".join(css)


def method_sections() -> list[list[str]]:
    """docs/methodology.md -> [[heading, para, ...], ...] for the Method tab."""
    md = (ROOT / "docs" / "methodology.md").read_text(encoding="utf-8")
    md = re.sub(r"^# .*\n", "", md, count=1)
    md = re.sub(r"\|.*\n", "", md)                      # tables don't belong in the panel
    out: list[list[str]] = []
    for block in [b.strip() for b in md.split("\n\n") if b.strip()]:
        text = " ".join(block.split())
        text = text.replace("**", "").replace("*", "")
        head, _, rest = text.partition(".")
        if len(head) < 34 and rest:
            out.append([head.strip(), rest.strip()])
        else:
            out.append([None, text])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None)
    ap.add_argument("--out", default=str(ROOT / "outputs" / "dashboard.html"))
    a = ap.parse_args()
    R = reports.read_results(a.db)
    data_path = reports.dashboard_json(R)
    data = data_path.read_text(encoding="utf-8")
    tpl = (ROOT / "docs" / "dashboard_template.html").read_text(encoding="utf-8")
    charts = (ROOT / "docs" / "charts.js").read_text(encoding="utf-8")
    fonts = font_faces()
    html = (tpl.replace("__FONTS__", fonts)
               .replace("__CHARTS__", charts)
               .replace("__DATA__", data.replace("</", "<\\/"))
               .replace("__METHOD__", json.dumps(method_sections(), ensure_ascii=False)))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"dashboard -> {out}  ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
