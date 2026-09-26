# bioinformatics-workflow

A Claude Code plugin for staged, human-reviewed cancer genomics analysis —
RNA-seq, methylation, fragmentomics, and DNA/variant calling — with compute on
AWS Batch and interpretation grounded in the literature through BioMCP.

## Required companion plugins

These two plugins are declared as dependencies in `plugin.json`, so installing
this plugin installs them automatically. They are **required**, not optional.
`code-simplifier` comes from `claude-plugins-official`. `aws-dev-toolkit` is
mirrored in this repo's marketplace (from
`aws-samples/sample-claude-code-plugins-for-startups`), so no extra marketplace
is needed.

> `aws-dev-toolkit` is deprecated upstream. The mirror tracks the upstream repo,
> so if AWS removes it, the dependency stops resolving and this plugin will not
> load.

- **aws-dev-toolkit** — all CDK infrastructure (Batch compute environments,
  job definitions, IAM, S3, VPC) must be authored through its skills. The
  workflow stops rather than hand-write CDK if it is missing.
- **code-simplifier** — runs a cleanup pass after every code write.

If either is disabled or missing (for example, its marketplace isn't available),
the hooks still fire and point to agents/commands that do not exist
in your session.

The PDF builder (`scripts/build_report.py`) also runs through `uv`, which
fetches `reportlab` and `matplotlib` for it on first use.

BioMCP runs through `uv` (`uv run --with biomcp-python biomcp run`), so `uv`
must be on your `PATH`. The hook scripts need `python3` (standard library only).

## Skills

### `analysis-workflow`

The core loop. Invoke it by describing a dataset and a goal ("I have 48 paired
tumor/normal RNA-seq FASTQs on GRCh38 and want DE between responders and
non-responders"), or with `/bioinformatics-workflow:analysis-workflow`.

1. **Plan** — collects modality, format, sample size, genome build, and goal;
   writes `plan.md` with staged objectives, inputs, methods, decision points,
   QC criteria, and the reason each stage is a review point. Nothing runs until
   you approve the plan.
2. **Execute one stage** — runs the method as written, logs any deviation,
   writes `stages/stage_0N_<name>.md`, updates the checkpoint, and **stops** for
   your review.
3. **PDF report after every stage** — always. Stages get figures wherever a
   visualization makes sense (not forced). A cumulative PDF
   (`reports/stage_0N_report.pdf`) is built and linked to you at every review
   stop: a cover page with per-stage summaries and deviations, then each
   completed stage on its own page under a banner (stage number, name, status,
   completion time), with a running header and PDF bookmarks, then the
   literature reviews consulted.
4. **Repeat** per stage. Changes to upcoming stages are proposed as edits to
   `plan.md` and need your approval.
5. **Final report** — `final_report.md`: findings first, then background →
   methods → results → discussion, a confidence-labeled hypothesis section
   (supported / plausible / speculative), limitations, and a compute cost rollup.

### `literature-review`

A narrow check of one bounded question via BioMCP (PubMed/PubTator3, plus
variant databases and ClinicalTrials.gov when relevant). Writes
`stages/stage_0N_litreview_<topic>.md` with the queries, PMIDs, a synthesis, and
a confidence level, and logs it in the checkpoint so it is not re-run. Used
automatically when a claim isn't highly confident; invoke it directly with
`/bioinformatics-workflow:literature-review <question>`.

## Checkpoint and resume

State lives in the project directory:

```
analysis_checkpoint.json   # status, current stage, per-stage summaries, deviations, Batch jobs, lit reviews
plan.md
stages/                    # stage_0N_<name>.md, litreview files, figures/
reports/                   # stage_0N_report.pdf, one per completed stage
final_report.md
```

Invoke `analysis-workflow` in a directory that has `analysis_checkpoint.json`
and it recaps where things stand and asks whether to continue, revise the next
stage, or redo the last one. It does not re-plan.

## Agents

| Agent | Model | Role |
|---|---|---|
| `analysis-interpreter` | Opus | Interpretation, statistical judgment calls, hypothesis generation |
| `stats-reviewer` | Opus | Second-pass check: multiple testing, power, effect size vs significance, test assumptions |
| `writeup-drafter` | Haiku | Formats decided content into stage files and the final report; escalates ambiguity |
| `lit-scout` | Sonnet | Broad "is there prior work on X" searches in an isolated context |
| `pipeline-runner` | Sonnet | AWS Batch submission, monitoring, and per-job cost reporting |

## AWS Batch cost model

- Managed compute environment, **EC2 launch type, on-demand only**. No Spot,
  no Fargate. Scales to zero between stages.
- One job definition per stage type. vCPU, memory, and instance family are not
  pre-set; each is sized for the specific analysis in `plan.md` during planning.
- S3 is the handoff between stages; every stage can be re-run from its
  recorded inputs.
- Each Batch job is logged with instance type, wall-clock time, and estimated
  cost (on-demand hourly price × hours, from the AWS Pricing API). The final
  report totals it per stage and overall. These are estimates: they exclude
  S3, data transfer, and EBS costs.

## Hooks

`PostToolUse` backstops on `Write`/`Edit`:

| Hook | Fires on | Effect |
|---|---|---|
| Literature check | `stages/*.md`, `final_report.md` | Flags hedged claims ("likely," "may," "unclear mechanism," …) with no PMID, DOI, or litreview reference in the same paragraph. Hypothesis/limitations sections are exempt. |
| Code simplifier | `.py .R .sh .ts .sql .js .tsx`, `cdk.json` | Always reminds to run `code-simplifier` / `/simplify`. |
| CDK authorship | paths with `cdk/`, `*-stack.ts`, `*_stack.py`, files inside a dir with `cdk.json` | Reminds that CDK must come from `aws-dev-toolkit`. |

The hooks add context to the conversation. They never block a write.

## Output style

`direct-and-grounded` is forced on while the plugin is enabled: results first,
numbers attached, no filler, every claim grounded, direct pushback. Hypothesis
generation is the exception, where breadth wins over brevity.

## Local testing

```
claude --plugin-dir ./bioinformatics-workflow
```

Check that both skills load and trigger, the output style applies, the `biomcp`
MCP server connects (`/mcp`), and each hook fires on a test write: a hedged
sentence in `stages/test.md`, any `.py`/`.ts` file, and a file under `cdk/`.
Don't publish to a marketplace until all of these pass.
