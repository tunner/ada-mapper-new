#!/usr/bin/env python3
"""
Core mapping generation utilities extracted from gen_mapper.py.

Provides a MapperGenerator that encapsulates parsing caches, nested
record/array handling, dotted source paths, and emission helpers.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Set, Tuple, List

from constants import DEFAULT_SENTINEL

from types_provider import TypesProvider


TypePair = Tuple[str, str]


class MapperGenerator:
    def __init__(
        self,
        provider: "TypesProvider",
        mapping_pairs: Set[TypePair],
    ) -> None:
        self.provider = provider
        self.mapping_pairs: Set[TypePair] = mapping_pairs
        self.needed_array_maps: Set[TypePair] = set()
        self.needed_enum_maps: Set[TypePair] = set()
        self.enum_overrides: Dict[TypePair, Dict[str, str]] = {}
        self.parsed_to: Dict[str, Dict[str, str]] = {}
        self.parsed_from: Dict[str, Dict[str, str]] = {}

    def format_record_lines(
        self, parts: List[Tuple[str, str, Optional[str]]], indent: str = "       "
    ) -> List[str]:
        lines: List[str] = []
        for idx, (dest, expr, comment) in enumerate(parts):
            line = f"{indent}{dest} => {expr}"
            if idx < len(parts) - 1:
                line += ","
            if comment:
                line += f" -- {comment}"
            lines.append(line)
        return lines

    def format_record_aggregate(self, parts: List[Tuple[str, str, Optional[str]]]) -> str:
        """Return a multi-line Ada aggregate for record assignments."""
        if not parts:
            return "( )"
        lines = self.format_record_lines(parts)
        joined = "\n".join(lines)
        return f"(\n{joined}\n    )"

    # Parsing with memoization
    def get_to_fields(self, tname: str) -> Optional[Dict[str, str]]:
        if not tname:
            return None
        if tname in self.parsed_to:
            return self.parsed_to[tname]
        fields = self.provider.get_record_fields("to", tname)
        if fields is not None:
            self.parsed_to[tname] = fields
        return fields

    def get_from_fields(self, tname: str) -> Optional[Dict[str, str]]:
        if not tname:
            return None
        if tname in self.parsed_from:
            return self.parsed_from[tname]
        fields = self.provider.get_record_fields("from", tname)
        if fields is not None:
            self.parsed_from[tname] = fields
        return fields

    # Arrays
    def to_array_elem(self, tname: Optional[str]) -> Optional[str]:
        if not tname:
            return None
        return self.provider.get_array_element_type("to", tname)

    def from_array_elem(self, tname: Optional[str]) -> Optional[str]:
        if not tname:
            return None
        return self.provider.get_array_element_type("from", tname)

    # Dotted source path resolution
    def resolve_src_path_type(self, start_type: str, path: str) -> Optional[str]:
        cur_t = start_type
        for part in path.split('.'):
            field_map = self.get_from_fields(cur_t)
            if not field_map:
                return None
            key = part if part in field_map else next((k for k in field_map if k.lower() == part.lower()), None)
            if not key:
                return None
            cur_t = field_map[key].strip()
        return cur_t

    # Expression builder (records, arrays, scalars)
    def value_expr(self, dst_t: Optional[str], src_t: Optional[str], src_expr: str) -> Tuple[str, Optional[str]]:
        if isinstance(src_expr, str) and src_expr.strip().upper() == DEFAULT_SENTINEL:
            return self.default_expr(dst_t), f"defaulted ({DEFAULT_SENTINEL})"
        # Records: nested aggregate or delegate to Map if explicit mapping exists
        to_fields = self.get_to_fields(dst_t) if dst_t else None
        from_fields = self.get_from_fields(src_t) if src_t else None
        if to_fields and from_fields:
            if src_t and dst_t and (src_t.strip(), dst_t.strip()) in self.mapping_pairs:
                return f"Map({src_expr})", None
            parts: List[Tuple[str, str, Optional[str]]] = []
            for d_name, d_ftype in to_fields.items():
                s_name = d_name if d_name in from_fields else None
                if not s_name:
                    lf = {k.lower(): k for k in from_fields.keys()}
                    s_name = lf.get(d_name.lower())
                if not s_name:
                    parts.append((d_name, f"{d_ftype} ({src_expr})", None))
                    continue
                s_ftype = from_fields[s_name]
                sub_expr, sub_comment = self.value_expr(d_ftype, s_ftype, f"{src_expr}.{s_name}")
                parts.append((d_name, sub_expr, sub_comment))
            return self.format_record_aggregate(parts), None

        # Arrays: delegate to Map and register required overload
        to_elem = self.to_array_elem(dst_t) if dst_t else None
        from_elem = self.from_array_elem(src_t) if src_t else None
        if to_elem and from_elem:
            self.needed_array_maps.add((src_t.strip(), dst_t.strip()))
            return f"Map({src_expr})", None

        # Enums: map by identical literal names when possible, else by position
        to_enums = self.provider.get_enum_literals("to", dst_t) if dst_t else None
        from_enums = self.provider.get_enum_literals("from", src_t) if src_t else None
        if to_enums and from_enums:
            # Defer to a dedicated enum Map overload
            self.needed_enum_maps.add((src_t.strip(), dst_t.strip()))
            return f"Map({src_expr})", None

        # Scalars: cast to destination type if available
        return (f"{dst_t} ({src_expr})" if dst_t else src_expr), None

    # Generate a record mapping function body
    def gen_record_function_body(
        self,
        src_type: str,
        dst_type: str,
        fields: Dict[str, str],
        field_enum_overrides: "Optional[Dict[str, Dict[str, str]]]" = None,
    ) -> str:
        dst_field_types = self.get_to_fields(dst_type) or {}
        src_field_types = self.get_from_fields(src_type) or {}

        associations: List[Tuple[str, str, Optional[str]]] = []
        for dest, src in fields.items():
            d_t = dst_field_types.get(dest)
            if isinstance(src, str) and src.strip().upper() == DEFAULT_SENTINEL:
                associations.append((dest, self.default_expr(d_t), f"defaulted ({DEFAULT_SENTINEL})"))
                continue
            if isinstance(src, str) and '.' in src:
                s_t = self.resolve_src_path_type(src_type, src)
            else:
                s_t = src_field_types.get(src)
            # If this field maps enums and has an explicit override, register it
            if d_t and s_t:
                if self.provider.get_enum_literals("to", d_t) and self.provider.get_enum_literals("from", s_t):
                    pair = (s_t.strip(), d_t.strip())
                    self.needed_enum_maps.add(pair)
                    if field_enum_overrides and dest in field_enum_overrides:
                        overrides = field_enum_overrides[dest]
                        if pair in self.enum_overrides:
                            self.enum_overrides[pair].update(overrides)
                        else:
                            self.enum_overrides[pair] = dict(overrides)
            expr, comment = self.value_expr(d_t, s_t, f"X.{src}")
            associations.append((dest, expr, comment))

        lines = self.format_record_lines(associations)
        if lines:
            body_lines = "\n".join(lines)
            aggregate = f"(\n{body_lines}\n     )"
        else:
            aggregate = "( )"
        return (
            f"   function Map (X : Types_From.{src_type}) return Types_To.{dst_type} is\n"
            f"     {aggregate};\n"
        )

    def default_expr(self, type_name: Optional[str], seen: Optional[Set[str]] = None) -> str:
        if not type_name:
            return "<>"
        type_name = type_name.strip()
        if not type_name:
            return "<>"
        if seen is None:
            seen = set()
        if type_name in seen:
            return f"{type_name}'First"
        seen.add(type_name)

        base_type = type_name.split('(')[0].strip()

        record_fields = self.get_to_fields(base_type)
        if record_fields:
            parts = []
            for fname, ftype in record_fields.items():
                parts.append(f"{fname} => {self.default_expr(ftype, seen)}")
            inner = ",\n         ".join(parts)
            return f"{base_type}'(\n         {inner}\n      )"

        array_elem = self.to_array_elem(base_type)
        if array_elem:
            dims = None
            try:
                dims = self.provider.get_array_dimension("to", base_type)
            except AttributeError:
                dims = None
            elem_default = self.default_expr(array_elem, seen)
            if dims is None:
                dims = 1
            expr = elem_default
            for _ in range(dims):
                expr = f"(others => {expr})"
            return expr if type_name != base_type else f"{base_type}'{expr}"

        enum_literals = self.provider.get_enum_literals("to", base_type)
        if enum_literals:
            return enum_literals[0]

        lowered = base_type.lower()
        if "access" in lowered:
            return "null"

        return f"{base_type}'First"


    # Compute transitive closure for nested array mappings
    def expand_array_pairs_transitively(self) -> None:
        changed = True
        while changed:
            changed = False
            for src_arr, dst_arr in list(self.needed_array_maps):
                src_elem = self.from_array_elem(src_arr)
                dst_elem = self.to_array_elem(dst_arr)
                if src_elem and dst_elem:
                    src_elem2 = self.from_array_elem(src_elem)
                    dst_elem2 = self.to_array_elem(dst_elem)
                    if src_elem2 and dst_elem2:
                        pair = (src_elem, dst_elem)
                        if pair not in self.needed_array_maps:
                            self.needed_array_maps.add(pair)
                            changed = True

    # Array spec/body are implemented in tools/arrays; this class orchestrates only
