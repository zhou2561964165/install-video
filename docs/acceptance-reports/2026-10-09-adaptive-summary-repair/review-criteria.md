# Adaptive repair review criteria

Use the original [rubric](../2026-10-09-summary-quality-repaired/rubric.json), [short/medium clause review](../2026-10-09-summary-quality-repaired/short-medium-semantic-review.md), [latest failed candidate review](../2026-10-09-adaptive-short-medium/report.md) and original [corpus manifest](../2026-10-04-natural-subtitle-quality/corpus/manifest.json). This is a known-sample regression, not a holdout.

## Coverage and precision

- zh1–zh4: preserve MIT Chinese course, second-day all-Chinese instruction and first-day preparation/syllabus/expectations; understandable classroom language and preparation/practice alignment with the unprepared→English consequence; fixed classroom phrases and the repeat-once example within that teaching scope; actual lack of understanding/need for English, first45/last5 minutes, after-class and email channels, and classroom atmosphere purpose.
- en1–en4: preserve daily/per-class assessment and instructor-attributed persistent-effort expectation; usually after-class, each student's language/cultural behavior, subsequent improvement and usually written feedback; Engrade grade entry plus private comments and the student's own account; performance-dependent pronunciation/compliment examples, attributed cultural illustration and possible replies, L1 condition, encouragement/feedback, covered textbook/course material and improvement purpose.
- Every necessary clause must be full for an essential to be full; omissions remain partial or missing. Optional details can be omitted, but included details must be accurate. Do not require the source-absent beginner label or promote cultural examples to universal rules.
- Unsupported source-genre labels are precision defects. Do not rewrite the source, inject fixed answers into prompts or change the rubric to turn previous failures into passes.

## Organization

Apply the original definition: the same proposition with no new relevant condition, consequence, example or scope is duplicate. A useful higher-level overview can share topic names with detailed points; that alone is not a duplicate. Copying a full list of operational rules in both fields, or a parent point that merely repeats following points, fails organization.

Preserve complementary capabilities and important conditions across the final summary/points, without a fixed point/character target, automatic text deletion or judging semantic success by IDs/HTTP200/JSON compliance. Shorter output is not automatically better. Check all output assertions against the source lines.

## Resources and engineering

This phase has maximum2 POSTs, prior22/hard26, no paid repair stage or retry; root is the only serial caller. UI would require ui-ux-pro-max/design-system and three-layer tokens; keep configurable narrow interfaces, sole yt-dlp/LLM service layers, scene read-only, and protected env/db/accounts/old evidence. Existing saved failure outputs are the red evidence; mechanical offline tests cannot replace actual content review. No claims about the revised prompt's real long-source quality are made from these two samples.
