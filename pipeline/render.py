"""Markdown digest renderer: cycle-level assembly of the retrieved papers --
header, grouping by disease, the flagged-retraction section, and the
reproducibility footer. Each item is shown as identification info + the
verbatim PubMed abstract.
"""

import json
import os
from datetime import datetime

from . import config

CLOSING_LINE = (
    '*"Surveillance aid only. This is a retrieval/triage tool that surfaces '
    'published abstracts; it does not interpret or appraise them. Verify every '
    'item against the primary source and apply clinical judgment and '
    'institutional protocols before any clinical use."*'
)


def _group_label(group_key: str) -> str:
    group = config.DISEASE_GROUPS.get(group_key)
    return group.label if group else group_key


def pubmed_record_to_markdown(rec: dict) -> str:
    """Format a retrieved PubMed record as a Markdown block WITHOUT any LLM:
    identification info followed by the verbatim abstract. Used when AI
    summarization is turned off."""
    title = rec.get("title") or "(untitled)"
    lines = [f"#### {title}", ""]
    meta = [
        f"**Journal:** {rec.get('journal') or 'not reported'}",
        f"**Date:** {rec.get('pub_date') or 'not reported'}",
    ]
    if rec.get("pmid"):
        meta.append(f"**PMID:** {rec['pmid']}")
    if rec.get("doi"):
        meta.append(f"**DOI:** {rec['doi']}")
    lines.append(" | ".join(meta))
    pub_types = rec.get("publication_types") or []
    if pub_types:
        lines.append("")
        lines.append(f"**Publication types:** {', '.join(pub_types)}")
    lines.append("")
    lines.append("**Abstract:**")
    lines.append("")
    lines.append(rec.get("abstract") or "_No abstract available in the source record._")
    return "\n".join(lines)


def render_cycle_digest(cycle_row, items: list, queries_meta: dict) -> str:
    included = [i for i in items if i["status"] == "included"]
    needs_review = [i for i in items if i["status"] == "needs_review"]
    flagged = [i for i in items if i["status"] == "flagged_retraction"]
    recent_t1 = [i for i in items if i["status"] == "recent_tier1"]
    recent_t2 = [i for i in items if i["status"] == "recent_tier2"]

    disease_groups = json.loads(cycle_row["disease_groups"])
    lines = []

    lines.append(f"# Heme/Onc Literature Surveillance -- Cycle {cycle_row['run_date']}")
    lines.append("")
    lines.append(f"- **Surveillance window:** {cycle_row['window_start']} to {cycle_row['window_end']}")
    lines.append(f"- **Disease groups covered:** {', '.join(_group_label(g) for g in disease_groups)}")
    lines.append(f"- **Total new items surfaced:** {len(included)}")
    lines.append(f"- **Flagged for retraction/concern:** {len(flagged)}")
    lines.append(f"- **Needs human review:** {len(needs_review)}")
    if recent_t1 or recent_t2:
        lines.append(f"- **Recent, not yet indexed:** {len(recent_t1)} Tier 1, {len(recent_t2)} Tier 2 "
                     "— reported separately in the `recent_tier1` / `recent_tier2` files.")
    lines.append("- Each item shows its identification info and the verbatim source abstract.")
    lines.append("")
    lines.append("---")
    lines.append("")

    by_group: dict[str, list] = {}
    for item in included:
        by_group.setdefault(item["disease_group"], []).append(item)

    for group_key in disease_groups:
        group_items = by_group.get(group_key, [])
        lines.append(f"## {_group_label(group_key)}")
        lines.append("")
        if not group_items:
            lines.append("_No new qualifying items this cycle._")
            lines.append("")
            continue

        guidelines = [i for i in group_items if i["record_type"] == "guideline"]
        trials = [i for i in group_items if i["record_type"] != "guideline"]

        def sort_key(i):
            return i["pub_date"] or ""

        for label, bucket in (("Guidelines", guidelines), ("Trials", sorted(trials, key=sort_key, reverse=True))):
            if not bucket:
                continue
            lines.append(f"### {label}")
            lines.append("")
            for item in bucket:
                block = json.loads(item["llm_output"])["markdown_block"] if item["llm_output"] else None
                lines.append(block or f"_(missing block for {item['pmid'] or item['nct']})_")
                lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Needs human review")
    lines.append("")
    if not needs_review:
        lines.append("_None this cycle._")
    else:
        for item in needs_review:
            reason = None
            if item["llm_output"]:
                reason = json.loads(item["llm_output"]).get("error")
            ident = item["pmid"] or item["doi"] or item["nct"] or "no identifier"
            lines.append(f"- **{item['title'] or '(untitled)'}** [{ident}] -- {item['disease_group']}: {reason or 'flagged as ambiguous by triage'}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Flagged: retraction / expression of concern")
    lines.append("")
    if not flagged:
        lines.append("_None this cycle._")
    else:
        for item in flagged:
            block = json.loads(item["llm_output"])["markdown_block"] if item["llm_output"] else None
            lines.append(block or f"_(missing block for {item['pmid'] or item['nct']})_")
            lines.append("")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Footer: exact queries used")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(queries_meta, indent=2, default=str))
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(CLOSING_LINE)
    lines.append("")

    return "\n".join(lines)


def render_recent_digest(cycle_row, items: list, status_value: str, tier_label: str,
                          queries_meta: dict) -> str:
    """Standalone document for the 'fresh scan' hits of one journal tier:
    recent papers not yet MeSH-indexed, matched by journal + date + disease
    text/MeSH, shown as identification info + verbatim abstract (no AI
    appraisal). Grouped by disease."""
    recent = [i for i in items if i["status"] == status_value]
    disease_groups = json.loads(cycle_row["disease_groups"])
    lines = [
        f"# Recent {tier_label} papers — not yet indexed (needs review)",
        "",
        f"- **Cycle:** {cycle_row['run_date']} | **Window:** {cycle_row['window_start']} to {cycle_row['window_end']}",
        f"- **{tier_label} journals scanned; items found:** {len(recent)}",
        "",
        "> These are recent papers from the approved **" + tier_label + "** journals that the "
        "strict, MeSH-verified digest does not yet catch because PubMed has not finished indexing "
        "them (no MeSH terms or publication types assigned yet). They are matched by journal + "
        "publication date + disease name (and, unless the broad option was used, phase II/III-trial "
        "or guideline wording in the title/abstract). Case reports/series and preclinical/animal "
        "studies are filtered out. They are **not** AI-appraised, and the study type is inferred "
        "from wording, not verified. Treat as a heads-up list to scan manually; verify each against "
        "the source.",
        "",
        "---",
        "",
    ]
    by_group: dict[str, list] = {}
    for item in recent:
        by_group.setdefault(item["disease_group"], []).append(item)

    if not recent:
        lines.append("_No recent not-yet-indexed items this cycle._")
        lines.append("")

    for group_key in disease_groups:
        group_items = by_group.get(group_key, [])
        if not group_items:
            continue
        lines.append(f"## {_group_label(group_key)}")
        lines.append("")
        for item in sorted(group_items, key=lambda i: i["pub_date"] or "", reverse=True):
            block = json.loads(item["llm_output"])["markdown_block"] if item["llm_output"] else None
            lines.append(block or f"_(missing block for {item['pmid']})_")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(CLOSING_LINE)
    lines.append("")
    return "\n".join(lines)


def write_outputs(digests_dir: str, cycle_row, stem: str, md_content: str,
                   fmt: str, index_label: str | None = None) -> list[str]:
    """Write `<stem>.md` and/or `<stem>.pdf` per `fmt` ('md'|'pdf'|'both'), and
    add an index entry (pointing at the .md, or .pdf if md wasn't written).
    Returns the paths written."""
    os.makedirs(digests_dir, exist_ok=True)
    written = []
    if fmt in ("md", "both"):
        md_path = os.path.join(digests_dir, f"{stem}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        written.append(md_path)
    if fmt in ("pdf", "both"):
        written.append(markdown_to_pdf(md_content, os.path.join(digests_dir, f"{stem}.pdf")))
    if index_label and written:
        link_target = f"{stem}.md" if fmt in ("md", "both") else f"{stem}.pdf"
        update_index(digests_dir, cycle_row, link_target, index_label)
    return written


# Print stylesheet for the PDF. h1 = cycle title, h2 = disease group
# subheading, h3 = Guidelines/Trials, h4 = per-article title; each article
# block renders underneath its disease-group subheading.
_PDF_CSS = """
@page { size: letter; margin: 2cm 1.8cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 9.5pt; color: #1a1a1a; line-height: 1.4; }
h1 { font-size: 17pt; color: #10243f; border-bottom: 2px solid #10243f; padding-bottom: 4px; margin: 0 0 6px 0; }
h2 { font-size: 13pt; color: #10243f; background: #eef2f7; padding: 5px 8px;
     margin: 18px 0 8px 0; border-left: 4px solid #10243f; -pdf-keep-with-next: true; }
h3 { font-size: 11pt; color: #33475b; margin: 12px 0 4px 0; -pdf-keep-with-next: true; }
h4 { font-size: 10pt; color: #10243f; margin: 12px 0 3px 0; -pdf-keep-with-next: true; }
p { margin: 3px 0; }
hr { border: none; border-top: 1px solid #c8d2de; margin: 10px 0; }
table { -pdf-keep-in-frame-mode: shrink; border-collapse: collapse; width: 100%; margin: 4px 0 8px 0; }
th, td { border: 1px solid #c8d2de; padding: 3px 5px; text-align: left; vertical-align: top; font-size: 9pt; }
th { background: #f2f5f9; }
code, pre { font-family: Courier, monospace; font-size: 7.5pt; background: #f5f5f5; }
pre { padding: 6px; white-space: pre-wrap; word-wrap: break-word; }
ul { margin: 3px 0 3px 0; }
em { color: #444; }
"""


def markdown_to_pdf(md_content: str, out_path: str) -> str:
    """Convert the cycle's Markdown digest to a styled PDF (pure Python:
    markdown -> HTML -> xhtml2pdf). Disease groups render as subheadings with
    their identified articles underneath."""
    import markdown as md_lib
    from xhtml2pdf import pisa

    html_body = md_lib.markdown(
        md_content,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )
    html = (
        f"<html><head><meta charset='utf-8'><style>{_PDF_CSS}</style></head>"
        f"<body>{html_body}</body></html>"
    )
    with open(out_path, "wb") as f:
        result = pisa.CreatePDF(html, dest=f, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"PDF generation failed ({result.err} errors) for {out_path}")
    return out_path


def update_index(digests_dir: str, cycle_row, filename: str, label: str | None = None) -> None:
    index_path = os.path.join(digests_dir, "index.md")
    text = label or f"{cycle_row['run_date']} cycle"
    line = f"- [{text}]({filename}) -- window {cycle_row['window_start']} to {cycle_row['window_end']}\n"
    header = "# Surveillance digest index\n\n"
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            existing = f.read()
        if line.strip() in existing:
            return
        with open(index_path, "a", encoding="utf-8") as f:
            f.write(line)
    else:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(header + line)
