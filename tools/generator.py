#!/usr/bin/env python3
"""
Core mapping generation utilities extracted from gen_mapper.py.

Provides a MapperGenerator that encapsulates parsing caches, nested
record/array handling, dotted source paths, and emission helpers.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Set, Tuple

from parser import parse_record_components
from arrays import parse_array_component_type


TypePair = Tuple[str, str]


class MapperGenerator:
    def __init__(
        self,
        types_from_ads: Path,
        types_to_ads: Path,
        mapping_pairs: Set[TypePair],
    ) -> None:
        self.types_from_ads = types_from_ads
        self.types_to_ads = types_to_ads
        self.mapping_pairs: Set[TypePair] = mapping_pairs
        self.needed_array_maps: Set[TypePair] = set()
        self.parsed_to: Dict[str, Dict[str, str]] = {}
        self.parsed_from: Dict[str, Dict[str, str]] = {}

    # Parsing with memoization
    def get_to_fields(self, tname: str) -> Optional[Dict[str, str]]:
        if not tname:
            return None
        if tname in self.parsed_to:
            return self.parsed_to[tname]
        try:
            fields = parse_record_components(self.types_to_ads, tname)
        except Exception:
            fields = None
        if fields is not None:
            self.parsed_to[tname] = fields
        return fields

    def get_from_fields(self, tname: str) -> Optional[Dict[str, str]]:
        if not tname:
            return None
        if tname in self.parsed_from:
            return self.parsed_from[tname]
        try:
            fields = parse_record_components(self.types_from_ads, tname)
        except Exception:
            fields = None
        if fields is not None:
            self.parsed_from[tname] = fields
        return fields

    # Arrays
    def to_array_elem(self, tname: Optional[str]) -> Optional[str]:
        if not tname:
            return None
        return parse_array_component_type(self.types_to_ads, tname)

    def from_array_elem(self, tname: Optional[str]) -> Optional[str]:
        if not tname:
            return None
        return parse_array_component_type(self.types_from_ads, tname)

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
    def value_expr(self, dst_t: Optional[str], src_t: Optional[str], src_expr: str) -> str:
        # Records: nested aggregate or delegate to Map if explicit mapping exists
        to_fields = self.get_to_fields(dst_t) if dst_t else None
        from_fields = self.get_from_fields(src_t) if src_t else None
        if to_fields and from_fields:
            if src_t and dst_t and (src_t.strip(), dst_t.strip()) in self.mapping_pairs:
                return f"Map({src_expr})"
            parts = []
            for d_name, d_ftype in to_fields.items():
                s_name = d_name if d_name in from_fields else None
                if not s_name:
                    lf = {k.lower(): k for k in from_fields.keys()}
                    s_name = lf.get(d_name.lower())
                if not s_name:
                    parts.append(f"{d_name} => {d_ftype} ({src_expr})")
                    continue
                s_ftype = from_fields[s_name]
                sub_expr = self.value_expr(d_ftype, s_ftype, f"{src_expr}.{s_name}")
                parts.append(f"{d_name} => {sub_expr}")
            return f"( {', '.join(parts)} )"

        # Arrays: delegate to Map and register required overload
        to_elem = self.to_array_elem(dst_t) if dst_t else None
        from_elem = self.from_array_elem(src_t) if src_t else None
        if to_elem and from_elem:
            self.needed_array_maps.add((src_t.strip(), dst_t.strip()))
            return f"Map({src_expr})"

        # Scalars: cast to destination type if available
        return f"{dst_t} ({src_expr})" if dst_t else src_expr

    # Generate a record mapping function body
    def gen_record_function_body(
        self,
        src_type: str,
        dst_type: str,
        fields: Dict[str, str],
    ) -> str:
        dst_field_types = self.get_to_fields(dst_type) or {}
        src_field_types = self.get_from_fields(src_type) or {}

        associations = []
        for dest, src in fields.items():
            d_t = dst_field_types.get(dest)
            if isinstance(src, str) and '.' in src:
                s_t = self.resolve_src_path_type(src_type, src)
            else:
                s_t = src_field_types.get(src)
            expr = self.value_expr(d_t, s_t, f"X.{src}")
            associations.append(f"{dest} => {expr}")

        joined = ",\n       ".join(associations)
        return (
            f"   function Map (X : Types_From.{src_type}) return Types_To.{dst_type} is\n"
            f"     ( {joined} );\n"
        )

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

    # Emit array map spec line
    @staticmethod
    def array_map_spec(src_arr: str, dst_arr: str) -> str:
        return f"   function Map (A : Types_From.{src_arr}) return Types_To.{dst_arr};\n"

    # Emit array map body
    def array_map_body(self, src_arr: str, dst_arr: str) -> str:
        src_elem = self.from_array_elem(src_arr) or ""
        dst_elem = self.to_array_elem(dst_arr) or ""
        elem_expr = f"{dst_elem} (A(I))" if dst_elem else "A(I)"
        to_elem2 = self.to_array_elem(dst_elem) if dst_elem else None
        from_elem2 = self.from_array_elem(src_elem) if src_elem else None
        if (src_elem, dst_elem) in self.mapping_pairs or (src_elem, dst_elem) in self.needed_array_maps:
            elem_expr = "Map(A(I))"
        elif to_elem2 and from_elem2:
            elem_expr = "Map(A(I))"
        else:
            try:
                to_fields = self.get_to_fields(dst_elem) or {}
                from_fields = self.get_from_fields(src_elem) or {}
                if to_fields and from_fields:
                    parts = []
                    for d_name, d_ftype in to_fields.items():
                        s_name = d_name if d_name in from_fields else next((k for k in from_fields if k.lower() == d_name.lower()), None)
                        if not s_name:
                            parts.append(f"{d_name} => {dst_elem} (A(I))")
                            continue
                        parts.append(f"{d_name} => {d_ftype} (A(I).{s_name})")
                    elem_expr = f"( {', '.join(parts)} )"
            except Exception:
                pass

        return (
            f"   function Map (A : Types_From.{src_arr}) return Types_To.{dst_arr} is\n"
            f"      R : Types_To.{dst_arr};\n"
            f"   begin\n"
            f"      for I in R'Range loop\n"
            f"         R(I) := {elem_expr};\n"
            f"      end loop;\n"
            f"      return R;\n"
            f"   end Map;\n"
        )

