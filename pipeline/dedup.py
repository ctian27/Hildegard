"""Dedup against the seen_ids table. Keys: PMID, DOI, NCT number."""

from . import db


def filter_new_pubmed(conn, records: list[dict]) -> list[dict]:
    """Drop records whose PMID or DOI has been seen in a prior cycle."""
    new = []
    for rec in records:
        pmid = rec.get("pmid")
        doi = rec.get("doi")
        if pmid and db.is_seen(conn, "pmid", pmid):
            continue
        if doi and db.is_seen(conn, "doi", doi):
            continue
        new.append(rec)
    return new


def filter_new_ctgov(conn, records: list[dict]) -> list[dict]:
    """Drop records whose NCT number has been seen in a prior cycle."""
    new = []
    for rec in records:
        nct = rec.get("nct_id")
        if nct and db.is_seen(conn, "nct", nct):
            continue
        new.append(rec)
    return new


def mark_pubmed_seen(conn, cycle_id: int, group_key: str, rec: dict) -> None:
    if rec.get("pmid"):
        db.mark_seen(conn, "pmid", rec["pmid"], group_key, cycle_id)
    if rec.get("doi"):
        db.mark_seen(conn, "doi", rec["doi"], group_key, cycle_id)


def mark_ctgov_seen(conn, cycle_id: int, group_key: str, rec: dict) -> None:
    if rec.get("nct_id"):
        db.mark_seen(conn, "nct", rec["nct_id"], group_key, cycle_id)
