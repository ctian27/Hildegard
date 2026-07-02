"""ClinicalTrials.gov API v2 retrieval.

Catches results postings before journal publication. Public, no auth,
~50 req/min per IP. Date fields are inconsistent across the underlying
registry (mostly ISO YYYY[-MM[-DD]] via *DateStruct.date in v2, but some
legacy free-text forms like "January 2024" or "January 15, 2024" can still
surface) -- normalize_date() below handles both.
"""

import re
import time

import requests

from .. import config

HEADERS = {"User-Agent": "heme-onc-literature-surveillance/0.1"}
RATE_LIMIT_SLEEP = 1.3  # ~46/min, under the ~50/min per-IP ceiling
MAX_PAGES = 10  # safety cap: 10 * pageSize studies per group per cycle

_MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}
_MONTH_YYYY = re.compile(r"^([A-Za-z]+)\s+(\d{4})$")
_MONTH_D_YYYY = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$")
_ISO = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def normalize_date(raw: str | None) -> str | None:
    """Normalize CT.gov date strings to ISO 'YYYY', 'YYYY-MM', or 'YYYY-MM-DD'."""
    if not raw:
        return None
    raw = raw.strip()
    if _ISO.match(raw):
        return raw
    m = _MONTH_D_YYYY.match(raw)
    if m:
        month_name, day, year = m.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            return f"{year}-{month}-{int(day):02d}"
    m = _MONTH_YYYY.match(raw)
    if m:
        month_name, year = m.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            return f"{year}-{month}"
    return raw  # unrecognized format -- pass through rather than silently drop


def search_studies(condition: str, window_start: str, window_end: str,
                    phases: tuple[str, ...] = ("2", "3"),
                    page_size: int = 100) -> tuple[list[dict], dict]:
    """Returns (studies, query_meta) for interventional studies of `condition`
    at the given phases, last-updated within [window_start, window_end]
    (YYYY-MM-DD). query_meta records the exact params used, for the digest
    footer.
    """
    agg_filters = ",".join(f"phase:{p}" for p in phases)
    base_params = {
        "query.cond": condition,
        "aggFilters": agg_filters,
        "filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{window_start},{window_end}]",
        "sort": "LastUpdatePostDate:desc",
        "pageSize": page_size,
        "format": "json",
    }
    studies = []
    page_token = None
    for _ in range(MAX_PAGES):
        params = dict(base_params)
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(config.CTGOV_BASE, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        time.sleep(RATE_LIMIT_SLEEP)
        data = r.json()
        studies.extend(data.get("studies", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return studies, {"endpoint": config.CTGOV_BASE, "params": base_params}


def extract_record(study: dict) -> dict:
    protocol = study.get("protocolSection", {})
    ident = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    conditions_mod = protocol.get("conditionsModule", {})
    description = protocol.get("descriptionModule", {})
    sponsors = protocol.get("sponsorCollaboratorsModule", {})
    outcomes_mod = protocol.get("outcomesModule", {})
    arms_mod = protocol.get("armsInterventionsModule", {})

    has_results = bool(study.get("hasResults"))
    results_section = study.get("resultsSection", {}) if has_results else {}

    return {
        "nct_id": ident.get("nctId"),
        "title": ident.get("officialTitle") or ident.get("briefTitle"),
        "brief_title": ident.get("briefTitle"),
        "phases": design.get("phases", []),
        "study_type": design.get("studyType"),
        "overall_status": status.get("overallStatus"),
        "conditions": conditions_mod.get("conditions", []),
        "brief_summary": description.get("briefSummary"),
        "enrollment": design.get("enrollmentInfo", {}).get("count"),
        "lead_sponsor": sponsors.get("leadSponsor", {}).get("name"),
        "sponsor_class": sponsors.get("leadSponsor", {}).get("class"),
        "arms": arms_mod.get("armGroups", []),
        "interventions": arms_mod.get("interventions", []),
        "primary_outcomes": outcomes_mod.get("primaryOutcomes", []),
        "secondary_outcomes": outcomes_mod.get("secondaryOutcomes", []),
        "study_first_post_date": normalize_date(status.get("studyFirstPostDateStruct", {}).get("date")),
        "last_update_post_date": normalize_date(status.get("lastUpdatePostDateStruct", {}).get("date")),
        "results_first_post_date": normalize_date(status.get("resultsFirstPostDateStruct", {}).get("date")),
        "has_results": has_results,
        "results_outcome_measures": results_section.get("outcomeMeasuresModule", {}).get("outcomeMeasures", []) if has_results else [],
        "results_adverse_events": results_section.get("adverseEventsModule", {}) if has_results else {},
    }
