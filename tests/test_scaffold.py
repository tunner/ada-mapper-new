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
    assert is_placeholder(top["fields"]["Lat"])
    assert is_placeholder(top["fields"]["Lon"])
    assert top["fields"]["Speed"] == "Speed"
    assert top["fields"]["Satellites"] in {"Satellites", "FR_Satellites.List"}
    assert is_placeholder(top["fields"]["Lat"])
    assert is_placeholder(top["fields"]["Lon"])
    assert top["fields"]["Status"] == "Status"
    if "Sat_Position_Refs" in top["fields"]:
        assert top["fields"]["Sat_Position_Refs"] == "FR_Sat_Pos_Refs"
    if "Sat_Routes" in top["fields"]:
        assert top["fields"]["Sat_Routes"] == "FR_Sat_Routes"

    satellite = entries["T_Satellite"]
    assert satellite["from"] in {"T_Satellite", "e_Satellite"}
    assert satellite["fields"]["ID"] == "ID"
    assert satellite["fields"]["Position"] == "Position"
    assert satellite["fields"]["Speed"] == "Speed"

    speed = entries["T_Speed"]
    assert speed["from"] == "T_Speed"
    assert speed["fields"]["North"] == "North"

    status = entries["T_Status"]
    assert status["from"] == "T_Status"
    assert status["fields"]["Good"] == "Good"
    assert status["fields"]["Bad"] == "Bad"
    assert status["fields"]["None"] == "None"


def test_update_json_map_fills_placeholders(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    write(
        src_dir / "types_from.ads",
        """
package Types_From is
   type Sat is record
      ID : Integer;
   end record;
   type Sats is array (1 .. 3) of Sat;
   type Sat_List is record
      Count : Integer;
      List  : Sats;
   end record;
   type Foo_To is record
      Speed_North : Integer;
      Speed_South : Integer;
      Satellites  : Sat_List;
   end record;
end Types_From;
""".strip(),
    )
    write(
        src_dir / "types_to.ads",
        """
package Types_To is
   type Sat is record
      ID : Integer;
   end record;
   type Sats is array (1 .. 3) of Sat;
   type Foo_To is record
      Speed_North : Integer;
      Speed_South : Integer;
      Satellites  : Sats;
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
                    "Satellites": "Satellites.List",
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
    assert foo["fields"]["Satellites"] == "Satellites.List"
    assert foo["from"] == "Foo_To"
    sat_entry = by_to["Sat"]
    assert sat_entry["from"] == "Sat"


def test_update_json_map_does_not_reintroduce_placeholders(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    write(
        src_dir / "types_from.ads",
        """
package Types_From is
   type Item is record
      Value : Integer;
   end record;
   type Items is array (1 .. 4) of Item;
   type Record_From is record
      Items_Field : Items;
   end record;
end Types_From;
""".strip(),
    )
    write(
        src_dir / "types_to.ads",
        """
package Types_To is
   type Item is record
      Value : Integer;
   end record;
   type Items is array (1 .. 4) of Item;
   type Record_To is record
      Items_Field : Items;
   end record;
end Types_To;
""".strip(),
    )

    mappings = {
        "mappings": [
            {
                "name": "Record",
                "from": "Record_From",
                "to": "Record_To",
                "fields": {"Items_Field": "Items_Field"},
            }
        ]
    }
    mappings_path = tmp_path / "mappings.json"
    mappings_path.write_text(json.dumps(mappings, indent=2))

    # First update should keep explicit mapping and add element mapping.
    result = run_cli(tmp_path, [str(mappings_path), str(src_dir), "--update-json-map"])
    assert result.returncode == 0, result.stderr + result.stdout
    first = json.loads(mappings_path.read_text())
    entries = {entry["to"]: entry for entry in first["mappings"]}
    assert entries["Record_To"]["from"] == "Record_From"
    # Run update again: should not flip Items mapping back to placeholder.
    result = run_cli(tmp_path, [str(mappings_path), str(src_dir), "--update-json-map"])
    assert result.returncode == 0, result.stderr + result.stdout
    second = json.loads(mappings_path.read_text())
    entries = {entry["to"]: entry for entry in second["mappings"]}
    assert entries["Record_To"]["fields"]["Items_Field"] == "Items_Field"


def test_update_json_map_skips_type_family_mismatch(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    write(
        src_dir / "types_from.ads",
        """
package Types_From is
   type Speed_Scalar is Integer;
   type Record_From is record
      Speed : Speed_Scalar;
   end record;
end Types_From;
""".strip(),
    )
    write(
        src_dir / "types_to.ads",
        """
package Types_To is
   type Speed_Rec is record
      Value : Integer;
   end record;
   type Record_To is record
      Speed : Speed_Rec;
   end record;
end Types_To;
""".strip(),
    )

    mappings = {
        "mappings": [
            {
                "name": "Record",
                "from": "Record_From",
                "to": "Record_To",
                "fields": {
                    "Speed": "Speed",
                },
            }
        ]
    }
    mappings_path = tmp_path / "mappings.json"
    mappings_path.write_text(json.dumps(mappings, indent=2))

    result = run_cli(tmp_path, [str(mappings_path), str(src_dir), "--update-json-map"])
    assert result.returncode == 0, result.stderr + result.stdout
    data = json.loads(mappings_path.read_text())
    record = {entry["to"]: entry for entry in data["mappings"]}["Record_To"]
    # Because type families differ (record vs scalar), field remains placeholder
    assert record["fields"]["Speed"].startswith("<")


def test_init_json_map_errors_when_type_missing(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    write(
        src_dir / "types_from.ads",
        """
package Types_From is
   type T_Position_From_GPS is record
      Lat : Integer;
   end record;
end Types_From;
""".strip(),
    )
    write(
        src_dir / "types_to.ads",
        """
package Types_To is
   -- intentionally missing T_Position_To_Station record definition
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
    assert result.returncode != 0
    assert "destination type 'T_Position_To_Station'" in result.stderr
