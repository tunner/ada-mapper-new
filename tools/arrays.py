#!/usr/bin/env python3
"""
Array-related parsing helpers for Ada .ads files (MVP-level).

Currently supports detecting if a type is an array and extracting its
component (element) type name.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
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


def parse_array_dimension(ads_path: Path, type_name: str) -> int | None:
    text = ads_path.read_text()
    pat = re.compile(
        rf"\btype\s+{re.escape(type_name)}\s+is\s+array\s*\(([^)]*)\)\s*of\s+([^;]+);",
        re.IGNORECASE,
    )
    m = pat.search(text)
    if not m:
        return None
    indexes = m.group(1)
    if not indexes:
        return 1
    return indexes.count(',') + 1


def array_map_spec(src_arr: str, dst_arr: str) -> str:
    """Emit the function spec for an array mapping overload."""
    return f"   function Map (A : Types_From.{src_arr}) return Types_To.{dst_arr};\n"


def array_map_body(mg: Any, src_arr: str, dst_arr: str) -> str:
    """Emit the body for an array mapping overload.

    Depends on the MapperGenerator-like object `mg` providing:
    - from_array_elem(name) -> Optional[str]
    - to_array_elem(name) -> Optional[str]
    - mapping_pairs: set of (from_type, to_type)
    - needed_array_maps: set of (from_array, to_array)
    - get_to_fields(name) / get_from_fields(name)
    """
    src_elem = mg.from_array_elem(src_arr) or ""
    dst_elem = mg.to_array_elem(dst_arr) or ""

    dims = None
    try:
        dims = mg.provider.get_array_dimension("to", dst_arr)
    except AttributeError:
        dims = None
    if not dims:
        dims = 1

    idx_names = ["I", "J", "K", "L", "M"]
    indices = idx_names[:dims]
    access_expr = "A" + ("(" + ", ".join(indices) + ")" if dims > 1 else "(I)")

    elem_expr = f"{dst_elem} ({access_expr})" if dst_elem else access_expr
    to_elem2 = mg.to_array_elem(dst_elem) if dst_elem else None
    from_elem2 = mg.from_array_elem(src_elem) if src_elem else None
    if (src_elem, dst_elem) in mg.mapping_pairs or (src_elem, dst_elem) in mg.needed_array_maps:
        elem_expr = f"Map({access_expr})"
    elif to_elem2 and from_elem2:
        elem_expr = f"Map({access_expr})"
    else:
        try:
            to_fields = mg.get_to_fields(dst_elem) or {}
            from_fields = mg.get_from_fields(src_elem) or {}
            if to_fields and from_fields:
                parts = []
                for d_name, d_ftype in to_fields.items():
                    s_name = d_name if d_name in from_fields else next((k for k in from_fields if k.lower() == d_name.lower()), None)
                    if not s_name:
                        parts.append((d_name, f"{dst_elem} ({access_expr})", None))
                        continue
                    parts.append((d_name, f"{d_ftype} ({access_expr}.{s_name})", None))
                elem_expr = mg.format_record_aggregate(parts)
        except Exception:
            pass

    body_lines = []
    indent = "      "
    for level, idx in enumerate(indices):
        spaces = indent + "   " * level
        range_attr = "R'Range" if level == 0 else f"R'Range({level + 1})"
        body_lines.append(f"{spaces}for {idx} in {range_attr} loop")
    assign_indent = indent + "   " * len(indices)
    dest_indices = ", ".join(indices)
    dest_expr = f"R({dest_indices})" if dims > 1 else "R(I)"
    body_lines.append(f"{assign_indent}{dest_expr} := {elem_expr};")
    for level in reversed(range(len(indices))):
        spaces = indent + "   " * level
        body_lines.append(f"{spaces}end loop;")
    loops_str = "\n".join(body_lines)

    return (
        f"   function Map (A : Types_From.{src_arr}) return Types_To.{dst_arr} is\n"
        f"      R : Types_To.{dst_arr};\n"
        f"   begin\n"
        f"{loops_str}\n"
        f"      return R;\n"
        f"   end Map;\n"
    )
