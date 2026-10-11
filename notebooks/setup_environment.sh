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
if wise.__version__ != "1.0.0" or set(paper.ITEMS) != set(range(1, 35)):
    raise SystemExit("The installed package does not provide the frozen 34-item API.")
print("Frozen package installed; all 34 paper entry points are available.")
PYCHECK
