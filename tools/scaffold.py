#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
import re

from constants import DEFAULT_SENTINEL
from types_provider import TypesProvider


@dataclass
class MappingRequest:
    name: str
    to_type: str
    from_type: Optional[str] = None
    existing_fields: Optional[Dict[str, object]] = None


class MappingScaffolder:
    """Generate or update mapping.json scaffolds based on Ada spec types."""

    def __init__(self, provider: TypesProvider) -> None:
        self.provider = provider
        self._processed: set[Tuple[str, str]] = set()
        self._preferred_names: Dict[str, str] = {}

    @staticmethod
    def _default_name(type_name: str) -> str:
        if type_name.upper().startswith("T_") and len(type_name) > 2:
            return type_name[2:]
        return type_name

    @staticmethod
    def _field_placeholder(field_name: str) -> str:
        token = re.sub(r"[^A-Za-z0-9]+", "_", field_name.upper()).strip("_")
        if not token:
            token = "FIELD"
        return f"<{token}_INPUT_FIELD>"

    @staticmethod
    def _from_placeholder(type_name: str) -> str:
        token = re.sub(r"[^A-Za-z0-9]+", "_", type_name.upper()).strip("_")
        if not token:
            token = "TYPE"
        return f"<SOURCE_TYPE_FOR_{token}>"

    @staticmethod
    def is_placeholder(value: object) -> bool:
        return isinstance(value, str) and value.startswith("<") and value.endswith(">")

    def build_map(self, requests: List[MappingRequest], preferred_names: Optional[Dict[str, str]] = None) -> Dict[str, List[Dict[str, object]]]:
        queue: List[MappingRequest] = list(requests)
        self._processed = set()
        self._preferred_names = dict(preferred_names or {})
        for req in requests:
            self._preferred_names.setdefault(req.to_type, req.name)
        result: List[Dict[str, object]] = []

        while queue:
            req = queue.pop(0)
            to_type = req.to_type.strip()
            from_key = (req.from_type or "").strip()
            key = (from_key, to_type)
            if key in self._processed:
                continue
            entry, nested_requests = self._build_entry(req)
            self._processed.add(key)
            result.append(entry)
            for nested in nested_requests:
                self._preferred_names.setdefault(nested.to_type, nested.name)
                queue.append(nested)

        return {"mappings": result}

    def update_map(self, data: Dict[str, object]) -> bool:
        mappings = data.get("mappings")
        if not isinstance(mappings, list):
            return False

        preferred_names = {}
        requests: List[MappingRequest] = []
        for entry in mappings:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")) or self._default_name(str(entry.get("to", "")))
            to_type = str(entry.get("to", "")).strip()
            if not to_type:
                continue
            preferred_names[to_type] = name
            from_value = entry.get("from")
            actual_from: Optional[str] = None
            if isinstance(from_value, str) and not self.is_placeholder(from_value):
                if self._has_supported_type("from", from_value):
                    actual_from = from_value
            if self._entry_all_placeholders(entry):
                continue
            requests.append(
                MappingRequest(
                    name=name,
                    to_type=to_type,
                    from_type=actual_from,
                    existing_fields=entry.get("fields") if isinstance(entry.get("fields"), dict) else None,
                )
            )

        suggestions = self.build_map(requests, preferred_names=preferred_names)["mappings"]
        suggestion_by_to = {entry["to"]: entry for entry in suggestions}
        existing_by_to = {str(entry.get("to")): entry for entry in mappings if isinstance(entry, dict) and entry.get("to")}

        changed = False
        for to_type, suggestion in suggestion_by_to.items():
            existing = existing_by_to.get(to_type)
            if existing:
                # update 'from'
                sugg_from = suggestion.get("from")
                existing_from = existing.get("from")
                if (
                    isinstance(sugg_from, str)
                    and self.is_placeholder(existing_from)
                    and not self.is_placeholder(sugg_from)
                ):
                    existing["from"] = sugg_from
                    changed = True
                elif (
                    isinstance(sugg_from, str)
                    and not self.is_placeholder(sugg_from)
                    and isinstance(existing_from, str)
                    and not self.is_placeholder(existing_from)
                    and existing_from != sugg_from
                ):
                    existing["from"] = sugg_from
                    changed = True
                elif (
                    isinstance(sugg_from, str)
                    and self.is_placeholder(sugg_from)
                    and isinstance(existing_from, str)
                    and not self.is_placeholder(existing_from)
                ):
                    existing["from"] = sugg_from
                    changed = True
                # update fields selectively
                existing_fields = existing.setdefault("fields", {})
                if isinstance(existing_fields, dict):
                    for field_name, sugg_value in suggestion.get("fields", {}).items():
                        current_value = existing_fields.get(field_name)
                        if (current_value is None or self.is_placeholder(current_value)) and not self.is_placeholder(sugg_value):
                            existing_fields[field_name] = sugg_value
                            changed = True
                        elif (
                            isinstance(sugg_value, str)
                            and self.is_placeholder(sugg_value)
                            and isinstance(current_value, str)
                            and not self.is_placeholder(current_value)
                        ):
                            existing_fields[field_name] = sugg_value
                            changed = True
            else:
                mappings.append(suggestion)
                changed = True

        # Remove entries that are no longer suggested at all
        obsolete = set(existing_by_to.keys()) - set(suggestion_by_to.keys())
        if obsolete:
            new_list = [entry for entry in mappings if str(entry.get("to")) not in obsolete]
            if len(new_list) != len(mappings):
                mappings[:] = new_list
                changed = True

        return changed

    def _build_entry(self, req: MappingRequest) -> Tuple[Dict[str, object], List[MappingRequest]]:
        to_type = req.to_type.strip()
        dest_fields_raw = self.provider.get_record_fields("to", to_type)
        dest_fields = dest_fields_raw or {}
        dest_enum_literals = self.provider.get_enum_literals("to", to_type) or []

        if dest_fields_raw is None and not dest_enum_literals:
            raise ValueError(
                f"Unable to scaffold mapping '{req.name}': destination type '{to_type}' is not a record or enum in destination specs"
            )

        existing_fields = req.existing_fields or {}

        source_type = req.from_type.strip() if req.from_type else None
        if source_type and not self._has_supported_type("from", source_type):
            source_type = None
        if not source_type and self._has_supported_type("from", to_type):
            source_type = to_type

        # Enum mapping entry
        if dest_enum_literals and not dest_fields:
            from_value = source_type if source_type else self._from_placeholder(to_type)
            src_literals = (
                self.provider.get_enum_literals("from", source_type)
                if source_type
                else None
            ) or []
            src_lookup = {lit.lower(): lit for lit in src_literals}
            fields: Dict[str, object] = {}
            for lit in dest_enum_literals:
                existing = existing_fields.get(lit)
                if isinstance(existing, str) and not self.is_placeholder(existing):
                    fields[lit] = existing
                    continue
                match = src_lookup.get(lit.lower())
                fields[lit] = match if match else self._field_placeholder(lit)
            entry = {
                "name": self._preferred_names.get(to_type, req.name),
                "from": from_value,
                "to": to_type,
                "fields": fields,
            }
            return entry, []

        from_value = source_type if source_type else self._from_placeholder(to_type)
        from_fields_raw = self.provider.get_record_fields("from", source_type) if source_type else None
        from_fields = from_fields_raw or {}
        from_lookup = {name.lower(): name for name in from_fields.keys()}

        fields: Dict[str, object] = {}
        nested_requests: List[MappingRequest] = []

        for dest_name, dest_mark_raw in dest_fields.items():
            dest_mark = dest_mark_raw.strip()
            existing_spec = existing_fields.get(dest_name)
            src_name = None
            src_mark = None
            spec_value: Optional[object] = None

            if isinstance(existing_spec, str):
                spec_clean = existing_spec.strip()
                if self.is_placeholder(spec_clean):
                    existing_spec = None
                elif spec_clean.upper() == DEFAULT_SENTINEL:
                    spec_value = DEFAULT_SENTINEL
                else:
                    spec_value = existing_spec
                    src_name = from_lookup.get(spec_clean.lower())
                    if src_name:
                        src_mark = from_fields.get(src_name)
            elif isinstance(existing_spec, dict):
                src_ref = existing_spec.get("from") or existing_spec.get("source") or existing_spec.get("path")
                if isinstance(src_ref, str) and not self.is_placeholder(src_ref):
                    spec_value = existing_spec
                    src_name = from_lookup.get(src_ref.lower())
                    if src_name:
                        src_mark = from_fields.get(src_name)
                else:
                    existing_spec = None
            else:
                if dest_name.lower() in from_lookup:
                    src_name = from_lookup[dest_name.lower()]
                    src_mark = from_fields.get(src_name)
                    spec_value = src_name

            if spec_value is None:
                if src_name is None and dest_name.lower() in from_lookup:
                    src_name = from_lookup[dest_name.lower()]
                    src_mark = from_fields.get(src_name)
                    spec_value = src_name
                if spec_value is None:
                    spec_value = self._field_placeholder(dest_name)

            dest_record_fields = self.provider.get_record_fields("to", dest_mark)
            elem_type = self.provider.get_array_element_type("to", dest_mark)
            dest_enum = self.provider.get_enum_literals("to", dest_mark)

            if isinstance(spec_value, str) and self.is_placeholder(spec_value):
                suggestion = None
                if elem_type:
                    suggestion = self._find_array_source_path(
                        source_type, dest_name, dest_mark, elem_type
                    )
                if suggestion:
                    suggested_path, suggested_type = suggestion
                    resolved_type = self._resolve_path_type(source_type, suggested_path)
                    if resolved_type:
                        spec_value = suggested_path
                        src_mark = resolved_type

            fields[dest_name] = spec_value

            # Nested record mapping
            if isinstance(spec_value, str) and spec_value.upper() == DEFAULT_SENTINEL:
                continue

            src_mark_clean = src_mark.strip() if isinstance(src_mark, str) else None
            src_record_fields = (
                self.provider.get_record_fields("from", src_mark_clean)
                if src_mark_clean
                else None
            )
            if dest_record_fields is not None:
                nested_from_type = src_mark.strip() if src_mark else None
                if nested_from_type and not self.provider.get_record_fields("from", nested_from_type):
                    nested_from_type = None
                if not nested_from_type and self.provider.get_record_fields("from", dest_mark):
                    nested_from_type = dest_mark
                nested_name = self._preferred_names.get(dest_mark) or self._default_name(dest_mark)
                nested_requests.append(MappingRequest(name=nested_name, to_type=dest_mark, from_type=nested_from_type))
                continue
            if src_record_fields is not None:
                raise ValueError(
                    f"Unable to scaffold mapping '{req.name}': field '{dest_name}' references destination type '{dest_mark}' which could not be parsed as a record"
                )

            # Nested array mapping (focus on element records)
            if elem_type:
                src_elem_type = None
                if src_mark:
                    src_elem_type = self.provider.get_array_element_type("from", src_mark.strip())
                if src_elem_type and not self._has_supported_type("from", src_elem_type):
                    src_elem_type = None
                if not src_elem_type and self.provider.get_record_fields("from", elem_type):
                    src_elem_type = elem_type
                if self.provider.get_record_fields("to", elem_type):
                    nested_name = self._preferred_names.get(elem_type) or self._default_name(elem_type)
                    nested_requests.append(
                        MappingRequest(name=nested_name, to_type=elem_type, from_type=src_elem_type)
                    )
                continue
            if src_mark_clean and self.provider.get_array_element_type("from", src_mark_clean):
                raise ValueError(
                    f"Unable to scaffold mapping '{req.name}': field '{dest_name}' references destination array type '{dest_mark}' which could not be parsed"
                )

            # Enum mapping scaffold
            if dest_enum:
                src_enum_type = None
                if src_mark and self.provider.get_enum_literals("from", src_mark.strip()):
                    src_enum_type = src_mark.strip()
                elif source_type and self.provider.get_enum_literals("from", source_type):
                    src_enum_type = source_type
                elif self.provider.get_enum_literals("from", dest_mark):
                    src_enum_type = dest_mark
                nested_name = self._preferred_names.get(dest_mark) or self._default_name(dest_mark)
                nested_fields = None
                if isinstance(existing_spec, dict) and isinstance(existing_spec.get("fields"), dict):
                    nested_fields = existing_spec["fields"]
                nested_requests.append(
                    MappingRequest(
                        name=nested_name,
                        to_type=dest_mark,
                        from_type=src_enum_type,
                        existing_fields=nested_fields,
                    )
                )
                continue
            if src_mark_clean and self.provider.get_enum_literals("from", src_mark_clean):
                raise ValueError(
                    f"Unable to scaffold mapping '{req.name}': field '{dest_name}' references destination enum type '{dest_mark}' which could not be parsed"
                )

        entry = {
            "name": self._preferred_names.get(to_type, req.name),
            "from": from_value,
            "to": to_type,
            "fields": fields,
        }
        return entry, nested_requests

    @staticmethod
    def _canonical_name(value: Optional[str]) -> str:
        if not value:
            return ""
        base = value.split(".")[-1].lower()
        base = re.sub(r"^(?:t_|e_|p_|fr_|fs_|gs_|l_|r_|m_|n_)", "", base)
        return base

    def _resolve_path_type(self, root_type: Optional[str], path: str) -> Optional[str]:
        if not root_type or not path:
            return None
        current = root_type
        for segment in path.split('.'):
            fields = self.provider.get_record_fields("from", current)
            if not fields:
                return None
            mark = fields.get(segment)
            if mark is None:
                lowered = segment.lower()
                for name, candidate in fields.items():
                    if name.lower() == lowered:
                        mark = candidate
                        break
            if mark is None:
                return None
            current = mark.strip()
        return current

    def _find_array_source_path(
        self,
        source_type: Optional[str],
        dest_field_name: str,
        dest_array_type: str,
        dest_element_type: Optional[str],
    ) -> Optional[Tuple[str, str]]:
        if not source_type:
            return None
        target_array_canon = self._canonical_name(dest_array_type)
        target_elem_canon = self._canonical_name(dest_element_type)
        dest_field_canon = self._canonical_name(dest_field_name)
        visited: Set[str] = set()

        def visit(type_name: str, prefix: str) -> Optional[Tuple[str, str, int]]:
            fields = self.provider.get_record_fields("from", type_name)
            if not fields:
                return None
            best: Optional[Tuple[str, str, int]] = None
            for field, mark in fields.items():
                mark_clean = mark.strip()
                path = f"{prefix}{field}" if prefix else field
                array_elem = self.provider.get_array_element_type("from", mark_clean)
                if array_elem:
                    field_canon = self._canonical_name(field)
                    array_canon = self._canonical_name(mark_clean)
                    elem_canon = self._canonical_name(array_elem)
                    score = 0
                    if field_canon == dest_field_canon:
                        score = 3
                    elif array_canon == target_array_canon:
                        score = 2
                    elif target_elem_canon and elem_canon == target_elem_canon:
                        score = 1
                    if score > 0:
                        candidate = (path, mark_clean, score)
                        if not best or candidate[2] > best[2]:
                            best = candidate
                record_fields = self.provider.get_record_fields("from", mark_clean)
                if record_fields is not None and mark_clean not in visited:
                    visited.add(mark_clean)
                    child = visit(mark_clean, f"{path}.")
                    if child and (not best or child[2] > best[2]):
                        best = child
            return best

        visited.add(source_type)
        result = visit(source_type, "")
        if result:
            return result[0], result[1]
        return None

    def _has_supported_type(self, domain: str, type_name: str) -> bool:
        if not type_name:
            return False
        record_fields = self.provider.get_record_fields(domain, type_name)
        if record_fields is not None:
            return True
        if self.provider.get_array_element_type(domain, type_name):
            return True
        if self.provider.get_enum_literals(domain, type_name):
            return True
        return False

    def _entry_all_placeholders(self, entry: Dict[str, object]) -> bool:
        from_value = entry.get("from")
        if isinstance(from_value, str) and not (self.is_placeholder(from_value) or from_value.strip().upper() == DEFAULT_SENTINEL):
            return False
        fields = entry.get("fields")
        if not isinstance(fields, dict):
            return True
        for value in fields.values():
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned and not self.is_placeholder(cleaned) and cleaned.upper() != DEFAULT_SENTINEL:
                    return False
            elif isinstance(value, dict):
                return False
        return True
