"""JSON-lines v1 command contract adapter for the desktop UI."""
import json
import math

MAX_LINE = 512


def command(command_id, op, **fields):
    msg = {"v": 1, "type": "cmd", "id": int(command_id), "op": op, **fields}
    return json.dumps(msg, allow_nan=False, separators=(",", ":")) + "\n"


def set_target(command_id, az_deg, el_deg):
    return command(command_id, "set_target", az_deg=az_deg, el_deg=el_deg)


def set_mode(command_id, mode):
    return command(command_id, "set_mode", mode=mode)


def stop(command_id):
    return command(command_id, "stop")


def parse_message(line):
    if len(line.encode("utf-8")) > MAX_LINE:
        raise ValueError("E_LENGTH")
    obj = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("E_NUMBER")))
    if not isinstance(obj, dict) or obj.get("v") != 1 or obj.get("type") not in ("ack", "tel"):
        raise ValueError("E_FORMAT")
    return obj


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)
