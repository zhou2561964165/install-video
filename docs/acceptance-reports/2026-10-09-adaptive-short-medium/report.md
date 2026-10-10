# Adaptive short and medium transcript verification

## Scope and execution

This phase tested the default `legacy/adaptive` path on the known-issue Chinese short sample and an English medium sample. It was a regression check on two previously reviewed MIT OCW samples, not a holdout or statistical quality study.

| Item | Result |
|---|---|
| Frozen samples | `zh-short` 608 cleaned characters; `en-medium` 2,199 cleaned characters |
| Model/config | deepseek / deepseek-flash; `legacy`, `adaptive`, zh-CN output |
| Requests | 2 total, one per sample; both HTTP 200 and `finish_reason=stop` |
| Budget | Prior 20 + this phase 2 = **22/26 POSTs**; remaining 4 unallocated |
| Provider usage | This phase 2,605 tokens (1,864 prompt, 741 completion; 384 cached); work-group cumulative 147,217 tokens |
| Evidence | Independent phase freeze, pre-run offline `--check`, two durable pre-reservations, closed tracker, and post-run `--verify` all recorded |
| Product changes | None; no prompt or backend changes made |

The one-shot runner is [scripts/evaluate.py](scripts/evaluate.py). `--verify` confirmed request and result hashes and successful pipeline status; it explicitly reports `semantic_quality_verified=false`. Semantic judgments below were independently checked against the original cleaned captions using [review-criteria.md](review-criteria.md).

## Semantic results

| Sample | Essential coverage | Source precision | Organization | Verdict |
|---|---|---|---|---|
| `zh-short` | zh1–zh4 all full | Conditions, timings, examples and scope retained | Fails: summary repeats key points; P1, P2 and P5 restate the summary without enough new conditions or consequences | Not passed |
| `en-medium` | en1, en2, en4 full; en3 partial | Attribution, usually/possible qualifiers and cultural-example scope retained | Five points have distinct supporting detail, but the summary repeats the points | Not passed |

### `zh-short`

The output preserves the four essential claims, including the second-day start for all-Chinese instruction, both classroom mechanisms, the fixed-expression distinction, and the conditions/channels for English questions. It does not invent a “beginner” claim or convert the schedule to a 45+15 split.

The known organization issue remains in the adaptive path. The summary already states the course schedule, the two classroom mechanisms, and the English-question timing/channels. P1 repeats the schedule; P2 repeats the parent overview that P3 and P4 then detail; P5 repeats the question timing/channels. P3 and P4 contain useful additional details and should remain represented.

### `en-medium`

Three of four compound essentials are fully retained. `en3` is partial because neither the summary nor the key points says Engrade can be used to leave comments **in addition to entering grades** (caption lines 32–33); private teacher comments and student-account access are retained. This omission prevents a full-coverage pass.

The summary restates the five key-point topics, creating substantial cross-field repetition. Within the points, however, the different grading rationale, feedback mechanism, performance-dependent examples, cultural illustration, and L1 condition are distinct and should not be collapsed simply because they share a feedback theme. “该成绩单” is a minor unsupported genre label; the caption is the lecturer describing a grading system.

## Budget and limits

The historical 17 requests and closed adaptive-long 3-request phase remain unchanged. This distinct phase reserved and sent exactly 2 calls; its tracker is closed at 22/26. No additional calls were made after review. The remaining 4 calls are not an automatic allocation; any remediation must first identify an offline-verifiable prompt or code change and use a separately frozen phase.

The previous full backend result (1,342 passed, one existing deprecation warning) is historical and was not rerun in this verification. No product tests were added or run because this phase changed only its acceptance runner and review documents. No env, database, account, downloader core, deployment, commit, or push was changed.

MIT OCW source captions, derived summaries, and review material retain the creator/course attribution and CC BY-NC-SA 4.0 terms. This review describes source fidelity, not independent validation of every claim made in the lectures.

## Engineering conventions

Use `ui-ux-pro-max` and `design-system` for UI/visual/interaction work, with primitive → semantic → component tokens for colors, fonts and durations. Keep new behavior configurable, avoid unrelated refactors, preserve narrow one-way interfaces, keep yt-dlp access only in `ytdlp_service.py`, keep LLM access in `llm_service.py`, and keep the visual layer read-only over `scene`. This phase changed no UI or product implementation.
