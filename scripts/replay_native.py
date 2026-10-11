#!/usr/bin/env python3
"""Replay the three applications through the library and compare them with the reference arithmetic (Section 5.6).

    python scripts/replay_native.py --data <folder with the public logs> [--application bpic2019] [--output <folder>]

One line per application: cases, criteria, views, mode-view combinations and
the values of γ, the largest absolute difference between the library and the
reference arithmetic, the largest score difference of three further checks
(cases reordered, norm serialised and read back, whole-case context
attached), and whether all are below the tolerance of 1e-8; then one line
with the totals. With ``--output`` a verification file ``<application>.json``
is written for each application. The work is done by
``wise.evaluation.replay``.
"""

from wise.evaluation.replay import main

if __name__ == "__main__":
    raise SystemExit(main())
