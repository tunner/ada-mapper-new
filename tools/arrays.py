#!/usr/bin/env python3
"""
Array-related parsing helpers for Ada .ads files (MVP-level).

Currently supports detecting if a type is an array and extracting its
component (element) type name.
"""
from __future__ import annotations

from pathlib import Path
import re


def parse_array_component_type(ads_path: Path, type_name: str) -> str | None:
    """Return the element type mark of an Ada array type, or None if not an array.

    Looks for a line like:
        type <Name> is array (<index>) of <ElemType>;

    Limitations (acceptable for MVP):
    - Assumes the declaration fits on one line (as in our examples).
    - Doesn't understand private types or renamings.
    """
    text = ads_path.read_text()
    # crude one-line matcher; tolerates extra spaces
    pat = re.compile(
        rf"\btype\s+{re.escape(type_name)}\s+is\s+array\s*\(.*?\)\s*of\s+([^;]+);",
        re.IGNORECASE,
    )
    m = pat.search(text)
    if not m:
        return None
    elem = m.group(1).strip()
    return elem

