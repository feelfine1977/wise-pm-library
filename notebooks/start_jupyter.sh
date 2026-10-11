#!/usr/bin/env bash
set -euo pipefail
notebook_folder="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ "$#" -gt 1 ]; then
    echo "Usage: start_jupyter.sh [data-folder]" >&2
    exit 2
fi
if [ "$#" -eq 1 ]; then
    export WISE_PAPER_DATA="$1"
fi
if [ -z "${WISE_PAPER_DATA:-}" ]; then
    echo "Provide the data folder as an argument or set WISE_PAPER_DATA." >&2
    exit 2
fi
if [ ! -x "$notebook_folder/.venv/bin/jupyter" ]; then
    echo "Run setup_environment.sh first." >&2
    exit 2
fi
work_folder="$notebook_folder/_evaluation_work"
export JUPYTER_CONFIG_DIR="$work_folder/jupyter-config"
export JUPYTER_DATA_DIR="$work_folder/jupyter-data"
export JUPYTER_RUNTIME_DIR="$work_folder/runtime"
export IPYTHONDIR="$work_folder/ipython"
export MPLCONFIGDIR="$work_folder/mpl"
export XDG_CACHE_HOME="$work_folder/cache"
export TMPDIR="$work_folder/tmp"
for folder in "$JUPYTER_CONFIG_DIR" "$JUPYTER_DATA_DIR" "$JUPYTER_RUNTIME_DIR" "$IPYTHONDIR" "$MPLCONFIGDIR" "$XDG_CACHE_HOME" "$TMPDIR"; do
    mkdir -p "$folder"
done
cd -- "$notebook_folder"
exec "$notebook_folder/.venv/bin/jupyter" lab WISE_Evaluation.ipynb
