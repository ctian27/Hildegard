"""Markdown digest renderer, following the paired system prompt's OUTPUT
FORMAT section. LLM calls happen per-item (see llm.py); this module is
responsible for the cycle-level assembly: header, grouping, needs-review
and flagged-retraction sections, and the reproducibility footer.
"""

import json
import os
from datetime import datetime

from . import config

CLOSING_LINE = (
    '*"Surveillance aid only. Verify every item against the primary source and '
    'apply clinical judgment and institutional protocols before any clinical use. '
    'Automated extraction can misread numbers, endpoints, and populations."*'
)


def _group_label(group_key: str) -> str:
    group = config.DISEASE_GROUPS.get(group_key)
    return group.label if group else group_key


def render_cycle_digest(cycle_row, items: list, queries_meta: dict) -> str:
    included = [i for i in items if i["status"] == "included"]
    needs_review = [i for i in items if i["status"] == "needs_review"]
    flagged = [i for i in items if i["status"] == "flagged_retraction"]

    disease_groups = json.loads(cycle_row["disease_groups"])
    lines = []

    lines.append(f"# Heme/Onc Literature Surveillance -- Cycle {cycle_row['run_date']}")
    lines.append("")
    lines.append(f"- **Surveillance window:** {cycle_row['window_start']} to {cycle_row['window_end']}")
    lines.append(f"- **Disease groups covered:** {', '.join(_group_label(g) for g in disease_groups)}")
    lines.append(f"- **Total new items surfaced:** {len(included)}")
    lines.append(f"- **Flagged for retraction/concern:** {len(flagged)}")
    lines.append(f"- **Needs human review:** {len(needs_review)}")
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


def write_digest(digests_dir: str, cycle_row, content: str) -> str:
    os.makedirs(digests_dir, exist_ok=True)
    filename = f"{cycle_row['run_date']}_cycle.md"
    path = os.path.join(digests_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    update_index(digests_dir, cycle_row, filename)
    return path


def update_index(digests_dir: str, cycle_row, filename: str) -> None:
    index_path = os.path.join(digests_dir, "index.md")
    line = f"- [{cycle_row['run_date']}]({filename}) -- window {cycle_row['window_start']} to {cycle_row['window_end']}\n"
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
