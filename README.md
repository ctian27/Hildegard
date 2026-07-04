# Hildegard — Heme/Onc Literature Surveillance Pipeline

A scheduled pipeline that surveils top hematology/oncology journals via
PubMed for newly published practice-relevant evidence (guidelines + phase
II/III trials, plus per-group exceptions), dedups and groups it by disease,
and emits a Markdown/PDF digest of each paper's identification info + verbatim
abstract. It surfaces **published, peer-reviewed papers only** — no LLM, no API
key. It is a retrieval/triage aid, not an interpreter: it never summarizes or
appraises the papers.

**Surveillance aid only.** It never makes patient-specific recommendations,
and every item carries a verifiable identifier (PMID / DOI). See
`heme_onc_literature_surveillance_prompt.md` for the clinical inclusion
criteria that shaped the queries, and `pipeline_build_brief.txt` for the build
spec.

## Status

**All 26 disease groups** work end-to-end against live PubMed, producing a
disease-grouped digest of identification info + abstract per paper.

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
  render.py            Markdown digest (identification info + abstract) + PDF conversion (markdown -> HTML -> xhtml2pdf)
  main.py              orchestrator: retrieve -> dedup -> retraction recheck -> render
  retrieval/
    pubmed.py          E-utilities esearch/efetch; parses abstract/MeSH/pub-types; retraction/EoC detect
digests/               YYYY-MM-DD_cycle.md per run + index.md
data/                  surveillance.db (git-ignored)
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

No API key is required. A `.env` is **optional** — set `NCBI_API_KEY` in one
(copy `.env.example`) only if you want a higher PubMed rate limit. `.env` is
git-ignored.

## Standalone app (no Python needed)

For a true one-click experience with **nothing to install**, use the
standalone build — the Python interpreter and every dependency are bundled
inside the app.

- **Get it:** download the zip for your OS from the repo's **Releases** page
  (produced by CI — see "Building the standalone apps" below), unzip, and:
  - **macOS:** double-click **`Hildegard.app`**. First launch: right-click →
    **Open** → **Open** (unsigned app, one-time Gatekeeper step).
  - **Windows:** open the unzipped folder and double-click **`Hildegard.exe`**.
- **No Python, no setup, no API key required.** It works immediately.
- **Where output goes:** the app writes digests to a **`Hildegard` folder in
  your home directory** (`~/Hildegard/digests` on macOS, `%USERPROFILE%\Hildegard\digests`
  on Windows), so it works no matter where the app itself lives.

The macOS build from CI is Apple-Silicon (arm64); Intel-Mac users should run
from source or the launcher below.

## GUI from source (point-and-click, needs Python)

**Easiest:**
- **macOS:** double-click **`Run Hildegard.command`**.
- **Windows:** double-click **`Run Hildegard.bat`**.

Either opens a small console window and then the GUI. On first run it sets up
its own Python environment automatically (takes a minute); after that it
launches straight away. On macOS the first launch may ask Terminal for
permission to access your Documents folder — click **Allow**. On Windows you
need Python installed first (python.org — tick "Add Python to PATH" during
install).

> There is also a `Hildegard.app` launcher bundle here (no Terminal window),
> but macOS privacy rules block a double-clicked app from reading files inside
> `~/Documents`/`~/Desktop`/`~/Downloads`. If the project lives in one of those
> folders, use the `.command` file instead (or move the project elsewhere).
> (This launcher bundle still needs Python — for the no-Python version use the
> standalone build above.)

> There is also a `Hildegard.app` bundle (no Terminal window),
> but macOS privacy rules block a double-clicked app from reading files inside
> `~/Documents`/`~/Desktop`/`~/Downloads`. If the project lives in one of those
> folders, use the `.command` file instead (or move the project elsewhere).

Or from a terminal:

```bash
python -m pipeline.gui
```

A desktop window opens: tick the disease groups you want, choose the output
format, optionally set a **date range** (From / To, `YYYY-MM-DD`), or toggle
"ignore previously seen papers" / "dry run" / a max-items cap, then click **Run
cycle**. Leave the dates blank to use each group's default rolling window.
Output streams into the log pane. Uses Tkinter (bundled with Python — no extra
install). Everything it does is also available on the command line below.

## Sharing this tool with someone else

Send them the project folder (zip it, or share the git repo), then they
double-click **`Run Hildegard.command`** (macOS) or **`Run
Hildegard.bat`** (Windows) — it builds the Python environment on their
machine on first launch. The pipeline itself is cross-platform; only the
launcher differs by OS. When zipping, **exclude these** (they are
machine-specific):

- `.venv/` — a virtual environment is not portable; the launcher rebuilds it.
- `data/` — your local seen-items database (optional to share).
- `.env` — if you made one (optional, holds only an NCBI key).

The recipient needs Python 3 installed (python.org). No API key is required.
(Or just hand them the standalone app — no Python needed at all.)

## Run (command line)

```bash
# retrieval + dedup only, don't render item blocks (quick smoke test):
python -m pipeline.main --group aml --dry-run

# cap the number of items rendered per group (quick test):
python -m pipeline.main --group aml --max-items 3

# disable the recent/not-yet-indexed fresh scan (on by default):
python -m pipeline.main --group aml --no-fresh-scan

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

**Date range.** By default each group searches a rolling **30-day** window
back from today. Use `--start-date`/`--end-date` (YYYY-MM-DD,
by publication date) to search a fixed range instead — this applies to every
selected group and overrides the per-group windows. `--start-date` alone runs
from that date to today; `--window-days N` sets a custom rolling length.

**Recent, not-yet-indexed papers (fresh scan).** NLM adds MeSH terms and
publication types weeks-to-months after a paper appears, so the strict,
MeSH-verified query misses the newest papers — often the most important ones.
On by default, a supplementary scan of the approved journals (matched by
journal + date + disease name, no MeSH/pub-type gate) catches these and writes
them to **separate files** so they never mix with the strict digest:
`YYYY-MM-DD_recent_tier1.{md,pdf}` (core clinical journals — high signal) and
`YYYY-MM-DD_recent_tier2.{md,pdf}` (broader set — noisier). They are shown as
identification info + abstract, and the study type is inferred from wording,
not verified.

Because un-indexed papers have no publication-type tags, the fresh scan
restricts to **phase II/III trials and guidelines** by title/abstract wording
(e.g. "phase 3", "randomized", "guideline") — this is the default and cuts most
non-trial noise. Pass `--recent-all` (or untick the GUI sub-option) to include
every recent paper instead. Either way, **case reports/series and
preclinical/animal studies are filtered out** (by publication type + title).
Disable the whole scan with `--no-fresh-scan`.

Active group keys — hematologic: `aml`, `mds`, `mpn`, `cll`, `dlbcl`,
`follicular_lymphoma`, `mantle_cell_lymphoma`, `marginal_zone_lymphoma`,
`hodgkin`, `multiple_myeloma`, `all`, `cml`, `aplastic_anemia`, `chip`,
`sickle_cell`; solid tumor: `head_neck`, `breast`, `lung`, `pancreatic`,
`gastric`, `liver`, `colorectal`, `melanoma`, `prostate`, `sarcomas`,
`thyroid`.

Note: a full default run queries all 26 groups (plus their fresh scans), so it
makes a lot of PubMed calls and can take a while. Use `--dry-run` first to see
item counts, or run a single group at a time.

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
`--ignore-seen` to reprocess every retrieved item and rewrite that window's
digest.

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

## Building the standalone apps

One entry point (`app.py`) serves both the GUI and, via `--pipeline`, a cycle;
`Hildegard.spec` packages it with PyInstaller.

- **Locally (your platform):**
  ```bash
  pip install -r requirements-build.txt
  pyinstaller --noconfirm --clean Hildegard.spec
  # -> dist/Hildegard.app (macOS)  or  dist/Hildegard/Hildegard.exe (Windows)
  ```
  To hand someone the macOS app, zip `dist/Hildegard.app`.
- **Both platforms via CI (recommended for Windows):** the
  `.github/workflows/build.yml` workflow builds the macOS app and the Windows
  `.exe` on GitHub's runners. Trigger it from the **Actions** tab (Run
  workflow), or push a tag like `v1.0` to also publish both as **Release**
  assets. This is how you produce a Windows build without a Windows machine.

`build/` and `dist/` are git-ignored; the apps are distributed via Releases,
not committed (they're ~80–150 MB each).

## Icon

The app/window icon (`assets/`) is a detail of *The Unicorn Rests in a Garden*
(a.k.a. *The Unicorn in Captivity*) from the Unicorn Tapestries, ca. 1495–1505,
The Metropolitan Museum of Art — public domain (Met Open Access).
