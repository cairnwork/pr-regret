### OpenHands/OpenHands  2026-09-01..2026-09-15  filter=all  merged=112  mature=112  (excluded 0 merged <7 days ago)

| signal | k/n | rate | Wilson 95% |
|---|---|---|---|
| revert | 0/112 | 0.0% | 0.0% - 3.3% |
| named fix | 1/112 | 0.9% | 0.2% - 4.9% |
| revert or named fix (headline) | 1/112 | 0.9% | 0.2% - 4.9% |
| same-file change (weak, separate) | 46/112 | 41.1% | 32.4% - 50.3% |

| revert or named fix by author class | k/n | rate | Wilson 95% |
|---|---|---|---|
| agent-authored (60 PRs) | 0/60 | 0.0% | 0.0% - 6.0% |
| other authors (52 PRs) | 1/52 | 1.9% | 0.3% - 10.1% |

PRs with revert or named fix: #17164

PRs with same-file change only (weak): #16089, #16178, #16600, #16685, #16883, #16903, #16939, #16944, #16955, #16964, #16971, #16972, #16982, #17009, #17060, #17064, #17086, #17089, #17116, #17123, #17129, #17136, #17138, #17175, #17179, #17190, #17191, #17203, #17228, #17238, #17243, #17245, #17256, #17264, #17289, #17317, #17318, #17343, #17353, #17357, #17364, #17414, #17423, #17425, #17458

> HEURISTIC TRACE RATE, not a bound and not the true rate of false completion: only traces left in titles, bodies, commit messages and changed-file lists are visible (silent fixes are missed) and some matches may not be real fixes. same_file_weak compares against every merged PR of any author and is not included in revert_or_named_fix.
