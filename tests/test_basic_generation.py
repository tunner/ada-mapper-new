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

