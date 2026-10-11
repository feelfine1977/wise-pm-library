"""A minimal reader for XES event logs, used by the two transfer adapters.

It streams the ``<trace>`` elements of a (gzip-compressed) XES file with the
standard library. A document that declares a document type or an entity is
refused before it is parsed, so no entity is ever expanded.
"""

from __future__ import annotations

import gzip
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any
from xml.etree import ElementTree

__all__ = ["iter_traces", "local"]

_PROLOG_BYTES = 65536


def local(tag: str) -> str:
    """The local name of a (possibly namespaced) tag."""
    return tag.rsplit("}", 1)[-1]


def _open(path: Path) -> IO[bytes]:
    if str(path).lower().endswith(".gz"):
        return gzip.open(path, "rb")  # type: ignore[return-value]
    return path.open("rb")


def _refuse_declarations(path: Path) -> None:
    """Refuse a document whose prolog declares a document type or an entity, or has no root element in sight."""
    with _open(path) as stream:
        head = stream.read(_PROLOG_BYTES)
    lowered = head.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("the XES file declares a document type or an entity; such a file is not read")
    if b"<log" not in lowered:
        raise ValueError("the file does not start with an XES <log> element")


def iter_traces(path: str | Path) -> Iterator[Any]:
    """Yield every ``<trace>`` element of an XES file, in file order.

    The element is complete when it is yielded and is released afterwards;
    read what is needed from it before asking for the next one.
    """
    path = Path(path)
    _refuse_declarations(path)
    with _open(path) as stream:
        parser = ElementTree.iterparse(stream, events=("start", "end"))
        _, root = next(parser)
        if local(root.tag) != "log":
            raise ValueError("expected an XES <log> element")
        for event, element in parser:
            if event == "end" and local(element.tag) == "trace":
                yield element
                root.remove(element)
