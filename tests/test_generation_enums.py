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


def test_enum_by_name_mapping(tmp_path: Path):
    # Same literals, different order -> expect dedicated enum Map with case mapping by name
    write(
        tmp_path / "src/types_from.ads",
        """
package Types_From is
   type Status_F is (Unknown, Good, Bad);
   type Wrap_From is record
      S : Status_F;
   end record;
end Types_From;
""".strip(),
    )
    write(
        tmp_path / "src/types_to.ads",
        """
package Types_To is
   type Status_T is (Good, Bad, Unknown);
   type Wrap_To is record
      S : Status_T;
   end record;
end Types_To;
""".strip(),
    )
    body = run_gen(
        tmp_path,
        {
            "mappings": [
                {"name": "Wrap", "from": "Wrap_From", "to": "Wrap_To", "fields": {"S": "S"}},
            ]
        },
    )
    assert "function Map (E : Types_From.Status_F) return Types_To.Status_T" in body
    assert "(case E is when Unknown => Unknown, when Good => Good, when Bad => Bad)" in body
    assert "S => Map(X.S)" in body


def test_enum_positional_mapping(tmp_path: Path):
    # Different literal names -> expect positional mapping via 'Val('Pos)
    write(
        tmp_path / "src/types_from.ads",
        """
package Types_From is
   type Color_F is (Red, Green, Blue);
   type Wrap_From is record
      C : Color_F;
   end record;
end Types_From;
""".strip(),
    )
    write(
        tmp_path / "src/types_to.ads",
        """
package Types_To is
   type Color_T is (Cyan, Magenta, Yellow);
   type Wrap_To is record
      C : Color_T;
   end record;
end Types_To;
""".strip(),
    )
    body = run_gen(
        tmp_path,
        {
            "mappings": [
                {"name": "Wrap", "from": "Wrap_From", "to": "Wrap_To", "fields": {"C": "C"}},
            ]
        },
    )
    assert "function Map (E : Types_From.Color_F) return Types_To.Color_T" in body
    assert "Color_T'Val(Color_F'Pos(E))" in body
    assert "C => Map(X.C)" in body
