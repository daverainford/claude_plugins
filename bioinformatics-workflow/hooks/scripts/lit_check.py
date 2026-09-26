#!/usr/bin/env python3
"""Flag hedged claims with no nearby citation in stage writeups and final_report.md.

Backstop only: the primary trigger for literature-review is the model's own judgment.
"""
import os
import re

from _common import emit, file_path, read_event, written_text

HEDGE = re.compile(
    r"\b(likely|unlikely|may|might|could|possibly|possible|perhaps|presumably|"
    r"potentially|suggests?|appears? to|seems? to|putative(?:ly)?|"
    r"unclear mechanism|mechanism (?:is|remains) unclear|not well understood|"
    r"thought to|believed to|is associated with)\b",
    re.IGNORECASE,
)
CITATION = re.compile(
    r"PMID:?\s*\d+|doi\.org/|\b10\.\d{4,9}/\S+|"
    r"stage_\d+_litreview_\w+|litreview|"
    r"\[\d+(?:[,–-]\s*\d+)*\]|"
    r"\([A-Z][A-Za-z\-]+(?: et al\.?)?,? (?:19|20)\d{2}[a-z]?\)",
)
# Sections where hedging is expected and labeled by design.
EXEMPT_HEADING = re.compile(r"hypothes|open questions|limitations|speculat", re.IGNORECASE)


def is_target(path):
    norm = path.replace(os.sep, "/")
    if os.path.basename(norm) == "final_report.md":
        return True
    return norm.endswith(".md") and ("/stages/" in norm or norm.startswith("stages/"))


def paragraphs(text):
    """Yield (heading, paragraph) pairs; heading is the most recent markdown heading."""
    heading = ""
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        body = []
        for ln in lines:
            if ln.lstrip().startswith("#"):
                heading = ln
            else:
                body.append(ln)
        if body:
            yield heading, " ".join(ln.strip() for ln in body)


def main():
    event = read_event()
    path = file_path(event)
    if not is_target(path) or "litreview" in os.path.basename(path):
        return

    flagged = []
    for heading, para in paragraphs(written_text(event)):
        if EXEMPT_HEADING.search(heading) or CITATION.search(para):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", para):
            match = HEDGE.search(sentence)
            if match:
                flagged.append((match.group(0), sentence.strip()[:200]))
    if not flagged:
        return

    lines = "\n".join(f'- "{hedge}": {sentence}' for hedge, sentence in flagged[:5])
    more = f"\n(+{len(flagged) - 5} more)" if len(flagged) > 5 else ""
    emit(
        f"This claim looks unverified — confirm the literature was checked before finalizing.\n"
        f"File: {path}\nHedged statements with no adjacent citation or literature-review reference:\n"
        f"{lines}{more}\n"
        "Either cite the supporting PMID / stages/stage_0N_litreview_*.md file, run the "
        "literature-review skill on the specific claim, or state it plainly if the hedge carries "
        "no real uncertainty."
    )


if __name__ == "__main__":
    main()
