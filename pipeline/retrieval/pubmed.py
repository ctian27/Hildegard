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
MAX_RETRIES = 5


def _sleep():
    time.sleep(RATE_LIMIT_SLEEP)


def _get(url: str, params: dict, timeout: int) -> requests.Response:
    """GET with backoff on transient NCBI errors (429 rate-limit, 5xx). Without
    an API key E-utilities allows only ~3 req/s, and the fresh scan multiplies
    the call volume, so a bare request would otherwise crash the whole run on a
    momentary 429."""
    delay = 1.0
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise requests.exceptions.HTTPError(f"{r.status_code}", response=r)
            r.raise_for_status()
            return r
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_exc = e
            if attempt == MAX_RETRIES - 1:
                break
            time.sleep(delay)
            delay = min(delay * 2, 16.0)  # exponential backoff, capped
    raise last_exc


def build_pubmed_term(mesh_terms: list[str], journals: list["config.Journal"],
                       publication_types: list[str]) -> str:
    pubtype_clause = " OR ".join(f'"{pt}"[Publication Type]' for pt in publication_types)
    mesh_clause = " OR ".join(f'"{m}"[MeSH Terms]' for m in mesh_terms)
    journal_clause = " OR ".join(f'"{j.pubmed_filter_term}"[Journal]' for j in journals)
    return (
        f"({pubtype_clause}) AND ({mesh_clause}) AND humans[MeSH Terms] AND ({journal_clause})"
    )


# Title/abstract cues for phase II/III trials and guidelines. Since not-yet-
# indexed papers carry no [Publication Type] tags, this is how the fresh scan
# can still restrict to trials/guidelines -- such papers almost always say so
# in the title or abstract. PubMed [tiab] matching is case-insensitive.
TRIAL_GUIDELINE_TIAB = (
    '("phase 2"[tiab] OR "phase 3"[tiab] OR "phase ii"[tiab] OR "phase iii"[tiab] '
    'OR "phase 2/3"[tiab] OR "phase 2b"[tiab] OR randomized[tiab] OR randomised[tiab] '
    'OR "clinical trial"[tiab] OR guideline[tiab] OR guidelines[tiab] OR consensus[tiab] '
    'OR recommendation[tiab] OR recommendations[tiab])'
)


def build_fresh_term(mesh_terms: list[str], journals: list["config.Journal"],
                      text_terms: list[str], trials_guidelines_only: bool = True) -> str:
    """Query for recently-published, possibly not-yet-indexed papers in a
    journal set. Deliberately drops the pub-type and humans[MeSH] gates and
    matches the disease by MeSH *or* title/abstract text, so a freshly-loaded
    citation with no MeSH yet is still caught. When `trials_guidelines_only`,
    also require phase II/III-trial or guideline language in the title/abstract
    to cut non-trial noise."""
    mesh_clause = " OR ".join(f'"{m}"[MeSH Terms]' for m in mesh_terms)
    tiab_clause = " OR ".join(f'"{t}"[Title/Abstract]' for t in text_terms)
    disease = f"({mesh_clause} OR {tiab_clause})"
    journal_clause = " OR ".join(f'"{j.pubmed_filter_term}"[Journal]' for j in journals)
    term = f"{disease} AND ({journal_clause})"
    if trials_guidelines_only:
        term += f" AND {TRIAL_GUIDELINE_TIAB}"
    return term


# Publication types that are clearly not primary practice-relevant evidence;
# used to trim obvious noise from the (ungated) fresh scan when a record does
# carry partial type tags.
NON_PRIMARY_PUB_TYPES = frozenset({
    "Editorial", "Comment", "Letter", "News", "Biography", "Historical Article",
    "Published Erratum", "Retraction of Publication", "Retracted Publication",
    "Expression of Concern", "Review", "Systematic Review",
})

# Extra exclusions for the fresh scan: case reports/series and preclinical /
# animal work (the tool never wants these). Matched on publication types +
# TITLE (not abstract) to avoid dropping a real trial whose abstract merely
# mentions a translational/lab sub-study.
_CASE_REPORT_PUB_TYPES = frozenset({"Case Reports"})
_CASE_REPORT_TITLE = (
    "case report", "case series", "a case of", "case study", "case studies",
    "case of ", ": a case", "report of a case",
)
_PRECLINICAL_TITLE = (
    "in vitro", "in vivo", "preclinical", "pre-clinical", "xenograft", "murine",
    "mouse model", "mouse models", "in mice", "in rats", "rat model", "cell line",
    "cell lines", "organoid", "organoids", "zebrafish", "patient-derived xenograft",
)


def fresh_exclusion_reason(rec: dict) -> str | None:
    """Return an exclusion reason if a fresh-scan record looks like a case
    report/series or preclinical/animal study; else None."""
    types = set(rec.get("publication_types") or [])
    title = (rec.get("title") or "").lower()
    if types & _CASE_REPORT_PUB_TYPES or any(m in title for m in _CASE_REPORT_TITLE):
        return "case report/series"
    if any(m in title for m in _PRECLINICAL_TITLE):
        return "preclinical/animal"
    return None


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
    r = _get(config.NCBI_EUTILS_BASE + "esearch.fcgi", params, timeout=30)
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
        r = _get(config.NCBI_EUTILS_BASE + "efetch.fcgi", params, timeout=60)
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
