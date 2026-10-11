"""Run the evaluation from the command line: numerical checks and Figures 4–6.

::

    python scripts/evaluate_paper.py --data <folder> [--output <folder>]
    python -m wise.evaluation.evaluate --data <folder> [--output <folder>]

``--data`` is the folder that holds the public logs (default: the environment
variable ``WISE_PAPER_DATA``). The command prints every printed value of the
paper beside the computed one and a summary per result item, writes
``comparison.csv``, ``summary.csv``, one calculation record per application
(``calculation_record_<application>.json``, see
:func:`wise.evaluation.paper.calculation_record`) and the figures to the
output folder (default ``outputs``), and exits with status 1 if a computed
value differs from a printed one, a numerical check fails or a log is
missing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from . import data as _data
from . import paper, replay

__all__ = ["format_value", "main", "render", "write_records"]

FIGURES = {"fig4_layers": paper.figure_4, "fig5_lag": paper.figure_5, "fig6_shortlists": paper.figure_6}


def format_value(value: Any) -> str:
    """A computed value as text: full precision for numbers, nothing for a value that was not computed."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.6e}" if value != 0 and abs(value) < 1e-4 else f"{value:.10g}"
    return str(value)


def render(comparison: pd.DataFrame) -> str:
    """The comparison as an aligned text table."""
    shown = comparison[["item", "place", "quantity", "printed", "computed", "status"]].copy()
    shown["computed"] = shown["computed"].map(format_value)
    shown["place"] = shown["place"].str.slice(0, 34)
    shown["quantity"] = shown["quantity"].str.slice(0, 66)
    shown["printed"] = shown["printed"].str.slice(0, 36)
    shown["computed"] = shown["computed"].str.slice(0, 36)
    return shown.to_string(index=False, justify="left")


def write_records(output: Path, data: str | Path | None = None) -> tuple[list[str], bool]:
    """Write the calculation record of every application whose log is in the data folder.

    Returns the names of the files written to ``output`` and whether every numerical check in them passed.
    """
    written, passed = [], True
    for name in replay.APPLICATIONS:
        try:
            record = paper.calculation_record(name, data)
        except _data.DataNotAvailable:
            continue
        checks = record["numerical_checks"]
        passed &= bool(checks["reference_arithmetic"]["passed"] and checks["further_checks"]["passed"])
        target = output / f"calculation_record_{name}.json"
        target.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        written.append(target.name)
    return written, passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute every result item of the paper and compare it with the printed value.")
    parser.add_argument("--data", type=Path, default=None, help=f"folder with the public logs (default: ${_data.DATA_ENVIRONMENT})")
    parser.add_argument("--output", type=Path, default=Path("outputs"), help="folder for the comparison table and the figures")
    parser.add_argument("--no-figures", action="store_true", help="do not draw the figures (Matplotlib is then not needed)")
    args = parser.parse_args(argv)

    try:
        _data.data_folder(args.data)
    except _data.DataNotAvailable as exc:
        parser.error(str(exc))
    print("Inputs")
    for row in _data.verify(args.data):
        print(f"  {row['dataset']:<20} {row['file']:<40} {row['status']}")

    comparison = paper.compare(args.data)
    summary = paper.summary(comparison)
    args.output.mkdir(parents=True, exist_ok=True)
    written = ["comparison.csv", "summary.csv"]
    comparison.assign(computed=comparison["computed"].map(format_value)).to_csv(args.output / "comparison.csv", index=False)
    summary.to_csv(args.output / "summary.csv")

    print()
    print(render(comparison))
    print()
    print(summary.drop(columns=["title"]).to_string())
    print()
    counts = comparison["status"].value_counts()
    print(
        f"Result items: {len(summary)}; agreeing in every printed value: {int(summary['agrees'].sum())}. "
        f"Printed values: {len(comparison)}; agree: {int(counts.get(paper.AGREES, 0))}; differ: {int(counts.get(paper.DIFFERS, 0))}; "
        f"not computed: {int(counts.get(paper.NOT_COMPUTED, 0))}."
    )

    records, checks_passed = write_records(args.output, args.data)
    written += records
    if not args.no_figures:
        from . import figures

        for stem, draw in FIGURES.items():
            try:
                written += figures.save(draw(args.data), stem, args.output)
            except _data.DataNotAvailable:
                print(f"{stem}: not drawn, its log is not in the data folder")
    print(f"Written to the output folder: {', '.join(written)}")
    failed = int(counts.get(paper.DIFFERS, 0)) > 0 or int(counts.get(paper.NOT_COMPUTED, 0)) > 0 or not checks_passed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
