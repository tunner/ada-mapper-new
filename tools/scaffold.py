#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import re

from types_provider import TypesProvider


@dataclass
class MappingRequest:
    name: str
    to_type: str
    from_type: Optional[str] = None


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
            requests.append(MappingRequest(name=name, to_type=to_type, from_type=actual_from))

        suggestions = self.build_map(requests, preferred_names=preferred_names)["mappings"]
        suggestion_by_to = {entry["to"]: entry for entry in suggestions}
        existing_by_to = {str(entry.get("to")): entry for entry in mappings if isinstance(entry, dict) and entry.get("to")}

        changed = False
        for to_type, suggestion in suggestion_by_to.items():
            existing = existing_by_to.get(to_type)
            if existing:
                # update 'from'
                sugg_from = suggestion.get("from")
                if self.is_placeholder(existing.get("from")) and isinstance(sugg_from, str) and not self.is_placeholder(sugg_from):
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
            else:
                mappings.append(suggestion)
                changed = True

        return changed

    def _build_entry(self, req: MappingRequest) -> Tuple[Dict[str, object], List[MappingRequest]]:
        to_type = req.to_type.strip()
        dest_fields = self.provider.get_record_fields("to", to_type) or {}
        dest_enum_literals = self.provider.get_enum_literals("to", to_type) or []

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
        from_fields = self.provider.get_record_fields("from", source_type) if source_type else None
        from_fields = from_fields or {}
        from_lookup = {name.lower(): name for name in from_fields.keys()}

        fields: Dict[str, object] = {}
        nested_requests: List[MappingRequest] = []

        for dest_name, dest_mark_raw in dest_fields.items():
            dest_mark = dest_mark_raw.strip()
            src_name = None
            src_mark = None
            if dest_name.lower() in from_lookup:
                src_name = from_lookup[dest_name.lower()]
                src_mark = from_fields.get(src_name)

            if src_name:
                fields[dest_name] = src_name
            else:
                fields[dest_name] = self._field_placeholder(dest_name)

            # Nested record mapping
            if self.provider.get_record_fields("to", dest_mark):
                nested_from_type = src_mark.strip() if src_mark else None
                if nested_from_type and not self.provider.get_record_fields("from", nested_from_type):
                    nested_from_type = None
                if not nested_from_type and self.provider.get_record_fields("from", dest_mark):
                    nested_from_type = dest_mark
                nested_name = self._preferred_names.get(dest_mark) or self._default_name(dest_mark)
                nested_requests.append(MappingRequest(name=nested_name, to_type=dest_mark, from_type=nested_from_type))
                continue

            # Nested array mapping (focus on element records)
            elem_type = self.provider.get_array_element_type("to", dest_mark)
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

            # Enum mapping scaffold
            elif self.provider.get_enum_literals("to", dest_mark):
                src_enum_type = None
                if source_type and self.provider.get_enum_literals("from", source_type):
                    src_enum_type = source_type
                elif self.provider.get_enum_literals("from", dest_mark):
                    src_enum_type = dest_mark
                nested_name = self._preferred_names.get(dest_mark) or self._default_name(dest_mark)
                nested_requests.append(
                    MappingRequest(name=nested_name, to_type=dest_mark, from_type=src_enum_type)
                )

        entry = {
            "name": self._preferred_names.get(to_type, req.name),
            "from": from_value,
            "to": to_type,
            "fields": fields,
        }
        return entry, nested_requests

    def _has_supported_type(self, domain: str, type_name: str) -> bool:
        if not type_name:
            return False
        if self.provider.get_record_fields(domain, type_name):
            return True
        if self.provider.get_array_element_type(domain, type_name):
            return True
        if self.provider.get_enum_literals(domain, type_name):
            return True
        return False
