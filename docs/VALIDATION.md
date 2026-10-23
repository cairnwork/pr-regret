# Validation on public repositories

Run date: 2026-10-23. Tool version 0.1.0. All reads were GitHub GET requests for public repositories (about 970 API calls in total, through a shared caching wrapper via `PR_REGRET_GH_CMD`; results are in `docs/data/`, numbers and booleans only). No private repository was scanned.

Chosen because each has a visible share of coding-agent PRs (Copilot coding agent, or OpenHands/Claude Code/Codex branches) and enough volume.

| repo | merged window (UTC) | merged PRs (mature) | revert | named fix | revert or named fix (Wilson 95%) | same-file (weak) |
|---|---|---|---|---|---|---|
| dotnet/aspire | 2026-08-01 .. 08-31 | 316 | 3 (0.9%) | 21 (6.6%) | 24 = 7.6% [5.2, 11.1] | 249 (78.8%) |
| dotnet/aspnetcore | 2026-08-01 .. 08-31 | 295 | 0 (0.0%) | 4 (1.4%) | 4 = 1.4% [0.5, 3.4] | 200 (67.8%) |
| OpenHands/OpenHands | 2026-09-01 .. 09-15 | 110 | 0 (0.0%) | 2 (1.8%) | 2 = 1.8% [0.5, 6.4] | 44 (40.0%) |

Agent-authored subset (`--author-filter bot` heuristic): aspire 5 PRs, aspnetcore 13, OpenHands 60; **0 of 78 had a revert or named fix** (Wilson 95% upper bound 4.7%). With so few PRs per repo this does not show that agent PRs are safer; it shows only that no deterministic trace was found.

## How to read these numbers

- **Lower bounds.** Anything not leaving a citation (silent fixes, fixes that cite an issue instead of the PR, defects found after 7 days) is invisible.
- **Precision is not perfect.** While developing, we read the matching lines for 10 random named-fix hits from the two dotnet repos (locally, not stored): 4 were clear fixes or follow-ups, 2 ambiguous, 4 not fixes (a PR merely mentioned later; cherry-pick/forward-port titles such as `Title (#orig) (#port)`). We then added rules that drop port/backport PRs, release-branch titles and changelog-like events citing more than 4 PRs; counts on the three repos fell from 33/8/19 to 21/4/2 named fixes. False positives remain possible (they push the rate up) while silent fixes are invisible (they push it down); we did not measure either error against full hand labels.
- **Same-file is weak** and high in busy repos because many PRs touch hot files; it is never added to the headline.
- **Agent detection is a heuristic** (author login, agent branch prefix like `copilot/`, `codex/`, `claude/`, or a "Generated with Claude Code"-style body marker). Maintainers who use agents from their own accounts without markers count as non-agent.
- **One window, one month or half month, three repos.** No claim about all projects. The windows are right-censored by the 7-day rule only for PRs merged in the last 7 days before the run, which were excluded (none here).
- Detection of PR lists is by creation date with a 30-day lookback (`--lookback-days`), so PRs that were open for more than 30 days before merging are missed.

## Reproduce

```sh
pr-regret scan dotnet/aspire --since 2026-08-01 --until 2026-08-31 --format markdown
```

Results change slightly as repositories evolve (late-arriving commit data, deleted branches), so exact numbers may differ on re-run; the cached responses used here are not shipped.
