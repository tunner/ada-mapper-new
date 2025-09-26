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

    Missing literals default to a by-name mapping (case-insensitive).
    Explicit overrides supplied via JSON can be partial; only the differing
    literals need to be listed. Raises if a literal cannot be resolved.
    """
    to_enums = mg.provider.get_enum_literals("to", dst_enum) or []
    from_enums = mg.provider.get_enum_literals("from", src_enum) or []

    if not to_enums or not from_enums:
        raise RuntimeError(
            f"Enum mapping between {src_enum} and {dst_enum} requires visible enum literals"
        )

    dest_lookup = {n.lower(): n for n in to_enums}
    src_lookup = {n.lower(): n for n in from_enums}

    raw_override = getattr(mg, "enum_overrides", {}).get((src_enum, dst_enum)) if (src_enum and dst_enum) else None
    override: dict[str, str] = {}
    if raw_override:
        for raw_src, raw_dst in raw_override.items():
            if not isinstance(raw_src, str) or not isinstance(raw_dst, str):
                raise RuntimeError(
                    f"Enum mapping override for {src_enum} -> {dst_enum} must use string literals"
                )
            src_key = raw_src.strip().lower()
            dst_key = raw_dst.strip().lower()
            if src_key not in src_lookup:
                raise RuntimeError(
                    f"Enum mapping override references unknown literal '{raw_src}' in {src_enum}"
                )
            if dst_key not in dest_lookup:
                raise RuntimeError(
                    f"Enum mapping override targets unknown literal '{raw_dst}' in {dst_enum}"
                )
            override[src_lookup[src_key]] = dest_lookup[dst_key]

    parts = []
    missing: list[str] = []
    for literal in from_enums:
        target = override.get(literal)
        if target is None:
            target = dest_lookup.get(literal.lower())
        if target is None:
            missing.append(literal)
            continue
        parts.append(f"when {literal} => {target}")

    if missing:
        missing_desc = ", ".join(missing)
        raise RuntimeError(
            f"Enum mapping between {src_enum} and {dst_enum} is missing mapping for: {missing_desc}. "
            "Add enum_map entries for these literals or align the enum names."
        )

    alts = ", ".join(parts)
    expr = f"(case E is {alts})"
    return (
        f"   function Map (E : Types_From.{src_enum}) return Types_To.{dst_enum} is\n"
        f"     {expr};\n"
    )
