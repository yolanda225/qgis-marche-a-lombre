# -*- coding: utf-8 -*-
import math
from datetime import datetime, timezone
try:
    import pvlib
    HAS_PVLIB = True
except (ImportError, ValueError, RuntimeError, OSError) as e:
    print(f"PVLib import failed ({e}). Using manual Solar Position Calculation")
    HAS_PVLIB = False

class TrailPoint:

    def __init__(self, lon, lat, x, y, z, datetime):
        self.lon = lon
        self.lat = lat
        self.x = x
        self.y = y
        self.z = z
        self.datetime = datetime
        self.solar_pos = self.calc_solar_pos(self.datetime)

    def calc_solar_pos(self, dt):
        """
        Calculates Solar Azimuth and Elevation for a given place and time
        
        Args:
            dt (datetime): A datetime object

        Returns:
            tuple (float): (elevation, azimuth) in radians
        """
        dt = dt.toUTC().toPyDateTime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        if HAS_PVLIB:
            try:
                sp = pvlib.solarposition.get_solarposition(dt, self.lat, self.lon, altitude=None, pressure=None, method='nrel_numpy')
                azimuth_pvlib = sp['azimuth'].iloc[0]
                elevation_pvlib = 90-sp['zenith'].iloc[0]
                return (math.radians(elevation_pvlib), math.radians(azimuth_pvlib))
            except Exception as e:
                print(f"PVLib failed, falling back to manual: {e}")
        
        # Calculate time variables
        start_of_year = datetime(dt.year, 1, 1, tzinfo=timezone.utc)
        day_of_year = (dt - start_of_year).days + 1
        hour_decimal = dt.hour + dt.minute / 60.0 + dt.second / 3600.0

        # Fractional year (gamma) in radians
        gamma = (2 * math.pi / 365.0) * (day_of_year - 1 + (hour_decimal - 12) / 24)

        # Equation of time describes offset between mean and true solar time for given day
        # is due to elliptic orbit and inclined axis of earth
        eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma) \
                 - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))

        # Solar Declination (angle between solar radiation and equatorial plane) Spencer's Method
        decl = 0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma) \
               - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma) \
               - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma)

        # True Solar Time
        # Earth rotates 1 degree every 4 minutes
        time_offset = eqtime + 4 * self.lon
        tst = hour_decimal * 60 + time_offset
        
        # Hour Angle in radians - angle between local lon and lon with solar noon
        # (tst / 4) - 180 converts minutes to degrees so that 12:00 PM becomes 0
        ha_deg = (tst / 4) - 180
        ha_rad = math.radians(ha_deg)
        
        # more efficient to compute cos(decl) and sin(decl) earlier
        lat_rad = math.radians(self.lat)
        sin_dec, cos_dec = math.sin(decl), math.cos(decl)
        sin_lat, cos_lat = math.sin(lat_rad), math.cos(lat_rad)
        sin_ha, cos_ha = math.sin(ha_rad), math.cos(ha_rad)

        # Caluclate Elevation angle
        sin_elev = sin_lat * sin_dec + cos_lat * cos_dec * cos_ha
        elevation_rad = math.asin(max(-1.0, min(1.0, sin_elev)))

        # Calculate Azimuth angle
        x = -cos_ha * sin_lat * cos_dec + sin_dec * cos_lat
        y = -sin_ha * cos_dec
        azimuth_rad = math.atan2(y, x)
        # Normalize to 0-2pi
        azimuth_rad = (azimuth_rad + 2 * math.pi) % (2 * math.pi)

        return (elevation_rad, azimuth_rad)
