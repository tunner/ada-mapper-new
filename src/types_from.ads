package Types_From is
   type T_Float_32 is digits 7;
   
   --  New nested type example
   type T_Speed is record
      North : T_Float_32;
      East  : T_Float_32;
      Down  : T_Float_32;
   end record;

   type T_Position_From_GPS is record
      Latitude  : T_Float_32;
      Longitude : T_Float_32;
      Speed     : T_Speed;
   end record;


end Types_From;
