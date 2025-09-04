with Ada.Text_IO;         use Ada.Text_IO;
with Types_From;          use Types_From;
with Types_To;            use Types_To;
with Position_Mappers;    use Position_Mappers;

procedure Main is
   From_Pos : T_Position_From_GPS :=
     (Latitude => Types_From.Float32(12.34),
      Longitude => Types_From.Float32(56.78));
   Dest     : T_Position_To_Station := Map(From_Pos);
begin
   Put_Line(
     "Lat=" & Types_To.Float16'Image(Dest.Lat) &
     " Long=" & Types_To.Float16'Image(Dest.Long));
end Main;
