Ada Mapper – Engineering Log (Codex Agents)

This document captures decisions, architecture, and next steps for the Ada mapping generator built with Codex CLI.

Project Snapshot
- Goal: Generate Ada mappers between source and destination record types using a minimal JSON mapping spec; rely on Ada types for conversions (inline casts), not JSON.
- Output: src/position_mappers.ads/.adb with Map overloads per mapping pair.
- Inputs:
  - mappings.json: pairs { from, to, fields } with optional dotted source paths (e.g., "Lat": "Position.Latitude").
  - Type specs in src/types_from.ads and src/types_to.ads.
- Key capabilities:
  - Inline casts, no central conversions package.
  - Nested records: delegate to Map for known pairs, otherwise inline aggregates.
  - Arrays: generate Map(A : From_Array) return To_Array and handle arrays-of-records and nested arrays.
  - Dotted source paths (flattening source into dest fields).
  - Optional validation: --validate compiles mapper with gnatmake (required on PATH).

Current Architecture
- tools/gen_mapper.py: CLI entry.
  - --validate: compile generated mapper via gnatmake only.
  - --provider {regex|lal}: choose type info backend (default: regex).
- tools/generator.py: MapperGenerator orchestrates generation.
  - Memoized type lookups, nested expression building, array pair closure, record mapping body emission.
  - Agnostic via TypesProvider.
- tools/types_provider.py: parsing abstraction.
  - TypesProvider protocol.
  - RegexTypesProvider (default) using simple parsers.
  - LibadalangTypesProvider (available if libadalang importable).
- tools/records.py: simple record component parser (regex/line-based).
- tools/arrays.py: array utilities and array Map emission helpers.
- tests/: pytest integration tests validate generated code strings only (no GNAT needed).
- .vscode/launch.json: run generator or generator+validate.

Decisions Log
- Use inline casts based on destination component type; remove Conversions package.
- Keep JSON type-agnostic; only names map, Ada resolves types; dotted paths allowed for source.
- Support nested records by delegation: emit Map(Subrecord) when a mapping pair exists.
- Support arrays at any nesting level; generate array Map overloads and delegate for arrays-of-arrays.
- Add --validate; require gnatmake (no fallback); error out if missing.
- Introduce TypesProvider abstraction to allow swapping parsers (regex now, libadalang later).
- Standardize naming: records.py and arrays.py under tools/.

How To Use
- Generate:
  - python3 tools/gen_mapper.py mappings.json src
- Generate + validate (requires gnatmake on PATH):
  - python3 tools/gen_mapper.py --validate mappings.json src
- VS Code: Run and Debug → "Python: Generate Mappers" or "Python: Generate + Validate".

Testing
- Create a venv, install pytest, run:
  - python3 -m venv .venv && source .venv/bin/activate
  - python -m pip install -U pip setuptools wheel pytest
  - pytest -q
- Tests cover: basic scalars, arrays, nested records, arrays of records, nested arrays, dotted source paths.

Tooling Notes
- GNAT installation (for --validate):
  - Via Alire + toolchain, or MacPorts (gcc-ada, gprbuild). Ensure gnatmake on PATH.
- Libadalang Python module is not on PyPI. Use AdaCore packages (Community Edition) for macOS.
  - Once installed, use --provider lal to enable the LAL-backed provider.

Roadmap / TODOs
- Libadalang provider parity:
  - Resolve derived/renamed types, subtypes, private/limited records, with/use resolution, and projects (GPR) for cross-unit analysis.
- Dotted destination paths (unflattening):
  - Group by destination prefixes to assemble nested aggregates for partial field assignment.
- Diagnostics:
  - Better error messages for missing fields/types; optional strict mode.
- Formatting options:
  - Configurable emitted package/unit names; stable ordering for functions.
- CI hooks:
  - Add a GitHub Actions workflow for tests and optional --validate matrix when GNAT is present.

Conventions
- Keep generator output deterministic and idempotent.
- Avoid changing file names or structure unless necessary.
- Prefer delegation (Map(...)) to keep nested logic DRY.

