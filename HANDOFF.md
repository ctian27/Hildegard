# Hildegard — Handoff for a future Claude Code session

Last updated during a **post-v1.2 maintenance session (2026-07-08)**, on top of
v1.2 (commit `e0336e1`). Read this first; it captures non-obvious context that
isn't derivable from the code alone.

**This maintenance session's changes — all shipped as release `v1.2.1`:**
- **`digests/` untracked + git-ignored** (commit `5e67ecd`) — per-user output,
  not for the public repo. Files stay on disk; only removed from git.
- **Source-journals reference added** (commit `89ffc84`) — new
  `pipeline/journals_reference.py` generates `Hildegard-Journals.{md,pdf}` (a
  tiered list of every searched journal) from `config.py`; regenerate with
  `python -m pipeline.journals_reference`. Page-breaks per tier so each table
  renders full-size (avoids xhtml2pdf keep-in-frame shrink).
- **Dry-run feature fully removed** (commit `184ef12`). See §3.
- **App bundle version bumped** to `1.2.1` in `Hildegard.spec`
  (`CFBundleShortVersionString`, was stuck at `1.0`; commit `6e1aef7`).
- **CI actions bumped to Node 24 majors** (commit `50ad3d8`) — checkout v4→v7,
  setup-python v5→v6, upload-artifact v4→v7, action-gh-release v2→v3; clears the
  Node 20 deprecation warning. Verified via a `workflow_dispatch` run (both
  jobs green, no deprecation annotations).
- **Released `v1.2.1`** — tag pushed, CI built + attached
  `Hildegard-macOS.zip` + `Hildegard-Windows.zip` to the GitHub Release.

## 1. What this project is

**Hildegard** is a literature-surveillance tool for a hematology/oncology
physician (the user, `changtai.tian1@gmail.com`). It queries PubMed for
recently published, practice-relevant papers (phase II/III trials + guidelines)
across 26 heme/onc disease groups, dedups across runs, and emits a
disease-grouped **Markdown + PDF digest** of each paper's identification info
(title / journal / date / PMID / DOI) plus its **verbatim abstract**.

It is a **retrieval/triage aid only** — as of v1.2 it does **not** interpret,
summarize, or appraise papers (the AI layer was removed; see §3). Named after
Hildegard of Bingen (medieval physician/compiler of medical knowledge); icon is
*The Unicorn in Captivity* tapestry (public domain, The Met).

- **Repo:** https://github.com/ctian27/Hildegard — **PUBLIC** (as of this
  handoff). Owner/account: `ctian27`. `gh` CLI is installed and authenticated.
- **Local path:** `/Users/ctian/Hildegard` (was `~/Documents/Hildegard` — moved
  out of Documents; see §5 macOS TCC).
- **Releases:** `v1.0`, `v1.1`, `v1.2` tags, each with `Hildegard-macOS.zip` +
  `Hildegard-Windows.zip` built by CI. v1.2 is current.

## 2. How it runs (three ways)

Data flow: `retrieve (pubmed) → dedup → retraction recheck → render (md+pdf)`.

- **From source, CLI:** `python -m pipeline.main --group aml [...]`
- **From source, GUI:** `python -m pipeline.gui`, or double-click
  `Run Hildegard.command` (macOS) / `Run Hildegard.bat` (Windows). These
  launchers self-bootstrap a `.venv` and deps on first run.
- **Standalone app (no Python):** `dist/Hildegard.app` (macOS) /
  `dist/Hildegard/Hildegard.exe` (Windows), built by PyInstaller from `app.py`.
  Entry point `app.py` dispatches: `--pipeline <args>` runs a cycle, otherwise
  launches the GUI. The GUI shells out to the same executable with `--pipeline`.

**Output location (`DATA_HOME` in config.py):** project root when run from
source; **`~/Hildegard`** when frozen (visible, avoids macOS Documents
prompts). Override with env `HILDEGARD_HOME`. Digests go to
`<DATA_HOME>/digests/`, SQLite DB to `<DATA_HOME>/data/surveillance.db`.

## 3. Key decisions & rationale (the "why")

- **PubMed only; ClinicalTrials.gov removed.** User wanted published papers
  only. `pipeline/retrieval/ctgov.py` was deleted (early on). `ctgov_condition`
  remains as vestigial per-group metadata in config.
- **Dry-run mode removed (post-v1.2 maintenance).** The `--dry-run` flag / GUI
  checkbox was vestigial once the AI layer was gone — its label still said "no
  Claude calls, free," but there are no Claude calls anymore, so it only meant
  "retrieve+dedup, skip rendering." Removed entirely: the GUI checkbox +
  `dry_run_var`, the `build_command` `dry_run` param, the `--dry-run` argparse
  flag, the `run_group` `dry_run` param, and its four branches (item stub,
  retraction-recheck gate, fresh-scan gate). Retraction recheck + fresh scan now
  always run (they always did in real runs). README de-referenced too.
- **AI/LLM layer removed (v1.2).** User found Claude summaries uneven in quality
  and the `anthropic`→`pydantic`/`pydantic_core` dependency caused install
  complexity + the arm64/x86_64 crash (see §5). Removal was low-risk because an
  abstract-only path already existed and was proven. Now abstract-only is the
  **only** mode. `pipeline/llm.py` was **deleted**. No API key needed anywhere.
- **All 26 disease groups active.** 15 hematologic (journals =
  `AML_JOURNALS` = Tier 1 + Tier 2-Hematology) + 11 solid tumor (journals =
  `ONCOLOGY_JOURNALS` = Tier 1 + Tier 2-Oncology). **Every MeSH heading was
  verified live** via `esearch db=mesh`, and **every journal `[Journal]` filter
  term + ISSN was resolved live** against PubMed — do NOT trust raw journal
  names (e.g. "New England Journal of Medicine" returns 0 hits; must use
  `N Engl J Med`). See the verified `Journal(...)` entries in `config.py`.
- **30-day default window for all groups (v1.2).** Was 14 (CHIP 30). Changed
  `DiseaseGroup.window_days` default → 30 and AML's explicit 14 → 30.
- **Fresh scan for not-yet-indexed papers (v1.1).** THE key clinical insight:
  NLM assigns MeSH terms + publication types weeks-to-months after publication,
  so the strict `[Publication Type]`+`[MeSH]` query silently misses the newest
  (often most important) papers — proven with NEJM PMID `42223072`
  (`10.1056/NEJMoa2605555`, pancreatic, status `Publisher`, no MeSH/pub-types).
  Fresh scan (`pubmed.build_fresh_term`) drops the MeSH/pub-type/humans gate,
  matches disease by MeSH **or** title/abstract text, restricted to the approved
  journals. Results go to **separate files** `<date>_recent_tier1.{md,pdf}` and
  `<date>_recent_tier2.{md,pdf}` (Tier 1 and Tier 2 scanned separately → clean
  vs noisy), never mixed with the strict digest. Defaults to **phase II/III +
  guideline** wording (`TRIAL_GUIDELINE_TIAB`), and **excludes case
  reports/series + preclinical/animal** by pub-type + title
  (`fresh_exclusion_reason`). Toggle: `--recent-all` (broad), `--no-fresh-scan`
  (off).
- **429 retry/backoff** (`pubmed._get`) — the fresh scan ~triples PubMed calls;
  without an NCBI key the limit is ~3/s, so a 429 would crash a run.
- **Standalone apps via GitHub Actions** — user wanted single-click, no-Python
  distribution, incl. Windows without a Windows machine. `.github/workflows/
  build.yml` builds both on `v*` tags and publishes to a Release.
- **GUI defaults:** nothing checked by default (was AML). Groups split into
  Hematologic / Solid tumor subsections.

## 4. Files (all under `/Users/ctian/Hildegard`)

**Pipeline (source of truth):**
- `pipeline/config.py` — disease groups, journal sets + verified ISSNs, per-group
  overrides (CHIP, sickle cell), `DATA_HOME`/`BUNDLE_DIR`/frozen-path logic,
  `window_days` default (30). No more `ANTHROPIC_*`/`SYSTEM_PROMPT_PATH`.
- `pipeline/retrieval/pubmed.py` — E-utilities esearch/efetch; `build_pubmed_term`
  (strict), `build_fresh_term` (fresh), `TRIAL_GUIDELINE_TIAB`,
  `NON_PRIMARY_PUB_TYPES`, `fresh_exclusion_reason`, `_get` (retry/backoff),
  retraction/EoC parsing.
- `pipeline/dedup.py` — dedup by PMID/DOI against `seen_ids`.
- `pipeline/db.py` — SQLite (tables: cycles, items, seen_ids; raw payloads kept).
- `pipeline/render.py` — Markdown digest + `render_recent_digest` + PDF
  (`markdown` → HTML → `xhtml2pdf`); `write_outputs`, `update_index`,
  `pubmed_record_to_markdown` (the abstract block).
- `pipeline/main.py` — orchestrator + argparse + `_run_fresh_scan` +
  `_abstract_only_output` + `resolve_window`. `main(argv=None)`. No `dry_run`
  anymore (removed post-v1.2; see §3).
- `pipeline/gui.py` — Tkinter GUI; `build_command` (pure, testable),
  `default_window_note`. No AI checkbox / API-key field, and no dry-run checkbox.
- `pipeline/journals_reference.py` — generates the tiered source-journals
  reference doc (`Hildegard-Journals.{md,pdf}`) from `config.py`, reusing
  `render.markdown_to_pdf`. Run: `python -m pipeline.journals_reference`.
- `pipeline/retrieval/ctgov.py` — **deleted**. `pipeline/llm.py` — **deleted**.

**Packaging / launchers:**
- `app.py` — frozen entry point (dispatch on `--pipeline`).
- `Hildegard.spec` — PyInstaller spec (bundles icon; NOT anthropic anymore).
- `Run Hildegard.command` (macOS, LF), `Run Hildegard.bat` (Windows, CRLF) —
  self-bootstrapping launchers; force `arch -arm64` on Apple Silicon.
- `Hildegard.app/` — a **launcher-style** `.app` (runs from source; needs
  Python). Distinct from the PyInstaller `dist/Hildegard.app` (standalone).
- `.github/workflows/build.yml` — CI build on `v*` tags + `workflow_dispatch`.
- `requirements.txt` (requests, python-dotenv, markdown, xhtml2pdf — NO
  anthropic), `requirements-build.txt` (+ pyinstaller, pillow).
- `assets/` — `hildegard_icon.png` (GUI), `hildegard.icns` (mac app),
  `hildegard.ico` (win), `hildegard_source.jpg` (source crop).

**Docs / reference:**
- `README.md` — user-facing docs (kept current; de-AI'd in v1.2).
- `heme_onc_literature_surveillance_prompt.md` — the ORIGINAL LLM system prompt,
  now retained ONLY as the **clinical criteria reference** (inclusion/exclusion,
  disease groups, journal tiers). Has a header note that AI behavior no longer
  runs. `_2.md` is a later revision of it.
- `pipeline_build_brief.txt` — original build spec.
- `.env.example` — optional; only `NCBI_API_KEY` matters now.

**Git-ignored (not in repo):** `.env` (may hold `NCBI_API_KEY`), `.venv/`,
`dist/`, `build/`, `data/*.db`, `gui_error.log`, `*.rtf`, personal folders.

## 5. Active constraints / gotchas

- **macOS Terminal runs under Rosetta (x86_64) on this M2 machine.** The
  framework Python is universal2; launched under Rosetta it starts x86_64 and
  can't load arm64 wheels. The launchers force `arch -arm64`; `arch -arm64
  .venv/bin/python` is how commands were run this whole session. Keep doing that
  for source runs, or the user should uncheck "Open using Rosetta" on Terminal.
- **Do NOT put the project back in `~/Documents`/`~/Desktop`/`~/Downloads`** —
  macOS TCC blocks a double-clicked app from reading those; that's why it lives
  at `~/Hildegard`.
- **Python is 3.14** locally; CI uses **3.12**. Code uses `X | None` hints
  (3.10+). Keep compatible with both.
- **PubMed journal filter:** always resolve names to the exact `[Journal]` term
  + ISSN via live esearch before adding a journal. Verify MeSH via `db=mesh`.
- **NCBI key optional** (`NCBI_API_KEY`) — raises rate limit; `_get` retries on
  429 either way.
- **Unsigned apps:** first launch needs right-click→Open (macOS) / More
  info→Run anyway (Windows). Signing needs paid dev accounts (not done).
- **CI macOS build is arm64** (macos-latest) — Intel Mac users must run from
  source. Windows build is x64.
- **Only commit/push when asked.** Every commit this session ended with the
  `Co-Authored-By: Claude Opus 4.8` trailer. Before staging, always confirm
  `.env`, `dist/`, `build/`, and the personal `Literature Updates/` folder are
  NOT included (they never were).
- **Known limitation (documented, not fixed):** a fresh-scan paper marked
  `seen` won't later re-surface in the strict digest once indexed; and the fresh
  scan only helps within the searched window.

## 6. How to make a new release

```bash
cd /Users/ctian/Hildegard
# ... make + commit changes ...
git push origin main
git tag -a v1.3 -m "..." && git push origin v1.3     # triggers CI build + Release
gh run watch <id> --exit-status                       # both jobs should pass
gh release view v1.3 --json assets                    # confirm 2 zips attached
```
To rebuild the local app: `arch -arm64 .venv/bin/pyinstaller --noconfirm --clean Hildegard.spec`.
Note: `git push` may need `git config http.postBuffer 524288000` (binary assets).

## 7. Verification steps (how each change was checked)

- **MeSH/journals:** live `esearch` (`db=mesh` for headings; `db=pubmed` +
  `esummary` for `[Journal]`/ISSN). All 26 groups' headings + full journal sets
  verified this way.
- **Fresh scan:** reproduced the miss — strict query over a window incl.
  2026-05-31 does NOT return NEJM PMID 42223072; fresh scan DOES. Re-run after
  every fresh-scan change to confirm it still catches it and lands in
  `recent_tier1`.
- **Exclusions:** unit-tested `fresh_exclusion_reason` on synthetic titles
  (case report / mouse model / in vitro excluded; real trials pass).
- **Standalone app:** run `dist/Hildegard.app/Contents/MacOS/Hildegard
  --pipeline --group aml --format both` with a scratch `HILDEGARD_HOME` — must
  produce cycle + recent_tier1/2 in md+pdf with NO external Python. GUI launch:
  brief background launch confirms Tkinter is bundled and the window opens.
- **No AI deps:** `python -c "import pipeline.main, sys; assert 'anthropic' not
  in sys.modules and 'pydantic' not in sys.modules"`.
- **GUI:** build headless with `tk.Tk(); root.withdraw(); PipelineGUI(root);
  root.update_idletasks()` and assert on `group_vars` / widgets (never blocks on
  mainloop).
- Use a **scratch DB + digests dir** for tests
  (`--db-path`/`--digests-dir`) so the user's real `~/Hildegard` data isn't
  touched; abstract-only runs are free (no API cost).

## 8. Possible next steps (raised, not done)

- Re-surface fresh-scan papers for the strict digest once they get indexed.
- Society-guideline page scraping (NCCN/ASCO/ASH/ESMO); Europe PMC full text;
  scheduling (cron/Actions). Solid-tumor `ctgov_condition` strings were never
  verified (CT.gov is gone, so moot unless registry retrieval returns).
