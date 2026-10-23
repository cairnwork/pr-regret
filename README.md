# pr-regret

**English.** How many merged pull requests get reverted or fixed within 7 days? `pr-regret` reads the **public GitHub API** (or any repo your own token can read) with **no model calls**, and for each merged PR answers three yes/no questions about the 7 days after merge: was it **reverted**, was it **named in a fix / follow-up**, did another merged PR **touch the same files** (weak signal, reported separately). It prints the share with a Wilson 95% interval, and can restrict to agent-authored PRs. Standard library only, Python 3.10+.

**中文。** 「合併後 7 天內被撤回或修正的 PR 有多少？」`pr-regret` 只讀公開的 GitHub API（或你自己的 token 讀得到的 repo），**不呼叫任何模型**，對每張已合併 PR 回答三個是非題：7 天內有沒有被 **revert**、有沒有被後續 PR／commit **指名修正**、有沒有別的合併 PR **改到同一批檔案**（弱訊號，分開報）。輸出比例與 Wilson 95% 區間，可只看 AI 代理寫的 PR。只用標準庫，Python 3.10 以上。

**This is a lower bound, not the true rate of false completion.** It only sees traces people left (titles, bodies, commit messages, changed-file lists). Silent fixes, fixes that do not cite the PR, and defects found after 7 days are invisible. An internal audit by the author that used a model to classify follow-up PRs found 6.6% as a confirmed lower bound (estimated 7-10%); see `docs/REPORT_en.md`.

## Install

```sh
git clone <this repo> && cd pr-regret
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/pr-regret --help
```

## Usage

```sh
export GITHUB_TOKEN=...        # optional; falls back to `gh auth token`, then anonymous (60 requests/hour)
pr-regret scan OWNER/REPO --since 2026-08-01 --until 2026-08-31
pr-regret scan OWNER/REPO --since 2026-08-01 --until 2026-08-31 --author-filter bot --format markdown
pr-regret scan OWNER/REPO --since 2026-08-01 --until 2026-08-31 --format json -o result.json
```

Options: `--author-filter bot|all` (bot = agent-authored: author login such as Copilot/Devin/Codex/Claude/Cursor/Jules, an agent branch prefix like `copilot/` or `codex/`, or a "Generated with Claude Code"-style body marker; dependabot, renovate and release bots are excluded), `--format text|json|markdown`, `-o FILE`, `--no-samefile` (skips one API call per PR; no same-file signal), `--lookback-days N` (PRs created up to N days before `--since` are still found; default 30), `--cache-dir`, `--no-cache`, `--refresh`.

Pages are cached on disk (`~/.cache/pr-regret/<owner>-<repo>.json`), so a re-run costs no API calls; use `--refresh` for fresh data. If you run behind a shared caching wrapper, set `PR_REGRET_GH_CMD="/path/to/wrapper"` (called as `wrapper api <path>`).

## What is detected (7 days after merge, all deterministic)

| signal | rule |
|---|---|
| revert | A later PR or commit whose title/message says Revert and points at the PR: its `#N` / `owner/repo#N`, "This reverts commit <merge sha>", or `Revert "<exact title>"` |
| named fix | A later PR or commit that cites `#N` and uses fix, hotfix, regression, follow-up, broke ... on the same line or in its title (reverts are not counted here) |
| same file (weak) | Another PR merged within 7 days changes at least one of the same files (lockfiles and changelogs ignored) |

The headline number is **revert or named fix**. The same-file signal is reported on its own because many unrelated PRs touch hot files. PRs merged less than 7 days before the run are excluded from the denominator.

## Privacy

- Reads only public API responses or what your own token can read. The only network traffic is `GET` requests to `api.github.com` (or your wrapper).
- Output contains PR numbers, booleans and aggregate counts only. No titles, bodies, commit messages, file names or author names are printed or stored in results. (The optional on-disk cache stores raw API responses, like a browser cache; delete it with `rm -r ~/.cache/pr-regret`, or use `--no-cache`.)
- Tests use recorded fake API responses only.

## Tests

In a venv: `pip install -e .[dev]` then `pytest`.

## Limits

See `docs/VALIDATION.md` for runs on public repos and what they do and do not show. Short list: lower bound only; agent-authored detection is a heuristic; one repo and one window per run; PR lists are found by creation date (see `--lookback-days`); a single day in UTC is the unit for `--since/--until`.

Next step: to make sure PRs merged to main are really complete and backed by evidence, see [Cairnwork](https://github.com/cairnwork/cairnwork) (the main product).

License: Apache-2.0. Author: James3014.
