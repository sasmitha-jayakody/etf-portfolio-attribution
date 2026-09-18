"""Render the markdown documents in docs/ to PDF.

    python scripts/build_docs.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from portfolio_lab.pdfs import markdown_to_pdf  # noqa: E402

DOCS = [
    ("methodology.md", "methodology.pdf", 8.6, "Methodology"),
    ("investment_conclusion.md", "investment_conclusion.pdf", 8.1, "Investment conclusion"),
]


def main() -> None:
    for src, out, size, title in DOCS:
        p = markdown_to_pdf(ROOT / "docs" / src, ROOT / "docs" / out, base_size=size, title=title)
        print(f"{src} -> {p}")


if __name__ == "__main__":
    main()
