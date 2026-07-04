"""Orchestrator: retrieve -> dedup -> enrich(retraction recheck) -> LLM -> render.

Usage:
    python -m pipeline.main --group aml
    python -m pipeline.main --group aml --dry-run          # retrieval+dedup only, no Claude calls
    python -m pipeline.main --group aml --max-items 3       # cap LLM calls, for smoke-testing
"""

import argparse
import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

from . import config, db, dedup, render
from .retrieval import pubmed


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Heme/onc literature surveillance cycle")
    p.add_argument("--group", action="append", dest="groups",
                    help="Disease group key to run (repeatable). Default: all active groups.")
    p.add_argument("--window-days", type=int, default=None,
                    help="Rolling window size in days, counted back from the end date "
                         "(default: each group's own window). Ignored if --start-date is given.")
    p.add_argument("--start-date", default=None,
                    help="Explicit start of the search window (YYYY-MM-DD, publication date). "
                         "Overrides the rolling window and per-group windows for all groups.")
    p.add_argument("--end-date", default=None,
                    help="Explicit end of the search window (YYYY-MM-DD, publication date). "
                         "Defaults to today.")
    p.add_argument("--dry-run", action="store_true", help="Retrieve + dedup only; skip building/writing item blocks.")
    p.add_argument("--max-items", type=int, default=None, help="Cap items rendered per group (for quick tests).")
    p.add_argument("--no-fresh-scan", action="store_true",
                    help="Disable the supplementary scan for recent, not-yet-MeSH-indexed "
                         "papers in the approved journals. That scan (on by default) catches "
                         "major new papers the strict MeSH/pub-type query misses due to PubMed "
                         "indexing lag; results go to separate recent_tier1/recent_tier2 files.")
    p.add_argument("--recent-all", action="store_true",
                    help="In the fresh scan, include ALL recent papers, not just phase II/III "
                         "trials and guidelines. By default the fresh scan restricts to "
                         "trial/guideline-like papers (by title/abstract cues) to cut noise.")
    p.add_argument("--ignore-seen", action="store_true",
                    help="Reprocess every retrieved item even if seen in a prior cycle "
                         "(regenerate the same window's digest from scratch instead of "
                         "reporting 'no new items').")
    p.add_argument("--format", choices=["pdf", "md", "both"], default="both",
                    help="Digest output format (default: both). 'pdf' = PDF only, "
                         "'md' = Markdown only, 'both' = write both.")
    p.add_argument("--db-path", default=config.DB_PATH)
    p.add_argument("--digests-dir", default=config.DIGESTS_DIR)
    return p.parse_args(argv)


def resolve_groups(keys: list[str] | None) -> list[config.DiseaseGroup]:
    if keys:
        missing = [k for k in keys if k not in config.DISEASE_GROUPS]
        if missing:
            sys.exit(f"Unknown disease group(s): {missing}. Known: {list(config.DISEASE_GROUPS)}")
        return [config.DISEASE_GROUPS[k] for k in keys]
    return config.ACTIVE_GROUPS


def _parse_date(label: str, value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        sys.exit(f"Invalid {label} {value!r}: expected YYYY-MM-DD.")


def resolve_window(group: config.DiseaseGroup, today: date,
                    window_days: int | None, start_date: str | None,
                    end_date: str | None) -> tuple[str, str]:
    """Compute the (start, end) publication-date window for a group as ISO
    strings. An explicit --start-date/--end-date overrides the rolling window
    (and the group's own window) for every group; otherwise the window is
    `window_days` (or the group's default) counted back from the end date.
    """
    end = _parse_date("--end-date", end_date) if end_date else today
    if start_date:
        start = _parse_date("--start-date", start_date)
    else:
        days = window_days if window_days is not None else group.window_days
        start = end - timedelta(days=days)
    if start > end:
        sys.exit(f"Start date {start.isoformat()} is after end date {end.isoformat()}.")
    return start.isoformat(), end.isoformat()


def recheck_retractions(conn, cycle_id: int, ncbi_api_key: str | None) -> list[dict]:
    """Re-check previously-seen PMIDs; return newly-detected retractions/EoC
    (transitioned from not-retracted to retracted) as item dicts ready for
    db.insert_item, so they surface in this cycle's flagged section."""
    pmids = db.get_all_seen_pmids(conn)
    if not pmids:
        return []
    prev_flagged = {
        row["id_value"] for row in conn.execute(
            "SELECT id_value FROM seen_ids WHERE id_type='pmid' AND retracted=1"
        ).fetchall()
    }
    statuses = pubmed.check_retractions(pmids, api_key=ncbi_api_key)
    newly_flagged = []
    for pmid, status in statuses.items():
        if status["retracted"]:
            db.update_retraction_status(conn, pmid, True, status["note"] or "")
            if pmid not in prev_flagged:
                row = conn.execute(
                    "SELECT disease_group FROM seen_ids WHERE id_type='pmid' AND id_value=?", (pmid,)
                ).fetchone()
                group_key = row["disease_group"] if row else "unknown"
                note = status["note"] or "Retraction/expression of concern detected on recheck"
                newly_flagged.append({
                    "disease_group": group_key,
                    "source_type": "pubmed",
                    "pmid": pmid, "doi": None, "nct": None,
                    "title": f"PMID {pmid} -- retraction/EoC status changed",
                    "journal": None, "pub_date": None, "record_type": None,
                    "raw_payload": status,
                    "status": "flagged_retraction",
                    "llm_output": {
                        "decision": "flagged_retraction", "record_type": None,
                        "markdown_block": (
                            f"**PMID {pmid}** -- previously surveilled item now carries a "
                            f"retraction/expression-of-concern flag on PubMed.\n\n"
                            f"Detail: {note}\n\nExcluded from clinical use pending review."
                        ),
                        "error": note,
                    },
                })
    return newly_flagged


def _abstract_only_output(rec: dict) -> tuple[str, dict]:
    """Build the (status, stored-output) for a record when AI summarization is
    off: identification info + verbatim abstract, retracted items flagged."""
    record_type = "guideline" if any(
        "Guideline" in (pt or "") for pt in rec.get("publication_types", [])
    ) else "trial"
    retracted = bool(rec.get("retracted"))
    block = render.pubmed_record_to_markdown(rec)
    if retracted:
        note = rec.get("retraction_note") or "Retraction/expression of concern flagged on PubMed."
        block = f"**FLAGGED — retraction / expression of concern.** {note}\n\n{block}"
    status = "flagged_retraction" if retracted else "included"
    out = {
        "decision": status, "record_type": record_type, "markdown_block": block,
        "appraisal_flags": [], "override_applied": None, "error": rec.get("retraction_note"),
    }
    return status, out


def _run_fresh_scan(conn, cycle_id: int, group: config.DiseaseGroup,
                     window_start: str, window_end: str, ncbi_key: str | None,
                     ignore_seen: bool, journals: list, status_value: str,
                     meta: dict, meta_key: str, trials_guidelines_only: bool = True) -> int:
    """Ungated scan of `journals` for recent, possibly not-yet-indexed papers.
    Inserts survivors as abstract-only items with `status_value`; returns the
    count kept. Deduped against everything already seen (incl. this cycle's
    strict + retraction items, since those were marked seen first)."""
    if not journals:
        return 0
    term = pubmed.build_fresh_term(group.mesh_terms, journals, [group.ctgov_condition],
                                    trials_guidelines_only=trials_guidelines_only)
    es = pubmed.esearch(term, window_start.replace("-", "/"), window_end.replace("-", "/"), api_key=ncbi_key)
    records = pubmed.efetch(es["pmids"], api_key=ncbi_key)
    new = records if ignore_seen else dedup.filter_new_pubmed(conn, records)
    # Trim obvious non-primary noise (editorials/letters/reviews when a record
    # carries those types) plus case reports/series and preclinical/animal work.
    kept = [r for r in new
            if not (set(r.get("publication_types") or []) & pubmed.NON_PRIMARY_PUB_TYPES)
            and pubmed.fresh_exclusion_reason(r) is None]
    meta[meta_key] = {"term": term, "pubmed_count": es["count"], "kept": len(kept)}
    for rec in kept:
        retracted = bool(rec.get("retracted"))
        status = "flagged_retraction" if retracted else status_value
        block = render.pubmed_record_to_markdown(rec)
        if retracted:
            note = rec.get("retraction_note") or "Retraction/expression of concern flagged on PubMed."
            block = f"**FLAGGED — retraction / expression of concern.** {note}\n\n{block}"
        out = {"decision": status, "record_type": None, "markdown_block": block,
               "appraisal_flags": [], "override_applied": None, "error": rec.get("retraction_note")}
        db.insert_item(conn, cycle_id, group.key, "pubmed", rec.get("pmid"), rec.get("doi"), None,
                        rec.get("title") or "", rec.get("journal"), rec.get("pub_date"),
                        None, rec, status, out)
        dedup.mark_pubmed_seen(conn, cycle_id, group.key, rec)
    return len(kept)


def run_group(conn, cycle_id: int, group: config.DiseaseGroup, window_start: str, window_end: str,
              dry_run: bool, max_items: int | None, queries_meta: dict, ignore_seen: bool = False,
              fresh_scan: bool = True, fresh_trials_only: bool = True) -> None:
    override = config.PER_GROUP_OVERRIDES.get(group.key)
    pub_types = list(config.DEFAULT_PUBLICATION_TYPES)
    if override:
        for rt in override.also_include_record_types:
            if rt not in pub_types:
                pub_types.append(rt)

    term = pubmed.build_pubmed_term(group.mesh_terms, group.journals, pub_types)
    ncbi_key = os.environ.get("NCBI_API_KEY") or None
    es = pubmed.esearch(term, window_start.replace("-", "/"), window_end.replace("-", "/"), api_key=ncbi_key)
    pm_records = pubmed.efetch(es["pmids"], api_key=ncbi_key)

    queries_meta[group.key] = {
        "pubmed_term": term,
        "pubmed_querytranslation": es["querytranslation"],
        "pubmed_count": es["count"],
        "window": [window_start, window_end],
    }

    if ignore_seen:
        new_pm = pm_records
        seen_label = "all (--ignore-seen)"
    else:
        new_pm = dedup.filter_new_pubmed(conn, pm_records)
        seen_label = "new"

    print(f"[{group.key}] PubMed: {len(pm_records)} retrieved, {len(new_pm)} {seen_label}.")

    if max_items is not None:
        new_pm = new_pm[:max_items]

    for rec in new_pm:
        if dry_run:
            status, out = "needs_review", {"decision": None, "markdown_block": None, "error": "dry-run: not rendered"}
        else:
            status, out = _abstract_only_output(rec)
        db.insert_item(conn, cycle_id, group.key, "pubmed", rec.get("pmid"), rec.get("doi"), None,
                        rec.get("title") or "", rec.get("journal"), rec.get("pub_date"),
                        out.get("record_type"), rec, status, out)
        dedup.mark_pubmed_seen(conn, cycle_id, group.key, rec)

    if not dry_run:
        retraction_items = recheck_retractions(conn, cycle_id, ncbi_key)
        for item in retraction_items:
            if item["disease_group"] != group.key:
                continue
            db.insert_item(conn, cycle_id, item["disease_group"], item["source_type"],
                            item["pmid"], item["doi"], item["nct"], item["title"], item["journal"],
                            item["pub_date"], item["record_type"], item["raw_payload"],
                            item["status"], item["llm_output"])

    # Supplementary "fresh scan": recent, possibly not-yet-MeSH-indexed papers
    # the strict query misses (PubMed indexing lag). Tier 1 and Tier 2 are
    # scanned separately so they can be reported in separate files. Runs after
    # the strict pass so already-surfaced papers are deduped out.
    if fresh_scan and not dry_run:
        tier2_journals = [j for j in group.journals if j.tier == 2]
        f1 = _run_fresh_scan(conn, cycle_id, group, window_start, window_end, ncbi_key,
                              ignore_seen, config.TIER1_JOURNALS, "recent_tier1",
                              queries_meta[group.key], "fresh_tier1", fresh_trials_only)
        f2 = _run_fresh_scan(conn, cycle_id, group, window_start, window_end, ncbi_key,
                              ignore_seen, tier2_journals, "recent_tier2",
                              queries_meta[group.key], "fresh_tier2", fresh_trials_only)
        print(f"[{group.key}] Fresh scan (not-yet-indexed): {f1} Tier-1, {f2} Tier-2.")


def main(argv=None):
    load_dotenv(config.DOTENV_PATH)
    args = parse_args(argv)
    groups = resolve_groups(args.groups)
    if not groups:
        sys.exit("No disease groups to run (none active; pass --group explicitly).")

    # Ensure the writable output locations exist (matters for the standalone
    # app, whose DATA_HOME is created on first run).
    os.makedirs(os.path.dirname(args.db_path) or ".", exist_ok=True)
    os.makedirs(args.digests_dir, exist_ok=True)

    today = date.today()
    run_date = today.isoformat()

    conn = db.get_connection(args.db_path)
    db.init_db(conn)

    group_keys = [g.key for g in groups]
    group_windows = {
        g.key: resolve_window(g, today, args.window_days, args.start_date, args.end_date)
        for g in groups
    }
    overall_start = min(start for start, _ in group_windows.values())
    overall_end = max(end for _, end in group_windows.values())

    cycle_id = db.start_cycle(conn, run_date, overall_start, overall_end, group_keys, {})

    queries_meta: dict = {}
    for group in groups:
        window_start, window_end = group_windows[group.key]
        run_group(conn, cycle_id, group, window_start, window_end,
                   args.dry_run, args.max_items, queries_meta, ignore_seen=args.ignore_seen,
                   fresh_scan=not args.no_fresh_scan, fresh_trials_only=not args.recent_all)

    conn.execute("UPDATE cycles SET queries_json = ? WHERE id = ?",
                 (__import__("json").dumps(queries_meta, default=str), cycle_id))
    conn.commit()

    cycle_row = conn.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
    items = db.get_items_for_cycle(conn, cycle_id)
    rd = cycle_row["run_date"]

    # Main verified digest.
    digest_md = render.render_cycle_digest(cycle_row, items, queries_meta)
    for p in render.write_outputs(args.digests_dir, cycle_row, f"{rd}_cycle", digest_md,
                                   args.format, index_label=f"{rd} cycle"):
        print(f"Digest written to {p}")

    # Separate files for the fresh-scan (recent, not-yet-indexed) hits, per tier.
    for status_value, tier_label, stem in (
        ("recent_tier1", "Tier 1", f"{rd}_recent_tier1"),
        ("recent_tier2", "Tier 2", f"{rd}_recent_tier2"),
    ):
        n = sum(1 for i in items if i["status"] == status_value)
        if not n:
            continue
        recent_md = render.render_recent_digest(cycle_row, items, status_value, tier_label, queries_meta)
        for p in render.write_outputs(args.digests_dir, cycle_row, stem, recent_md,
                                       args.format, index_label=f"{rd} recent {tier_label} ({n})"):
            print(f"Recent {tier_label} written to {p}")

    conn.close()


if __name__ == "__main__":
    main()
