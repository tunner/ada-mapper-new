#!/usr/bin/env python3
"""
Lightweight Ada record parser utilities for the generator.

Module renamed to `records.py` to align with `arrays.py` naming.

Currently provides:
- parse_record_components(ads_path, type_name) -> {field_name: type_mark}

Parsing is intentionally simple and line-oriented for MVP purposes.
"""
from __future__ import annotations

from pathlib import Path
import re


def parse_record_components(ads_path: Path, type_name: str) -> dict[str, str]:
    """Extract a mapping of field name to type for a given record type.

    Assumptions:
    - The file contains 'type <Name> is record' ... 'end record;'
    - Fields are on single lines in the form: 'Name : Type;'
    - No nested records in the same declaration block.
    """
    text = ads_path.read_text()
    start_re = re.compile(rf"\btype\s+{re.escape(type_name)}\s+is\s+record\b", re.IGNORECASE)
    end_re = re.compile(r"\bend\s+record\s*;", re.IGNORECASE)
    field_re = re.compile(r"^\s*([A-Za-z]\w*)\s*:\s*([^;]+);\s*$")

    in_block = False
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not in_block:
            if start_re.search(line):
                in_block = True
            continue
        if end_re.search(line):
            break
        m = field_re.match(line)
        if m:
            fname = m.group(1).strip()
            ftype = m.group(2).strip()
            fields[fname] = ftype
    if not fields:
        raise RuntimeError(f"Could not parse fields for type {type_name} in {ads_path}")
    return fields
