#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Protocol, List
import re

from arrays import parse_array_component_type
from enums import parse_enum_literals
from records import parse_record_components


class TypesProvider(Protocol):
    def get_record_fields(self, domain: str, type_name: str) -> Optional[Dict[str, str]]:
        ...

    def get_array_element_type(self, domain: str, type_name: str) -> Optional[str]:
        ...

    def get_enum_literals(self, domain: str, type_name: str) -> Optional[List[str]]:
        ...

    def get_array_dimension(self, domain: str, type_name: str) -> Optional[int]:
        ...


class RegexTypesProvider:
    """
    Regex-based provider that reads a pair of .ads files and extracts
    record fields and array element types. Serves as the default provider.
    """

    def __init__(self, types_from_ads: Path, types_to_ads: Path) -> None:
        self.types_from_ads = types_from_ads
        self.types_to_ads = types_to_ads
        self._text_cache: dict[str, str] = {}

    def _path(self, domain: str) -> Path:
        if domain == "from":
            return self.types_from_ads
        if domain == "to":
            return self.types_to_ads
        raise ValueError(f"Unknown domain: {domain}")

    def _text(self, domain: str) -> str:
        if domain not in self._text_cache:
            self._text_cache[domain] = self._path(domain).read_text()
        return self._text_cache[domain]

    def _strip_qualifiers(self, mark: str) -> str:
        cleaned = mark.split("--", 1)[0]
        cleaned = re.sub(r"\baliased\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bnot\s+null\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\baccess\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = " ".join(cleaned.split())
        return cleaned.strip()

    def _extract_type_name(self, mark: str) -> Optional[str]:
        cleaned = self._strip_qualifiers(mark)
        m = re.match(r"([A-Za-z]\w*(?:\.[A-Za-z]\w*)*)", cleaned)
        if not m:
            return None
        name = m.group(1)
        return name.split(".")[-1]

    def _find_subtype_base(self, domain: str, type_name: str) -> Optional[str]:
        text = self._text(domain)
        pat = re.compile(
            rf"\bsubtype\s+{re.escape(type_name)}\s+is\s+(.+?);",
            re.IGNORECASE | re.DOTALL,
        )
        m = pat.search(text)
        if not m:
            return None
        return m.group(1).split("--", 1)[0].strip()

    def _resolve_record_fields(self, domain: str, type_name: str, seen: set[str]) -> Optional[Dict[str, str]]:
        if not type_name or type_name in seen:
            return None
        seen.add(type_name)
        try:
            fields = parse_record_components(self._path(domain), type_name)
            if fields:
                return fields
        except Exception:
            pass
        base = self._find_subtype_base(domain, type_name)
        if not base:
            return None
        base_name = self._extract_type_name(base)
        if not base_name:
            return None
        return self._resolve_record_fields(domain, base_name, seen)

    def _resolve_array_element(self, domain: str, type_name: str, seen: set[str]) -> Optional[str]:
        if not type_name or type_name in seen:
            return None
        seen.add(type_name)
        try:
            elem = parse_array_component_type(self._path(domain), type_name)
            if elem:
                return self._strip_qualifiers(elem.strip())
        except Exception:
            pass
        base = self._find_subtype_base(domain, type_name)
        if not base:
            return None
        array_match = re.search(
            r"array\s*\(.*?\)\s*of\s+([^;]+)",
            base,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if array_match:
            component = array_match.group(1).strip()
            return self._strip_qualifiers(component)
        base_name = self._extract_type_name(base)
        if not base_name:
            return None
        return self._resolve_array_element(domain, base_name, seen)

    def _resolve_enum_literals(self, domain: str, type_name: str, seen: set[str]) -> Optional[List[str]]:
        if not type_name or type_name in seen:
            return None
        seen.add(type_name)
        try:
            lits = parse_enum_literals(self._path(domain), type_name)
            if lits:
                return lits
        except Exception:
            pass
        base = self._find_subtype_base(domain, type_name)
        if not base:
            return None
        base_name = self._extract_type_name(base)
        if not base_name:
            return None
        return self._resolve_enum_literals(domain, base_name, seen)

    def get_record_fields(self, domain: str, type_name: str) -> Optional[Dict[str, str]]:
        try:
            fields = self._resolve_record_fields(domain, type_name, set())
            return fields
        except Exception:
            return None

    def get_array_element_type(self, domain: str, type_name: str) -> Optional[str]:
        try:
            return self._resolve_array_element(domain, type_name, set())
        except Exception:
            return None

    def get_enum_literals(self, domain: str, type_name: str) -> Optional[List[str]]:
        try:
            return self._resolve_enum_literals(domain, type_name, set())
        except Exception:
            return None

    def get_array_dimension(self, domain: str, type_name: str) -> Optional[int]:
        try:
            dim = parse_array_dimension(self._path(domain), type_name)
            if dim is not None:
                return dim
        except Exception:
            pass
        base = self._find_subtype_base(domain, type_name)
        if not base:
            return None
        elem = self._extract_type_name(base)
        if not elem:
            return None
        return self.get_array_dimension(domain, elem)



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
