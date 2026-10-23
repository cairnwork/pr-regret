# What share of AI-written PRs get fixed or reverted within 7 days of merging?

**Short answer: about 7-10% in the author's own 11-repo agent development setup, and automated merge gates caught almost none of them. Real use and human review did.**

## 1. Our own numbers

In an agent development setup spanning 11 repositories, we looked at the 2,018 PRs merged between 2026-08-01 and 10-16 and asked: within 7 days of merge, did a later PR name it as a fix or revert it?

- **Confirmed lower bound: 133/2,018 = 6.6%** (Wilson 95% interval 5.6-7.8%); estimated true rate 7-10%. Main repo 6.9%, the other 10 repos 6.2%.
- **Strictness of merge governance made no visible difference.** August 7.0%; September, under the heaviest governance, 6.9%. Per-repo rates are not monotone in governance strength and the intervals overlap.
- **Who caught them:** real use 54, independent human review 27, live/wiring audit 10; automated gates almost none (core verification gate 0, CI 9).
- **Daily tracking:** the same metric computed daily sits at about 6.0-6.2%; per-PR precision and recall are about 0.73 each, so only weekly rates should be read.

Sources: "Repo family false completions, 8/1-10/16" (author's internal research note, 2026-10-17); "7-day fix/revert rate metric and incident evaluation set" (internal research note, 2026-10-19).

**Method, and how the public tool differs.** The internal version first filters candidate follow-up PRs by keyword, then uses a model to classify whether the follow-up fixes the earlier PR, and a second model re-checks the positives. The public tool (`pr-regret`) **uses no model at all**, only deterministic signals: a revert pointing at the PR, a later PR or commit that names it as a fix, and same-file changes. It is therefore reproducible and more conservative; the two sets of numbers are not directly comparable. Internal limits: silent fixes are missed, one labeller per item, the last two periods were not yet 7 days old.

## 2. External reference

The MSR 2026 Mining Challenge paper "When AI Code Doesn't Stick: An Empirical Study on Reverted Changes Introduced by AI Coding Agents" (Oukay, Begoug, Chouchen, Ouni) studied 33,580 agentic PRs (AIDev dataset: Claude, Copilot, Cursor, Devin, OpenAI Codex) and found **2.66% contain at least one reverting commit**; by agent, OpenAI Codex 0.7% and GitHub Copilot 7.6%. Source page: https://2026.msrconf.org/details/msr-2026-mining-challenge/27/ .

**The definitions differ, so do not compare directly.** That study measures reverts only; we measure reverts plus named fixes. How it decides that a PR was reverted, and whether there is a time window, we did not read in the paper's method section: **to be verified** (the arXiv version is also to be verified). Treat 2.66% and our revert column as same-order context only.

## 3. Lower bounds from the public tool on open-source repositories

We ran `pr-regret` (Apache-2.0, standard library only) on three public repos with visible coding-agent PRs, one month each (OpenHands half a month), on 2026-10-23:

| repo | merged PRs | reverts | named fixes | revert or named fix (95% interval) |
|---|---|---|---|---|
| dotnet/aspire (Aug) | 316 | 3 | 21 | 24 = 7.6% (5.2-11.1%) |
| dotnet/aspnetcore (Aug) | 295 | 0 | 4 | 4 = 1.4% (0.5-3.4%) |
| OpenHands/OpenHands (Sep 1-15) | 110 | 0 | 2 | 2 = 1.8% (0.5-6.4%) |

Among PRs flagged as agent-authored (78 in total: 5 + 13 + 60), **none** left a trace; the 95% upper bound is 4.7%. The sample is too small to say agent PRs are safer; it says only that no deterministic trace was found. Same-file changes are a weak signal (40-79%, busy repos keep touching the same files), reported separately and never added to the rate. We hand-read 10 random named-fix hits: 4 were real fixes, 2 ambiguous, 4 were not; we then added rules excluding backports, release-branch PRs and changelog-style PRs (see `docs/VALIDATION.md`).

## 4. How to read this

1. **Everything here is a lower bound.** Only traces people left (titles, bodies, commit messages, changed-file lists) are visible. Silent fixes, fixes that cite an issue rather than the PR, and defects found after 7 days are invisible. This is not the true false-completion rate.
2. **Same order of magnitude, but no cross-repo comparison.** Our 6.6% lower bound, the public repos' 1.4-7.6% and the external 2.66% revert rate all sit at a single-digit percentage; repos, periods and definitions differ.
3. **Why only real use and review catch them.** Merge gates check conditions at merge time (tests, rules, signatures); this class of defect usually shows up only when someone uses the change or reads the code. Of our 133 cases, 54 were found by real use and 27 by human review, automated gates about 0, and stricter governance did not lower the rate. Adding more pre-merge gates has limited payoff for this failure class; the better-supported direction is to make "done" wait for a witness from real use.

## 5. Next step

To make sure PRs merged to main are really complete and backed by evidence, see [Cairnwork](https://github.com/cairnwork/cairnwork) (our only main product).

*Author: James3014. License: Apache-2.0.*
