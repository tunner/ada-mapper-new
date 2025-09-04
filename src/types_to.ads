package Types_To is
   type T_Float_16 is digits 4;
   type T_Integer16 is range -32768 .. 32767;

   --  New nested type example
   type T_Speed is record
      North : T_Float_16;
      East  : T_Float_16;
      Down  : T_Float_16;
   end record;
   type T_Position_To_Station is record
      Lat  : T_Integer16;
      Long : T_Integer16;
      Speed: T_Speed;
   end record;

end Types_To;
