"""Render the Markdown training docs under Docs/training/ into formatted PDFs.

Markdown stays the single source of truth (easy to diff/update in a PR);
the PDF is a generated artifact for people who'd rather read/print/share a
formatted document than raw Markdown. Re-run this any time the .md source
changes - it always overwrites the matching .pdf next to it.

Usage:
    python scripts\\render_training_pdfs.py

Requires Markdown + xhtml2pdf (requirements-dev.txt) - not part of the
running Flask app, so these are deliberately not in requirements.txt.
"""
import sys
from datetime import date
from pathlib import Path

import markdown
from xhtml2pdf import pisa

TRAINING_DIR = Path(__file__).resolve().parent.parent / "Docs" / "training"

# filename (without extension) -> (subtitle, audience line) shown on the cover page
DOC_META = {
    "SAL_Technical_Deep_Dive": (
        "Engineering Reference",
        "Backend Python architecture &amp; SAP RFC mechanics, for engineers extending or operating SAL",
    ),
    "SAL_Analyst_User_Guide": (
        "User Guide",
        "Day-to-day use of SAL for security analysts: data collection, triage, and disposition",
    ),
    "SAL_Technical_Deep_Dive_v2": (
        "Engineering Reference &middot; v2",
        "Backend Python architecture &amp; SAP RFC mechanics, for engineers extending or operating SAL",
    ),
    "SAL_Analyst_User_Guide_v2": (
        "User Guide &middot; v2",
        "Day-to-day use of SAL for security analysts: data collection, triage, and disposition",
    ),
}

CSS = """
@page {
    size: letter;
    margin: 2.1cm 1.8cm 2.3cm 1.8cm;
    @frame footer_frame {
        -pdf-frame-content: footer_content;
        bottom: 1cm;
        margin-left: 1.8cm;
        margin-right: 1.8cm;
        height: 1cm;
    }
}
body { font-family: Helvetica, Arial, sans-serif; font-size: 9.5pt; line-height: 1.45; color: #1a2733; }
h1 { font-size: 19pt; color: #0a3d62; border-bottom: 2px solid #0a6ed1; padding-bottom: 5px; margin-top: 22px; }
h2 { font-size: 14pt; color: #0a3d62; border-bottom: 0.75px solid #b9c6d1; padding-bottom: 3px; margin-top: 18px; }
h3 { font-size: 11.5pt; color: #14507a; margin-top: 13px; }
h4 { font-size: 10pt; color: #14507a; margin-top: 9px; }
p { margin: 5px 0; text-align: left; }
strong { color: #14304a; }
code { font-family: Courier, monospace; background-color: #eef2f6; color: #0a3d62; padding: 1px 3px; font-size: 8.6pt; }
pre { font-family: Courier, monospace; background-color: #f4f6f8; border: 0.5px solid #cbd5df;
      padding: 7px 9px; font-size: 8.1pt; line-height: 1.3; white-space: pre-wrap; word-wrap: break-word; }
pre code { background-color: transparent; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px 0; font-size: 8.4pt; }
th { background-color: #0a6ed1; color: #ffffff; padding: 4px 6px; text-align: left; border: 0.5px solid #0a6ed1; }
th code { background-color: transparent; color: #ffffff; padding: 0; }
td { padding: 4px 6px; border: 0.5px solid #cbd5df; vertical-align: top; }
hr { border: none; border-top: 0.75px solid #cbd5df; margin: 12px 0; }
blockquote { border-left: 3px solid #0a6ed1; margin: 8px 0; padding: 3px 10px; color: #445566; background-color: #f4f8fb; }
ul, ol { margin: 3px 0 8px 16px; }
li { margin: 2px 0; }
a { color: #0a6ed1; text-decoration: none; }

.cover { text-align: center; }
.cover .kicker { color: #0a6ed1; font-size: 11pt; letter-spacing: 1px; margin-top: 210px; }
.cover .title { color: #0a3d62; font-size: 27pt; font-weight: bold; margin-top: 8px; }
.cover .subtitle { color: #14507a; font-size: 13pt; margin-top: 10px; }
.cover .bar { border-top: 3px solid #0a6ed1; width: 140px; margin: 22px auto; }
.cover .audience { color: #445566; font-size: 10pt; width: 340px; margin: 0 auto; }
.cover .meta { color: #7c8b99; font-size: 8.5pt; margin-top: 260px; }

.toc-title { color: #0a3d62; font-size: 14pt; border-bottom: 0.75px solid #b9c6d1; padding-bottom: 3px; }
.toc ul { list-style: none; margin: 4px 0 4px 4px; padding-left: 12px; }
.toc li { margin: 3px 0; font-size: 9.5pt; }
.toc a { color: #1a2733; }

#footer_content { font-size: 8pt; color: #7c8b99; text-align: center; border-top: 0.5px solid #dbe3ea; padding-top: 4px; }
"""

FOOTER_HTML = (
    '<div id="footer_content">SAL (Security Audit Log Tool) &middot; '
    'Generated {date} from Docs/training/{stem}.md &middot; '
    'Page <pdf:pagenumber /> of <pdf:pagecount /></div>'
)


def _strip_leading_h1(md_text: str) -> str:
    lines = md_text.lstrip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).lstrip("\n")


def render_one(md_path: Path) -> Path:
    stem = md_path.stem
    subtitle, audience = DOC_META.get(stem, ("", ""))
    title = md_path.read_text(encoding="utf-8").lstrip().splitlines()[0].lstrip("# ").strip()
    body_source = _strip_leading_h1(md_path.read_text(encoding="utf-8"))

    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        extension_configs={"toc": {"anchorlink": False, "permalink": False}},
    )
    body_html = md.convert(body_source)
    toc_html = md.toc  # nested <ul> of <a href="#slug">heading</a>

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{CSS}</style></head>
<body>
  <div class="cover">
    <div class="kicker">SAL &middot; {subtitle.upper()}</div>
    <div class="title">{title}</div>
    <div class="subtitle">{subtitle}</div>
    <div class="bar"></div>
    <div class="audience">{audience}</div>
    <div class="meta">Generated {date.today().isoformat()} from Docs/training/{md_path.name}</div>
  </div>
  <pdf:nextpage />
  <div class="toc">
    <div class="toc-title">Contents</div>
    {toc_html}
  </div>
  <pdf:nextpage />
  {body_html}
  {FOOTER_HTML.format(date=date.today().isoformat(), stem=stem)}
</body>
</html>"""

    out_path = md_path.with_suffix(".pdf")
    with open(out_path, "wb") as f:
        result = pisa.CreatePDF(html, dest=f, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"xhtml2pdf reported {result.err} error(s) rendering {md_path.name}")
    return out_path


def main() -> int:
    md_files = sorted(TRAINING_DIR.glob("*.md"))
    if not md_files:
        print(f"No .md files found under {TRAINING_DIR}")
        return 1
    for md_path in md_files:
        out_path = render_one(md_path)
        size_kb = out_path.stat().st_size / 1024
        print(f"Wrote {out_path.relative_to(TRAINING_DIR.parent.parent)} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
