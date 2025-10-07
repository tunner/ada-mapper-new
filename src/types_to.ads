package Types_To is
   type T_Float_16    is digits 4;
   type T_Integer16   is range -32_768 .. 32_767;
   type T_Unsigned_8  is range 0 .. 255;
   type T_Fixed_Angle is delta 0.25 range -720.0 .. 720.0;

   subtype T_Latitude_Count  is T_Integer16 range -540 .. 540;
   subtype T_Longitude_Count is T_Integer16 range -1_080 .. 1_080;

   type T_Speed_Fraction is delta 0.1 range -2_000.0 .. 2_000.0;

   package Telemetry is
      type T_Speed is record
         North : T_Speed_Fraction;
         East  : T_Speed_Fraction;
         Down  : T_Speed_Fraction;
      end record;

      type T_Speed_Buffer   is array (Positive range <>) of T_Speed;
      subtype T_Speed_Buffer_2 is T_Speed_Buffer(1 .. 2);

      type T_Position is record
         Lat           : T_Latitude_Count;
         Lon           : T_Longitude_Count;
         Heading_Track : T_Fixed_Angle;
         Recent_Speeds : T_Speed_Buffer_2;
      end record;

      type T_Position_Catalog   is array (Positive range <>) of T_Position;
      subtype T_Position_Catalog_4 is T_Position_Catalog(1 .. 4);

      --  Enum for demonstration (reordered literals)
      type T_Status is (Good, Bad, None);
   end Telemetry;

   package Diagnostics is
      type T_Speed is record
         Surge : T_Speed_Fraction;
         Sway  : T_Speed_Fraction;
         Heave : T_Speed_Fraction;
      end record;
   end Diagnostics;

   type T_Satellite is record
      ID        : T_Unsigned_8;
      Position  : Telemetry.T_Position;
      Speed     : Telemetry.T_Speed;
      Name      : String (1 .. 10);
      Snapshots : Telemetry.T_Position_Catalog_4;
   end record;

   subtype T_Satellite_Primary_Index is Positive range 1 .. 12;
   subtype T_Satellite_Secondary_Index is Positive range 1 .. 6;

   type T_Satellites          is array (T_Satellite_Primary_Index) of T_Satellite;
   type T_Satellite_Positions is array (T_Satellite_Primary_Index) of Telemetry.T_Position;
   type T_Satellite_Position_Routes is array (T_Satellite_Primary_Index range <>, T_Satellite_Secondary_Index range <>) of Telemetry.T_Position;
   subtype T_Satellite_Position_Routes_Window is T_Satellite_Position_Routes(1 .. 3, 1 .. 2);

   type T_Position_To_Station is record
      Lat               : T_Latitude_Count;
      Lon               : T_Longitude_Count;
      Speed             : Telemetry.T_Speed;
      Satellites        : T_Satellites;
      Status            : Telemetry.T_Status;
      Sat_Position_Refs : T_Satellite_Positions;
      Sat_Routes        : T_Satellite_Position_Routes_Window;
   end record;

end Types_To;
