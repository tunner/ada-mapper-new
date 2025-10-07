#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Protocol, List
import re


class TypesProvider(Protocol):
    def get_record_fields(self, domain: str, type_name: str) -> Optional[Dict[str, str]]:
        ...

    def get_array_element_type(self, domain: str, type_name: str) -> Optional[str]:
        ...

    def get_enum_literals(self, domain: str, type_name: str) -> Optional[List[str]]:
        ...

    def get_array_dimension(self, domain: str, type_name: str) -> Optional[int]:
        ...


class AdaSpecIndex:
    """Minimal index of an Ada package spec that keeps package-qualified type info."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.text = path.read_text()
        self.root: Optional[str] = None
        self.records: Dict[str, Dict[str, str]] = {}
        self.arrays: Dict[str, str] = {}
        self.array_dims: Dict[str, int] = {}
        self.enums: Dict[str, List[str]] = {}
        self.subtypes: Dict[str, str] = {}
        self.declared_types: set[str] = set()
        self._parse()

    def _current_segments(self, stack: List[str]) -> List[str]:
        if not stack:
            return []
        if self.root and stack[0].lower() == self.root.lower():
            return [seg for seg in stack[1:]]
        return stack[:]

    def _qualified_name(self, stack: List[str], name: str) -> str:
        segments = self._current_segments(stack)
        if segments:
            return ".".join(segments + [name])
        return name

    def _clean_reference(self, ref: str) -> str:
        cleaned = ref.split("--", 1)[0]
        cleaned = re.sub(r"\baliased\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bnot\s+null\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\baccess\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bconstant\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = " ".join(cleaned.split())
        return cleaned.strip()

    def _qualify_name(self, base: str, pkg_segments: List[str]) -> str:
        base = base.strip()
        if self.root and base.startswith(self.root + "."):
            base = base[len(self.root) + 1 :]
        if "." in base:
            return base
        if pkg_segments:
            candidate = ".".join(pkg_segments + [base])
            if candidate in self.declared_types:
                return candidate
        return base

    def _qualify_reference(self, pkg_segments: List[str], ref: str) -> str:
        cleaned = self._clean_reference(ref)
        if not cleaned:
            return cleaned
        suffix = ""
        if "(" in cleaned:
            base, rest = cleaned.split("(", 1)
            suffix = "(" + rest
        else:
            base = cleaned
        qualified_base = self._qualify_name(base.strip(), pkg_segments)
        if suffix:
            return f"{qualified_base} {suffix}"
        return qualified_base

    def normalize_name(self, name: str) -> str:
        cleaned = self._clean_reference(name)
        if not cleaned:
            return cleaned
        cleaned = cleaned.split("(", 1)[0].strip()
        if self.root and cleaned.startswith(self.root + "."):
            cleaned = cleaned[len(self.root) + 1 :]
        return cleaned

    def _parse(self) -> None:
        lines = self.text.splitlines()
        stack: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                i += 1
                continue

            pkg_start = re.match(r"^\s*package\s+([A-Za-z0-9_.]+)\s+is\b", stripped, re.IGNORECASE)
            if pkg_start:
                name = pkg_start.group(1)
                parts = name.split(".")
                if not stack:
                    stack = parts.copy()
                    if not self.root:
                        self.root = parts[0]
                else:
                    if len(parts) == 1:
                        stack.append(parts[0])
                    else:
                        stack = parts.copy()
                        if not self.root:
                            self.root = parts[0]
                i += 1
                continue

            pkg_end = re.match(r"^\s*end\s+([A-Za-z0-9_.]+)?\s*;", stripped, re.IGNORECASE)
            if pkg_end:
                name = pkg_end.group(1)
                if stack:
                    if name:
                        parts = name.split(".")
                        lowered_parts = [p.lower() for p in parts]
                        lowered_stack = [s.lower() for s in stack]
                        if len(lowered_parts) == 1:
                            if lowered_stack and lowered_stack[-1] == lowered_parts[0]:
                                stack.pop()
                        else:
                            if lowered_stack[-len(lowered_parts):] == lowered_parts:
                                stack = stack[:-len(lowered_parts)]
                    else:
                        stack.pop()
                i += 1
                continue

            subtype_match = re.match(r"^\s*subtype\s+([A-Za-z]\w*)\s+is\s+(.+?);", stripped, re.IGNORECASE)
            if subtype_match:
                type_name = subtype_match.group(1)
                base_expr = subtype_match.group(2)
                key = self._qualified_name(stack, type_name)
                qualified = self._qualify_reference(self._current_segments(stack), base_expr)
                self.subtypes[key] = qualified
                self.declared_types.add(key)
                i += 1
                continue

            record_match = re.match(r"^\s*type\s+([A-Za-z]\w*)\s+is\s+record\b", stripped, re.IGNORECASE)
            if record_match:
                type_name = record_match.group(1)
                fields: Dict[str, str] = {}
                j = i + 1
                field_re = re.compile(r"^\s*([A-Za-z]\w*)\s*:\s*([^;]+);")
                current_segments = self._current_segments(stack)
                while j < len(lines):
                    inner = lines[j]
                    if re.search(r"\bend\s+record\b", inner, re.IGNORECASE):
                        break
                    m_field = field_re.match(inner)
                    if m_field:
                        fname = m_field.group(1).strip()
                        ftype = m_field.group(2).split("--", 1)[0].strip()
                        if ftype.lower().startswith("aliased "):
                            ftype = ftype.split(None, 1)[1].strip()
                        fields[fname] = self._qualify_reference(current_segments, ftype)
                    j += 1
                key = self._qualified_name(stack, type_name)
                if fields:
                    self.records[key] = fields
                    self.declared_types.add(key)
                i = j + 1
                continue

            array_match = re.match(
                r"^\s*type\s+([A-Za-z]\w*)\s+is\s+array\s*\(([^)]*)\)\s*of\s+([^;]+);",
                stripped,
                re.IGNORECASE,
            )
            if array_match:
                type_name = array_match.group(1)
                index_text = array_match.group(2)
                component = array_match.group(3)
                key = self._qualified_name(stack, type_name)
                qualified_component = self._qualify_reference(self._current_segments(stack), component)
                self.arrays[key] = qualified_component
                self.array_dims[key] = index_text.count(",") + 1 if index_text.strip() else 1
                self.declared_types.add(key)
                i += 1
                continue

            enum_match = re.match(r"^\s*type\s+([A-Za-z]\w*)\s+is\s*\((.*)", stripped, re.IGNORECASE)
            if enum_match:
                type_name = enum_match.group(1)
                rest = enum_match.group(2)
                body_lines = [rest]
                j = i
                while not re.search(r"\)\s*;", body_lines[-1]) and j + 1 < len(lines):
                    j += 1
                    body_lines.append(lines[j].strip())
                combined = " ".join(body_lines)
                body_match = re.search(r"\((.*)\)", combined, re.DOTALL)
                inner = body_match.group(1) if body_match else combined
                literals: List[str] = []
                for part in inner.split(","):
                    lit = part.strip()
                    lit = lit.split("--", 1)[0].strip()
                    lit = lit.rstrip(");")
                    lit = lit.strip()
                    if lit:
                        literals.append(lit)
                key = self._qualified_name(stack, type_name)
                if literals:
                    self.enums[key] = literals
                    self.declared_types.add(key)
                i = j + 1
                continue

            i += 1

    def resolve_record_fields(self, name: str, seen: set[str]) -> Optional[Dict[str, str]]:
        key = self.normalize_name(name)
        if not key or key in seen:
            return None
        if key in self.records:
            return self.records[key]
        seen.add(key)
        base_expr = self.subtypes.get(key)
        if not base_expr:
            return None
        base_name = self.normalize_name(base_expr)
        if not base_name:
            return None
        return self.resolve_record_fields(base_name, seen)

    def resolve_array_element(self, name: str, seen: set[str]) -> Optional[str]:
        key = self.normalize_name(name)
        if not key or key in seen:
            return None
        if key in self.arrays:
            return self._clean_reference(self.arrays[key])
        seen.add(key)
        base_expr = self.subtypes.get(key)
        if not base_expr:
            return None
        base_name = self.normalize_name(base_expr)
        if not base_name:
            return None
        return self.resolve_array_element(base_name, seen)

    def resolve_array_dimension(self, name: str, seen: set[str]) -> Optional[int]:
        key = self.normalize_name(name)
        if not key or key in seen:
            return None
        if key in self.array_dims:
            return self.array_dims[key]
        seen.add(key)
        base_expr = self.subtypes.get(key)
        if not base_expr:
            return None
        base_name = self.normalize_name(base_expr)
        if not base_name:
            return None
        return self.resolve_array_dimension(base_name, seen)

    def resolve_enum_literals(self, name: str, seen: set[str]) -> Optional[List[str]]:
        key = self.normalize_name(name)
        if not key or key in seen:
            return None
        if key in self.enums:
            return self.enums[key]
        seen.add(key)
        base_expr = self.subtypes.get(key)
        if not base_expr:
            return None
        base_name = self.normalize_name(base_expr)
        if not base_name:
            return None
        return self.resolve_enum_literals(base_name, seen)


class RegexTypesProvider:
    """
    Regex-based provider that reads a pair of .ads files and extracts
    record fields and array element types. Serves as the default provider.
    """

    def __init__(self, types_from_ads: Path, types_to_ads: Path) -> None:
        self.types_from_ads = types_from_ads
        self.types_to_ads = types_to_ads
        self._index_cache: dict[str, AdaSpecIndex] = {}

    def _path(self, domain: str) -> Path:
        if domain == "from":
            return self.types_from_ads
        if domain == "to":
            return self.types_to_ads
        raise ValueError(f"Unknown domain: {domain}")

    def _index(self, domain: str) -> AdaSpecIndex:
        if domain not in self._index_cache:
            self._index_cache[domain] = AdaSpecIndex(self._path(domain))
        return self._index_cache[domain]

    def get_record_fields(self, domain: str, type_name: str) -> Optional[Dict[str, str]]:
        try:
            return self._index(domain).resolve_record_fields(type_name, set())
        except Exception:
            return None

    def get_array_element_type(self, domain: str, type_name: str) -> Optional[str]:
        try:
            return self._index(domain).resolve_array_element(type_name, set())
        except Exception:
            return None

    def get_enum_literals(self, domain: str, type_name: str) -> Optional[List[str]]:
        try:
            return self._index(domain).resolve_enum_literals(type_name, set())
        except Exception:
            return None

    def get_array_dimension(self, domain: str, type_name: str) -> Optional[int]:
        try:
            return self._index(domain).resolve_array_dimension(type_name, set())
        except Exception:
            return None



class LibadalangTypesProvider:
    """
    Libadalang-backed provider. Requires the `libadalang` Python module.

    Note: This is a best-effort minimal implementation to support direct
    record and array declarations. It does not yet resolve derived/renamed
    types or GPR projects; those can be added incrementally.
    """

    def __init__(self, types_from_ads: Path, types_to_ads: Path) -> None:
        self.paths = {"from": types_from_ads, "to": types_to_ads}
        try:
            import libadalang as lal  # type: ignore
            self.lal = lal
            self.ctx = lal.AnalysisContext()
            self.units: dict[str, object] = {}
            self._fallback = None
        except Exception:
            self.lal = None  # type: ignore
            self.ctx = None  # type: ignore
            self.units = {}
            from types_provider import RegexTypesProvider as _RTP
            self._fallback = _RTP(types_from_ads, types_to_ads)

    def _unit(self, domain: str):
        if domain not in self.units:
            self.units[domain] = self.ctx.get_from_file(str(self.paths[domain]))
        return self.units[domain]

    def _find_type_decl(self, domain: str, type_name: str):
        lal = self.lal
        u = self._unit(domain)
        for decl in u.root.findall(lal.TypeDecl):
            try:
                name = decl.f_decl_id.text
            except Exception:
                continue
            if name == type_name:
                return decl
        return None

    def get_record_fields(self, domain: str, type_name: str) -> Optional[dict[str, str]]:
        if self.lal is None:
            return self._fallback.get_record_fields(domain, type_name) if self._fallback else None
        lal = self.lal
        decl = self._find_type_decl(domain, type_name)
        if not decl:
            return None
        tdef = decl.f_type_def
        if not isinstance(tdef, lal.RecordTypeDef):
            return None
        comp_list = tdef.f_component_list
        if comp_list is None:
            return None
        fields: dict[str, str] = {}
        for comp in comp_list.f_components:
            # component ids can be a list; handle singular case
            if hasattr(comp.f_ids, 'text'):
                cname = comp.f_ids.text
            else:
                # Fallback: first identifier
                try:
                    cname = comp.f_ids[0].text
                except Exception:
                    continue
            # component type mark
            ctype = None
            try:
                # Typical path: subtype indication -> name
                ctype = comp.f_component_def.f_subtype_indication.f_name.text
            except Exception:
                try:
                    ctype = comp.f_component_def.text
                except Exception:
                    ctype = None
            if cname and ctype:
                fields[cname] = ctype.strip()
        return fields or None

    def get_array_element_type(self, domain: str, type_name: str) -> Optional[str]:
        if self.lal is None:
            return self._fallback.get_record_fields(domain, type_name) if self._fallback else None
        if self.lal is None:
            return self._fallback.get_array_element_type(domain, type_name) if self._fallback else None
        lal = self.lal
        decl = self._find_type_decl(domain, type_name)
        if not decl:
            return None
        tdef = decl.f_type_def
        if not isinstance(tdef, lal.ArrayTypeDef):
            return None
        try:
            return tdef.f_component_def.f_subtype_indication.f_name.text.strip()
        except Exception:
            try:
                return tdef.f_component_def.text.strip()
            except Exception:
                return None

    def get_enum_literals(self, domain: str, type_name: str) -> Optional[List[str]]:
        if self.lal is None:
            return self._fallback.get_enum_literals(domain, type_name) if self._fallback else None
        lal = self.lal
        decl = self._find_type_decl(domain, type_name)
        if not decl:
            return None
        tdef = decl.f_type_def
        # Try to detect enum-like type definition class names without importing specific symbols
        kind = type(tdef).__name__ if tdef is not None else ""
        if kind not in ("EnumTypeDef", "EnumerationTypeDef"):
            return None
        # Attempt to extract literals; this may vary by version
        try:
            lits = [lit.f_id.text for lit in tdef.f_enumeration_literals]
            return lits or None
        except Exception:
            return None

    def get_array_dimension(self, domain: str, type_name: str) -> Optional[int]:
        if self.lal is None:
            return self._fallback.get_array_dimension(domain, type_name) if self._fallback else None
        lal = self.lal
        decl = self._find_type_decl(domain, type_name)
        if not decl:
            return None
        tdef = decl.f_type_def
        if not isinstance(tdef, lal.ArrayTypeDef):
            return None
        try:
            dims = 0
            for _ in tdef.f_index_constraint.f_discrete_ranges:
                dims += 1
            return dims or 1
        except Exception:
            return None
