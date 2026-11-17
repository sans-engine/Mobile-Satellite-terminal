"""Reading measurement files (CSV). Bad content is skipped and counted, never raised.

Static F407 record columns:
  test_id, reference_deg, ax_raw, ay_raw, az_raw, tilt_signed_deg
  (reference_deg and tilt_signed_deg are optional, the rest are required)

Accepted: ',' ';' or tab separators, decimal point or decimal comma (with ';'),
UTF-8 / UTF-8 BOM / Windows-1254, blank lines, stray spaces, 'nan' cells.
"""
import csv
import math

REQUIRED = ["test_id", "ax_raw", "ay_raw", "az_raw"]
OPTIONAL = ["reference_deg", "tilt_signed_deg"]
NAN = float("nan")

# The app computes the tilt itself from the raw values. The file's own
# tilt_signed_deg is shown next to it; we pick the formula that matches it best.
FORMULAS = {
    "atan2(ax, az)": lambda ax, ay, az: math.degrees(math.atan2(ax, az)),
    "atan2(-ax, az)": lambda ax, ay, az: math.degrees(math.atan2(-ax, az)),
    "atan2(ay, az)": lambda ax, ay, az: math.degrees(math.atan2(ay, az)),
    "atan2(-ay, az)": lambda ax, ay, az: math.degrees(math.atan2(-ay, az)),
}
DEFAULT_FORMULA = "atan2(ax, az)"


def to_float(s):
    """Text to float. Returns NaN for empty, text, nan or inf."""
    if s is None:
        return NAN
    s = str(s).strip().replace(" ", "").replace(",", ".")
    if not s:
        return NAN
    try:
        v = float(s)
    except ValueError:
        return NAN
    return v if math.isfinite(v) else NAN


def _read_text(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as e:
        return None, f"Dosya okunamadı: {e.strerror or e}"
    for enc in ("utf-8-sig", "cp1254"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1"), None


def _split(line, d):
    try:
        return next(csv.reader([line], delimiter=d))
    except (csv.Error, StopIteration):
        return line.split(d)


def _table(text):
    """Return (header, rows, blank). rows = [(line_number, cells)]. header None if empty."""
    lines = text.replace("\x00", "").splitlines()
    first = next((i for i, ln in enumerate(lines) if ln.strip().strip(",;\t")), None)
    if first is None:
        return None, [], len(lines)
    head = lines[first]
    d = ";" if ";" in head else ("\t" if "\t" in head else ",")
    header = [c.strip().lstrip("\ufeff") for c in _split(head, d)]
    rows, blank = [], first
    for i in range(first + 1, len(lines)):
        ln = lines[i]
        if not ln.strip().strip(d + " "):
            blank += 1
            continue
        rows.append((i + 1, _split(ln, d)))
    return header, rows, blank


def tilt(name, ax, ay, az):
    return FORMULAS[name](ax, ay, az)


def best_formula(records):
    """Formula whose result is closest (RMS) to the file's own tilt column."""
    best = (None, None)
    for name in FORMULAS:
        errs = []
        for r in records:
            if not math.isnan(r["file_tilt"]):
                errs.append(tilt(name, r["ax"], r["ay"], r["az"]) - r["file_tilt"])
        if len(errs) < 2:
            return None, None
        rms = math.sqrt(sum(e * e for e in errs) / len(errs))
        if best[1] is None or rms < best[1]:
            best = (name, rms)
    return best


def load_static(path):
    res = {"records": [], "skipped": 0, "blank": 0, "error": None, "formula": None, "rms": None}
    text, err = _read_text(path)
    if err:
        res["error"] = err
        return res
    header, rows, blank = _table(text)
    res["blank"] = blank
    if header is None:
        res["error"] = "Dosya boş."
        return res
    low = [h.lower() for h in header]
    missing = [c for c in REQUIRED if c not in low]
    if missing:
        res["error"] = "Eksik sütun: " + ", ".join(missing)
        return res
    idx = {c: low.index(c) for c in REQUIRED + OPTIONAL if c in low}

    def cell(cells, name):
        i = idx.get(name)
        return cells[i] if i is not None and i < len(cells) else ""

    no = 0
    for lineno, cells in rows:
        ax, ay, az = (to_float(cell(cells, k)) for k in ("ax_raw", "ay_raw", "az_raw"))
        if math.isnan(ax) or math.isnan(ay) or math.isnan(az):
            res["skipped"] += 1
            continue
        no += 1
        res["records"].append({
            "no": no, "line": lineno,
            "test_id": cell(cells, "test_id").strip() or str(no),
            "ref": to_float(cell(cells, "reference_deg")),
            "ax": ax, "ay": ay, "az": az,
            "file_tilt": to_float(cell(cells, "tilt_signed_deg")),
        })
    res["formula"], res["rms"] = best_formula(res["records"])
    return res


def load_series(path):
    """Generic numeric CSV for simulation results: first column is x, the others are series."""
    res = {"xname": "", "x": [], "series": [], "skipped": 0, "blank": 0, "error": None}
    text, err = _read_text(path)
    if err:
        res["error"] = err
        return res
    header, rows, blank = _table(text)
    res["blank"] = blank
    if header is None or len(header) < 2:
        res["error"] = "En az iki sütun gerekli (x ve bir veri sütunu)."
        return res
    res["xname"] = header[0] or "x"
    cols = [[] for _ in header]
    for lineno, cells in rows:
        x = to_float(cells[0] if cells else "")
        if math.isnan(x):
            res["skipped"] += 1
            continue
        res["x"].append(x)
        for j in range(1, len(header)):
            cols[j].append(to_float(cells[j]) if j < len(cells) else NAN)
    for j in range(1, len(header)):
        if any(not math.isnan(v) for v in cols[j]):
            res["series"].append((header[j] or f"sütun {j}", cols[j]))
    if not res["x"]:
        res["error"] = "Dosyada geçerli veri satırı yok."
    elif not res["series"]:
        res["error"] = "Sayısal veri sütunu bulunamadı."
    return res
