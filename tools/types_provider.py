#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Protocol, List


class TypesProvider(Protocol):
    def get_record_fields(self, domain: str, type_name: str) -> Optional[Dict[str, str]]:
        ...

    def get_array_element_type(self, domain: str, type_name: str) -> Optional[str]:
        ...

    def get_enum_literals(self, domain: str, type_name: str) -> Optional[List[str]]:
        ...


class RegexTypesProvider:
    """
    Regex-based provider that reads a pair of .ads files and extracts
    record fields and array element types. Serves as the default provider.
    """

    def __init__(self, types_from_ads: Path, types_to_ads: Path) -> None:
        self.types_from_ads = types_from_ads
        self.types_to_ads = types_to_ads

    def _path(self, domain: str) -> Path:
        if domain == "from":
            return self.types_from_ads
        if domain == "to":
            return self.types_to_ads
        raise ValueError(f"Unknown domain: {domain}")

    def get_record_fields(self, domain: str, type_name: str) -> Optional[Dict[str, str]]:
        from records import parse_record_components

        try:
            return parse_record_components(self._path(domain), type_name)
        except Exception:
            return None

    def get_array_element_type(self, domain: str, type_name: str) -> Optional[str]:
        from arrays import parse_array_component_type

        try:
            return parse_array_component_type(self._path(domain), type_name)
        except Exception:
            return None

    def get_enum_literals(self, domain: str, type_name: str) -> Optional[List[str]]:
        from enums import parse_enum_literals

        try:
            return parse_enum_literals(self._path(domain), type_name)
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
        try:
            import libadalang as lal  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "libadalang is not available. Install it and retry (e.g., via AdaCore packages or Alire)."
            ) from exc
        self.lal = lal
        self.paths = {"from": types_from_ads, "to": types_to_ads}
        self.ctx = lal.AnalysisContext()
        self.units: dict[str, any] = {}

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
        # Minimal implementation; returns None to fall back to casts or positional mapping
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
