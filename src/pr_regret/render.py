from __future__ import annotations

import json


def _pct(x: float) -> str:
    return "%.1f%%" % (100 * x)


def _row(label: str, s: dict) -> tuple:
    return (label, "%d/%d" % (s["k"], s["n"]), _pct(s["rate"]), "%s - %s" % (_pct(s["ci95"][0]), _pct(s["ci95"][1])))


def render(res: dict, fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps(res, indent=2, sort_keys=True)
    s = res["summary"]
    rows = [_row("revert", s["revert"]), _row("named fix", s["named_fix"]),
            _row("revert or named fix (headline)", s["revert_or_named_fix"]),
            _row("same-file change (weak, separate)", s["same_file_weak"])]
    strat = res.get("by_author_class", {})
    srows = []
    for key, lab in (("agent_authored", "agent-authored"), ("other", "other authors")):
        g = strat.get(key)
        if g and res["author_filter"] == "all":
            srows.append(_row("%s (%d PRs)" % (lab, g["merged_mature"]), g["revert_or_named_fix"]))
    flagged = [r for r in res["prs"] if r["revert"] or r["named_fix"]]
    sf = [r for r in res["prs"] if r["same_file"]]
    head = "%s  %s..%s  filter=%s  merged=%d  mature=%d  (excluded %d merged <7 days ago)" % (
        res["repo"], res["since"], res["until"], res["author_filter"], res["merged_prs"],
        res["merged_prs"] - res["immature_excluded"], res["immature_excluded"])
    nums = lambda rs: ", ".join("#%d" % r["pr"] for r in rs) or "none"
    if fmt == "markdown":
        out = ["### %s" % head, "", "| signal | k/n | rate | Wilson 95% |", "|---|---|---|---|"]
        out += ["| %s | %s | %s | %s |" % r for r in rows]
        if srows:
            out += ["", "| revert or named fix by author class | k/n | rate | Wilson 95% |", "|---|---|---|---|"]
            out += ["| %s | %s | %s | %s |" % r for r in srows]
        out += ["", "PRs with revert or named fix: %s" % nums(flagged),
                "", "PRs with same-file change only (weak): %s" % nums([r for r in sf if r not in flagged]),
                "", "> " + res["note"]]
        return "\n".join(out)
    w = max(len(r[0]) for r in rows)
    out = [head, ""]
    out += ["%-*s  %9s  %7s  %s" % (w, *r) for r in rows]
    if srows:
        out += [""] + ["%-*s  %9s  %7s  %s" % (w, *r) for r in srows]
    out += ["", "revert/named-fix PRs: " + nums(flagged),
            "same-file-only PRs (weak): " + nums([r for r in sf if r not in flagged]), "", res["note"]]
    return "\n".join(out)
