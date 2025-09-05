#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
from typing import Optional, List, Any


def parse_enum_literals(ads_path: Path, type_name: str) -> Optional[List[str]]:
    """Parse enumeration literal list for a given type.

    Looks for: `type <Name> is (<lit1>, <lit2>, ...);`
    Accepts multiline lists. Returns a list of literal identifiers
    in declared order, or None if not found / not an enum type.
    """
    text = ads_path.read_text()
    # Match from 'type <Name> is' through the closing ')' before ';'
    pat = re.compile(
        rf"\btype\s+{re.escape(type_name)}\s+is\s*\((.*?)\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    m = pat.search(text)
    if not m:
        return None
    body = m.group(1)
    # Split by commas, strip, remove trailing comments/newlines
    lits = []
    for part in body.split(','):
        name = part.strip()
        # Remove anything after '--' Ada comment on the same line
        name = name.split('--', 1)[0].strip()
        if not name:
            continue
        # Enumeration literals are identifiers; keep as-is
        lits.append(name)
    return lits or None


def enum_map_spec(src_enum: str, dst_enum: str) -> str:
    """Emit function spec for enum mapping overload."""
    return f"   function Map (E : Types_From.{src_enum}) return Types_To.{dst_enum};\n"


def enum_map_body(mg: Any, src_enum: str, dst_enum: str) -> str:
    """Emit expression function for enum mapping.

    Prefers by-name mapping when all source literals exist in destination;
    otherwise falls back to positional mapping via 'Val('Pos()).
    """
    to_enums = mg.provider.get_enum_literals("to", dst_enum) or []
    from_enums = mg.provider.get_enum_literals("from", src_enum) or []
    # If an explicit override is provided, use it (source literal -> dest literal)
    override = getattr(mg, "enum_overrides", {}).get((src_enum, dst_enum)) if (src_enum and dst_enum) else None
    expr: str
    dest_names = to_enums or []
    dest_lookup = {n.lower(): n for n in dest_names}

    if override:
        # Build case mapping using overrides; fill unspecified entries by same-name if possible
        parts = []
        for s in from_enums:
            if s in override:
                d = override[s]
            elif s.lower() in dest_lookup:
                d = dest_lookup[s.lower()]
            else:
                raise RuntimeError(f"No enum mapping for source literal '{s}' from {src_enum} to {dst_enum}")
            parts.append(f"when {s} => {d}")
        alts = ", ".join(parts)
        expr = f"(case E is {alts})"
    elif to_enums and from_enums and all(n.lower() in {m.lower() for m in to_enums} for n in from_enums):
        alts = ", ".join([f"when {n} => {n}" for n in from_enums])
        expr = f"(case E is {alts})"
    else:
        # No safe mapping available
        raise RuntimeError(
            f"Enum mapping between {src_enum} and {dst_enum} requires explicit 'enum_map' or matching literal names"
        )
    return (
        f"   function Map (E : Types_From.{src_enum}) return Types_To.{dst_enum} is\n"
        f"     {expr};\n"
    )
