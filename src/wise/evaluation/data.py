"""The input catalogue: which public logs the evaluation reads, and the check before a log is read.

``data_catalog.json`` records, for each of the three applications of the
paper, the source identity of its log and the size and SHA-256 of the one
file the adapter reads. No log is part of this repository. The user supplies
a folder; a file is looked up in it by name (case-insensitive, at any depth)
and is read only after its size and checksum match the catalogue.

The folder is given as the ``data`` argument of the evaluation functions or
through the environment variable ``WISE_PAPER_DATA``.

Command line::

    python -m wise.evaluation.data --data <folder>

prints, per log, whether it was found and verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

__all__ = [
    "DATA_ENVIRONMENT",
    "DataMismatch",
    "DataNotAvailable",
    "available",
    "catalogue",
    "data_folder",
    "entry",
    "locate",
    "sha256",
    "verify",
]

DATA_ENVIRONMENT = "WISE_PAPER_DATA"


class DataNotAvailable(FileNotFoundError):
    """A log of the catalogue is not in the data folder, or no data folder was given."""


class DataMismatch(ValueError):
    """A file with the catalogue's name has another size or checksum than the catalogue records."""


@lru_cache(maxsize=1)
def catalogue() -> dict[str, Any]:
    """The input catalogue (``data_catalog.json``)."""
    text = resources.files(__package__).joinpath("data_catalog.json").read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def entry(dataset: str) -> dict[str, Any]:
    """The catalogue entry of one log (``"bpic2019"``, ``"bpic2013_incidents"``, ``"bpic2017"``)."""
    for item in catalogue()["datasets"]:
        if item["id"] == dataset:
            found: dict[str, Any] = item
            return found
    raise KeyError(f"unknown dataset {dataset!r}; known: {[d['id'] for d in catalogue()['datasets']]}")


def sha256(path: str | Path) -> str:
    """SHA-256 of a file, read in blocks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def data_folder(data: str | Path | None = None) -> Path:
    """The folder that holds the logs: ``data``, or the environment variable ``WISE_PAPER_DATA``."""
    chosen = data if data is not None else os.environ.get(DATA_ENVIRONMENT)
    if chosen is None or str(chosen) == "":
        raise DataNotAvailable(
            f"no data folder given: pass the folder that holds the public logs as `data`, or set {DATA_ENVIRONMENT}"
        )
    folder = Path(chosen)
    if not folder.is_dir():
        raise DataNotAvailable("the data folder does not exist or is not a folder")
    return folder


@lru_cache(maxsize=32)
def _verified(folder: str, dataset: str) -> Path:
    item = entry(dataset)["file"]
    wanted = item["name"].lower()
    candidates = sorted(p for p in Path(folder).rglob("*") if p.name.lower() == wanted and p.is_file())
    if not candidates:
        raise DataNotAvailable(
            f"{item['name']} is not in the data folder (log {dataset!r}); see the README for where to obtain it"
        )
    for path in candidates:
        if path.stat().st_size == item["bytes"] and sha256(path) == item["sha256"]:
            return path
    raise DataMismatch(
        f"{item['name']} was found, but its size or SHA-256 differs from the catalogue "
        f"({item['bytes']:,} bytes, {item['sha256']}); a different export needs its own adapter configuration"
    )


def locate(dataset: str, data: str | Path | None = None) -> Path:
    """The verified input file of one log.

    Raises :class:`DataNotAvailable` when the file is not in the folder and
    :class:`DataMismatch` when a file of that name has another size or
    checksum. The check is made once per session and folder.
    """
    return _verified(str(data_folder(data)), dataset)


def available(dataset: str, data: str | Path | None = None) -> bool:
    """Whether the verified input of a log is in the data folder."""
    try:
        locate(dataset, data)
    except DataNotAvailable:
        return False
    return True


def verify(data: str | Path | None = None) -> list[dict[str, Any]]:
    """Per log of the catalogue: file name, size, checksum and whether the folder holds the verified file."""
    rows = []
    for item in catalogue()["datasets"]:
        row = {
            "dataset": item["id"],
            "file": item["file"]["name"],
            "bytes": item["file"]["bytes"],
            "sha256": item["file"]["sha256"],
        }
        try:
            locate(item["id"], data)
            row["status"] = "verified"
        except DataNotAvailable:
            row["status"] = "not in the data folder"
        except DataMismatch:
            row["status"] = "found with another size or checksum"
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the public logs in a data folder against the input catalogue.")
    parser.add_argument("--data", type=Path, default=None, help=f"folder with the logs (default: ${DATA_ENVIRONMENT})")
    args = parser.parse_args(argv)
    rows = verify(args.data)
    for row in rows:
        print(f"{row['dataset']:<20} {row['file']:<40} {row['status']}")
    return 0 if all(row["status"] == "verified" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
