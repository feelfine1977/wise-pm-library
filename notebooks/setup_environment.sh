#!/usr/bin/env bash
set -euo pipefail
notebook_folder="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
package_folder="$(dirname -- "$notebook_folder")"
work_folder="$notebook_folder/_evaluation_work"
mkdir -p "$work_folder/tmp" "$work_folder/pip-cache"
export TMPDIR="$work_folder/tmp"
export PIP_CACHE_DIR="$work_folder/pip-cache"
export PYTHONDONTWRITEBYTECODE=1
if [ ! -x "$notebook_folder/.venv/bin/python" ]; then
    python3 -m venv "$notebook_folder/.venv"
fi
"$notebook_folder/.venv/bin/python" - "$package_folder" "$work_folder/install-source" <<'PYSETUP'
from pathlib import Path
import shutil, sys
source, target = map(Path, sys.argv[1:])
required = ("pyproject.toml", "LICENSE", "src/wise/evaluation/paper.py", "src/wise/evaluation/__init__.py", "src/wise/evaluation/figures.py")
missing = [name for name in required if not (source / name).is_file()]
if missing:
    raise SystemExit("The installation source is missing required package files: " + ", ".join(missing))
if target.exists():
    shutil.rmtree(target)
target.mkdir(parents=True)
for name in ("pyproject.toml", "README.md", "LICENSE", "LICENSE.txt", "MANIFEST.in", "setup.cfg"):
    if (source / name).is_file():
        shutil.copy2(source / name, target / name)
if not (target / "README.md").is_file():
    shutil.copy2(source / "notebooks" / "README.md", target / "README.md")
    print("The installation snapshot uses the notebook guide because the package README was not found.")
shutil.copytree(source / "src", target / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
PYSETUP
"$notebook_folder/.venv/bin/python" -m pip install "$work_folder/install-source[notebook]"
"$notebook_folder/.venv/bin/python" -m ipykernel install \
    --prefix "$notebook_folder/.venv" --name wise-pm-library --display-name "WISE paper (frozen)"
"$notebook_folder/.venv/bin/python" - <<'PYCHECK'
import wise
from wise.evaluation import paper
if wise.__version__ != "1.0.1":
    raise SystemExit("The installed package is not version 1.0.1.")
required_functions = (
    "item_01_table_4",
    "item_02_worked_arithmetic",
    "item_03_log_size",
    "item_04_flow_categories",
    "item_05_slices",
    "item_06_scored_cases",
    "item_07_mean_coverage",
    "item_08_c04_evaluable",
    "item_09_lag_medians",
    "item_10_lag_medians_df2",
    "item_11_figure_5",
    "item_12_worked_po_item",
    "item_13_population_mean_penalty",
    "item_14_packaging",
    "item_15_logistics",
    "item_16_slice_coverage",
    "item_17_layer_contributions",
    "item_18_figure_4",
    "item_19_logistics_absences",
    "item_20_vendor_concentration",
    "item_21_document_shortlists",
    "item_22_first_two_slices",
    "item_24_ranking_policies",
    "item_25_figure_6",
    "item_26_incident_log_size",
    "item_29_prod542",
    "item_30_prod424",
    "item_31_lending_log_size",
    "item_32_lending_first_slices",
    "item_33_consistency_check",
    "item_35_c04_endpoints",
    "item_36_first_documents",
    "item_37_prod424_layers",
    "item_38_incident_adjustment",
    "item_39_lending_adjustment",
    "item_40_view_weights",
    "item_41_illustration",
    "item_42_constructed_checks",
    "table_3",
    "table_b1",
    "incident_criteria",
    "lending_criteria",
    "figure_4",
    "figure_5",
    "figure_6",
    "compare",
    "summary",
    "further_checks",
    "input_identity",
)
if any(not callable(getattr(paper, name, None)) for name in required_functions):
    raise SystemExit("The installed package lacks a required evaluation function.")
print("Frozen package 1.0.1 installed; functions for all 38 result items are available.")
PYCHECK
