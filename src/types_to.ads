package Types_To is
   type Float16 is digits 4;
   type T_Integer16 is range -32768 .. 32767;
   type T_Position_To_Station is record
      Lat  : T_Integer16;
      Long : T_Integer16;
   end record;
end Types_To;
