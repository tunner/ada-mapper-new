package Types_To is
   type T_Float_16 is digits 4;
   type T_Integer16 is range -32768 .. 32767;
   type T_Unsigned_8 is range 0 .. 255;   
   type T_Float_32 is digits 7;

   --  New nested type example
   type T_Speed is record
      North : T_Float_16;
      East  : T_Float_16;
      Down  : T_Float_16;
   end record;

   Type T_Position is record
      Lat  : T_Integer16;
      Lon : T_Integer16;
   end record;

   type T_Satellite is record
      ID       : T_Unsigned_8;
      Position : T_Position;
      Speed    : T_Speed;
   end record;

   type T_Satellites is array (1 .. 12) of T_Satellite;

   type T_Position_To_Station is record
      Position: T_Position;
      Speed: T_Speed;
      Satellites: T_Satellites;
   end record;

end Types_To;
