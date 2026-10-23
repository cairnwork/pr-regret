from __future__ import annotations

import argparse
import sys

from . import __version__
from .github import Client, GitHubError
from .render import render
from .scan import scan


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pr-regret", description=__doc__ or "Heuristic trace rate of merged PRs fixed or reverted within 7 days.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="scan merged PRs of OWNER/REPO")
    sc.add_argument("repo", help="OWNER/REPO (public, or readable with your token)")
    sc.add_argument("--since", required=True, help="YYYY-MM-DD (merged on or after, UTC)")
    sc.add_argument("--until", required=True, help="YYYY-MM-DD (merged on or before, UTC)")
    sc.add_argument("--author-filter", choices=["bot", "all"], default="all",
                    help="bot = agent-authored PRs only (author login, agent branch prefix, or body marker)")
    sc.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    sc.add_argument("-o", "--output", help="write to FILE instead of stdout")
    sc.add_argument("--no-samefile", action="store_true", help="skip the per-PR files calls (no same-file signal)")
    sc.add_argument("--cache-dir", help="response cache dir (default ~/.cache/pr-regret)")
    sc.add_argument("--no-cache", action="store_true")
    sc.add_argument("--refresh", action="store_true", help="ignore existing cache and refetch")
    a = ap.parse_args(argv)
    if "/" not in a.repo:
        ap.error("repo must be OWNER/REPO")
    try:
        cl = Client(a.repo, cache_dir=a.cache_dir, use_cache=not a.no_cache, refresh=a.refresh)
        res = scan(cl, a.since, a.until, a.author_filter, not a.no_samefile)
    except GitHubError as e:
        print("pr-regret: %s" % e, file=sys.stderr)
        return 2
    text = render(res, a.format)
    if a.output:
        open(a.output, "w").write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
