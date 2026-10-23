import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pr_regret import detect, render, stats
from pr_regret.github import Client
from pr_regret.scan import is_ai_pr, scan

FX = json.loads((Path(__file__).parent / "fixtures" / "api_o_r.json").read_text())
NOW = datetime(2026, 3, 20, tzinfo=timezone.utc)


def fake(path):
    if path not in FX:
        raise AssertionError("unexpected API path (tests never hit the network): " + path)
    return FX[path]


def run(**kw):
    cl = Client("o/r", use_cache=False, transport=fake)
    return scan(cl, "2026-03-01", "2026-03-20", now=NOW, **kw)


def by_pr(res):
    return {r["pr"]: r for r in res["prs"]}


def test_wilson_known_values():
    lo, hi = stats.wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3) and hi == pytest.approx(0.7634, abs=1e-3)
    lo, hi = stats.wilson(0, 10)
    assert lo == 0 and hi == pytest.approx(0.2775, abs=1e-3)
    assert stats.wilson(0, 0) == (0.0, 0.0)
    lo, hi = stats.wilson(133, 2018)  # internal audit: 6.6% [5.6-7.8]
    assert (round(lo, 3), round(hi, 3)) == (0.056, 0.078)


def test_revert_by_pr_reference_and_by_commit_sha():
    r = by_pr(run())
    assert r[1]["revert"] is True      # PR 2 "Reverts o/r#1"
    assert r[5]["revert"] is True      # commit "This reverts commit <sha of PR 5>"
    assert r[3]["revert"] is False and r[4]["revert"] is False


def test_named_fix_detector():
    r = by_pr(run())
    assert r[3]["named_fix"] is True    # PR 4 "follow-up to #3"
    assert r[1]["named_fix"] is True    # commit "Hotfix: broke login after #1"
    assert r[5]["named_fix"] is False   # revert commits are not double counted as fixes
    assert r[2]["named_fix"] is False


def test_window_and_self_reference_excluded():
    r = by_pr(run())
    # PR 6 "Late fix for #3" is 10 days after PR 3 -> outside 7 days
    # PR 3's own body "Fix typos (#3)" must not count against itself
    assert r[3]["named_fix"] is True  # only through PR 4
    d = detect.detect({"number": 3, "merged_at": datetime(2026, 3, 2, tzinfo=timezone.utc),
                       "merge_sha": "x" * 40, "title": "t", "body": "", "files": None},
                      [{"number": 6, "merged_at": datetime(2026, 3, 12, tzinfo=timezone.utc),
                        "merge_sha": "y", "title": "Late fix for #3", "body": "", "files": None}], [])
    assert d == {"revert": False, "named_fix": False, "same_file": None}


def test_same_file_weak_signal_ignores_lockfiles():
    r = by_pr(run())
    assert r[1]["same_file"] is True    # PR 2 touches a.py
    assert r[3]["same_file"] is True    # PR 4 touches c.py (uv.lock ignored as noise)
    assert r[99]["same_file"] is False  # only a lockfile
    assert r[2]["same_file"] is False and r[4]["same_file"] is False


def test_other_repo_reference_does_not_count():
    pr = {"number": 3, "merged_at": datetime(2026, 3, 2, tzinfo=timezone.utc), "merge_sha": "z" * 40,
          "title": "t", "body": ""}
    ev = {"title": "Fix bug", "body": "closes other/repo#3"}
    assert not detect.named_fix_hits(ev, pr, "o/r")
    assert detect.named_fix_hits({"title": "Fix bug", "body": "closes o/r#3"}, pr, "o/r")
    assert detect.named_fix_hits({"title": "Fix bug (#3)", "body": ""}, pr, "o/r")
    assert not detect.named_fix_hits({"title": "Fix bug (#33)", "body": ""}, pr, "o/r")


def test_revert_by_exact_title():
    pr = {"number": 8, "merged_at": datetime(2026, 3, 2, tzinfo=timezone.utc), "merge_sha": "q" * 40,
          "title": "Add retry logic (#8)", "body": ""}
    assert detect.revert_hits({"title": 'Revert "Add retry logic"', "body": ""}, pr)
    assert not detect.revert_hits({"title": 'Revert "Something else entirely"', "body": ""}, pr)


def test_immature_prs_excluded_from_denominator():
    res = run()
    assert res["immature_excluded"] == 1  # PR 7 merged one day before NOW
    assert 7 not in {r["pr"] for r in res["prs"] if r["mature"]}
    s = res["summary"]["revert_or_named_fix"]
    assert (s["k"], s["n"]) == (3, 7)    # PRs 1, 3, 5 of 7 mature


def test_author_filter_bot_and_dependabot_not_ai():
    res = run(author_filter="bot")
    assert sorted(r["pr"] for r in res["prs"]) == [1, 4]   # agent branch prefix, copilot login
    assert is_ai_pr({"user": {"login": "dependabot[bot]"}, "head": {"ref": "dependabot/x"}}) is False
    assert is_ai_pr({"user": {"login": "h"}, "head": {"ref": "x"}, "body": "Generated with [Claude Code](x)"})


def test_no_samefile_skips_files_calls():
    res = run(samefile=False)
    assert res["summary"]["same_file_weak"]["n"] == 0
    assert all(r["same_file"] is None for r in res["prs"] if r["mature"])


def test_output_contains_numbers_and_booleans_only():
    res = run()
    for fmt in ("json", "text", "markdown"):
        out = render.render(res, fmt)
        for secret in ("Add widget", "Add parser", "crash in parser", "login"):
            assert secret not in out
    assert "LOWER BOUND" in render.render(res, "text")


def test_disk_cache_roundtrip(tmp_path):
    calls = []

    def t(path):
        calls.append(path)
        return fake(path)

    for _ in range(2):
        cl = Client("o/r", cache_dir=str(tmp_path), transport=t)
        scan(cl, "2026-03-01", "2026-03-20", now=NOW)
    first = len(calls)
    assert first > 0 and len(calls) == first   # second run served entirely from cache


def test_changelog_and_backport_events_are_not_fixes():
    pr = {"number": 3, "merged_at": datetime(2026, 3, 2, tzinfo=timezone.utc), "merge_sha": "z" * 40,
          "title": "t", "body": ""}
    notes = "chore: release 1.2\n\n* fix: a (#3)\n* fix: b (#11)\n* feat: c (#12)\n* fix: d (#13)\n* fix: e (#14)"
    t, b = notes.split("\n\n")
    assert not detect.named_fix_hits({"title": t, "body": b}, pr, "o/r")
    assert not detect.named_fix_hits({"title": "[release/1.0] Fix thing (backport of #3)", "body": ""}, pr, "o/r")
    assert detect.named_fix_hits({"title": "Fix thing", "body": "regression from #3"}, pr, "o/r")

    assert not detect.named_fix_hits({"title": "Fix crash on start (#3) (#40)", "body": ""}, pr, "o/r")
