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

import anthropic
from dotenv import load_dotenv

from . import config, db, dedup, llm, render
from .retrieval import ctgov, pubmed


def parse_args():
    p = argparse.ArgumentParser(description="Heme/onc literature surveillance cycle")
    p.add_argument("--group", action="append", dest="groups",
                    help="Disease group key to run (repeatable). Default: all active groups.")
    p.add_argument("--window-days", type=int, default=None, help="Override the group's default window.")
    p.add_argument("--dry-run", action="store_true", help="Retrieve + dedup only; skip Claude calls.")
    p.add_argument("--max-items", type=int, default=None, help="Cap LLM calls per group (smoke-testing).")
    p.add_argument("--ignore-seen", action="store_true",
                    help="Reprocess every retrieved item even if seen in a prior cycle "
                         "(regenerate the same window's digest from scratch instead of "
                         "reporting 'no new items').")
    p.add_argument("--db-path", default=config.DB_PATH)
    p.add_argument("--digests-dir", default=config.DIGESTS_DIR)
    return p.parse_args()


def resolve_groups(keys: list[str] | None) -> list[config.DiseaseGroup]:
    if keys:
        missing = [k for k in keys if k not in config.DISEASE_GROUPS]
        if missing:
            sys.exit(f"Unknown disease group(s): {missing}. Known: {list(config.DISEASE_GROUPS)}")
        return [config.DISEASE_GROUPS[k] for k in keys]
    return config.ACTIVE_GROUPS


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


def run_group(conn, cycle_id: int, group: config.DiseaseGroup, window_start: str, window_end: str,
              client: anthropic.Anthropic | None, system_prompt: str, dry_run: bool,
              max_items: int | None, queries_meta: dict, ignore_seen: bool = False) -> None:
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

    studies, ctgov_meta = ctgov.search_studies(group.ctgov_condition, window_start, window_end)
    ct_records = [ctgov.extract_record(s) for s in studies]

    queries_meta[group.key] = {
        "pubmed_term": term,
        "pubmed_querytranslation": es["querytranslation"],
        "pubmed_count": es["count"],
        "window": [window_start, window_end],
        "ctgov": ctgov_meta,
    }

    if ignore_seen:
        new_pm, new_ct = pm_records, ct_records
        seen_label = "all (--ignore-seen)"
    else:
        new_pm = dedup.filter_new_pubmed(conn, pm_records)
        new_ct = dedup.filter_new_ctgov(conn, ct_records)
        seen_label = "new"

    print(f"[{group.key}] PubMed: {len(pm_records)} retrieved, {len(new_pm)} {seen_label}. "
          f"CT.gov: {len(ct_records)} retrieved, {len(new_ct)} {seen_label}.")

    if max_items is not None:
        new_pm = new_pm[:max_items]
        new_ct = new_ct[:max(0, max_items - len(new_pm))]

    for rec in new_pm:
        identifiers = {"pmid": rec.get("pmid"), "doi": rec.get("doi"), "nct": None}
        if dry_run:
            status, llm_out = "needs_review", {"decision": None, "markdown_block": None, "error": "dry-run: LLM skipped"}
        else:
            result = llm.process_item(client, system_prompt, group.key, "pubmed", rec, identifiers)
            status, llm_out = result["status"], result
        db.insert_item(conn, cycle_id, group.key, "pubmed", rec.get("pmid"), rec.get("doi"), None,
                        rec.get("title") or "", rec.get("journal"), rec.get("pub_date"),
                        llm_out.get("record_type"), rec, status, llm_out)
        dedup.mark_pubmed_seen(conn, cycle_id, group.key, rec)

    for rec in new_ct:
        identifiers = {"pmid": None, "doi": None, "nct": rec.get("nct_id")}
        if dry_run:
            status, llm_out = "needs_review", {"decision": None, "markdown_block": None, "error": "dry-run: LLM skipped"}
        else:
            result = llm.process_item(client, system_prompt, group.key, "ctgov", rec, identifiers)
            status, llm_out = result["status"], result
        db.insert_item(conn, cycle_id, group.key, "ctgov", None, None, rec.get("nct_id"),
                        rec.get("title") or "", "ClinicalTrials.gov", rec.get("last_update_post_date"),
                        llm_out.get("record_type") or "trial", rec, status, llm_out)
        dedup.mark_ctgov_seen(conn, cycle_id, group.key, rec)

    if not dry_run:
        retraction_items = recheck_retractions(conn, cycle_id, ncbi_key)
        for item in retraction_items:
            if item["disease_group"] != group.key:
                continue
            db.insert_item(conn, cycle_id, item["disease_group"], item["source_type"],
                            item["pmid"], item["doi"], item["nct"], item["title"], item["journal"],
                            item["pub_date"], item["record_type"], item["raw_payload"],
                            item["status"], item["llm_output"])


def main():
    load_dotenv()
    args = parse_args()
    groups = resolve_groups(args.groups)
    if not groups:
        sys.exit("No disease groups to run (none active; pass --group explicitly).")

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not args.dry_run and not anthropic_key:
        sys.exit("ANTHROPIC_API_KEY not set (in .env or environment). Use --dry-run to test retrieval only.")

    client = None if args.dry_run else anthropic.Anthropic(api_key=anthropic_key)
    system_prompt = llm.load_system_prompt()

    today = date.today()
    run_date = today.isoformat()

    conn = db.get_connection(args.db_path)
    db.init_db(conn)

    group_keys = [g.key for g in groups]
    windows = {g.key: args.window_days or g.window_days for g in groups}
    overall_window_days = max(windows.values())
    overall_start = (today - timedelta(days=overall_window_days)).isoformat()

    cycle_id = db.start_cycle(conn, run_date, overall_start, run_date, group_keys, {})

    queries_meta: dict = {}
    for group in groups:
        window_days = windows[group.key]
        window_start = (today - timedelta(days=window_days)).isoformat()
        run_group(conn, cycle_id, group, window_start, run_date, client, system_prompt,
                   args.dry_run, args.max_items, queries_meta, ignore_seen=args.ignore_seen)

    conn.execute("UPDATE cycles SET queries_json = ? WHERE id = ?",
                 (__import__("json").dumps(queries_meta, default=str), cycle_id))
    conn.commit()

    cycle_row = conn.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
    items = db.get_items_for_cycle(conn, cycle_id)
    digest_md = render.render_cycle_digest(cycle_row, items, queries_meta)
    path = render.write_digest(args.digests_dir, cycle_row, digest_md)
    print(f"Digest written to {path}")

    conn.close()


if __name__ == "__main__":
    main()
