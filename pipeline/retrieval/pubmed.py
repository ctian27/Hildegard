"""PubMed E-utilities retrieval: esearch (find PMIDs) + efetch (parse records).

Only titles/abstracts/MeSH/pub-types/IDs are extracted -- this is metadata,
not paywalled full text, consistent with the paired system prompt's sourcing
rules.
"""

import time
import xml.etree.ElementTree as ET

import requests

from .. import config

HEADERS = {"User-Agent": "heme-onc-literature-surveillance/0.1"}
RATE_LIMIT_SLEEP = 0.11  # ~9/s, safely under the 10/s API-key ceiling


def _sleep():
    time.sleep(RATE_LIMIT_SLEEP)


def build_pubmed_term(mesh_terms: list[str], journals: list["config.Journal"],
                       publication_types: list[str]) -> str:
    pubtype_clause = " OR ".join(f'"{pt}"[Publication Type]' for pt in publication_types)
    mesh_clause = " OR ".join(f'"{m}"[MeSH Terms]' for m in mesh_terms)
    journal_clause = " OR ".join(f'"{j.pubmed_filter_term}"[Journal]' for j in journals)
    return (
        f"({pubtype_clause}) AND ({mesh_clause}) AND humans[MeSH Terms] AND ({journal_clause})"
    )


def esearch(term: str, mindate: str, maxdate: str, api_key: str | None = None,
            retmax: int = 300) -> dict:
    """Returns {"pmids": [...], "count": int, "querytranslation": str}."""
    params = {
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retmax": retmax,
        "datetype": "pdat",
        "mindate": mindate,
        "maxdate": maxdate,
    }
    if api_key:
        params["api_key"] = api_key
    r = requests.get(config.NCBI_EUTILS_BASE + "esearch.fcgi", params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    _sleep()
    es = r.json()["esearchresult"]
    return {
        "pmids": es.get("idlist", []),
        "count": int(es.get("count", 0)),
        "querytranslation": es.get("querytranslation", term),
    }


def _text(el, path, default=None):
    found = el.find(path)
    return found.text if found is not None and found.text else default


def _parse_pub_date(article_el) -> str | None:
    pd = article_el.find(".//Journal/JournalIssue/PubDate")
    if pd is None:
        return None
    year = _text(pd, "Year")
    month = _text(pd, "Month", "")
    day = _text(pd, "Day", "")
    medline_date = _text(pd, "MedlineDate")
    if year:
        return "-".join(p for p in (year, month, day) if p)
    return medline_date


def _parse_article(pubmed_article: ET.Element) -> dict:
    medline = pubmed_article.find("MedlineCitation")
    article = medline.find("Article")
    pmid = _text(medline, "PMID")

    doi = None
    for aid in pubmed_article.findall(".//PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi":
            doi = aid.text
            break

    title = _text(article, "ArticleTitle", "")
    journal = _text(article, "Journal/Title") or _text(article, "Journal/ISOAbbreviation")
    pub_date = _parse_pub_date(article)

    abstract_parts = []
    for ab in article.findall(".//Abstract/AbstractText"):
        label = ab.get("Label")
        text = ab.text or ""
        abstract_parts.append(f"{label}: {text}" if label else text)
    abstract = "\n".join(abstract_parts) if abstract_parts else None

    pub_types = [pt.text for pt in article.findall(".//PublicationTypeList/PublicationType") if pt.text]
    mesh_terms = [
        dn.text for dn in medline.findall(".//MeshHeadingList/MeshHeading/DescriptorName") if dn.text
    ]

    retraction_note = None
    retracted = False
    for cc in medline.findall(".//CommentsCorrectionsList/CommentsCorrections"):
        ref_type = cc.get("RefType", "")
        if ref_type in ("RetractionIn", "ExpressionOfConcernIn"):
            retracted = True
            note_src = _text(cc, "RefSource", "")
            retraction_note = f"{ref_type}: {note_src}"
    if any(pt and "Retracted Publication" in pt for pt in pub_types):
        retracted = True
        retraction_note = retraction_note or "PublicationType: Retracted Publication"

    return {
        "pmid": pmid,
        "doi": doi,
        "title": title,
        "journal": journal,
        "pub_date": pub_date,
        "abstract": abstract,
        "publication_types": pub_types,
        "mesh_terms": mesh_terms,
        "retracted": retracted,
        "retraction_note": retraction_note,
    }


def efetch(pmids: list[str], api_key: str | None = None, batch_size: int = 150) -> list[dict]:
    if not pmids:
        return []
    records = []
    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i + batch_size]
        params = {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}
        if api_key:
            params["api_key"] = api_key
        r = requests.get(config.NCBI_EUTILS_BASE + "efetch.fcgi", params=params, headers=HEADERS, timeout=60)
        r.raise_for_status()
        _sleep()
        root = ET.fromstring(r.content)
        for pa in root.findall("PubmedArticle"):
            records.append(_parse_article(pa))
    return records


def check_retractions(pmids: list[str], api_key: str | None = None) -> dict[str, dict]:
    """Re-fetch previously-seen PMIDs and report current retraction/EoC status."""
    records = efetch(pmids, api_key=api_key)
    return {
        r["pmid"]: {"retracted": r["retracted"], "note": r["retraction_note"]}
        for r in records
    }
