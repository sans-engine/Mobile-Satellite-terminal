"""Geostationary satellite look angles.

Longitudes are degrees East. VERIFY them before the competition.
Add 4A here if the committee confirms it (about 42.0 East).
"""
import math

SATS = {"4B": 50.0, "5A": 31.0}

RE = 6378.137    # Earth radius, km
R = 42164.0      # geostationary orbit radius, km


def look_angles(sat_lon, lat, lon, heading_offset=0.0):
    """Return (azimuth, elevation) in degrees for a northern-hemisphere site.

    heading_offset: the true-north bearing that the base's azimuth zero points to.
    Azimuth is returned in the base frame (true azimuth minus the offset).
    """
    d = math.radians(sat_lon - lon)      # east positive
    phi = math.radians(lat)
    cos_g = math.cos(phi) * math.cos(d)
    sin_g = math.sqrt(max(1.0 - cos_g * cos_g, 1e-12))
    el = math.degrees(math.atan2(cos_g - RE / R, sin_g))
    az = 180.0 - math.degrees(math.atan2(math.sin(d), math.cos(d) * math.sin(phi)))
    return (az - heading_offset) % 360.0, el


if __name__ == "__main__":
    for name, sat_lon in SATS.items():
        az, el = look_angles(sat_lon, 36.90, 30.70)
        print(f"Turksat {name}: az {az:.1f}  el {el:.1f}")
