package Types_From is
   type Float32 is digits 7;
   type T_Position_From_GPS is record
      Latitude  : Float32;
      Longitude : Float32;
   end record;
end Types_From;
