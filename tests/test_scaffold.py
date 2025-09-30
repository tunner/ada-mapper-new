import json
import subprocess
import sys
from pathlib import Path


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def is_placeholder(value: object) -> bool:
    return isinstance(value, str) and value.startswith("<") and value.endswith(">")


def run_cli(tmp_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path("tools/gen_mapper.py"))] + args,
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )


def test_init_json_map_scaffolding(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    write(
        src_dir / "types_from.ads",
        """
package Types_From is
   type T_Float_32 is digits 7;
   type T_Integer16 is range -32768 .. 32767;
   type T_Speed is record
      North : T_Float_32;
      East  : T_Float_32;
      Down  : T_Float_32;
   end record;
   type T_Position is record
      Latitude  : T_Float_32;
      Longitude : T_Float_32;
   end record;
   type T_Satellite is record
      ID       : T_Integer16;
      Position : T_Position;
      Speed    : T_Speed;
   end record;
   type T_Satellites is array (1 .. 12) of T_Satellite;
   type T_Status is (Good, Bad, None);
   type T_Position_From_GPS is record
      Position   : T_Position;
      Speed      : T_Speed;
      Satellites : T_Satellites;
      Status     : T_Status;
   end record;
end Types_From;
""".strip(),
    )
    write(
        src_dir / "types_to.ads",
        """
package Types_To is
   type T_Float_16 is digits 4;
   type T_Integer16 is range -32768 .. 32767;
   type T_Speed is record
      North : T_Float_16;
      East  : T_Float_16;
      Down  : T_Float_16;
   end record;
   type T_Position is record
      Lat : T_Integer16;
      Lon : T_Integer16;
   end record;
   type T_Satellite is record
      ID       : T_Integer16;
      Position : T_Position;
      Speed    : T_Speed;
   end record;
   type T_Satellites is array (1 .. 12) of T_Satellite;
   type T_Status is (Good, Bad, None);
   type T_Position_To_Station is record
      Lat        : T_Integer16;
      Lon        : T_Integer16;
      Speed      : T_Speed;
      Satellites : T_Satellites;
      Status     : T_Status;
   end record;
end Types_To;
""".strip(),
    )

    mappings_path = tmp_path / "mappings.json"
    result = run_cli(
        tmp_path,
        [
            str(mappings_path),
            str(src_dir),
            "--init-json-map",
            "Position_From_GPS_To_Station:T_Position_From_GPS:T_Position_To_Station",
        ],
    )
    assert result.returncode == 0, result.stderr + result.stdout

    data = json.loads(mappings_path.read_text())
    entries = {entry["to"]: entry for entry in data["mappings"]}

    top = entries["T_Position_To_Station"]
    assert top["fields"]["Speed"] == "Speed"
    assert top["fields"]["Satellites"] == "Satellites"
    assert top["fields"]["Status"] == "Status"
    assert is_placeholder(top["fields"]["Lat"])
    assert is_placeholder(top["fields"]["Lon"])

    satellite = entries["T_Satellite"]
    assert satellite["from"] == "T_Satellite"
    assert satellite["fields"]["ID"] == "ID"
    assert satellite["fields"]["Position"] == "Position"
    assert satellite["fields"]["Speed"] == "Speed"

    speed = entries["T_Speed"]
    assert speed["from"] == "T_Speed"
    assert speed["fields"]["North"] == "North"


def test_update_json_map_fills_placeholders(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    write(
        src_dir / "types_from.ads",
        """
package Types_From is
   type Foo_To is record
      Speed_North : Integer;
      Speed_South : Integer;
   end record;
end Types_From;
""".strip(),
    )
    write(
        src_dir / "types_to.ads",
        """
package Types_To is
   type Foo_To is record
      Speed_North : Integer;
      Speed_South : Integer;
   end record;
end Types_To;
""".strip(),
    )

    mappings = {
        "mappings": [
            {
                "name": "Foo",
                "from": "<SOURCE_TYPE_FOR_FOO_TO>",
                "to": "Foo_To",
                "fields": {
                    "Speed_North": "<SPEED_NORTH_INPUT_FIELD>",
                    "Speed_South": "Speed_South",
                },
            }
        ]
    }
    mappings_path = tmp_path / "mappings.json"
    mappings_path.write_text(json.dumps(mappings, indent=2))

    result = run_cli(
        tmp_path,
        [
            str(mappings_path),
            str(src_dir),
            "--update-json-map",
        ],
    )
    assert result.returncode == 0, result.stderr + result.stdout

    data = json.loads(mappings_path.read_text())
    by_to = {entry["to"]: entry for entry in data["mappings"]}
    foo = by_to["Foo_To"]
    assert foo["fields"]["Speed_North"] == "Speed_North"
    assert foo["fields"]["Speed_South"] == "Speed_South"
    assert foo["from"] == "Foo_To"
