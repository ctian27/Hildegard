# Heme/Onc Literature Surveillance Pipeline

A scheduled pipeline that surveils top hematology/oncology journals via
PubMed for newly published practice-relevant evidence (guidelines + phase
II/III trials, plus per-group exceptions), triages / extracts / appraises
each new item via the Claude API using the paired system prompt, and emits a
Markdown digest. It surfaces **published, peer-reviewed papers only** —
ClinicalTrials.gov registry retrieval has been removed.

**Surveillance aid only.** It never makes patient-specific recommendations,
and every item it surfaces carries a verifiable identifier (PMID / DOI /
NCT). See `heme_onc_literature_surveillance_prompt.md` for the full LLM-layer
contract and `pipeline_build_brief.txt` for the build spec.

## Status

**All 26 disease groups** work end-to-end against live PubMed, with a real
Claude extraction call per item and a rendered digest.

- **Hematologic (15):** AML, MDS, MPN, CLL, DLBCL, follicular lymphoma, mantle
  cell lymphoma, marginal zone lymphoma, Hodgkin, multiple myeloma, ALL, CML,
  aplastic anemia, CHIP (30-day window + observational override), sickle cell
  (gene/cell-therapy override). Journals: Tier 1 + Tier 2-Hematology.
- **Solid tumor (11):** head & neck, breast, lung, pancreatic, gastric, liver
  (hepatocellular/biliary), colorectal, melanoma, prostate, sarcomas, thyroid.
  Journals: Tier 1 + Tier 2-Oncology.

Every group's MeSH heading was verified live against NCBI (`db=mesh`) and every
journal `[Journal]` term + ISSN resolved live against PubMed (2026-07-01/02).

## Layout

```
pipeline/
  config.py            disease groups, journals+ISSNs (verified 2026-07-01), per-group overrides
  db.py                SQLite: cycles, items, seen_ids (+ raw payloads for audit)
  dedup.py             dedup by PMID/DOI across cycles
  llm.py               per-item Claude call; enforces the identifier hard-rule downstream
  render.py            Markdown digest per the OUTPUT FORMAT + PDF conversion (markdown -> HTML -> xhtml2pdf)
  main.py              orchestrator: retrieve -> dedup -> retraction recheck -> LLM -> render
  retrieval/
    pubmed.py          E-utilities esearch/efetch; parses abstract/MeSH/pub-types; retraction/EoC detect
digests/               YYYY-MM-DD_cycle.md per run + index.md
data/                  surveillance.db (git-ignored)
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in ANTHROPIC_API_KEY and (optional) NCBI_API_KEY
```

Secrets live in `.env` (git-ignored). Never commit real keys. The
`ANTHROPIC_API_KEY` is only needed for AI summaries; the abstracts-only mode
(`--no-llm` / unchecking "Use AI summaries") runs without any key.

## GUI (point-and-click)

**Easiest:**
- **macOS:** double-click **`Run Surveillance.command`**.
- **Windows:** double-click **`Run Surveillance.bat`**.

Either opens a small console window and then the GUI. On first run it sets up
its own Python environment automatically (takes a minute); after that it
launches straight away. On macOS the first launch may ask Terminal for
permission to access your Documents folder — click **Allow**. On Windows you
need Python installed first (python.org — tick "Add Python to PATH" during
install).

> There is also a `Literature Surveillance.app` bundle (no Terminal window),
> but macOS privacy rules block a double-clicked app from reading files inside
> `~/Documents`/`~/Desktop`/`~/Downloads`. If the project lives in one of those
> folders, use the `.command` file instead (or move the project elsewhere).

Or from a terminal:

```bash
python -m pipeline.gui
```

A desktop window opens: tick the disease groups you want, choose the output
format, optionally set a **date range** (From / To, `YYYY-MM-DD`), toggle
**"Use AI summaries"** (see below), or toggle "ignore previously seen papers" /
"dry run" / a max-items cap, then click **Run cycle**. Leave the dates blank to
use each group's default rolling window. Output streams into the log pane. Uses
Tkinter (bundled with Python — no extra install). Everything it does is also
available on the command line below.

**AI summaries vs. abstracts only.** By default ("Use AI summaries" checked)
each paper is sent to Claude for structured extraction and appraisal — this
needs an `ANTHROPIC_API_KEY`. Uncheck it (or pass `--no-llm`) to skip Claude
entirely: the digest then lists each paper's identification info plus its
verbatim PubMed abstract. That mode needs **no API key**, so the surveillance /
retrieval function is usable on its own.

## Sharing this tool with someone else

Send them the project folder (zip it, or share the git repo), then they
double-click **`Run Surveillance.command`** (macOS) or **`Run
Surveillance.bat`** (Windows) — it builds the Python environment on their
machine on first launch. The pipeline itself is cross-platform; only the
launcher differs by OS. When zipping, **exclude these** (they are
machine-specific or private):

- `.venv/` — a virtual environment is not portable; the launcher rebuilds it.
- `.env` — your private API keys. Each person supplies their own.
- `data/` — your local seen-items database (optional to share).

The recipient needs Python 3 installed (python.org) and their own
`ANTHROPIC_API_KEY` (and optional `NCBI_API_KEY`) placed in a `.env` file
(copy `.env.example` to `.env`). The launcher warns if no key is set.

## Run (command line)

```bash
# retrieval + dedup only, no Claude calls (free, good for smoke-testing):
python -m pipeline.main --group aml --dry-run

# capped live run (limits Claude calls while validating):
python -m pipeline.main --group aml --max-items 3

# abstracts only -- no Claude, no API key needed (identification info + abstract):
python -m pipeline.main --group aml --no-llm

# full cycle for AML:
python -m pipeline.main --group aml

# regenerate the same window from scratch, ignoring what was already seen
# (re-extracts every item and rewrites the digest instead of "0 new"):
python -m pipeline.main --group aml --ignore-seen

# a specific group (any active group key, e.g. multiple_myeloma, cll, chip):
python -m pipeline.main --group multiple_myeloma

# several groups in one cycle (repeat --group):
python -m pipeline.main --group aml --group mds --group cll

# explicit publication-date range (overrides the rolling window for all groups):
python -m pipeline.main --group aml --start-date 2026-01-01 --end-date 2026-03-31

# rolling window of a custom length, counted back from the end date (today):
python -m pipeline.main --group aml --window-days 30

# default: every group with active=True in config (all 26 groups):
python -m pipeline.main
```

**Date range.** By default each group searches its own rolling window (14
days; CHIP 30) back from today. Use `--start-date`/`--end-date` (YYYY-MM-DD,
by publication date) to search a fixed range instead — this applies to every
selected group and overrides the per-group windows. `--start-date` alone runs
from that date to today; `--window-days N` sets a custom rolling length.

Active group keys — hematologic: `aml`, `mds`, `mpn`, `cll`, `dlbcl`,
`follicular_lymphoma`, `mantle_cell_lymphoma`, `marginal_zone_lymphoma`,
`hodgkin`, `multiple_myeloma`, `all`, `cml`, `aplastic_anemia`, `chip`,
`sickle_cell`; solid tumor: `head_neck`, `breast`, `lung`, `pancreatic`,
`gastric`, `liver`, `colorectal`, `melanoma`, `prostate`, `sarcomas`,
`thyroid`.

Note: a full default run makes one Claude call per new item across all 15
groups, so it can take a while and costs accordingly. Use `--dry-run` first
to see item counts, or run a single group at a time.

Output per cycle: `digests/<date>_cycle.pdf` and `digests/<date>_cycle.md`
(the Markdown is linked from `digests/index.md`). The PDF renders each
disease group as a subheading with its identified articles underneath. Choose
the format with `--format`:

```bash
python -m pipeline.main --group aml --format pdf    # PDF only
python -m pipeline.main --group aml --format md     # Markdown only
python -m pipeline.main --group aml                 # both (default)
```

By default the pipeline dedups against everything it has seen in prior runs,
so a second run over the same window reports "0 new items". Pass
`--ignore-seen` to force a full re-extraction of every retrieved item and
rewrite that window's digest (this re-incurs one Claude call per item).

## Model

Extraction uses `claude-haiku-4-5-20251001` (`ANTHROPIC_MODEL` in
`pipeline/config.py`). `ANTHROPIC_MAX_TOKENS` is set to 6000 to leave headroom
above the model's internal reasoning tokens; truncated responses are routed to
"needs human review" rather than emitted partially.

## Adding a disease group

1. In `pipeline/config.py`, fill in `mesh_terms` and `journals` for the group.
2. Verify the MeSH heading (`esearch` against `db=mesh`) and each journal's
   PubMed `[Journal]` filter term + ISSN (see the note at the top of
   `config.py` for exactly how AML's were verified).
3. Set `mesh_verified=True` and `active=True`.

## Not yet built (out of scope for this milestone)

- Society guideline-page scraping (NCCN/ASCO/ASH/ESMO update off their own
  cadence, not via PubMed).
- Europe PMC open-access full-text enrichment.
- Scheduling (cron / GitHub Actions). The pipeline is a single idempotent
  command; wiring a scheduler is a thin wrapper.
