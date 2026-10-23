"""Fetch merged PRs for a window and run the detectors."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import detect
from .github import Client
from .stats import summarize

NOT_AI_BOTS = re.compile(r"(dependabot|renovate|github-actions|pre-commit-ci|greenkeeper|snyk|"
                         r"mergify|allcontributors|imgbot|weblate|transifex|crowdin)", re.I)
AI_LOGIN = re.compile(r"(copilot|devin|codex|claude|cursor|jules|openhands|sweep-ai|"
                      r"gemini-code|amazon-q|codegen|factory-droid|aider)", re.I)
AI_BRANCH = re.compile(r"^(copilot|codex|devin|claude|cursor|jules|openhands|aider|sweep)[/-]", re.I)
AI_BODY = re.compile(r"(generated with \[?claude code|co-authored-by:\s*claude|codex\.openai|"
                     r"created by devin|devin\.ai|session[_ ]?url.*devin|cursor agent|jules\.google)", re.I)


def is_ai_pr(raw: dict) -> bool:
    """Heuristic, deterministic 'agent-authored' flag: author login, agent branch prefix, or body marker."""
    user = (raw.get("user") or {})
    login = user.get("login") or ""
    if NOT_AI_BOTS.search(login):
        return False
    if AI_LOGIN.search(login):
        return True
    ref = ((raw.get("head") or {}).get("ref")) or ""
    if AI_BRANCH.match(ref):
        return True
    return bool(AI_BODY.search(raw.get("body") or ""))


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_date(s: str, end: bool = False) -> datetime:
    d = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return d + timedelta(days=1) - timedelta(seconds=1) if end else d


def _norm_pr(raw: dict) -> dict:
    return {"number": raw["number"], "merged_at": parse_ts(raw["merged_at"]),
            "merge_sha": raw.get("merge_commit_sha"), "title": raw.get("title") or "",
            "body": raw.get("body") or "", "author": (raw.get("user") or {}).get("login", ""),
            "head_ref": ((raw.get("head") or {}).get("ref")) or "", "ai": is_ai_pr(raw), "files": None}


def fetch_prs(cl: Client, lo: datetime, hi: datetime, lookback_days: int) -> list[dict]:
    """Closed PRs sorted by creation (newest first); stop once creation is older than lo - lookback."""
    stop = lo - timedelta(days=lookback_days)
    out = []
    for page in cl.pages("/repos/%s/pulls?state=closed&sort=created&direction=desc" % cl.repo):
        done = False
        for raw in page:
            if parse_ts(raw["created_at"]) < stop:
                done = True
                continue
            if raw.get("merged_at") and lo <= parse_ts(raw["merged_at"]) <= hi:
                out.append(_norm_pr(raw))
        if done:
            break
    return out


def fetch_commits(cl: Client, lo: datetime, hi: datetime) -> list[dict]:
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    out = []
    for page in cl.pages("/repos/%s/commits?since=%s&until=%s" % (cl.repo, lo.strftime(fmt), hi.strftime(fmt))):
        for c in page:
            cm = c.get("commit") or {}
            date = (cm.get("committer") or {}).get("date") or (cm.get("author") or {}).get("date")
            if date:
                out.append({"sha": c["sha"], "date": parse_ts(date), "message": cm.get("message") or ""})
    return out


def fetch_files(cl: Client, number: int) -> set[str]:
    files = set()
    for page in cl.pages("/repos/%s/pulls/%d/files" % (cl.repo, number), max_pages=3):
        files.update(f["filename"] for f in page)
    return files


def scan(cl: Client, since: str, until: str, author_filter: str = "all", samefile: bool = True,
         lookback_days: int = 30, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    lo, hi_targets = parse_date(since), parse_date(until, end=True)
    hi_ext = min(hi_targets + detect.WINDOW, now)
    prs = fetch_prs(cl, lo, hi_ext, lookback_days)
    commits = fetch_commits(cl, lo, hi_ext)
    if samefile:
        for p in prs:
            p["files"] = fetch_files(cl, p["number"])
    cl.save()
    ev = detect._events(prs, commits)
    rows = []
    for p in sorted(prs, key=lambda x: x["number"]):
        if p["merged_at"] > hi_targets:
            continue
        if author_filter == "bot" and not p["ai"]:
            continue
        mature = p["merged_at"] + detect.WINDOW <= now
        r = {"pr": p["number"], "ai": p["ai"], "mature": mature}
        r.update(detect.detect(p, prs, commits, cl.repo, events=ev) if mature
                 else {"revert": None, "named_fix": None, "same_file": None})
        rows.append(r)
    m = [r for r in rows if r["mature"]]
    k_rev = sum(1 for r in m if r["revert"])
    k_fix = sum(1 for r in m if r["named_fix"])
    k_any = sum(1 for r in m if r["revert"] or r["named_fix"])
    sf = [r for r in m if r["same_file"] is not None]
    return {
        "repo": cl.repo, "since": since, "until": until, "author_filter": author_filter,
        "window_days": 7, "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "merged_prs": len(rows), "immature_excluded": len(rows) - len(m),
        "summary": {
            "revert": summarize(k_rev, len(m)),
            "named_fix": summarize(k_fix, len(m)),
            "revert_or_named_fix": summarize(k_any, len(m)),
            "same_file_weak": summarize(sum(1 for r in sf if r["same_file"]), len(sf)),
        },
        "prs": rows,
        "note": ("LOWER BOUND: only traces left in titles, bodies, commit messages and changed-file lists "
                 "are visible. This is not the true rate of false completion. same_file_weak is a weak "
                 "signal and is not included in revert_or_named_fix."),
        "api_calls": cl.calls, "cache_hits": cl.hits,
    }
