# Heme/Onc Literature Surveillance Pipeline

A scheduled pipeline that surveils top hematology/oncology journals and
ClinicalTrials.gov for newly published practice-relevant evidence
(guidelines + phase II/III trials, plus per-group exceptions), triages /
extracts / appraises each new item via the Claude API using the paired
system prompt, and emits a Markdown digest.

**Surveillance aid only.** It never makes patient-specific recommendations,
and every item it surfaces carries a verifiable identifier (PMID / DOI /
NCT). See `heme_onc_literature_surveillance_prompt.md` for the full LLM-layer
contract and `pipeline_build_brief.txt` for the build spec.

## Status

First milestone complete: **AML** works end-to-end against live PubMed +
ClinicalTrials.gov, with a real Claude extraction call per item and a
rendered digest. Other disease groups are seeded in config but not yet
verified/activated (see `pipeline/config.py`).

## Layout

```
pipeline/
  config.py            disease groups, journals+ISSNs (verified 2026-07-01), per-group overrides
  db.py                SQLite: cycles, items, seen_ids (+ raw payloads for audit)
  dedup.py             dedup by PMID/DOI/NCT across cycles
  llm.py               per-item Claude call; enforces the identifier hard-rule downstream
  render.py            Markdown digest per the system prompt's OUTPUT FORMAT
  main.py              orchestrator: retrieve -> dedup -> retraction recheck -> LLM -> render
  retrieval/
    pubmed.py          E-utilities esearch/efetch; parses abstract/MeSH/pub-types; retraction/EoC detect
    ctgov.py           ClinicalTrials.gov API v2; token pagination; date normalization
digests/               YYYY-MM-DD_cycle.md per run + index.md
data/                  surveillance.db (git-ignored)
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in ANTHROPIC_API_KEY and (optional) NCBI_API_KEY
```

Secrets live in `.env` (git-ignored). Never commit real keys.

## Run

```bash
# retrieval + dedup only, no Claude calls (free, good for smoke-testing):
python -m pipeline.main --group aml --dry-run

# capped live run (limits Claude calls while validating):
python -m pipeline.main --group aml --max-items 3

# full cycle for AML:
python -m pipeline.main --group aml

# regenerate the same window from scratch, ignoring what was already seen
# (re-extracts every item and rewrites the digest instead of "0 new"):
python -m pipeline.main --group aml --ignore-seen

# default (all groups with active=True in config -- currently just AML):
python -m pipeline.main
```

Output: `digests/<date>_cycle.md`, linked from `digests/index.md`.

By default the pipeline dedups against everything it has seen in prior runs,
so a second run over the same window reports "0 new items". Pass
`--ignore-seen` to force a full re-extraction of every retrieved item and
rewrite that window's digest (this re-incurs one Claude call per item).

## Model

Extraction uses `claude-sonnet-5` (`ANTHROPIC_MODEL` in `pipeline/config.py`).
`ANTHROPIC_MAX_TOKENS` is set to 6000 to leave headroom above the model's
internal reasoning tokens; truncated responses are routed to "needs human
review" rather than emitted partially.

## Adding a disease group

1. In `pipeline/config.py`, fill in `mesh_terms`, `journals`,
   `ctgov_condition` for the group.
2. Verify the MeSH heading (`esearch` against `db=mesh`) and each journal's
   PubMed `[Journal]` filter term + ISSN (see the note at the top of
   `config.py` for exactly how AML's were verified).
3. Set `mesh_verified=True` and `active=True`.

## Not yet built (out of scope for this milestone)

- Solid-tumor + remaining heme groups (config seeded, unverified/inactive).
- Society guideline-page scraping (NCCN/ASCO/ASH/ESMO update off their own
  cadence, not via PubMed).
- Europe PMC open-access full-text enrichment.
- Scheduling (cron / GitHub Actions). The pipeline is a single idempotent
  command; wiring a scheduler is a thin wrapper.
