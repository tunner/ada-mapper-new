#!/usr/bin/env python3
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from generator import MapperGenerator
from constants import DEFAULT_SENTINEL


def is_placeholder(value: object) -> bool:
    return isinstance(value, str) and value.startswith("<") and value.endswith(">")


def is_default_sentinel(value: object) -> bool:
    return isinstance(value, str) and value.strip().upper() == DEFAULT_SENTINEL


EnumCache = Dict[str, Dict[str, Tuple[str, ...]]]
FieldLookup = Dict[str, Tuple[str, str]]


def _build_lookup(fields: Dict[str, str]) -> FieldLookup:
    return {name.lower(): (name, fields[name]) for name in fields}


def _enum_literals(
    domain: str, type_name: Optional[str], provider, cache: EnumCache
) -> Tuple[str, ...]:
    if not type_name:
        return ()
    type_key = type_name.strip()
    if not type_key:
        return ()
    domain_cache = cache.setdefault(domain, {})
    if type_key in domain_cache:
        return domain_cache[type_key]
    literals = provider.get_enum_literals(domain, type_key) or ()
    if not isinstance(literals, tuple):
        literals = tuple(literals)
    domain_cache[type_key] = literals
    return literals


def _resolve_source_reference(
    reference: str,
    *,
    ctx: str,
    dest_field: str,
    mg: MapperGenerator,
    from_type: Optional[str],
    from_lookup: FieldLookup,
    errors: List[str],
) -> Optional[str]:
    ref_clean = reference.strip()
    if is_default_sentinel(ref_clean):
        return DEFAULT_SENTINEL
    if "." in ref_clean:
        if from_type and from_type != DEFAULT_SENTINEL:
            resolved = mg.resolve_src_path_type(from_type, ref_clean)
            if resolved is None:
                errors.append(
                    f"{ctx}: field '{dest_field}' references unknown source path '{reference}'"
                )
                return None
            return resolved.strip()
        errors.append(
            f"{ctx}: field '{dest_field}' uses dotted path '{reference}' but source type is missing"
        )
        return None
    if not from_lookup:
        return None
    match = from_lookup.get(ref_clean.lower())
    if not match:
        errors.append(
            f"{ctx}: field '{dest_field}' references unknown source field '{reference}' in type '{from_type}'"
        )
        return None
    return match[1].strip()


def _validate_enum_override(
    ctx: str,
    dest_field: str,
    enum_map: object,
    dest_type: str,
    source_type: Optional[str],
    provider,
    cache: EnumCache,
    errors: List[str],
) -> None:
    if not isinstance(enum_map, dict):
        errors.append(
            f"{ctx}: field '{dest_field}' has 'enum_map' but it must be an object"
        )
        return
    dest_literals = _enum_literals("to", dest_type, provider, cache)
    src_literals = (
        _enum_literals("from", source_type, provider, cache)
        if source_type and source_type != DEFAULT_SENTINEL
        else ()
    )
    if not dest_literals or not src_literals:
        errors.append(
            f"{ctx}: field '{dest_field}' provides 'enum_map' but either source '{source_type}' or destination '{dest_type}' is not an enum"
        )
        return
    dest_lookup = {lit.lower(): lit for lit in dest_literals}
    src_lookup = {lit.lower(): lit for lit in src_literals}
    for raw_src, raw_dst in enum_map.items():
        if not isinstance(raw_src, str) or not isinstance(raw_dst, str):
            errors.append(
                f"{ctx}: field '{dest_field}' has non-string enum_map entry {raw_src!r}: {raw_dst!r}"
            )
            continue
        if raw_src.lower() not in src_lookup:
            errors.append(
                f"{ctx}: field '{dest_field}' enum_map references unknown source literal '{raw_src}'"
            )
        if raw_dst.lower() not in dest_lookup:
            errors.append(
                f"{ctx}: field '{dest_field}' enum_map targets unknown destination literal '{raw_dst}'"
            )


def validate_mappings(mappings: List[dict], provider) -> List[str]:
    errors: List[str] = []
    mg = MapperGenerator(provider, set())

    mapping_pairs = set()
    for entry in mappings:
        src = entry.get("from")
        dst = entry.get("to")
        if isinstance(src, str) and isinstance(dst, str) and not is_placeholder(src):
            mapping_pairs.add((src.strip(), dst.strip()))
    mg.mapping_pairs = mapping_pairs

    for entry in mappings:
        errors.extend(_validate_mapping_entry(entry, mg, provider))
    return errors


def _validate_mapping_entry(entry: dict, mg: MapperGenerator, provider) -> List[str]:
    errors: List[str] = []
    enum_cache: EnumCache = {"to": {}, "from": {}}

    name = entry.get("name")
    to_type_raw = entry.get("to")
    from_type_raw = entry.get("from")
    ctx = f"mapping '{name}'" if name else "a mapping entry"

    if not isinstance(to_type_raw, str) or not to_type_raw.strip():
        errors.append(f"{ctx}: destination type ('to') is missing or empty")
        return errors
    to_type = to_type_raw.strip()

    dest_fields = mg.get_to_fields(to_type)
    dest_enum_literals = _enum_literals("to", to_type, provider, enum_cache)

    if not dest_fields:
        if dest_enum_literals:
            errors.extend(
                _validate_enum_entry(
                    ctx=ctx,
                    to_type=to_type,
                    from_type_raw=from_type_raw,
                    fields_entry=entry.get("fields"),
                    dest_literals=dest_enum_literals,
                    provider=provider,
                    cache=enum_cache,
                )
            )
        else:
            errors.append(
                f"{ctx}: destination type '{to_type}' not found or is not a record in destination specs"
            )
        return errors

    if not isinstance(from_type_raw, str) or not from_type_raw.strip():
        errors.append(f"{ctx}: source type ('from') is missing")
        from_type = None
        from_fields = {}
    elif is_default_sentinel(from_type_raw):
        from_type = DEFAULT_SENTINEL
        from_fields = {}
    else:
        if is_placeholder(from_type_raw):
            errors.append(f"{ctx}: source type is still a placeholder '{from_type_raw}'")
        from_type = from_type_raw.strip()
        from_fields = mg.get_from_fields(from_type) or {}
        if not from_fields:
            errors.append(
                f"{ctx}: source type '{from_type}' not found or is not a record in source specs"
            )

    fields_entry = entry.get("fields")
    if not isinstance(fields_entry, dict):
        errors.append(f"{ctx}: 'fields' must be an object mapping destination fields to sources")
        return errors

    dest_lookup = _build_lookup(dest_fields)
    dest_field_keys_lower = {field.lower() for field in fields_entry}
    missing_fields = [
        field
        for field in dest_fields
        if field.lower() not in dest_field_keys_lower
    ]
    if missing_fields:
        errors.append(
            f"{ctx}: missing mappings for destination fields {', '.join(missing_fields)} in type '{to_type}'"
        )

    extra_fields = [field for field in fields_entry if field.lower() not in dest_lookup]
    for extra in extra_fields:
        errors.append(
            f"{ctx}: destination field '{extra}' does not exist in type '{to_type}'"
        )

    from_lookup = _build_lookup(from_fields)

    for dest_field, spec in fields_entry.items():
        lookup = dest_lookup.get(dest_field.lower())
        if not lookup:
            continue
        dest_actual, dest_type_raw = lookup
        dest_type = dest_type_raw.strip()

        source_type: Optional[str] = None

        if isinstance(spec, str):
            spec_value = spec.strip()
            if is_placeholder(spec_value):
                errors.append(
                    f"{ctx}: field '{dest_actual}' still uses placeholder value '{spec_value}'"
                )
                continue
            if is_default_sentinel(spec_value):
                continue
            if "." in spec_value and (not from_type or from_type == DEFAULT_SENTINEL):
                errors.append(
                    f"{ctx}: field '{dest_actual}' uses dotted path '{spec_value}' but source type is missing"
                )
                continue
            if "." not in spec_value and not from_lookup:
                continue
            resolved = _resolve_source_reference(
                spec_value,
                ctx=ctx,
                dest_field=dest_actual,
                mg=mg,
                from_type=from_type,
                from_lookup=from_lookup,
                errors=errors,
            )
            if resolved is not None:
                source_type = resolved

        elif isinstance(spec, dict):
            src_ref = spec.get("from") or spec.get("source") or spec.get("path")
            if not src_ref:
                errors.append(
                    f"{ctx}: field '{dest_actual}' mapping object must include 'from'/'source'/'path'"
                )
                continue
            if is_placeholder(src_ref):
                errors.append(
                    f"{ctx}: field '{dest_actual}' still uses placeholder value '{src_ref}'"
                )
                continue
            src_ref_str = str(src_ref).strip()
            if is_default_sentinel(src_ref_str):
                source_type = DEFAULT_SENTINEL
            else:
                if "." in src_ref_str and (not from_type or from_type == DEFAULT_SENTINEL):
                    errors.append(
                        f"{ctx}: field '{dest_actual}' uses dotted path '{src_ref_str}' but source type is missing"
                    )
                elif "." not in src_ref_str and not from_lookup:
                    pass
                else:
                    resolved = _resolve_source_reference(
                        src_ref_str,
                        ctx=ctx,
                        dest_field=dest_actual,
                        mg=mg,
                        from_type=from_type,
                        from_lookup=from_lookup,
                        errors=errors,
                    )
                    if resolved is not None:
                        source_type = resolved

            if "enum_map" in spec:
                _validate_enum_override(
                    ctx=ctx,
                    dest_field=dest_actual,
                    enum_map=spec.get("enum_map"),
                    dest_type=dest_type,
                    source_type=source_type,
                    provider=provider,
                    cache=enum_cache,
                    errors=errors,
                )
        else:
            errors.append(
                f"{ctx}: field '{dest_actual}' has unsupported mapping value {spec!r}"
            )
            continue

        if source_type and source_type != DEFAULT_SENTINEL:
            dest_record = mg.get_to_fields(dest_type)
            if dest_record and not mg.get_from_fields(source_type):
                errors.append(
                    f"{ctx}: field '{dest_actual}' expects record type '{dest_type}' but source expression resolves to '{source_type}', which is not a record"
                )
            dest_array = mg.to_array_elem(dest_type)
            if dest_array and not mg.from_array_elem(source_type):
                errors.append(
                    f"{ctx}: field '{dest_actual}' expects array type '{dest_type}' but source expression resolves to '{source_type}', which is not an array"
                )

    return errors


def _validate_enum_entry(
    ctx: str,
    to_type: str,
    from_type_raw: object,
    fields_entry: object,
    dest_literals: Tuple[str, ...],
    provider,
    cache: EnumCache,
) -> List[str]:
    errors: List[str] = []

    if not isinstance(from_type_raw, str) or not from_type_raw.strip():
        errors.append(f"{ctx}: source type ('from') is missing for enum mapping")
        from_type = None
        from_literals: List[str] = []
    elif is_default_sentinel(from_type_raw):
        from_type = DEFAULT_SENTINEL
        from_literals = []
    else:
        if is_placeholder(from_type_raw):
            errors.append(f"{ctx}: source type is still a placeholder '{from_type_raw}'")
        from_type = from_type_raw.strip()
        from_literals = list(_enum_literals("from", from_type, provider, cache))
        if not from_literals:
            errors.append(
                f"{ctx}: source type '{from_type}' not found or is not an enum in source specs"
            )

    if not isinstance(fields_entry, dict):
        errors.append(f"{ctx}: 'fields' must be an object mapping enum literals")
        return errors

    dest_lookup = {lit.lower(): lit for lit in dest_literals}
    from_lookup = {lit.lower(): lit for lit in from_literals}

    missing = [lit for lit in dest_literals if lit not in fields_entry]
    if missing:
        errors.append(
            f"{ctx}: missing mappings for enum literals {', '.join(missing)} in '{to_type}'"
        )

    for dest_lit, src_spec in fields_entry.items():
        if dest_lit not in dest_lookup.values():
            errors.append(
                f"{ctx}: destination literal '{dest_lit}' does not exist in enum '{to_type}'"
            )
            continue
        if isinstance(src_spec, str):
            spec_clean = src_spec.strip()
            if is_placeholder(spec_clean):
                errors.append(
                    f"{ctx}: literal '{dest_lit}' still uses placeholder value '{src_spec}'"
                )
            elif is_default_sentinel(spec_clean):
                continue
            elif from_lookup and spec_clean.lower() not in from_lookup:
                errors.append(
                    f"{ctx}: literal '{dest_lit}' references unknown source literal '{src_spec}'"
                )
        else:
            errors.append(
                f"{ctx}: literal '{dest_lit}' has unsupported mapping value {src_spec!r}"
            )

    return errors
