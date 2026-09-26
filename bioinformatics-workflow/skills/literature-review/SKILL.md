---
name: literature-review
description: Runs a literature check via BioMCP (PubMed/PubTator3) for a specific biological question, mechanism, or methods uncertainty. Use whenever a biological interpretation, mechanism claim, or best-practice methods choice is not highly confident, before finalizing that claim in an analysis writeup.
---

# Literature review

A narrow, single-question literature check. For open-ended "is there prior work
on X" surveys, use the `lit-scout` agent instead.

## 1. Pin down the question

The input must be a bounded, answerable question — not "check the literature."

| Too broad | Bounded |
|---|---|
| "Check the literature on TP53" | "Is TP53 loss associated with increased cfDNA fragment-length heterogeneity in solid tumors?" |
| "Is our normalization OK?" | "Is TMM or median-of-ratios preferred for bulk RNA-seq with > 30% of genes differentially expressed?" |
| "What does this methylation mean?" | "Is promoter hypermethylation of MLH1 associated with MSI-H status in colorectal cancer?" |

If the caller's question is broad, narrow it to the claim that is actually
about to be written, and state the narrowed version.

Before searching, read `analysis_checkpoint.json` → `literature_reviews`. If an
existing review already answers this question, return its synthesis and
confidence and stop — do not re-search.

## 2. Search

Use the BioMCP MCP tools (server `biomcp`):

- **PubMed / PubTator3 article search** — the default. Search by gene,
  disease, variant, and keyword entities. Run 2–4 queries that approach the
  question from different angles (e.g. gene + phenotype; mechanism term +
  cancer type; method name + benchmark).
- **Variant databases** — when the question concerns a specific variant's
  frequency, pathogenicity, or annotation.
- **ClinicalTrials.gov** — only when the question concerns clinical use,
  trial evidence, or a therapeutic association.

Fetch full details/abstracts for the papers that look directly relevant.
Prefer primary studies with sample sizes and effect sizes, recent reviews, and
benchmarking papers for methods questions.

If the BioMCP server is unavailable, say so and stop; do not substitute
unsourced recall for a search.

## 3. Write the review file

Determine the current stage number `N` from the checkpoint's `current_stage`
(use `0` during planning). Write
`stages/stage_0N_litreview_<topic>.md`, where `<topic>` is a short snake_case
slug:

```markdown
# Literature review: <topic>

**Stage:** N
**Question:** <the bounded question>
**Trigger:** <which claim/method choice prompted this>
**Date:** YYYY-MM-DD

## Queries run
| Source | Query | Hits reviewed |

## Key papers
| PMID | First author, year | Design / n | Finding relevant to the question |

## Synthesis
What the literature says about the question, with PMIDs inline. Note where
studies disagree and why (cohort, platform, cancer type).

## Confidence
**High / Moderate / Low / Unresolved** — one or two sentences on how well
this resolves the original uncertainty, and what it means for the claim
(state it plainly / state it with a specific caveat / don't make it).
```

## 4. Log it

Append to `literature_reviews` in `analysis_checkpoint.json` (use a JSON
serializer, not string edits):

```json
{
  "stage": N,
  "trigger_reason": "<the claim or method choice that prompted the check>",
  "file": "stages/stage_0N_litreview_<topic>.md",
  "date": "YYYY-MM-DD"
}
```

Update `last_updated`.

## 5. Return

Return to the calling context: the synthesis (a few sentences, PMIDs inline),
the confidence level, the file path, and a one-line recommendation for how
the pending claim should be worded. The caller finalizes the interpretation
and cites the review file in the stage's "Literature reviews consulted"
section.
