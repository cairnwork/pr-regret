"""Minimal read-only GitHub REST client (urllib), with an on-disk response cache.

Transport order: if PR_REGRET_GH_CMD is set (e.g. a shared caching wrapper that accepts
`<cmd> api <path>`), use it; otherwise urllib with GITHUB_TOKEN / `gh auth token` / anonymous.
Only GET requests are ever made.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


def find_token() -> str | None:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok.strip()
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


class Client:
    def __init__(self, repo: str, cache_dir: str | None = None, use_cache: bool = True,
                 refresh: bool = False, token: str | None = None, transport=None, clock=None):
        self.repo = repo
        self.clock = clock or time.time  # epoch seconds; injectable for tests
        self.calls = 0
        self.hits = 0
        self._transport = transport
        self._cmd = os.environ.get("PR_REGRET_GH_CMD")
        self._token = token if token is not None else (None if (transport or self._cmd) else find_token())
        if not (transport or self._cmd) and not self._token:
            print("pr-regret: no GITHUB_TOKEN / `gh auth token`; using anonymous calls "
                  "(60 requests/hour). Set GITHUB_TOKEN for 5,000/hour.", file=sys.stderr)
        self._path = None
        self._cache: dict = {}
        self._dirty = False
        if use_cache:
            d = Path(cache_dir or os.environ.get("PR_REGRET_CACHE") or Path.home() / ".cache" / "pr-regret")
            self._path = d / (repo.replace("/", "-") + ".json")
            if self._path.exists() and not refresh:
                try:
                    raw = json.loads(self._path.read_text())
                    if isinstance(raw, dict) and raw.get("v") == 2:
                        self._cache = raw["e"]            # {path: [fetched_at, data]}
                    elif isinstance(raw, dict):           # v1 cache: entries get the file's mtime
                        mt = self._path.stat().st_mtime
                        self._cache = {k: [mt, v] for k, v in raw.items()}
                except (OSError, ValueError, KeyError):
                    self._cache = {}

    def save(self) -> None:
        if self._path and self._dirty:
            self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                os.chmod(self._path.parent, 0o700)
            except OSError:
                pass
            tmp = self._path.with_suffix(".tmp")
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps({"v": 2, "e": self._cache}))
            os.chmod(tmp, 0o600)
            tmp.replace(self._path)
            self._dirty = False

    def _fetch(self, path: str):
        if self._transport:
            return self._transport(path)
        if self._cmd:
            r = subprocess.run(shlex.split(self._cmd) + ["api", path], capture_output=True, text=True)
            if r.returncode != 0:
                raise GitHubError("%s failed: %s" % (self._cmd, r.stderr.strip()[:300]))
            return json.loads(r.stdout)
        req = urllib.request.Request(API + path, headers={
            "Accept": "application/vnd.github+json", "User-Agent": "pr-regret",
            "X-GitHub-Api-Version": "2022-11-28"})
        if self._token:
            req.add_header("Authorization", "Bearer " + self._token)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and e.headers.get("x-ratelimit-remaining") == "0":
                raise GitHubError("GitHub rate limit reached (resets at epoch %s). Set GITHUB_TOKEN "
                                  "and re-run; fetched pages are cached." % e.headers.get("x-ratelimit-reset"))
            raise GitHubError("GET %s -> HTTP %s" % (path, e.code))

    def get(self, path: str, fresh_after: float | None = None):
        """Cached GET. `fresh_after` (epoch seconds): a cached entry fetched before that moment is
        stale and refetched. Listings whose answer can still change (e.g. later fix PRs) pass the
        end of the 7-day observation window here, so a first run made too early is never reused."""
        ent = self._cache.get(path)
        if ent is not None and (fresh_after is None or ent[0] >= fresh_after):
            self.hits += 1
            return ent[1]
        try:
            data = self._fetch(path)
        except GitHubError:
            self.save()  # keep the pages already fetched so a re-run resumes from cache
            raise
        self.calls += 1
        self._cache[path] = [self.clock(), data]
        self._dirty = True
        if self.calls % 20 == 0:
            self.save()
        return data

    def pages(self, path: str, per_page: int = 100, max_pages: int = 100, strict: bool = True,
              fresh_after: float | None = None):
        """Yield pages (lists) until a short page. `path` may already contain a query string.
        If max_pages is reached with more data pending: raise (strict) instead of silently truncating."""
        sep = "&" if "?" in path else "?"
        for n in range(1, max_pages + 1):
            page = self.get("%s%sper_page=%d&page=%d" % (path, sep, per_page, n), fresh_after)
            yield page
            if not isinstance(page, list) or len(page) < per_page:
                return
        if strict:
            raise GitHubError("more than %d pages for %s; narrow --since/--until instead of "
                              "accepting a silently truncated sample" % (max_pages, path.split("?")[0]))
