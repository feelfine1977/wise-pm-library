"""Compact aggregate reference results of the three applications.

The tables shipped in ``expected`` (``view_summary.csv``,
``group_rankings.csv``, ``layer_contributions.csv``) document reported
results: per application and view the size of the scored population with its
mean case penalty and mean coverage, the ranked investigation groups, and
their signed layer contributions. They hold aggregates only, no case of a
log, and they do not replace execution on the corresponding inputs: the
dataset evaluation test computes them from the logs and compares the results.

Command line (rewrites the tables from the logs)::

    python -m wise.evaluation.reference_tables --data <folder> --output <folder>
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

import wise

from . import data as _data
from . import paper, replay

__all__ = ["RANKED_GROUPS", "TABLES", "build", "main"]

TABLES = ("view_summary", "group_rankings", "layer_contributions")
RANKED_GROUPS = 30
"""At most this many groups per application and view, in rank order (all 30 of BPIC'19, all 27 of BPIC'17)."""


def build(data: str | Path | None = None, applications: Sequence[str] | None = None) -> dict[str, pd.DataFrame]:
    """The three reference tables, computed from the logs in the data folder."""
    summary, rankings, contributions = [], [], []
    for name in applications or replay.APPLICATIONS:
        app = paper.application(name, data)
        groups = app.assessment.groups
        for view in app.views:
            backlog = app.backlog(view)
            table = backlog.table
            coverage = app.result.coverage(view)
            penalty = app.penalty(view)
            summary.append(
                {
                    "application": name,
                    "view": view,
                    "cases": len(penalty),
                    "scored": int(penalty.notna().sum()),
                    "groups": len(table),
                    "positive_groups": int((table["PI"] > paper.POSITIVE).sum()),
                    "mean_penalty": float(penalty.mean()),
                    "mean_coverage": float(coverage.mean()),
                }
            )
            group_coverage = coverage.groupby(groups).mean()
            signed = wise.layer_contributions(app.result, backlog)
            for rank, (group, row) in enumerate(table.head(RANKED_GROUPS).iterrows(), start=1):
                rankings.append(
                    {
                        "application": name,
                        "view": view,
                        "rank": rank,
                        "group": str(group),
                        "scored_cases": int(row["n_cases"]),
                        "mean_penalty": float(1.0 - row["mean_score"]),
                        "gap": float(row["gap"]),
                        "priority_index": float(row["PI"]),
                        "mean_coverage": float(group_coverage[group]),
                    }
                )
                for layer in signed.columns:
                    contributions.append(
                        {
                            "application": name,
                            "view": view,
                            "group": str(group),
                            "layer": str(layer),
                            "contribution": float(signed.loc[group, layer]),
                        }
                    )
    return {
        "view_summary": pd.DataFrame(summary),
        "group_rankings": pd.DataFrame(rankings),
        "layer_contributions": pd.DataFrame(contributions),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the compact aggregate reference tables computed from the public logs.")
    parser.add_argument("--data", type=Path, default=None, help=f"folder with the public logs (default: ${_data.DATA_ENVIRONMENT})")
    parser.add_argument("--output", type=Path, required=True, help="folder to write the three CSV tables to")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, frame in build(args.data).items():
        frame.to_csv(args.output / f"{name}.csv", index=False, float_format="%.17g", lineterminator="\n")
        print(f"{name}.csv: {len(frame)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
