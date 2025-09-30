package Types_From is
   type T_Unsigned_32 is range 0 .. 4_294_967_295;
   subtype e_Satellite_Id is T_Unsigned_32 range 0 .. 65_535;

   type T_Float_32 is digits 7;
   subtype e_Latitude_F32  is T_Float_32 range -90.0  .. 90.0;
   subtype e_Longitude_F32 is T_Float_32 range -180.0 .. 180.0;

   type e_Fixed_Angle is delta 0.25 range -720.0 .. 720.0;

   type e_Speed_Fixed is delta 0.05 range -1_000.0 .. 1_000.0;

   type e_Speed is record
      North : e_Speed_Fixed;
      East  : e_Speed_Fixed;
      Down  : e_Speed_Fixed;
   end record;

   type e_Speed_Buffer  is array (Positive range <>) of e_Speed;
   subtype e_Speed_Buffer_2 is e_Speed_Buffer(1 .. 2);

   type e_Position is record
      Latitude        : e_Latitude_F32;
      Longitude       : e_Longitude_F32;
      Heading         : e_Fixed_Angle;
      Speed_History   : e_Speed_Buffer_2;
   end record;

   type e_Position_Catalog  is array (Positive range <>) of e_Position;
   subtype e_Position_Catalog_4 is e_Position_Catalog(1 .. 4);

   subtype e_Satellite_Index is Positive range 1 .. 12;
   subtype e_Satellite_Path_Slot is Positive range 1 .. 6;

   type e_Satellite_Position_Routes is array (e_Satellite_Index range <>, e_Satellite_Path_Slot range <>) of e_Position;
   subtype e_Satellite_Route_Window is e_Satellite_Position_Routes(1 .. 3, 1 .. 2);

   type e_Satellite is record
      ID         : e_Satellite_Id;
      Position   : e_Position;
      Speed      : e_Speed;
      Snapshots  : e_Position_Catalog_4;
      Waypoints  : e_Satellite_Route_Window;
   end record;

   type e_Satellites      is array (e_Satellite_Index) of e_Satellite;
   type e_Satellite_Refs  is array (e_Satellite_Index) of e_Position;

   --  Enum for demonstration
   type e_Status is (Unknown, Good, Bad);

   type T_Position_From_GPS is record
      FR_Position        : e_Position;
      FR_Speed           : e_Speed;
      FR_Satellites      : e_Satellites;
      FR_Sat_Pos_Refs    : e_Satellite_Refs;
      FR_Sat_Routes      : e_Satellite_Route_Window;
      FR_Status          : e_Status;
   end record;

end Types_From;
