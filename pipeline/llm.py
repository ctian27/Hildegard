"""Per-item triage/extraction/appraisal via the Claude API.

The paired system prompt (heme_onc_literature_surveillance_prompt.md) is
used verbatim as the `system` field, per the build brief. Its OUTPUT FORMAT
section describes a full multi-item cycle digest, but this pipeline calls
the model once per NEW item (per the brief's "For each NEW item, call...").
To reconcile the two, the user turn adds a short framing note asking for
just this item's schema block plus a machine-parseable routing envelope;
the renderer (render.py) is responsible for assembling per-item blocks into
the full OUTPUT FORMAT digest afterward.
"""

import json
import re

import anthropic

from . import config

WRAPPER_INSTRUCTIONS = """\
You are being called as one step in an automated surveillance pipeline, \
processing a single retrieved record at a time (not a full cycle). Apply \
the ROLE, SOURCES, DISEASE GROUPS, INCLUSION/EXCLUSION CRITERIA, PER-GROUP \
OVERRIDES, VERIFICATION & ANTI-FABRICATION RULES, EXTRACTION SCHEMA, and \
APPRAISAL FLAGS sections of your system prompt to the single record below. \
Do NOT produce the full multi-item OUTPUT FORMAT digest -- the pipeline \
assembles per-item output into that digest separately.

Disease group for this record (already matched by the retrieval layer): {disease_group}
Source type: {source_type}

Respond with ONLY a single JSON object (no prose, no markdown code fence) \
with exactly these keys:
{{
  "decision": one of "include", "exclude", "needs_review", "flagged_retraction",
  "exclude_or_review_reason": string or null (required if decision is not "include"),
  "record_type": one of "trial", "guideline", null,
  "override_applied": string or null (name the PER-GROUP OVERRIDE that let this item in, if any, else null),
  "appraisal_flags": array of strings (from the APPRAISAL FLAGS section; empty array if none apply),
  "markdown_block": string or null (the item formatted per the EXTRACTION SCHEMA \
for its record_type, in Markdown; required if decision is "include" or "flagged_retraction"; \
must include the PMID/DOI/NCT identifier verbatim; use "not reported" for any absent field \
per the anti-fabrication rules; null if decision is "exclude")
}}

Retrieved record:
{record_json}
"""

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def load_system_prompt(path: str = config.SYSTEM_PROMPT_PATH) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_user_content(disease_group: str, source_type: str, record: dict) -> str:
    return WRAPPER_INSTRUCTIONS.format(
        disease_group=disease_group,
        source_type=source_type,
        record_json=json.dumps(record, indent=2, default=str),
    )


def _strip_fence(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text.strip()).strip()


def parse_response(raw_text: str) -> dict:
    cleaned = _strip_fence(raw_text)
    return json.loads(cleaned)


def _has_identifier(markdown_block: str | None, identifiers: dict) -> bool:
    if not markdown_block:
        return False
    for key in ("pmid", "doi", "nct"):
        val = identifiers.get(key)
        if val and str(val) in markdown_block:
            return True
    return False


def process_item(client: anthropic.Anthropic, system_prompt: str, disease_group: str,
                  source_type: str, record: dict, identifiers: dict,
                  model: str = config.ANTHROPIC_MODEL,
                  max_tokens: int = config.ANTHROPIC_MAX_TOKENS) -> dict:
    """Returns a dict with keys: status, decision, record_type, appraisal_flags,
    override_applied, markdown_block, raw_model_text, error.
    `status` is the value stored in items.status and is what downstream
    hard-rule enforcement decides, NOT just what the model claims.
    """
    user_content = build_user_content(disease_group, source_type, record)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        truncated = response.stop_reason == "max_tokens"
    except Exception as e:  # network/API errors -> needs human review, never silently dropped
        return {
            "status": "needs_review", "decision": None, "record_type": None,
            "appraisal_flags": [], "override_applied": None, "markdown_block": None,
            "raw_model_text": None, "error": f"API call failed: {e}",
        }

    try:
        parsed = parse_response(raw_text)
    except json.JSONDecodeError as e:
        note = "Response truncated at max_tokens before valid JSON completed" if truncated else f"Unparseable model output: {e}"
        return {
            "status": "needs_review", "decision": None, "record_type": None,
            "appraisal_flags": [], "override_applied": None, "markdown_block": None,
            "raw_model_text": raw_text, "error": note,
        }

    decision = parsed.get("decision")
    markdown_block = parsed.get("markdown_block")

    # Hard rule (system prompt VERIFICATION & ANTI-FABRICATION RULES #1),
    # enforced downstream, not just trusted from the model: no identifier in
    # the rendered block -> do not surface as included/flagged.
    if decision in ("include", "flagged_retraction"):
        if not _has_identifier(markdown_block, identifiers):
            return {
                "status": "needs_review", "decision": decision, "record_type": parsed.get("record_type"),
                "appraisal_flags": parsed.get("appraisal_flags", []),
                "override_applied": parsed.get("override_applied"),
                "markdown_block": markdown_block, "raw_model_text": raw_text,
                "error": "Rejected by hard rule: no verifiable PMID/DOI/NCT found in markdown_block",
            }
        status = "flagged_retraction" if decision == "flagged_retraction" else "included"
    elif decision == "exclude":
        status = "excluded"
    else:
        status = "needs_review"

    return {
        "status": status,
        "decision": decision,
        "record_type": parsed.get("record_type"),
        "appraisal_flags": parsed.get("appraisal_flags", []),
        "override_applied": parsed.get("override_applied"),
        "markdown_block": markdown_block,
        "raw_model_text": raw_text,
        "error": parsed.get("exclude_or_review_reason"),
    }
