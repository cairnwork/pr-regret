# Validation on public repositories

Run date: 2026-10-23, tool version 0.1.0 (final rules). All reads were GitHub GET requests on public repositories, through a shared caching wrapper (`PR_REGRET_GH_CMD`); results in `docs/data/` contain PR numbers and booleans only. No private repository was scanned. The result is a **heuristic trace rate**: it can miss silent fixes and it also fires on some text that is not a fix.

| repo | merged window (UTC) | merged PRs | revert | named fix | revert or named fix (Wilson 95%) | same-file (weak) |
|---|---|---|---|---|---|---|
| dotnet/aspire | 2026-08-01 .. 08-31 | 333 | 3 | 5 | 8 = 2.4% [1.2, 4.7] | 264 (79.3%) |
| dotnet/aspnetcore | 2026-08-01 .. 08-31 | 308 | 0 | 3 | 3 = 1.0% [0.3, 2.8] | 205 (66.6%) |
| OpenHands/OpenHands | 2026-09-01 .. 09-15 | 112 | 0 | 1 | 1 = 0.9% [0.2, 4.9] | 46 (41.1%) |

Agent-authored subset (`--author-filter bot` heuristic): 5 + 16 + 60 = 81 PRs, **0 hits** (Wilson 95% upper bound 4.5%). Too few per repo to compare with other authors.

## Precision measurement (the rules were tuned, then re-measured on another window)

1. **Tuning sample (2026-07; aspire, aspnetcore, OpenHands; 24 hits under the first rule set).** An independent labeller (a separate model run that saw only the target title and the matched lines) judged 6 TRUE, 16 FALSE, 2 UNCLEAR (precision 25%). Dominant false hits: release-PR changelogs listing conventional-commit "fix" lines, "follow-up to #N" feature extensions, ports/backports. We then removed "follow-up" as a keyword and skipped release PRs and changelog lines. All 6 TRUE hits survive; 12 of the 24 hits remain.
2. **Re-measurement on an untouched window (2026-06; aspire, aspnetcore, OpenHands, dotnet/runtime two sub-windows; 22 unique hit PRs under the final rules).** A second independent labeller, now given target numbers and body starts: **15 TRUE, 5 FALSE, 2 UNCLEAR = 68% precision (Wilson 95% [47, 84])**. Two of the TRUE labels are cases where the target was itself a fix and the later event completed it. The remaining false hits are mostly ports of a fix to other files and passing mentions.
3. **Recall was not measured.** There is no hand-labelled complete sample, so the rate says nothing about how many real fixes leave no trace.

Labellers were model runs, one per sample; their labels are not ground truth.

## How to read these numbers

- **Not a lower bound.** Silent fixes, fixes that cite an issue instead of the PR, and defects found after 7 days are invisible; false hits (about a third by the June measurement) push the other way.
- **Same-file is weak** and high in busy repos; it compares each target against every merged PR of any author in the following 7 days (also with `--author-filter bot`) and is never added to the headline. PRs with more than 300 changed files are compared on their first 300.
- **Agent detection is a heuristic** (author login, agent branch prefix like `copilot/`, `codex/`, `claude/`, or a "Generated with Claude Code"-style body marker). Maintainers using agents from their own accounts without markers count as non-agent.
- **Three repos, one or two months.** No claim about all projects. PRs merged in the last 7 days before a run are excluded from the denominator (none here).
- **Listing.** PRs are listed by last update (`sort=updated`) so long-open PRs are found; a PR updated while a run pages can shift a page boundary and be skipped or repeated; a listing that exceeds 10,000 items makes the run fail instead of truncating. Cached listings fetched before the 7-day window closed are refetched automatically.

## Reproduce

```sh
pr-regret scan dotnet/aspire --since 2026-08-01 --until 2026-08-31 --format markdown
```

Counts can drift slightly on re-run as repositories change; the cached responses used here are not shipped.
