Ada Mapper — Type Recognition Coverage

Scope: RegexTypesProvider parsing of Ada .ads specs. Tracks constructs we handle, partial gaps, and known misses that affect code generation.

Legend
- Implemented: Supported and covered by tests.
- Partial: Parsed but with limitations or incorrect semantics in some cases.
- Not Implemented: Not recognized or leads to wrong code generation.
- Planned: On roadmap (typically for LAL provider parity).

Records
- Multiple component names per line (e.g., `A, B : Integer;`)
  - Status: Implemented
  - Notes: Lines with comma-separated component identifiers expand into individual field entries.
  - Impact: Covered by tests (`test_record_multiple_component_declarations`).

- Components with default expressions (e.g., `X : Integer := 0;`)
  - Status: Implemented
  - Notes: Trailing `:= ...` values are stripped before storing the subtype indication.
  - Impact: Cast targets stay valid (`test_record_component_with_default_expression`).

- Constrained/qualified scalar components (`range`, `digits`, `delta`, `mod`)
  - Status: Implemented
  - Notes: Constraint clauses are dropped so the base subtype name is kept for casts.
  - Impact: Verified with `test_record_constrained_scalar_component`.

- Discriminated and variant records (e.g., `type T (D : Integer) is record ... case D is ... end case;`)
  - Status: Partial
  - Notes: Fields inside variants are parsed as regular components.
  - Impact: Generated aggregates may reference fields not present for a given discriminant; compile-time errors.

- Derived records without extension (`type T is new Base;`)
  - Status: Implemented
  - Notes: Derived declarations register as subtypes of their base record.
  - Impact: `test_record_derived_without_extension` exercises the resolution.

- Record extension with explicit `with record` (`type T is new Root with record ... end record;`)
  - Status: Implemented (simple case)
  - Notes: Fields inside the `record` block are captured. Base type semantics (inheritance) are not otherwise used.

- Private/limited/private extensions (`type T is private;`, `type T is new Root with private;`)
  - Status: Not Implemented
  - Notes: No visibility into full view.
  - Impact: Treated as scalar.

- Component aspects (`with Atomic`, `with Pack` on components)
  - Status: Partial
  - Notes: Aspects are not stripped; become part of captured type.
  - Impact: Can corrupt cast target expression.

- Access components (`X : not null access Some_Type;`)
  - Status: Implemented
  - Notes: Access qualifiers are preserved; record mapping treats them as references and defaults use `null`.
  - Impact: Confirmed with `test_record_access_component_mapping`.

Arrays
- Anonymous array subtype indications in components (`X : array (1 .. 10) of Integer;`)
  - Status: Not Implemented
  - Notes: Only named array type declarations are recognized.
  - Impact: Treated as scalars; array `Map` overloads not emitted.

- Derived arrays (`type A2 is new A1;`) and type renames (`type A2 renames A1;`)
  - Status: Not Implemented
  - Notes: Not resolved to element type/dimensions.
  - Impact: Array delegation/closure not discovered.

- Access-qualified array components (`array (...) of not null access T`)
  - Status: Partial
  - Notes: Qualifiers stripped; pointer-ness lost.
  - Impact: Defaulting and element handling semantics wrong.

- Unusual index subtype identifiers (`array (Index_Subtype range <>) of T`)
  - Status: Implemented (dimension detection only)
  - Notes: Index constraints are ignored; dimension count is correct.

Enums
- Derived enums (`type E2 is new E1;`) and renames (`type E2 renames E1;`)
  - Status: Not Implemented
  - Notes: Only direct `is (A, B, ...)` are recognized.
  - Impact: Enum-to-enum map overloads not generated.

Subtypes / Renames / Derived
- Constrained subtypes (`subtype Index is Positive range 1 .. 10;`)
  - Status: Partial
  - Notes: (unchanged) still recorded with constraints; affects indirect lookups.
  - Impact: Resolution to underlying kind (enum/array/record) fails.

- Attribute bases in subtype indications (`Some_Type'Base`, `Some_Type'Class`)
  - Status: Not Implemented
  - Notes: Attributes persist in captured names; not resolved.
  - Impact: Degrades to scalar casting.

- Type renames (`type T renames U;`)
  - Status: Not Implemented
  - Notes: Not matched by current patterns; no transitive resolution.

- Derived types (`type T is new Base;`)
  - Status: Implemented
  - Notes: Resolved transitively via the subtype map used for records/arrays/enums.

Packages / Visibility
- Private types across specs; private/limited record full views in other units
  - Status: Not Implemented
  - Impact: Degrades to scalar; requires Libadalang for proper view.

- Cross-unit references via `with`/`use`
  - Status: Not Implemented
  - Notes: Indexer only sees a single .ads per domain.
  - Impact: Types from other units treated as scalars.

- Deeply nested packages with duplicate short names
  - Status: Partial
  - Notes: Qualification relies on local declared types; ambiguous names can mis-resolve.

General Parsing
- Aspects on type declarations (`type T is record ... end record with Pack;`)
  - Status: Implemented (tolerated)
  - Notes: Record/array/enum detection still works; aspects ignored.

- Comments and formatting
  - Status: Implemented (tolerated)
  - Notes: Comments are stripped before block analysis; unusual wraps may still break simple `FIELD_RE`.

- Defaults for access types in `default_expr`
  - Status: Implemented
  - Notes: `access` markers survive normalisation, allowing defaults to collapse to `null`.

Quick Wins (Regex Provider)
- Strip `:= ...` and component aspects after subtype indication. [Implemented (defaults stripped; aspects pending)]
- Support multiple component identifiers per line (`A, B : T;`). [Implemented]
- Normalize subtype indications by removing `range/digits/delta/mod` and attributes to base name. [Implemented (attributes still pending)]
- Preserve an "is access" marker through cleaning so defaults produce `null`. [Implemented]
- Recognize anonymous array subtype indications in record components and extract element type. [Not Implemented]
- Add transitive resolution for `type ... is new Base;` and `type ... renames Base;`. [Implemented for `is new`]

Recommended LAL (Libadalang) Parity Items
- Resolve derived/renamed types and subtypes across units. [Planned]
- Handle private/limited records and private extensions via full views. [Planned]
- Support discriminants/variants with visibility rules. [Planned]
- Respect `with`/`use` and project graphs (GPR). [Planned]

Related Test Ideas
- Record with `A, B : Integer;` → both fields mapped.
- Components with `:=` default and aspects → stripped in cast target.
- Subtype with `range`/`digits`/`delta`/`mod` → normalized to base.
- Anonymous array component in a record → array map emitted.
- Derived/renamed enum/array/record → resolved to base for mapping.
- Access component defaults → `null` in `__DEFAULT__` aggregate.

Last updated: 2024-11-24
