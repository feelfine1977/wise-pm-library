#!/usr/bin/env python3
"""Run the process evaluation and draw Figures 4–6.

    python scripts/evaluate_paper.py --data <folder with the public logs> [--output <folder>]

Prints the comparison of computed with printed values and writes the
comparison table and the three figures to the output folder. The work is done
by ``wise.evaluation.evaluate``; install the package first
(``python -m pip install ".[figures]"``).
"""

from wise.evaluation.evaluate import main

if __name__ == "__main__":
    raise SystemExit(main())
