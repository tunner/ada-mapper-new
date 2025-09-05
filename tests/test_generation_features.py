import json
import subprocess
import sys
from pathlib import Path


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def run_gen(tmp_path: Path, mappings_obj: dict) -> str:
    src_dir = tmp_path / "src"
    mappings = tmp_path / "mappings.json"
    mappings.write_text(json.dumps(mappings_obj))
    result = subprocess.run(
        [sys.executable, str(Path("tools/gen_mapper.py")), str(mappings), str(src_dir)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return (src_dir / "position_mappers.adb").read_text()


def test_array_of_scalars_mapping(tmp_path: Path):
    # From: array of Int32 -> To: array of Int16 inside a record
    write(
        tmp_path / "src/types_from.ads",
        """
package Types_From is
   type I32 is range -2147483648 .. 2147483647;
   type Arr_From is array (1 .. 4) of I32;
   type Rec_From is record
      A : Arr_From;
   end record;
end Types_From;
""".strip(),
    )
    write(
        tmp_path / "src/types_to.ads",
        """
package Types_To is
   type I16 is range -32768 .. 32767;
   type Arr_To is array (1 .. 4) of I16;
   type Rec_To is record
      A : Arr_To;
   end record;
end Types_To;
""".strip(),
    )
    body = run_gen(
        tmp_path,
        {
            "mappings": [
                {"name": "Rec", "from": "Rec_From", "to": "Rec_To", "fields": {"A": "A"}}
            ]
        },
    )
    assert "function Map (X : Types_From.Rec_From) return Types_To.Rec_To" in body
    assert "A => Map(X.A)" in body
    assert "function Map (A : Types_From.Arr_From) return Types_To.Arr_To" in body
    assert "R(I) := I16 (A(I))" in body


def test_nested_record_mapping_delegation(tmp_path: Path):
    # Parent contains nested record; provide explicit inner mapping and expect delegation
    write(
        tmp_path / "src/types_from.ads",
        """
package Types_From is
   type I32 is range -2147483648 .. 2147483647;
   type Inner_From is record
      X : I32;
      Y : I32;
   end record;
   type Outer_From is record
      Inr : Inner_From;
   end record;
end Types_From;
""".strip(),
    )
    write(
        tmp_path / "src/types_to.ads",
        """
package Types_To is
   type I16 is range -32768 .. 32767;
   type Inner_To is record
      X : I16;
      Y : I16;
   end record;
   type Outer_To is record
      Inr : Inner_To;
   end record;
end Types_To;
""".strip(),
    )
    body = run_gen(
        tmp_path,
        {
            "mappings": [
                {"name": "Inner", "from": "Inner_From", "to": "Inner_To", "fields": {"X": "X", "Y": "Y"}},
                {"name": "Outer", "from": "Outer_From", "to": "Outer_To", "fields": {"Inr": "Inr"}},
            ]
        },
    )
    assert "function Map (X : Types_From.Inner_From) return Types_To.Inner_To" in body
    assert "X => I16 (X.X)" in body and "Y => I16 (X.Y)" in body
    assert "function Map (X : Types_From.Outer_From) return Types_To.Outer_To" in body
    assert "Inr => Map(X.Inr)" in body


def test_array_of_records_mapping(tmp_path: Path):
    # Array of records; element mapping exists -> delegate per element
    write(
        tmp_path / "src/types_from.ads",
        """
package Types_From is
   type I32 is range -2147483648 .. 2147483647;
   type E_From is record
      V : I32;
   end record;
   type A_From is array (1 .. 3) of E_From;
   type R_From is record
      A : A_From;
   end record;
end Types_From;
""".strip(),
    )
    write(
        tmp_path / "src/types_to.ads",
        """
package Types_To is
   type I16 is range -32768 .. 32767;
   type E_To is record
      V : I16;
   end record;
   type A_To is array (1 .. 3) of E_To;
   type R_To is record
      A : A_To;
   end record;
end Types_To;
""".strip(),
    )
    body = run_gen(
        tmp_path,
        {
            "mappings": [
                {"name": "Elem", "from": "E_From", "to": "E_To", "fields": {"V": "V"}},
                {"name": "Rec", "from": "R_From", "to": "R_To", "fields": {"A": "A"}},
            ]
        },
    )
    assert "function Map (A : Types_From.A_From) return Types_To.A_To" in body
    assert "R(I) := Map(A(I))" in body


def test_nested_arrays_in_record_mapping(tmp_path: Path):
    # Arrays of arrays as a field inside a record
    write(
        tmp_path / "src/types_from.ads",
        """
package Types_From is
   type I32 is range -2147483648 .. 2147483647;
   type Inner_Arr_From is array (1 .. 2) of I32;
   type Outer_Arr_From is array (1 .. 3) of Inner_Arr_From;
   type Holder_From is record
      A : Outer_Arr_From;
   end record;
end Types_From;
""".strip(),
    )
    write(
        tmp_path / "src/types_to.ads",
        """
package Types_To is
   type I16 is range -32768 .. 32767;
   type Inner_Arr_To is array (1 .. 2) of I16;
   type Outer_Arr_To is array (1 .. 3) of Inner_Arr_To;
   type Holder_To is record
      A : Outer_Arr_To;
   end record;
end Types_To;
""".strip(),
    )
    body = run_gen(
        tmp_path,
        {
            "mappings": [
                {"name": "Holder", "from": "Holder_From", "to": "Holder_To", "fields": {"A": "A"}},
            ]
        },
    )
    # Outer array map delegates to inner array map per element
    assert "function Map (A : Types_From.Outer_Arr_From) return Types_To.Outer_Arr_To" in body
    assert "R(I) := Map(A(I))" in body
    # Inner array map casts elements
    assert "function Map (A : Types_From.Inner_Arr_From) return Types_To.Inner_Arr_To" in body
    assert "R(I) := I16 (A(I))" in body


def test_dotted_source_path_scalar(tmp_path: Path):
    # Flatten nested source into top-level destination using dotted path
    write(
        tmp_path / "src/types_from.ads",
        """
package Types_From is
   type I32 is range -2147483648 .. 2147483647;
   type Pos_From is record
      X : I32;
      Y : I32;
   end record;
   type Wrap_From is record
      P : Pos_From;
   end record;
end Types_From;
""".strip(),
    )
    write(
        tmp_path / "src/types_to.ads",
        """
package Types_To is
   type I16 is range -32768 .. 32767;
   type Pos_To is record
      X : I16;
      Y : I16;
   end record;
end Types_To;
""".strip(),
    )
    body = run_gen(
        tmp_path,
        {
            "mappings": [
                {"name": "Flatten", "from": "Wrap_From", "to": "Pos_To", "fields": {"X": "P.X", "Y": "P.Y"}},
            ]
        },
    )
    assert "function Map (X : Types_From.Wrap_From) return Types_To.Pos_To" in body
    assert "X => I16 (X.P.X)" in body
    assert "Y => I16 (X.P.Y)" in body

