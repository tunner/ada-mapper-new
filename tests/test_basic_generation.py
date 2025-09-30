import json
import subprocess
import sys
from pathlib import Path


def write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_basic_scalar_mapping(tmp_path: Path):
    # Arrange minimal types and mapping in a temp workspace
    src_dir = tmp_path / "src"
    types_from = src_dir / "types_from.ads"
    types_to = src_dir / "types_to.ads"
    mappings = tmp_path / "mappings.json"

    write(
        types_from,
        """
package Types_From is
   type T_Int32 is range -2147483648 .. 2147483647;
   type T_From is record
      A : T_Int32;
      B : T_Int32;
      C : T_Int32;
   end record;
end Types_From;
""".strip()
    )

    write(
        types_to,
        """
package Types_To is
   type T_Int16 is range -32768 .. 32767;
   type T_To is record
      A : T_Int16;
      B : T_Int16;
      C : T_Int16;
   end record;
end Types_To;
""".strip()
    )

    mappings.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "name": "Basic",
                        "from": "T_From",
                        "to": "T_To",
                        "fields": {"A": "A", "B": "B", "C": "C"},
                    }
                ]
            }
        )
    )

    # Act: run the generator pointing to the temp files
    result = subprocess.run(
        [sys.executable, str(Path("tools/gen_mapper.py")), str(mappings), str(src_dir)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout

    body = (src_dir / "position_mappers.adb").read_text()

    # Assert: generated code maps and casts each field
    assert "function Map (X : Types_From.T_From) return Types_To.T_To" in body
    assert "A => T_Int16 (X.A)" in body
    assert "B => T_Int16 (X.B)" in body
    assert "C => T_Int16 (X.C)" in body


def test_aliased_field_type(tmp_path: Path):
    src_dir = tmp_path / "src"
    types_from = src_dir / "types_from.ads"
    types_to = src_dir / "types_to.ads"
    mappings = tmp_path / "mappings.json"

    write(
        types_from,
        """
package Types_From is
   type Flag_From is record
      Trigger : Boolean;
   end record;
end Types_From;
""".strip()
    )

    write(
        types_to,
        """
package Types_To is
   type Flag_To is record
      Trigger : aliased Boolean;
   end record;
end Types_To;
""".strip()
    )

    mappings.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "name": "Flag",
                        "from": "Flag_From",
                        "to": "Flag_To",
                        "fields": {"Trigger": "Trigger"},
                    }
                ]
            }
        )
    )

    result = subprocess.run(
        [sys.executable, str(Path("tools/gen_mapper.py")), str(mappings), str(src_dir)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout

    body = (src_dir / "position_mappers.adb").read_text()
    assert "function Map (X : Types_From.Flag_From) return Types_To.Flag_To" in body
    assert "Trigger => Boolean (X.Trigger)" in body


def test_record_subtype_resolution(tmp_path: Path):
    src_dir = tmp_path / "src"
    types_from = src_dir / "types_from.ads"
    types_to = src_dir / "types_to.ads"
    mappings = tmp_path / "mappings.json"

    write(
        types_from,
        """
package Types_From is
   type Inner_Base is record
      Value : Integer;
   end record;
   subtype Inner_From is Inner_Base;
   type Wrapper_From is record
      Inner : Inner_From;
   end record;
end Types_From;
""".strip()
    )

    write(
        types_to,
        """
package Types_To is
   type Inner_Base is record
      Value : Integer;
   end record;
   subtype Inner_To is Inner_Base;
   type Wrapper_To is record
      Inner : Inner_To;
   end record;
end Types_To;
""".strip()
    )

    mappings.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "name": "Wrapper",
                        "from": "Wrapper_From",
                        "to": "Wrapper_To",
                        "fields": {"Inner": "Inner"},
                    }
                ]
            }
        )
    )

    result = subprocess.run(
        [sys.executable, str(Path("tools/gen_mapper.py")), str(mappings), str(src_dir)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout

    body = (src_dir / "position_mappers.adb").read_text()
    assert "function Map (X : Types_From.Wrapper_From) return Types_To.Wrapper_To" in body
    assert "Inner => (" in body
    assert "Value => Integer (X.Inner.Value)" in body


def test_array_subtype_resolution(tmp_path: Path):
    src_dir = tmp_path / "src"
    types_from = src_dir / "types_from.ads"
    types_to = src_dir / "types_to.ads"
    mappings = tmp_path / "mappings.json"

    write(
        types_from,
        """
package Types_From is
   type Byte is range 0 .. 255;
   type Byte_Array_Base is array (0 .. 7) of Byte;
   subtype Byte_Array_From is Byte_Array_Base;
   type Wrapper_From is record
      Data : Byte_Array_From;
   end record;
end Types_From;
""".strip()
    )

    write(
        types_to,
        """
package Types_To is
   type Byte_To is range 0 .. 255;
   type Byte_Array_Base is array (0 .. 7) of Byte_To;
   subtype Byte_Array_To is Byte_Array_Base;
   type Wrapper_To is record
      Data : Byte_Array_To;
   end record;
end Types_To;
""".strip()
    )

    mappings.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "name": "Wrapper",
                        "from": "Wrapper_From",
                        "to": "Wrapper_To",
                        "fields": {"Data": "Data"},
                    }
                ]
            }
        )
    )

    result = subprocess.run(
        [sys.executable, str(Path("tools/gen_mapper.py")), str(mappings), str(src_dir)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout

    body = (src_dir / "position_mappers.adb").read_text()
    assert "function Map (X : Types_From.Wrapper_From) return Types_To.Wrapper_To" in body
    assert "Data => Map(X.Data)" in body
    assert "function Map (A : Types_From.Byte_Array_From) return Types_To.Byte_Array_To" in body
    assert "R(I) := Byte_To (A(I));" in body


def test_generation_fails_when_placeholders_remain(tmp_path: Path):
    src_dir = tmp_path / "src"
    types_from = src_dir / "types_from.ads"
    types_to = src_dir / "types_to.ads"
    mappings = tmp_path / "mappings.json"

    write(
        types_from,
        """
package Types_From is
   type T_Int32 is range -2147483648 .. 2147483647;
   type T_From is record
      A : T_Int32;
   end record;
end Types_From;
""".strip()
    )

    write(
        types_to,
        """
package Types_To is
   type T_Int16 is range -32768 .. 32767;
   type T_To is record
      A : T_Int16;
   end record;
end Types_To;
""".strip()
    )

    mappings.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "name": "Basic",
                        "from": "T_From",
                        "to": "T_To",
                        "fields": {"A": "<A_INPUT_FIELD>"},
                    }
                ]
            }
        )
    )

    result = subprocess.run(
        [sys.executable, str(Path("tools/gen_mapper.py")), str(mappings), str(src_dir)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "placeholder" in result.stderr.lower()
    assert "Basic" in result.stderr


def test_generation_fails_for_unknown_fields(tmp_path: Path):
    src_dir = tmp_path / "src"
    types_from = src_dir / "types_from.ads"
    types_to = src_dir / "types_to.ads"
    mappings = tmp_path / "mappings.json"

    write(
        types_from,
        """
package Types_From is
   type T_Int32 is range -2147483648 .. 2147483647;
   type T_From is record
      A : T_Int32;
   end record;
end Types_From;
""".strip()
    )

    write(
        types_to,
        """
package Types_To is
   type T_Int16 is range -32768 .. 32767;
   type T_To is record
      B : T_Int16;
   end record;
end Types_To;
""".strip()
    )

    mappings.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "name": "Basic",
                        "from": "T_From",
                        "to": "T_To",
                        "fields": {"B": "Missing_Field"},
                    }
                ]
            }
        )
    )

    result = subprocess.run(
        [sys.executable, str(Path("tools/gen_mapper.py")), str(mappings), str(src_dir)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "unknown source field" in result.stderr.lower()
    assert "Missing_Field" in result.stderr


def test_default_sentinel_generates_defaults(tmp_path: Path):
    src_dir = tmp_path / "src"
    types_from = src_dir / "types_from.ads"
    types_to = src_dir / "types_to.ads"
    mappings = tmp_path / "mappings.json"

    write(
        types_from,
        """
package Types_From is
   type T_From is record
      A : Integer;
   end record;
end Types_From;
""".strip(),
    )

    write(
        types_to,
        """
package Types_To is
   type Color is (Red, Green, Blue);
   type Vector is array (1 .. 2) of Integer;
   type T_To is record
      A : Integer;
      B : Color;
      C : Vector;
   end record;
end Types_To;
""".strip(),
    )

    mappings.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "name": "Defaults",
                        "from": "T_From",
                        "to": "T_To",
                        "fields": {"A": "__DEFAULT__", "B": "__DEFAULT__", "C": "__DEFAULT__"},
                    }
                ]
            }
        )
    )

    result = subprocess.run(
        [sys.executable, str(Path("tools/gen_mapper.py")), str(mappings), str(src_dir)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout

    body = (src_dir / "position_mappers.adb").read_text()
    assert "A => Integer'First, -- defaulted (__DEFAULT__)" in body
    assert "B => Red, -- defaulted (__DEFAULT__)" in body
    assert "C => Vector'(others => Integer'First) -- defaulted (__DEFAULT__)" in body


def test_array_with_aliased_component(tmp_path: Path):
    src_dir = tmp_path / "src"
    types_from = src_dir / "types_from.ads"
    types_to = src_dir / "types_to.ads"
    mappings = tmp_path / "mappings.json"

    write(
        types_from,
        """
package Types_From is
   type Byte is range 0 .. 255;
   type Byte_Array_From is array (0 .. 7) of aliased Byte;
   type Wrapper_From is record
      Data : Byte_Array_From;
   end record;
end Types_From;
""".strip()
    )

    write(
        types_to,
        """
package Types_To is
   type Byte_To is range 0 .. 255;
   type Byte_Array_To is array (0 .. 7) of Byte_To;
   type Wrapper_To is record
      Data : Byte_Array_To;
   end record;
end Types_To;
""".strip()
    )

    mappings.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "name": "Wrapper",
                        "from": "Wrapper_From",
                        "to": "Wrapper_To",
                        "fields": {"Data": "Data"},
                    }
                ]
            }
        )
    )

    result = subprocess.run(
        [sys.executable, str(Path("tools/gen_mapper.py")), str(mappings), str(src_dir)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout

    body = (src_dir / "position_mappers.adb").read_text()
    assert "function Map (X : Types_From.Wrapper_From) return Types_To.Wrapper_To" in body
    assert "Data => Map(X.Data)" in body
    assert "function Map (A : Types_From.Byte_Array_From) return Types_To.Byte_Array_To" in body
    assert "R(I) := Byte_To (A(I));" in body
