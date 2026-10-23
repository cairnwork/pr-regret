"""Deterministic detectors. Pure functions over already-fetched records; no I/O, no model.

Records
  PR:     dict(number, merged_at: datetime, merge_sha, title, body, author, head_ref, files: set|None)
  Commit: dict(sha, date: datetime, message)
All detectors answer "within WINDOW after merge". They are heuristics over traces people left
in titles, bodies, commit messages and changed-file lists: they can miss silent fixes and can
also fire on text that is not really a fix, so the result is a heuristic trace rate, not a bound.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

WINDOW = timedelta(days=7)

FIX_RE = re.compile(
    r"\b(fix(?:es|ed|ing|up)?|hotfix|regress(?:ion|ions|ed|es)?|broke|broken|breaks|oops)\b",
    re.I,
)
# "follow-up to #N" is deliberately NOT a keyword: in a hand-labelled sample it was mostly a feature
# extension, not a repair.
RELEASE_EVENT_RE = re.compile(r"^\W*(?:chore(?:\([^)]*\))?:\s*)?(?:release|bump version|version bump)\b", re.I)
CHANGELOG_LINE_RE = re.compile(r"\bby @[\w-]+ in https?://|^\s*[*-]\s*@[\w-]+ made their first contribution", re.I)
BACKPORT_RE = re.compile(r"\b(back-?port(?:s|ed|ing)?|cherry[- ]?pick(?:s|ed)?)\b", re.I)
ANY_REF_RE = re.compile(r"(?<![\w/.#-])#(\d+)(?![\w])|(?<![\w.-])https?://(?:www\.)?github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)(?![\w])", re.I)
RELEASE_BRANCH_RE = re.compile(r"(\[(?:release|servicing|backport)[^\]]*\]|\b(?:release|servicing)/v?\d)", re.I)
PORT_TITLE_RE = re.compile(r"\(#\d+\)\s*\(#\d+\)\s*$")  # "Title (#orig) (#port)": a cherry-pick / forward port
MAX_REFS = 4  # an event citing more PR numbers than this is a changelog / release / batch, not a fix
REVERT_RE = re.compile(r"\brevert(?:s|ed|ing)?\b", re.I)
REVERTS_COMMIT_RE = re.compile(r"this reverts commit\s+([0-9a-f]{7,40})", re.I)
SELF_NUM_RE = re.compile(r"\(#(\d+)\)\s*$")

# Files that change on almost every PR and say nothing about "the same change".
NOISE_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "cargo.lock",
    "gemfile.lock", "go.sum", "composer.lock", "changelog.md", "changelog", "history.md",
}


def ref_regex(number: int, repo: str | None = None) -> re.Pattern:
    """Matches #N, <this repo>#N, or a .../<this repo>/pull/N URL; never other repos' #N,
    never C#12 / foo#12 / #12abc / .../pull/12 of another repo."""
    parts = [r"(?<![\w/.#-])#%d(?![\w])" % number]
    if repo:
        o = re.escape(repo)
        parts.append(r"(?<![\w/.#-])%s#%d(?![\w])" % (o, number))
        parts.append(r"(?<![\w.-])https?://(?:www\.)?github\.com/%s/pull/%d(?![\w])" % (o, number))
    return re.compile("|".join(parts), re.I)


def any_ref_numbers(text: str, repo: str | None = None) -> set[str]:
    """Distinct PR/issue numbers of THIS repo cited in the text (bare #N, or a URL of `repo`;
    all URLs when repo is None), with the same strict boundaries as ref_regex."""
    out = set()
    for m in ANY_REF_RE.finditer(text or ""):
        if m.group(1):
            out.add(m.group(1))
        elif repo is None or m.group(2).lower() == repo.lower():
            out.add(m.group(3))
    return out


def _lines(text: str) -> list[str]:
    return [ln for ln in (text or "").splitlines() if ln.strip()]


def references(text: str, pr: dict, repo: str | None = None) -> bool:
    """Does this text point at the PR (by number, by merge sha, or by `Revert "<title>"`)?"""
    if ref_regex(pr["number"], repo).search(text):
        return True
    sha = (pr.get("merge_sha") or "").lower()
    if sha:
        for m in REVERTS_COMMIT_RE.finditer(text):
            s = m.group(1).lower()
            if sha.startswith(s) or s.startswith(sha):
                return True
    return False


def _title_core(title: str) -> str:
    return re.sub(r"\s*\(#\d+\)\s*$", "", title or "").strip()


def is_revert_text(title: str, body: str = "") -> bool:
    first = (title or "").strip()
    if re.match(r"^\W*revert\b", first, re.I):
        return True
    return bool(REVERTS_COMMIT_RE.search(body or "")) or bool(
        re.search(r"^\s*reverts?\s+\S*#\d+", body or "", re.I | re.M)
    )


def revert_hits(event: dict, pr: dict, repo: str | None = None) -> bool:
    """Event (PR or commit text) is a revert pointing at `pr`."""
    title, body = event["title"], event["body"]
    if not is_revert_text(title, body):
        return False
    full = title + "\n" + body
    if references(full, pr, repo):
        return True
    core = _title_core(pr["title"])
    if len(core) < 8:
        return False
    return bool(re.search(r'"\s*%s\s*(?:\(#\d+\)\s*)?"' % re.escape(core), title, re.I))


def named_fix_hits(event: dict, pr: dict, repo: str | None = None) -> bool:
    """Event cites the PR and uses a fix-type keyword on the same line as the citation (the title is a line)."""
    if is_revert_text(event["title"], event["body"]):
        return False  # reverts are reported by their own detector
    rx = ref_regex(pr["number"], repo)
    title, body = event["title"], event["body"]
    full = title + "\n" + body
    if not rx.search(full):
        return False
    if len(any_ref_numbers(full, repo)) > MAX_REFS:
        return False  # release notes / batch PRs list many numbers beside "fix" lines
    if RELEASE_EVENT_RE.search(title):
        return False  # release PRs list changes, they do not fix them
    if PORT_TITLE_RE.search(title) or BACKPORT_RE.search(title) or RELEASE_BRANCH_RE.search(title):
        return False  # backports / release-branch ports copy a change, they do not repair it
    for ln in _lines(full):
        if rx.search(ln) and FIX_RE.search(ln) and not BACKPORT_RE.search(ln) and not CHANGELOG_LINE_RE.search(ln):
            return True
    return False


def _events(prs: list[dict], commits: list[dict]) -> list[dict]:
    pr_shas = {p["merge_sha"]: p["number"] for p in prs if p.get("merge_sha")}
    out = []
    for p in prs:
        out.append({"time": p["merged_at"], "title": p["title"] or "", "body": p["body"] or "",
                    "self": p["number"], "sha": p.get("merge_sha"), "src": "pr"})
    for c in commits:
        lines = (c["message"] or "").split("\n", 1)
        title, body = lines[0], (lines[1] if len(lines) > 1 else "")
        selfn = pr_shas.get(c["sha"])
        if selfn is None:
            m = SELF_NUM_RE.search(title)
            selfn = int(m.group(1)) if m else None
        out.append({"time": c["date"], "title": title, "body": body, "self": selfn,
                    "sha": c["sha"], "src": "commit"})
    return out


def _in_window(t: datetime, merged: datetime) -> bool:
    return merged < t <= merged + WINDOW


def _tracked_files(files):
    if files is None:
        return None
    return {f for f in files if f.rsplit("/", 1)[-1].lower() not in NOISE_FILES}


def detect(pr: dict, all_prs: list[dict], commits: list[dict], repo: str | None = None,
           events: list[dict] | None = None, min_overlap: int = 1) -> dict:
    """Return the three booleans for one PR (+ the hit counts, never the content)."""
    ev = events if events is not None else _events(all_prs, commits)
    merged = pr["merged_at"]
    revert = fix = False
    for e in ev:
        if e["self"] == pr["number"] or e["sha"] == pr.get("merge_sha"):
            continue
        if not _in_window(e["time"], merged):
            continue
        if not revert and revert_hits(e, pr, repo):
            revert = True
        if not fix and named_fix_hits(e, pr, repo):
            fix = True
    same = None
    mine = _tracked_files(pr.get("files"))
    if mine is not None:
        same = False
        if mine:
            for q in all_prs:
                if q["number"] == pr["number"] or q.get("files") is None:
                    continue
                if _in_window(q["merged_at"], merged) and len(mine & _tracked_files(q["files"])) >= min_overlap:
                    same = True
                    break
    return {"revert": revert, "named_fix": fix, "same_file": same}
