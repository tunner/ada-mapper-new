#!/usr/bin/env python3
from __future__ import annotations

from typing import List, Optional

from generator import MapperGenerator


def is_placeholder(value: object) -> bool:
    return isinstance(value, str) and value.startswith("<") and value.endswith(">")


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

    name = entry.get("name")
    to_type_raw = entry.get("to")
    from_type_raw = entry.get("from")
    ctx = f"mapping '{name}'" if name else "a mapping entry"

    if not isinstance(to_type_raw, str) or not to_type_raw.strip():
        errors.append(f"{ctx}: destination type ('to') is missing or empty")
        return errors
    to_type = to_type_raw.strip()

    dest_fields = provider.get_record_fields("to", to_type)
    dest_enum_literals = provider.get_enum_literals("to", to_type)

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
    else:
        if is_placeholder(from_type_raw):
            errors.append(f"{ctx}: source type is still a placeholder '{from_type_raw}'")
        from_type = from_type_raw.strip()
        from_fields = provider.get_record_fields("from", from_type) or {}
        if not from_fields:
            errors.append(
                f"{ctx}: source type '{from_type}' not found or is not a record in source specs"
            )

    fields_entry = entry.get("fields")
    if not isinstance(fields_entry, dict):
        errors.append(f"{ctx}: 'fields' must be an object mapping destination fields to sources")
        return errors

    dest_lookup = {field.lower(): (field, dest_fields[field]) for field in dest_fields}
    dest_field_keys_lower = {field.lower() for field in fields_entry}
    missing_fields = [field for field in dest_fields if field.lower() not in dest_field_keys_lower]
    if missing_fields:
        errors.append(
            f"{ctx}: missing mappings for destination fields {', '.join(missing_fields)} in type '{to_type}'"
        )

    extra_fields = [field for field in fields_entry if field.lower() not in dest_lookup]
    for extra in extra_fields:
        errors.append(
            f"{ctx}: destination field '{extra}' does not exist in type '{to_type}'"
        )

    from_lookup = {name.lower(): (name, from_fields[name]) for name in from_fields}

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
            if '.' in spec_value:
                if from_type:
                    resolved = mg.resolve_src_path_type(from_type, spec_value)
                    if resolved is None:
                        errors.append(
                            f"{ctx}: field '{dest_actual}' references unknown source path '{spec_value}'"
                        )
                    else:
                        source_type = resolved.strip()
                else:
                    errors.append(
                        f"{ctx}: field '{dest_actual}' uses dotted path '{spec_value}' but source type is missing"
                    )
            else:
                if not from_lookup:
                    continue
                match = from_lookup.get(spec_value.lower())
                if not match:
                    errors.append(
                        f"{ctx}: field '{dest_actual}' references unknown source field '{spec_value}' in type '{from_type}'"
                    )
                else:
                    source_type = match[1].strip()

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
            if '.' in src_ref_str:
                if from_type:
                    resolved = mg.resolve_src_path_type(from_type, src_ref_str)
                    if resolved is None:
                        errors.append(
                            f"{ctx}: field '{dest_actual}' references unknown source path '{src_ref_str}'"
                        )
                    else:
                        source_type = resolved.strip()
                else:
                    errors.append(
                        f"{ctx}: field '{dest_actual}' uses dotted path '{src_ref_str}' but source type is missing"
                    )
            else:
                if not from_lookup:
                    continue
                match = from_lookup.get(src_ref_str.lower())
                if not match:
                    errors.append(
                        f"{ctx}: field '{dest_actual}' references unknown source field '{src_ref_str}' in type '{from_type}'"
                    )
                else:
                    source_type = match[1].strip()

            enum_map = spec.get("enum_map")
            if enum_map is not None:
                if not isinstance(enum_map, dict):
                    errors.append(
                        f"{ctx}: field '{dest_actual}' has 'enum_map' but it must be an object"
                    )
                else:
                    dest_lits = provider.get_enum_literals("to", dest_type)
                    src_lits = provider.get_enum_literals("from", source_type) if source_type else None
                    if not dest_lits or not src_lits:
                        errors.append(
                            f"{ctx}: field '{dest_actual}' provides 'enum_map' but either source '{source_type}' or destination '{dest_type}' is not an enum"
                        )
                    else:
                        dest_lookup = {lit.lower(): lit for lit in dest_lits}
                        src_lookup = {lit.lower(): lit for lit in src_lits}
                        for raw_src, raw_dst in enum_map.items():
                            if not isinstance(raw_src, str) or not isinstance(raw_dst, str):
                                errors.append(
                                    f"{ctx}: field '{dest_actual}' has non-string enum_map entry {raw_src!r}: {raw_dst!r}"
                                )
                                continue
                            if raw_src.lower() not in src_lookup:
                                errors.append(
                                    f"{ctx}: field '{dest_actual}' enum_map references unknown source literal '{raw_src}'"
                                )
                            if raw_dst.lower() not in dest_lookup:
                                errors.append(
                                    f"{ctx}: field '{dest_actual}' enum_map targets unknown destination literal '{raw_dst}'"
                                )
        else:
            errors.append(
                f"{ctx}: field '{dest_actual}' has unsupported mapping value {spec!r}"
            )
            continue

        if source_type:
            dest_record = provider.get_record_fields("to", dest_type)
            if dest_record and not provider.get_record_fields("from", source_type):
                errors.append(
                    f"{ctx}: field '{dest_actual}' expects record type '{dest_type}' but source expression resolves to '{source_type}', which is not a record"
                )
            dest_array = provider.get_array_element_type("to", dest_type)
            if dest_array and not provider.get_array_element_type("from", source_type):
                errors.append(
                    f"{ctx}: field '{dest_actual}' expects array type '{dest_type}' but source expression resolves to '{source_type}', which is not an array"
                )

    return errors


def _validate_enum_entry(
    ctx: str,
    to_type: str,
    from_type_raw: object,
    fields_entry: object,
    dest_literals: List[str],
    provider,
) -> List[str]:
    errors: List[str] = []

    if not isinstance(from_type_raw, str) or not from_type_raw.strip():
        errors.append(f"{ctx}: source type ('from') is missing for enum mapping")
        from_type = None
        from_literals: List[str] = []
    else:
        if is_placeholder(from_type_raw):
            errors.append(f"{ctx}: source type is still a placeholder '{from_type_raw}'")
        from_type = from_type_raw.strip()
        from_literals = provider.get_enum_literals("from", from_type) or []
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
            elif from_lookup and spec_clean.lower() not in from_lookup:
                errors.append(
                    f"{ctx}: literal '{dest_lit}' references unknown source literal '{src_spec}'"
                )
        else:
            errors.append(
                f"{ctx}: literal '{dest_lit}' has unsupported mapping value {src_spec!r}"
            )

    return errors
