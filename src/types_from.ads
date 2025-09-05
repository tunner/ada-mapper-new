package Types_From is
   type T_Unsigned_32 is range 0 .. 4294967295;
   type T_Float_32 is digits 7;
   
   --  New nested type example
   type T_Speed is record
      North : T_Float_32;
      East  : T_Float_32;
      Down  : T_Float_32;
   end record;

   Type T_Position is record
      Latitude  : T_Float_32;
      Longitude : T_Float_32;
   end record;

   type T_Satellite is record
      ID       : T_Unsigned_32;
      Position : T_Position;
      Speed    : T_Speed;
   end record;

   type T_Satellites is array (1 .. 12) of T_Satellite;

   --  Enum for demonstration
   type T_Status is (Unknown, Good, Bad);

   type T_Position_From_GPS is record
      Position : T_Position;
      Speed     : T_Speed;
      Satellites: T_Satellites;
      Status    : T_Status;
   end record;


end Types_From;
