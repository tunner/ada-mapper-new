package Types_To is
   type T_Float_16    is digits 4;
   type T_Integer16   is range -32_768 .. 32_767;
   type T_Unsigned_8  is range 0 .. 255;
   type T_Fixed_Angle is delta 0.25 range -720.0 .. 720.0;

   subtype T_Latitude_Count  is T_Integer16 range -540 .. 540;
   subtype T_Longitude_Count is T_Integer16 range -1_080 .. 1_080;

   type T_Speed_Fraction is delta 0.1 range -2_000.0 .. 2_000.0;

   type T_Speed is record
      North : T_Speed_Fraction;
      East  : T_Speed_Fraction;
      Down  : T_Speed_Fraction;
   end record;

   type T_Speed_Access   is access all T_Speed;
   type T_Speed_Buffer   is array (Positive range <>) of T_Speed_Access;

   Type T_Position is record
      Lat : T_Latitude_Count;
      Lon : T_Longitude_Count;
   end record;

   type T_Position_Access    is access all T_Position;
   type T_Position_Handle_Set is array (Positive range <>) of T_Position_Access;

   type T_Satellite is record
      ID       : T_Unsigned_8;
      Position : T_Position;
      Speed    : T_Speed;
   end record;

   subtype T_Satellite_Index is Positive range 1 .. 12;
   type T_Satellites         is array (T_Satellite_Index) of T_Satellite;
   type T_Satellite_Positions is array (T_Satellite_Index) of T_Position_Access;

   --  Enum for demonstration (reordered literals)
   type T_Status is (Good, Bad, None);

   type T_Position_To_Station is record
      Lat        : T_Latitude_Count;
      Lon        : T_Longitude_Count;
      Speed      : T_Speed;
      Satellites : T_Satellites;
      Status     : T_Status;
   end record;

end Types_To;
