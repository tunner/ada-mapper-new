import json
import subprocess
import sys
from pathlib import Path


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_custom_spec_filenames(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    write(
        src_dir / "custom_from.ads",
        """
package Types_From is
   type Foo_From is record
      Value : Integer;
   end record;
end Types_From;
""".strip(),
    )
    write(
        src_dir / "custom_to.ads",
        """
package Types_To is
   type Foo_To is record
      Value : Integer;
   end record;
end Types_To;
""".strip(),
    )

    mappings = {
        "mappings": [
            {"name": "Foo", "from": "Foo_From", "to": "Foo_To", "fields": {"Value": "Value"}}
        ]
    }
    mappings_path = tmp_path / "mappings.json"
    mappings_path.write_text(json.dumps(mappings))

    result = subprocess.run(
        [
            sys.executable,
            str(Path("tools/gen_mapper.py")),
            "--from-spec",
            "custom_from.ads",
            "--to-spec",
            "custom_to.ads",
            str(mappings_path),
            str(src_dir),
        ],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    generated = (src_dir / "position_mappers.adb").read_text()
    assert "function Map (X : Types_From.Foo_From) return Types_To.Foo_To" in generated
    assert "Value => Integer (X.Value)" in generated
