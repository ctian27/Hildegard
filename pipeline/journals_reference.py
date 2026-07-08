"""Generate a user-facing reference document listing the journals Hildegard
searches, grouped by tier.

Reads the journal lists straight from :mod:`pipeline.config` (so it stays in
sync with what the pipeline actually queries) and reuses the digest PDF styling
from :mod:`pipeline.render`.

Run:  python -m pipeline.journals_reference [--out-dir .]
Writes ``Hildegard-Journals.md`` and ``Hildegard-Journals.pdf``.
"""
from __future__ import annotations

import argparse
import os

from . import config
from .render import markdown_to_pdf


def _issn_cell(j: config.Journal) -> str:
    """Human-readable ISSN cell: 'print / electronic', omitting missing ones."""
    parts = []
    if j.issn_print:
        parts.append(f"{j.issn_print} (print)")
    if j.issn_electronic:
        parts.append(f"{j.issn_electronic} (online)")
    return " · ".join(parts) if parts else "—"


# A page break so each large table starts on a fresh page and renders at full
# size, rather than being auto-shrunk by xhtml2pdf's keep-in-frame mode when two
# tables would otherwise share one page. (xhtml2pdf honours page-break-before.)
_PAGE_BREAK = '<div style="page-break-before: always;"></div>'


def _table(journals: list[config.Journal]) -> str:
    lines = [
        "| Journal | PubMed abbreviation | ISSN |",
        "| --- | --- | --- |",
    ]
    for j in sorted(journals, key=lambda x: x.name.lower()):
        lines.append(f"| {j.name} | {j.pubmed_filter_term} | {_issn_cell(j)} |")
    return "\n".join(lines)


def build_markdown() -> str:
    """Assemble the journal-reference Markdown from the live config lists."""
    n_t1 = len(config.TIER1_JOURNALS)
    n_t2h = len(config.TIER2_HEMATOLOGY_JOURNALS)
    n_t2o = len(config.TIER2_ONCOLOGY_JOURNALS)

    parts = [
        "# Hildegard — Source Journals",
        "",
        "Hildegard surveils PubMed for recently published, practice-relevant "
        "papers (phase II/III trials and guidelines). Every search is "
        "**restricted to the journals listed below** — nothing outside this set "
        "is retrieved. Journal names, PubMed filter terms, and ISSNs were each "
        "verified live against PubMed.",
        "",
        "**How the tiers are used**",
        "",
        "- **Tier 1 — core clinical journals** are searched for *every* disease "
        "group, hematologic and solid-tumor alike.",
        "- **Tier 2 — Hematology** is added for the hematologic disease groups.",
        "- **Tier 2 — Oncology** is added for the solid-tumor disease groups "
        "(plus *Journal of Hematology & Oncology*, which spans both).",
        "",
        "In the newest-paper \"fresh scan,\" Tier 1 and Tier 2 are searched "
        "separately and written to separate files, so the higher-signal Tier 1 "
        "results stay clean.",
        "",
        f"## Tier 1 — Core clinical ({n_t1} journals)",
        "",
        "Searched for all disease groups.",
        "",
        _table(config.TIER1_JOURNALS),
        "",
        _PAGE_BREAK,
        "",
        f"## Tier 2 — Hematology ({n_t2h} journals)",
        "",
        "Added for hematologic disease groups (e.g. AML, MDS, CLL, lymphomas, "
        "multiple myeloma, MPN, sickle cell).",
        "",
        _table(config.TIER2_HEMATOLOGY_JOURNALS),
        "",
        _PAGE_BREAK,
        "",
        f"## Tier 2 — Oncology ({n_t2o} journals)",
        "",
        "Added for solid-tumor disease groups. Several titles here are "
        "high-volume or review-heavy; the publication-type filter screens out "
        "reviews, so they rarely dominate the digest.",
        "",
        _table(config.TIER2_ONCOLOGY_JOURNALS),
        "",
        "---",
        "",
        "*Hildegard is a retrieval/triage aid only; it does not interpret or "
        "appraise papers. Journal set verified 2026-07-01/02.*",
    ]
    return "\n".join(parts)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        default=".",
        help="Directory to write Hildegard-Journals.{md,pdf} (default: cwd).",
    )
    args = parser.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    md = build_markdown()

    md_path = os.path.join(args.out_dir, "Hildegard-Journals.md")
    pdf_path = os.path.join(args.out_dir, "Hildegard-Journals.pdf")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    markdown_to_pdf(md, pdf_path)
    print(f"Wrote {md_path}")
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
