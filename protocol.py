"""Line protocol between the UI and the STM32.

PC -> board (one line each, ending with newline):
  PING | MODE,MAN|TGT|SAT | AZEL,az,el | SAT,4B | SITE,lat,lon,alt,offset | START | STOP

Board -> PC (20 per second):
  T,<ms>,<mode>,<state>,<cmd_az>,<cmd_el>,<act_az>,<act_el>,<roll>,<pitch>,<yaw>,<err>,<flags_hex>

state: IDLE | SLEW | TRACK | FAULT
flags (bits, 0 = all fine): 0 enc AZ, 1 enc EL, 2 IMU, 3 driver
"""

NUM_FIELDS = ["cmd_az", "cmd_el", "act_az", "act_el", "roll", "pitch", "yaw", "err"]


def parse_telemetry(line):
    """Return a dict, or None if the line is not a valid telemetry packet."""
    p = line.strip().split(",")
    if len(p) != 13 or p[0] != "T":
        return None
    try:
        d = {"ms": int(p[1]), "mode": p[2], "state": p[3]}
        for k, v in zip(NUM_FIELDS, p[4:12]):
            d[k] = float(v)
        d["flags"] = int(p[12], 16)
    except ValueError:
        return None
    return d
