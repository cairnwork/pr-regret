# Are AI-written PRs fixed or reverted within 7 days of merge? Three measurements, not to be mixed

**Most visible result first:** in the public tool's runs on 3 open-source repos, **0 of 81 PRs flagged as agent-authored** left a revert or named-fix trace (95% upper bound 4.5%). The sample is small and the flag is a heuristic; this does not show that AI PRs are safer.

The three sets of numbers below use **different definitions and must not be compared or combined**:

| | Population | How decided | Number |
|---|---|---|---|
| A. Internal audit | 2,018 PRs in the author's own 11-repo agent development setup | model classification + re-check of "false completions" | confirmed lower bound 6.6%, estimate 7-10% |
| B. Public tool | merged PRs of 3 open-source repos | zero-model, deterministic "trace rate" | 0.9%-2.4% |
| C. External study | agentic PRs in an MSR 2026 study | contains a reverting commit | 2.66% |

## A. Internal audit (positives re-checked by a second model, not by humans; a confirmed lower bound under that definition)

PRs merged 2026-08-01 to 10-16; question: within 7 days of merge, did a later PR name it as something it fixes?

- **Confirmed lower bound 133/2,018 = 6.6%** (Wilson 95% interval 5.6-7.8%); the audit's estimate of the true rate is 7-10%.
- **The denominator includes PRs younger than 7 days (right-censoring).** Excluding the two newest periods gives 112/1,615 = 6.9% (5.8-8.3%); the conclusion holds.
- **Who caught them:** real use / experiments 54, independent review (mostly AI reviewers) 27, unknown 26, live/wiring audit 10, CI 9, owner 5, other 2; **the core verification gate 0**.
- **Governance strength:** the data cannot show that stricter merge governance lowers false completions (August 7.0%, September 6.9%; intervals across tiers overlap; repos with no required checks 13.1%, but only 61 PRs).
- **Method:** keyword filter of follow-up PRs, one model first-pass label, positives re-checked once; one first-pass labeller per item. Limits: silent fixes are missed; per-PR attribution is noisy, the rate is more reliable than any single case.

Source: "Repo family false completions, 8/1-10/16" (author's internal research note, 2026-10-17).

## B. Public tool: heuristic trace rate (not a lower bound)

`pr-regret` (Apache-2.0, standard library, no model) looks for three traces only: a revert, a later PR/commit that names the PR as something it fixes, and same-file changes. Results on public repos, run 2026-10-23:

| repo | merged PRs | reverts | named fixes | revert or named fix (95% interval) |
|---|---|---|---|---|
| dotnet/aspire (2026-08) | 333 | 3 | 5 | 8 = 2.4% (1.2-4.7%) |
| dotnet/aspnetcore (2026-08) | 308 | 0 | 3 | 3 = 1.0% (0.3-2.8%) |
| OpenHands/OpenHands (2026-09-01..15) | 112 | 0 | 1 | 1 = 0.9% (0.2-4.9%) |

Same-file changes are a weak signal (41-79%; busy repos keep touching the same files), reported separately and never added.

**Why it is not a lower bound:** misses (silent fixes, fixes citing only an issue, defects found after 7 days) and false hits (keyword matches) both exist. On a different time window (2026-06) we drew 22 hits and had an independent labeller read them: 15 were real fixes or reverts (precision 68%, Wilson 95% interval 47-84%), 5 were not, 2 unclear; recall was not measured. So B is a reproducible trace signal, not a true rate.

## C. External study

The MSR 2026 Mining Challenge paper "When AI Code Doesn't Stick: An Empirical Study on Reverted Changes Introduced by AI Coding Agents" reports 2.66% (PRs containing a reverting commit); its definition differs from A and B and the numbers cannot be compared directly (we could not obtain the full text and cite only the abstract-level figure). Source page: https://2026.msrconf.org/details/msr-2026-mining-challenge/27/

## How to read this

1. A is a lower bound whose positives were re-checked by a second model (not human-verified), B a heuristic signal, C another definition; they do not validate one another.
2. Why only real use and review catch them: merge gates check conditions at merge time, while this class of defect usually shows up when someone uses the change or reads the code (in A, 54 cases by use, 27 by review, core gate 0). Evidence for adding more pre-merge gates against this failure class is limited; the better-supported direction is to make "done" wait for a witness from real use.
3. Other limits: B covers 3 repos and 1-2 months; the AI-authored flag is a heuristic (author login, branch prefix, body marker); public repos differ from our setup.

Related project: [Cairnwork](https://github.com/cairnwork/cairnwork).

*Author: James3014. License: Apache-2.0.*
