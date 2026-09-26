---
name: analysis-workflow
description: Staged, human-reviewed genomics analysis workflow for cancer omics data (RNA, methylation, fragmentomics, DNA). Use when the user describes a dataset and analysis goal and wants a full plan-through-writeup workflow, or when resuming an existing analysis project that has an analysis_checkpoint.json.
---

# Analysis workflow

A staged loop: plan → approve → execute one stage → review → approve → next
stage → … → final report. Every stage ends at a human review gate. State lives
on disk (`analysis_checkpoint.json`, `plan.md`, `stages/`) so any session can
resume without re-deriving anything.

Project layout (all paths relative to the analysis project root, i.e. the
current working directory):

```
analysis_checkpoint.json     # machine-readable state (schema in section 5)
plan.md                      # approved staged plan
stages/
  stage_01_<name>.md         # one result file per completed stage
  stage_0N_litreview_<topic>.md
  figures/                   # PNGs embedded in the stage files (where a stage has any)
reports/
  stage_0N_report.pdf        # cumulative PDF report, rebuilt after every stage
final_report.md              # written only after the last stage is approved
```

Hard rules that apply everywhere below:

- Never start a stage without explicit user approval.
- After every completed stage, always build the PDF report and link it to the
  user (section 3, steps 9 and 10). No stage is presented without it.
- Never silently deviate from `plan.md`. Deviations are minimal and logged.
- Never hand-write CDK. See section 7.1.
- Update `analysis_checkpoint.json` at every state change, not at the end.

---

## 1. Entry behavior

On invocation, check the working directory for `analysis_checkpoint.json`.

**If it exists — resume, don't re-plan:**

1. Read `analysis_checkpoint.json`.
2. Read `plan.md`.
3. Read the most recent stage file under `stages/` (the `file` of the highest
   `id` stage with status `complete`, or the in-progress stage's file if one
   exists).
4. Check `literature_reviews` so already-answered questions are not re-searched.
5. Give the user a short recap — no more than a few lines:
   - Current stage number and name, and its status
   - The last completed stage's one-line result (from its `summary`)
   - Any open `plan_deviation` or a pending plan modification
   - A link to the latest `reports/stage_0N_report.pdf` (rebuild it if missing)
6. Ask which of these they want: **continue** to the next stage as planned,
   **revise** the next stage before running it, or **redo** the last stage.
   Wait for the answer.

If `status` is `complete`, say so, point to `final_report.md`, and ask what
follow-up they want. Do not re-plan from scratch in any resume case.

**If it does not exist** — this is a new analysis. Go to section 2.

---

## 2. Planning phase

### 2.1 Gather inputs

Collect anything the user has not already given. Ask only for what is missing:

- **Modality**: RNA-seq, methylation (array or bisulfite/EM-seq), fragmentomics
  (cfDNA), or DNA (WGS/WES/panel, germline vs somatic)
- **Format**: FASTQ, BAM/CRAM, VCF, IDAT, count matrix, beta matrix, etc.
- **Sample size and design**: n per group, tumor/normal pairing, batches,
  covariates, replicates
- **Reference genome build**: GRCh37/hg19 vs GRCh38/hg38 (and annotation
  version, e.g. GENCODE release)
- **Data location**: S3 URIs if already staged
- **Analysis goal**: the question to answer, stated as specifically as the user
  can

### 2.2 Write `plan.md`

Decompose the analysis into stages. A stage is one unit of analysis that ends
at a natural point for human review — a place where the result could change
what happens next. Do not chunk arbitrarily by effort or time. Typical stage
boundaries: QC/filtering (a failed sample changes the design), primary
analysis (DE, DMR calling, variant calling), downstream analysis (enrichment,
signatures, integration).

For every stage, write these six fields:

| Field | Content |
|---|---|
| **Objective** | The question this stage answers. |
| **Inputs** | Exact files/data, with S3 URIs once known. Outputs of prior stages referenced by their S3 path. |
| **Method** | Specific enough to execute with no further clarification: tools and versions, parameters, statistical test, thresholds (e.g. "DESeq2 1.42, design `~ batch + condition`, Wald test, BH-adjusted padj < 0.05, apeglm LFC shrinkage, |log2FC| > 1"). Include the Batch job definition(s) it uses, with vCPU/memory/instance family sized for this workload (section 7.2). |
| **Decision points** | Result patterns that would change the next stage (e.g. "if PC1 separates by batch not condition, add batch correction before DE"). |
| **Success/QC criteria** | What "this stage worked" looks like, with numbers (e.g. "≥ 20M uniquely mapped reads per sample, mapping rate > 85%"). |
| **Why this is a stopping point** | What a human needs to see before approving the next stage. |

If a method choice depends on best practice you are not confident about (e.g.
which normalization suits a fragmentomics coverage profile), run the
`literature-review` skill on that specific question during planning and cite
it in the method.

### 2.3 Approval

Present the plan. Iterate until the user explicitly approves it. Silence or
"looks interesting" is not approval — ask.

On approval, create `analysis_checkpoint.json` (section 5) with:

- `status: "in_progress"`
- `current_stage: 1`
- every stage from `plan.md` listed with `status: "pending"`, `file` set to
  its planned `stages/stage_0N_<name>.md` path, and null/empty result fields
- `created` and `last_updated` set to the current ISO 8601 timestamp

Create the `stages/` directory.

---

## 3. Stage execution

For the stage at `current_stage`:

1. Set that stage's `status` to `"in_progress"` in the checkpoint.
2. **Execute exactly the method in `plan.md`.** Code, scripts, and Batch jobs
   are written/submitted from the main thread; long-running or parallel Batch
   work goes to the `pipeline-runner` agent (section 7).
3. **Deviations**: if the plan cannot be executed as written (missing data, a
   QC failure, a method that does not apply to the data as it actually is),
   make the smallest reasonable deviation that keeps the stage's objective
   intact. Record it in the stage file and in the stage's `plan_deviation`.
   If the deviation would change the objective, stop and ask instead.
4. **Literature grounding**: if a biological interpretation, mechanism claim,
   or methods choice needs literature support and you are not highly
   confident in it, invoke the `literature-review` skill with a bounded
   question before finalizing the interpretation. Check
   `literature_reviews` first — do not repeat a search already on record.
   A `PostToolUse` hook flags hedged, uncited claims in stage files as a
   backstop; do not rely on it as the primary trigger.
5. **Interpretation and stats**: route interpretation to
   `analysis-interpreter` and any non-trivial statistical claim to
   `stats-reviewer` before it goes into the stage file (section 6).
6. **Make figures where a visualization helps.** Most stages will have one —
   QC distributions, PCA/UMAP, volcano/MA plots, heatmaps, coverage or
   fragment-size profiles, enrichment plots. Some won't (a file-conversion or
   bookkeeping stage, a result that is one number or a small table); don't
   force a plot there, and omit the Figures section. Save each figure as a PNG
   (about 200 dpi, roughly 7 in wide) to `stages/figures/stage_0N_<what>.png`.
   Label axes with units, state n, mark thresholds used in the analysis, and use
   colorblind-safe colors. A figure must show data from this stage, not a
   decorative or schematic image.
7. **Write the stage file** `stages/stage_0N_<name>.md` with exactly these
   sections, in this order:

   ```markdown
   # Stage N: <name>

   ## What was run
   Commands/tools/parameters actually executed. Deviations from plan.md, if
   any, stated explicitly with the reason.

   ## Key results
   Plain statements with numbers attached. No hedging unless the hedge carries
   real information about uncertainty.

   ## Figures
   Only if the stage has figures; otherwise omit this section. Each embedded
   with `![caption](figures/stage_0N_<what>.png)` — the paths are relative to
   the stage file. The caption says what is plotted, n, and what to look at.

   ## QC / sanity checks
   | Check | Criterion | Result | Pass/Fail |

   ## Interpretation

   ## Recommendation
   One of: proceed as planned / modify stage N+1 because X / stop here because Y.

   ## Artifacts
   Full paths (S3 URIs and local paths) to every output.

   ## Literature reviews consulted
   File references to stages/stage_0N_litreview_*.md, or "None".
   ```

8. **Update the checkpoint**: set the stage `status: "complete"`,
   `completed_at`, `summary` (1–3 sentences), `plan_deviation` (or null),
   `batch_jobs` (section 7.3), top-level `last_updated`, advance
   `current_stage`, and set top-level `status: "awaiting_review"`.
9. **Build the PDF report** — always, after the checkpoint update:

   ```
   uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/build_report.py" --project-dir .
   ```

   It writes `reports/stage_0N_report.pdf` and prints its absolute path. The
   report is cumulative: a cover page (objective, data, per-stage summaries,
   deviations), then the full text and any figures of every completed stage so far,
   then the literature reviews consulted. Each stage starts on its own page
   under a banner (stage number, name, status, completion time, whether a plan
   deviation was logged), with a running header naming the stage and a PDF
   bookmark. Exit code 2 means the PDF was written but a referenced stage file
   or figure file is missing — fix it and rebuild. Do not present the stage until the script exits 0. If it fails
   outright, report the error and give the user the stage file instead; don't
   silently skip the report.
10. **Stop.** Present the stage summary (key results, QC, recommendation) and
    **link the PDF** as a clickable absolute path, e.g.
    `[stage_02_report.pdf](file:///abs/path/reports/stage_02_report.pdf)`,
    then wait for explicit approval. When the user approves, set `status` back
    to `"in_progress"` before starting the next stage.
11. **Plan modifications**: if the recommendation is to modify the next stage,
   propose the exact edit to `plan.md` (a diff or the rewritten stage block).
   Apply it only after the user approves that edit, then mark that stage
   `"revised"` in the checkpoint until it runs.

**Redo**: if the user asks to redo a stage, re-run it from its recorded S3
inputs, overwrite its stage file (and figures), and update its checkpoint entry.
Later stages that consumed its outputs revert to `"pending"`. Rebuild and link
the PDF as in steps 9–10.

---

## 4. Recursion

Repeat section 3 for each stage until the final stage is complete and approved.

---

## 5. `analysis_checkpoint.json`

Maintain at the project root. Exact schema:

```json
{
  "project_name": "string",
  "created": "ISO 8601 timestamp",
  "last_updated": "ISO 8601 timestamp",
  "status": "planning | in_progress | awaiting_review | complete",
  "objective": "one-line statement of the overall analysis goal",
  "data_description": "short inline description or pointer to a data notes file",
  "plan_file": "plan.md",
  "current_stage": 1,
  "stages": [
    {
      "id": 1,
      "name": "string",
      "status": "pending | in_progress | complete | revised",
      "file": "stages/stage_01_<name>.md",
      "completed_at": "ISO 8601 timestamp or null",
      "summary": "1-3 sentence result summary",
      "plan_deviation": "string or null",
      "batch_jobs": [
        {
          "job_id": "string",
          "job_definition": "string",
          "instance_type": "string",
          "wall_clock_seconds": 0,
          "estimated_cost_usd": 0.0
        }
      ]
    }
  ],
  "literature_reviews": [
    {
      "stage": 1,
      "trigger_reason": "string",
      "file": "stages/stage_0N_litreview_<topic>.md",
      "date": "ISO 8601 date"
    }
  ],
  "final_report": "final_report.md or null"
}
```

Rules:

- Write it with a real JSON serializer (e.g. `python3 -c 'import json …'` or
  `jq`), not by string-editing, and read it back after writing to confirm it
  parses.
- S3 input/output URIs for each stage live in `plan.md` (inputs) and the stage
  file's Artifacts section (outputs), so any stage can be re-run independently.
- `current_stage` points to the next stage to run; after the last stage it
  equals the number of stages + 1.

---

## 6. Model delegation

Default routing — not a mandatory hop. Skip delegation when the task is trivial
enough that the handoff costs more than it saves (e.g. a one-line summary of a
count table).

| Work | Handled by |
|---|---|
| Code, pipeline scripts, Batch job definitions/submission, orchestration, checkpoint updates | Main thread (intended to run on Sonnet) |
| Long-running / parallel Batch job submission and monitoring | `pipeline-runner` agent (Sonnet) |
| Results interpretation, hypothesis generation, statistical judgment calls | `analysis-interpreter` agent (Opus) |
| Second-pass review of statistical claims and models | `stats-reviewer` agent (Opus) |
| Turning already-decided content into stage/final writeup prose | `writeup-drafter` agent (Haiku) |
| Broad "is there prior work on X" searches | `lit-scout` agent (Sonnet) |
| Narrow single-question literature checks | `literature-review` skill |

`writeup-drafter` does not resolve ambiguity. If it hits a judgment call, it
returns the question; send that question to `analysis-interpreter`, then give
the answer back to `writeup-drafter`.

---

## 7. AWS Batch compute

All heavy compute runs on AWS Batch. S3 is the handoff layer between stages.

### 7.1 CDK authorship requirement

All infrastructure-as-code — Batch compute environments, job queues, job
definitions, IAM roles/policies, S3 buckets, VPC/subnet/security-group config,
ECR repositories, anything provisioned by CDK — must be authored through the
`aws-dev-toolkit` plugin's CDK skills/agents.

Before writing any CDK file:

1. Check that `aws-dev-toolkit` is installed and enabled (its skills/agents
   appear in the available skill/agent lists).
2. If it is enabled, use its skills for scaffolding and authoring. Give it the
   specs from 7.2.
3. If it is **not** enabled, stop. Tell the user:
   `/plugin install aws-dev-toolkit@david-plugins`
   Do not fall back to hand-writing CDK constructs.

A `PostToolUse` hook flags writes under `cdk/` and to `*-stack.ts` /
`*_stack.py` as a reminder of this rule. It cannot check which skill was used;
the rule is yours to follow.

### 7.2 Infrastructure spec (input to aws-dev-toolkit)

**Compute environment**: managed, **EC2 launch type, on-demand only**. No
Spot. No Fargate. `minvCpus: 0` so it scales to zero between stages. Allowed
instance families matched to the job definitions below.

**Job definitions** — one per pipeline stage type in this analysis, with the
container image pinned by digest or version tag. Nothing is pre-sized: during
planning, set each job definition's vCPU, memory, and instance family in that
stage's **Method** in `plan.md`, based on the tools, data volume, and genome
build of this analysis. Give the reason for the sizing (e.g. memory-bound vs.
compute-bound, index size, threads the tool actually uses). Resize only when
observed usage says so, and record the change as a `plan_deviation`.

**IAM**: job role with read on input prefixes and read/write on the project's
output prefix only.

**S3 layout**:

```
s3://<bucket>/<project_name>/
  raw/                        # immutable inputs
  stage_01_<name>/            # outputs of stage 1
  stage_02_<name>/
  ...
```

Every stage reads its inputs from S3 URIs recorded in `plan.md` and writes
outputs under its own `stage_0N_<name>/` prefix, listed in the stage file's
Artifacts section. No stage depends on local state from another stage.

### 7.3 Job submission and cost tracking

- Delegate submission and monitoring of long-running or array/parallel jobs
  to `pipeline-runner`, so the main thread is not blocked polling. Short
  single jobs can be submitted directly.
- For every job, record in the stage's `batch_jobs`: `job_id`,
  `job_definition`, `instance_type`, `wall_clock_seconds` (from
  `startedAt`/`stoppedAt` in `aws batch describe-jobs`), and
  `estimated_cost_usd`.
- `estimated_cost_usd` = on-demand hourly price for the instance type in the
  job's region × wall-clock hours. Get the price from the AWS Pricing API
  (`aws pricing get-products --service-code AmazonEC2 --region us-east-1` with
  filters for instanceType, location, operatingSystem=Linux, tenancy=Shared,
  capacitystatus=Used, preInstalledSw=NA) and note the price used. When
  several jobs share one instance, this per-job figure overstates cost; say so
  in the stage file rather than inventing an apportionment.
- `final_report.md` includes a cost rollup: per stage and total, from the
  `batch_jobs` arrays.

---

## 8. Final synthesis

After the final stage is approved, produce `final_report.md` (draft prose via
`writeup-drafter`; the hypothesis section via `analysis-interpreter`):

1. **Findings and hypotheses** — up front, numbers attached.
2. **Background** — the question and why it matters, briefly.
3. **Methods** — per stage, from `plan.md` plus recorded deviations.
4. **Results** — per stage, from the stage files.
5. **Discussion**
6. **Hypothesis generation** — the creativity exception in the
   `direct-and-grounded` output style applies here: breadth over terseness,
   multiple angles, speculative threads allowed. Label every hypothesis
   **supported / plausible / speculative**, and name the evidence or the
   experiment that would test it.
7. **Open questions and limitations** — sample size/power, batch structure,
   reference/annotation caveats, deviations from plan.
8. **Compute cost** — table of per-stage and total `estimated_cost_usd`, with
   instance types and the pricing source.
9. **Literature reviews** — list of `stages/stage_0N_litreview_*.md` files.

Then set `status: "complete"`, `final_report: "final_report.md"`, and
`last_updated` in the checkpoint.
