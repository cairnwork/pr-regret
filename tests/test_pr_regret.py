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


def test_wilson_exact_bounds_at_extremes():
    assert stats.wilson(10, 10)[1] == 1.0
    assert stats.wilson(1, 1)[1] == 1.0
    assert stats.wilson(0, 10)[0] == 0.0


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
    ev = {"title": "Fix bug", "body": "fixes other/repo#3"}
    assert not detect.named_fix_hits(ev, pr, "o/r")
    assert detect.named_fix_hits({"title": "Fix bug o/r#3", "body": ""}, pr, "o/r")
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
    assert (s["k"], s["n"]) == (3, 8)    # PRs 1, 3, 5 of 8 mature


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
    assert "HEURISTIC TRACE RATE" in render.render(res, "text")


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


def test_long_open_pr_is_found_and_listing_is_by_update():
    r = by_pr(run())
    assert 60 in r and r[60]["mature"]   # created 3 months before the window, merged inside it
    assert 10 not in r                    # merged before the window


def test_bot_filter_fetches_files_only_where_needed():
    paths = []

    def t(path):
        paths.append(path)
        return fake(path)

    scan(Client("o/r", use_cache=False, transport=t), "2026-03-01", "2026-03-20", "bot", now=NOW)
    fetched = {int(p.split("/pulls/")[1].split("/")[0]) for p in paths if "/files" in p}
    assert {1, 4} <= fetched              # targets
    assert 7 not in fetched               # merged 14 days later: never needed
    res = scan(Client("o/r", use_cache=False, transport=fake), "2026-03-01", "2026-03-20", "bot", now=NOW)
    # same-file compares against every merged PR of any author (PR 2 is human-authored)
    assert by_pr(res)[1]["same_file"] is True


def test_named_fix_needs_citation_and_keyword_on_one_line():
    pr = {"number": 3, "merged_at": datetime(2026, 3, 2, tzinfo=timezone.utc), "merge_sha": "z" * 40,
          "title": "t", "body": ""}
    # keyword in the title, citation only somewhere else in the body: not a named fix
    assert not detect.named_fix_hits({"title": "Fix parser", "body": "unrelated\nsee also #3"}, pr, "o/r")
    assert detect.named_fix_hits({"title": "Fix parser (#3)", "body": ""}, pr, "o/r")


def test_reference_boundaries():
    rx = detect.ref_regex(12, "o/r")
    assert not rx.search("uses C#12 features")
    assert not rx.search("see foo#12")
    assert not rx.search("#123 and #12abc")
    assert not rx.search("https://github.com/other/repo/pull/12")
    assert not rx.search("/pull/12")
    assert rx.search("closes #12.") and rx.search("o/r#12")
    assert rx.search("https://github.com/o/r/pull/12")
    assert detect.any_ref_numbers("C#12 #5 https://github.com/a/b/pull/7 /pull/9") == {"5", "7"}
    assert detect.any_ref_numbers("#5 https://github.com/a/b/pull/7 https://github.com/o/r/pull/8", "o/r") == {"5", "8"}


def test_revert_title_needs_closing_quote():
    pr = {"number": 8, "merged_at": datetime(2026, 3, 2, tzinfo=timezone.utc), "merge_sha": "q" * 40,
          "title": "Add retry logic (#8)", "body": ""}
    assert detect.revert_hits({"title": 'Revert "Add retry logic (#8)"', "body": ""}, pr)
    assert not detect.revert_hits({"title": 'Revert "Add retry logic for sockets"', "body": ""}, pr)


def test_cache_permissions_and_save_on_error(tmp_path):
    import stat
    from pr_regret.github import GitHubError
    n = []

    def t(path):
        n.append(path)
        if len(n) > 2:
            raise GitHubError("boom")
        return [] if "page=1" in path else []

    cl = Client("o/r", cache_dir=str(tmp_path / "c"), transport=t)
    cl.get("/a?page=1")
    cl.get("/b?page=1")
    with pytest.raises(GitHubError):
        cl.get("/c")
    f = tmp_path / "c" / "o-r.json"
    assert f.exists() and "/a?page=1" in json.loads(f.read_text())["e"]      # saved before raising
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert stat.S_IMODE(f.parent.stat().st_mode) == 0o700


def test_truncation_raises():
    from pr_regret.github import GitHubError
    cl = Client("o/r", use_cache=False, transport=lambda p: [1])
    with pytest.raises(GitHubError):
        list(cl.pages("/x", per_page=1, max_pages=3))
    assert len(list(cl.pages("/x", per_page=1, max_pages=3, strict=False))) == 3


def test_backport_checkbox_in_template_does_not_hide_a_fix():
    pr = {"number": 3, "merged_at": datetime(2026, 3, 2, tzinfo=timezone.utc), "merge_sha": "z" * 40,
          "title": "t", "body": ""}
    body = "Regression from #3 broke start-up.\n\n- [ ] Needs backport to release branch?"
    assert detect.named_fix_hits({"title": "Repair start-up", "body": body}, pr, "o/r")
    assert not detect.named_fix_hits({"title": "Fix start-up", "body": "Backport of #3 fix"}, pr, "o/r")


def test_other_repo_urls_do_not_trigger_changelog_cutoff():
    pr = {"number": 3, "merged_at": datetime(2026, 3, 2, tzinfo=timezone.utc), "merge_sha": "z" * 40,
          "title": "t", "body": ""}
    urls = " ".join("https://github.com/other/x/pull/%d" % i for i in range(100, 110))
    assert detect.named_fix_hits({"title": "Fix start-up (#3)", "body": urls}, pr, "o/r")


def test_stale_cache_listing_is_refetched_after_window_closes(tmp_path):
    """First run is too early (window still open, fix PR not merged yet); a later run must not
    reuse that listing and silently report 0."""
    early = json.loads(json.dumps(FX))
    key = "/repos/o/r/pulls?state=closed&sort=updated&direction=desc&per_page=100&page=1"
    late_listing = FX[key]
    early[key] = [x for x in late_listing if x["number"] not in (2, 6, 7)]  # revert PR 2 not merged yet
    t1 = datetime(2026, 3, 4, tzinfo=timezone.utc)   # before PR1 + 7 days
    t2 = datetime(2026, 4, 2, tzinfo=timezone.utc)   # after until + 7 days
    cdir = str(tmp_path)

    def run_at(fx, when, **kw):
        def tr(path):
            return fx.get(path, [])
        cl = Client("o/r", cache_dir=cdir, transport=tr, clock=lambda: when.timestamp(), **kw)
        return scan(cl, "2026-03-01", "2026-03-20", now=when), cl

    r1, _ = run_at(early, t1)
    assert all(not r["mature"] for r in r1["prs"])          # nothing mature yet: no verdicts
    r2, cl2 = run_at(FX, t2)                                 # listing was fetched at t1 < until+7d: refetched
    assert by_pr(r2)[1]["revert"] is True
    r3, cl3 = run_at(FX, t2)                                 # now valid: fully served from cache
    assert cl3.calls == 0 and by_pr(r3)[1]["revert"] is True
    r4, cl4 = run_at(FX, t2, refresh=True)                   # --refresh ignores the cache
    assert cl4.calls > 0 and by_pr(r4)[1]["revert"] is True


def test_precision_rules_from_hand_labelling():
    pr = {"number": 3, "merged_at": datetime(2026, 3, 2, tzinfo=timezone.utc), "merge_sha": "z" * 40,
          "title": "t", "body": ""}
    # "follow-up" alone is a feature extension, not a repair
    assert not detect.named_fix_hits({"title": "Add End mode", "body": "Follow-up to #3, extending the same approach."}, pr, "o/r")
    # release PR listing a conventional-commit "fix" line
    rel = {"title": "chore(main): release 1.7.2",
           "body": "* fix(e2e): do x by @a in https://github.com/o/r/pull/3"}
    assert not detect.named_fix_hits(rel, pr, "o/r")
    # changelog-style line inside an ordinary PR is skipped as well
    assert not detect.named_fix_hits({"title": "Docs", "body": "* fix: y by @b in https://github.com/o/r/pull/3"}, pr, "o/r")
    assert detect.named_fix_hits({"title": "Fix the crash caused by #3", "body": ""}, pr, "o/r")


def test_later_commit_with_trailing_pr_number_is_not_mistaken_for_self():
    """A later plain commit titled 'Fix regression (#3)' cites PR 3; only a PR's own merge commit is 'self'."""
    pr3 = {"number": 3, "merged_at": datetime(2026, 3, 2, tzinfo=timezone.utc), "merge_sha": "a" * 40,
           "title": "Add parser", "body": "", "files": None}
    later = {"sha": "b" * 40, "date": datetime(2026, 3, 4, tzinfo=timezone.utc), "message": "Fix regression (#3)"}
    own = {"sha": "a" * 40, "date": datetime(2026, 3, 2, 0, 0, 5, tzinfo=timezone.utc), "message": "Fix typo (#3)"}
    assert detect.detect(pr3, [pr3], [later], "o/r")["named_fix"] is True
    assert detect.detect(pr3, [pr3], [own], "o/r")["named_fix"] is False   # its own merge commit


def test_summarize_zero_denominator_is_no_data():
    s = stats.summarize(0, 0)
    assert s["rate"] is None and s["ci95"] is None and s["no_data"] is True
    assert stats.summarize(1, 4)["no_data"] is False
    res = run(samefile=False)
    assert res["summary"]["same_file_weak"]["rate"] is None
    out = render.render(res, "text")
    assert "no data" in out and "0.0%" not in out.split("same-file")[1].split("\n")[0]
    assert json.loads(render.render(res, "json"))["summary"]["same_file_weak"]["ci95"] is None


def test_full_name_references_count_toward_changelog_cutoff():
    pr = {"number": 3, "merged_at": datetime(2026, 3, 2, tzinfo=timezone.utc), "merge_sha": "z" * 40,
          "title": "t", "body": ""}
    body = "Fix thing for o/r#3\n" + " ".join("o/r#%d" % i for i in range(10, 16))
    assert not detect.named_fix_hits({"title": "Release notes", "body": body}, pr, "o/r")
    assert detect.any_ref_numbers("o/r#5 x/y#6 O/R#7 C#8", "o/r") == {"5", "7"}
    other = " ".join("x/y#%d" % i for i in range(10, 20))   # other repos' numbers do not count
    assert detect.named_fix_hits({"title": "Fix thing (#3)", "body": other}, pr, "o/r")
