# Adaptive summary content repair plan

> Root owns product prompt edits and real model calls. The acceptance worker owns only the new phase runner/tests; a separate reviewer checks the change. Existing phases remain closed.

**Goal:** Reduce detailed repetition between summary and points, retain important complementary capabilities, and prevent unsupported source-genre guesses.

**Execution status:** Two prompt revisions and both bounded acceptance phases are complete. Work-group budget is exhausted at26/26; short regression passed, medium quality did not. This plan has no pending model calls and does not declare all quality defects fixed.

**Spec:** [Current handoff](../../handoff-2026-10-09-adaptive.md), the two preserved failed outputs and their existing essential/precision/organization rubric.

**Architecture:** Update only the shared legacy request guidance in llm_service.py. Preserve public JSON fields, adaptive budgets, source text, parsing and call counts. Do not delete generated content programmatically or introduce a facts pipeline or another paid stage.

## Constraints and review focus

- Source fidelity, conditions, quantities, scope, attribution and final conclusions must survive. A useful high-level overview may share subject names with details; it must not copy their full inventory.
- Keep relevant parallel/complementary capabilities together, without injecting sample answers into prompts or demanding all incidental detail.
- Reuse recorded semantic failures as red evidence. Stub responses cannot prove semantic repair; do not create prose-change detectors as quality tests.
- Run existing relevant LLM/adaptive regressions after this actual prompt change. New runner guards use meaningful offline red/green tests against temp files and mock transport.
- Preserve all prior scripts/results/provenance/budget bytes and user work/env/db/accounts. yt-dlp and LLM access remain in their sole service layers, narrow interfaces and scene-read-only boundaries hold. UI changes would require ui-ux-pro-max/design-system and three-layer tokens; none are in scope here.
- Same work_id/hard26. Pre-repair22 + firstrepair2 + final2 =26, all phasesclosed; no remaining calls. Root single caller, same lock, durable pre-reservation, error stops each phase, no retry/fallback, budget reset or old-phase reopen.

## Tasks

1. [x] Trace both failures through source, outbound request, raw response and parser. The source was complete; token termination was normal; generation guidance omitted field-role and complementary-capability rules.
2. [x] Root updated only the common summary guidance; 91 existing relevant regressions passed, and independent product review found no new Critical/Important/Minor issues. Mechanical success is not semantic success.
3. [x] Worker created the one-shot runner and 19 meaningful offline guard tests. Observed reservation/drift/index/interruption and review-driven initialization/evidence-binding reds were fixed. Separate freeze/ledger/tracker and immutable snapshots are implemented.
4. [x] Independently reviewed, froze and offline checked the first repair before its POSTs.
5. [x] Root ran both samples, verified snapshots/raws and closed at24. Independent content review found partial improvement, but remaining duplicate/qualifier/granularity failures; original standard retained.
6. [x] Updated current implementation docs/AGENTS/handoff with actual26/26 and152726 tokens, short pass, medium failures and revised long-source quality not tested. Current candidate remains uncommitted/undeployed; historical artifacts preserved.
7. [x] Final targeted guidance,91 mechanical regressions,7 final tool tests/review, freeze/check and two serial POSTs completed. Snapshot/raw verification passed; short pass, medium3full/1partial plus repetition/attribution weakness; hard26 reached and real calls stopped.

## Validation limits

The saved semantic failures predate this change and are the regression red, without re-calling the old candidate. Local regression success proves mechanics, not model content. A two-sample real result does not certify other sources or the new prompt's long-source quality; prior long-content review applies to its frozen old prompt.

The first repair's new raw failures provide the evidence for task7: conditions/frequency were weakened in the detailed overview, and an overall label replaced per-event assessment. The final change guides overview abstraction and complete qualified point details without adding stages, IDs, fixed lengths or sample answers. Platform Agent credits recovering do not reset the finite project budget.
