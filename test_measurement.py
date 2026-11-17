"""Run:  python -m pytest -q   (pip install pytest)
Bad files must be skipped or reported, never crash the app."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import measurement as m

GOOD = "test_id,reference_deg,ax_raw,ay_raw,az_raw,tilt_signed_deg\nT1,0,0,0,16384,0\nT2,10,2845,0,16135,10.0\n"


def w(tmp_path, content, name="f.csv", mode="w", **kw):
    p = tmp_path / name
    if mode == "wb":
        p.write_bytes(content)
    else:
        p.write_text(content, encoding=kw.get("encoding", "utf-8"))
    return str(p)


def test_good_file(tmp_path):
    r = m.load_static(w(tmp_path, GOOD))
    assert r["error"] is None and len(r["records"]) == 2 and r["skipped"] == 0
    assert r["formula"] == "atan2(ax, az)"


def test_empty_file(tmp_path):
    assert m.load_static(w(tmp_path, ""))["error"]


def test_only_header(tmp_path):
    r = m.load_static(w(tmp_path, GOOD.splitlines()[0] + "\n"))
    assert r["error"] is None and r["records"] == []


def test_missing_columns(tmp_path):
    assert "ax_raw" in m.load_static(w(tmp_path, "test_id,reference_deg\nT1,0\n"))["error"]


def test_bad_rows_are_skipped(tmp_path):
    txt = GOOD + "\nT3,5,abc,0,1\nT4,5,nan,0,1\n,,,,,\nT5,5,1\nT6,5,100,0,16000,5.0\n"
    r = m.load_static(w(tmp_path, txt))
    assert [x["test_id"] for x in r["records"]] == ["T1", "T2", "T6"]
    assert r["skipped"] == 3 and r["blank"] >= 1


def test_semicolon_and_decimal_comma(tmp_path):
    txt = "test_id;reference_deg;ax_raw;ay_raw;az_raw;tilt_signed_deg\nA1;10;2845;12;16135;10,02\n"
    r = m.load_static(w(tmp_path, txt))
    assert r["records"][0]["file_tilt"] == 10.02


def test_header_spaces_and_bom(tmp_path):
    txt = "\ufefftest_id , reference_deg ,ax_raw,ay_raw,az_raw,tilt_signed_deg   \nT1,0,0,0,16384,0\n"
    assert len(m.load_static(w(tmp_path, txt))["records"]) == 1


def test_missing_optional_columns(tmp_path):
    r = m.load_static(w(tmp_path, "test_id,ax_raw,ay_raw,az_raw\nT1,0,0,16384\n"))
    assert len(r["records"]) == 1 and r["formula"] is None


def test_turkish_encoding(tmp_path):
    txt = "test_id,reference_deg,ax_raw,ay_raw,az_raw,tilt_signed_deg\nÖlçüm-ş,0,0,0,16384,0\n"
    r = m.load_static(w(tmp_path, txt, encoding="cp1254"))
    assert len(r["records"]) == 1


def test_binary_garbage(tmp_path):
    r = m.load_static(w(tmp_path, bytes(range(256)) * 20, mode="wb"))
    assert r["error"] and r["records"] == []


def test_missing_file(tmp_path):
    assert m.load_static(str(tmp_path / "yok.csv"))["error"]
    assert m.load_series(str(tmp_path / "yok.csv"))["error"]


def test_series_bad_rows(tmp_path):
    r = m.load_series(w(tmp_path, "t,a,b\n0,1,2\nx,1,2\n1,,3\n2,nan\n"))
    assert r["error"] is None and len(r["x"]) == 3 and r["skipped"] == 1


def test_series_errors(tmp_path):
    assert m.load_series(w(tmp_path, ""))["error"]
    assert m.load_series(w(tmp_path, "t\n1\n"))["error"]


def test_views_never_crash(tmp_path):
    from PySide6 import QtWidgets
    from views import SimView, StaticView
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    files = [w(tmp_path, c, name=f"{i}.csv") for i, c in enumerate(
        ["", GOOD, "a,b\n", GOOD + "x,y,z\n\n;;;\n", "\x00\x01\x02", "test_id,ax_raw\n"])]
    files.append(str(tmp_path / "yok.csv"))
    for view in (StaticView(), SimView()):
        for p in files:
            view.load(p)
    del app
