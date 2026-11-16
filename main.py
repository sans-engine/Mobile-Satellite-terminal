"""SoTM telemetry screen (PySide6 + pyqtgraph).

Run:  python main.py
Needs: pip install PySide6 pyqtgraph numpy pyserial
Starts with the fake device. Pick a COM port and press "Bağlan" for the real board.
"""
import collections
import sys
import time

import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from protocol import parse_telemetry
from satellite import SATS, look_angles
from transport import FakeTransport, SerialTransport

TOL_DEG = 0.72        # half-angle of the 10 cm circle at 4 m
RELOCK_LIMIT_S = 8.0
FAKE = "Sahte cihaz"

STYLE = """
QWidget { background:#12161C; color:#E8ECF1; font-family:Inter,'Segoe UI',sans-serif; font-size:14px; }
QFrame#panel { background:#1A2028; border:1px solid #2A323D; border-radius:10px; }
QLabel { background:transparent; }
QLabel#h { color:#9AA6B5; font-size:12px; }
QLabel#m { color:#9AA6B5; }
QLabel#big { font-size:26px; font-weight:600; }
QLabel#title { font-size:20px; font-weight:700; }
QPushButton, QComboBox, QDoubleSpinBox { min-height:36px; background:#222B35; border:1px solid #3A4552;
    border-radius:8px; padding:0 12px; font-weight:600; }
QPushButton:checked { background:#4DA3FF; border-color:#4DA3FF; color:#0B1118; }
QPushButton#go { background:#4DA3FF; border-color:#4DA3FF; color:#0B1118; min-height:52px; font-size:18px; }
QPushButton#stop { min-height:52px; font-size:18px; }
QProgressBar { background:#2A323D; border:none; border-radius:5px; max-height:10px; }
QProgressBar::chunk { background:#4DA3FF; border-radius:5px; }
QProgressBar#warn::chunk { background:#FFB454; }
"""

STATES = {"IDLE": ("BEKLİYOR", "#9AA6B5"), "SLEW": ("KİLİTLENİYOR", "#FFB454"),
          "TRACK": ("TAKİP", "#4DA3FF"), "FAULT": ("HATA", "#FF6B6B")}


def f(x, n=1):
    return f"{x:.{n}f}".replace(".", ",")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SoTM Yer Terminali – Telemetri")
        self.resize(1280, 820)
        self.link = None
        self.source = FAKE
        self.last_rx = 0.0
        self.last_try = 0.0
        self.prev_state = ""
        self.slew_ms = None
        self.track_ms = None
        self.hx = collections.deque(maxlen=6000)   # 5 min at 20 Hz
        self.hy = collections.deque(maxlen=6000)
        self.v = {}
        self.build()
        self.open_link(FAKE)
        self.t1 = QtCore.QTimer(self, interval=50, timeout=self.tick)
        self.t2 = QtCore.QTimer(self, interval=200, timeout=self.redraw)
        self.t1.start()
        self.t2.start()

    # ---------- layout helpers ----------
    def panel(self, title):
        fr = QtWidgets.QFrame()
        fr.setObjectName("panel")
        lay = QtWidgets.QVBoxLayout(fr)
        lay.setSpacing(8)
        if title:
            h = QtWidgets.QLabel(title.upper())
            h.setObjectName("h")
            lay.addWidget(h)
        return fr, lay

    def row(self, lay, name, key, big=False):
        r = QtWidgets.QHBoxLayout()
        a = QtWidgets.QLabel(name)
        a.setObjectName("m")
        b = QtWidgets.QLabel("–")
        if big:
            b.setObjectName("big")
        r.addWidget(a)
        r.addStretch()
        r.addWidget(b)
        lay.addLayout(r)
        self.v[key] = b

    def spin(self, lo, hi, val, dec=2, suffix=""):
        s = QtWidgets.QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(dec)
        s.setValue(val)
        s.setSuffix(suffix)
        s.setMinimumWidth(130)
        return s

    def form_row(self, lay, name, widget):
        r = QtWidgets.QHBoxLayout()
        a = QtWidgets.QLabel(name)
        a.setObjectName("m")
        r.addWidget(a)
        r.addStretch()
        r.addWidget(widget)
        lay.addLayout(r)

    # ---------- build ----------
    def build(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        g = QtWidgets.QGridLayout(root)
        g.setContentsMargins(20, 20, 20, 20)
        g.setSpacing(16)

        # header
        h = QtWidgets.QHBoxLayout()
        t = QtWidgets.QLabel("SoTM Yer Terminali")
        t.setObjectName("title")
        h.addWidget(t)
        h.addStretch()
        self.modes = QtWidgets.QButtonGroup(self)
        for key, name in (("MAN", "Manuel"), ("TGT", "Hedef"), ("SAT", "Uydu")):
            b = QtWidgets.QPushButton(name)
            b.setCheckable(True)
            b.setProperty("mode", key)
            self.modes.addButton(b)
            h.addWidget(b)
        self.modes.buttonClicked.connect(lambda b: self.send("MODE," + b.property("mode")))
        h.addStretch()
        self.src = QtWidgets.QComboBox()
        self.refresh_ports()
        bc = QtWidgets.QPushButton("Bağlan")
        bc.clicked.connect(lambda: self.open_link(self.src.currentText()))
        br = QtWidgets.QPushButton("Yenile")
        br.clicked.connect(self.refresh_ports)
        self.conn = QtWidgets.QLabel("")
        for w in (self.src, bc, br, self.conn):
            h.addWidget(w)
        g.addLayout(h, 0, 0, 1, 3)

        # left: satellite + site + manual
        left, lv = self.panel("Uydu")
        self.sat = QtWidgets.QComboBox()
        self.sat.addItems(list(SATS))
        self.sat.currentTextChanged.connect(self.on_sat)
        lv.addWidget(self.sat)
        self.lat = self.spin(-90, 90, 36.90, 2, " °K")
        self.lon = self.spin(-180, 180, 30.70, 2, " °D")
        self.alt = self.spin(-100, 9000, 30, 0, " m")
        self.off = self.spin(-180, 180, 0.0, 1, " °")
        for name, w in (("Enlem", self.lat), ("Boylam", self.lon),
                        ("Yükseklik", self.alt), ("Yön ofseti", self.off)):
            self.form_row(lv, name, w)
            w.valueChanged.connect(self.refresh_calc)
        ba = QtWidgets.QPushButton("Konumu uygula")
        ba.clicked.connect(self.apply_site)
        lv.addWidget(ba)
        lh = QtWidgets.QLabel("HESAPLANAN")
        lh.setObjectName("h")
        lv.addWidget(lh)
        self.row(lv, "Azimut", "calc_az", True)
        self.row(lv, "Elevasyon", "calc_el", True)
        mh = QtWidgets.QLabel("MANUEL AÇI")
        mh.setObjectName("h")
        lv.addWidget(mh)
        self.maz = self.spin(0, 360, 0, 1, " °")
        self.mel = self.spin(0, 90, 30, 1, " °")
        self.form_row(lv, "Azimut", self.maz)
        self.form_row(lv, "Elevasyon", self.mel)
        bg = QtWidgets.QPushButton("Git")
        bg.clicked.connect(lambda: self.send(f"AZEL,{self.maz.value():.2f},{self.mel.value():.2f}"))
        lv.addWidget(bg)
        lv.addStretch()
        g.addWidget(left, 1, 0)

        # center: state
        mid, mv = self.panel("Durum")
        self.state = QtWidgets.QLabel("–")
        self.state.setStyleSheet("font-size:44px; font-weight:700;")
        mv.addWidget(self.state)
        self.sub = QtWidgets.QLabel("")
        self.sub.setObjectName("m")
        mv.addWidget(self.sub)
        self.row(mv, "Azimut komut / gerçek", "az")
        self.row(mv, "Elevasyon komut / gerçek", "el")
        self.row(mv, "Hata", "err", True)
        self.errbar = QtWidgets.QProgressBar()
        self.errbar.setTextVisible(False)
        mv.addWidget(self.errbar)
        n = QtWidgets.QLabel(f"Sınır ±{f(TOL_DEG, 2)}° (Ø10 cm çember, 4 m)")
        n.setObjectName("m")
        mv.addWidget(n)
        self.row(mv, "Son yeniden kilitlenme", "relock")
        self.relbar = QtWidgets.QProgressBar()
        self.relbar.setTextVisible(False)
        self.relbar.setObjectName("warn")
        mv.addWidget(self.relbar)
        mv.addStretch()
        g.addWidget(mid, 1, 1)

        # right: IMU + health
        right, rv = self.panel("Platform (IMU)")
        self.row(rv, "Roll", "roll")
        self.row(rv, "Pitch", "pitch")
        self.row(rv, "Yaw", "yaw")
        sh = QtWidgets.QLabel("SAĞLIK")
        sh.setObjectName("h")
        rv.addWidget(sh)
        self.row(rv, "Enkoder AZ", "h_az")
        self.row(rv, "Enkoder EL", "h_el")
        self.row(rv, "IMU", "h_imu")
        self.row(rv, "Sürücüler", "h_drv")
        rv.addStretch()
        g.addWidget(right, 1, 2)

        # bottom: plot + buttons
        pl, pv = self.panel("Takip hatası – son 5 dk")
        self.plot = pg.PlotWidget(background="#1A2028")
        self.plot.setYRange(0, 1.0)
        self.plot.setXRange(-300, 0)
        self.plot.setLabel("left", "Hata", units="°")
        self.plot.setLabel("bottom", "Süre", units="s")
        self.plot.addItem(pg.InfiniteLine(pos=TOL_DEG, angle=0,
                                          pen=pg.mkPen("#FFB454", style=QtCore.Qt.DashLine)))
        self.curve = self.plot.plot(pen=pg.mkPen("#4DA3FF", width=2))
        pv.addWidget(self.plot)
        pl.setMinimumHeight(220)
        g.addWidget(pl, 2, 0, 1, 2)

        bt, bv = self.panel("")
        go = QtWidgets.QPushButton("BAŞLAT")
        go.setObjectName("go")
        go.clicked.connect(lambda: self.send("START"))
        st = QtWidgets.QPushButton("DURDUR")
        st.setObjectName("stop")
        st.clicked.connect(lambda: self.send("STOP"))
        bv.addStretch()
        bv.addWidget(go)
        bv.addWidget(st)
        bv.addStretch()
        g.addWidget(bt, 2, 2)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(2, 1)
        self.refresh_calc()

    # ---------- connection ----------
    def refresh_ports(self):
        cur = self.src.currentText()
        self.src.clear()
        self.src.addItem(FAKE)
        try:
            from serial.tools import list_ports
            for p in list_ports.comports():
                self.src.addItem(p.device)
        except ImportError:
            pass
        i = self.src.findText(cur)
        self.src.setCurrentIndex(max(i, 0))

    def open_link(self, source):
        if self.link:
            self.link.close()
            self.link = None
        self.source = source
        self.last_try = time.time()
        try:
            self.link = FakeTransport() if source == FAKE else SerialTransport(source)
        except Exception:
            self.link = None
        self.prev_state = ""

    def send(self, line):
        if self.link:
            self.link.send(line)

    # ---------- satellite ----------
    def refresh_calc(self):
        az, el = look_angles(SATS[self.sat.currentText()], self.lat.value(),
                             self.lon.value(), self.off.value())
        self.v["calc_az"].setText(f(az) + "°")
        self.v["calc_el"].setText(f(el) + "°")

    def on_sat(self, name):
        self.refresh_calc()
        self.send("SAT," + name)

    def apply_site(self):
        self.send(f"SITE,{self.lat.value():.4f},{self.lon.value():.4f},"
                  f"{self.alt.value():.0f},{self.off.value():.1f}")

    # ---------- telemetry ----------
    def tick(self):
        lines = self.link.poll() if self.link else []
        for ln in lines:
            if ln == "#LOST":
                self.link.close()
                self.link = None
                break
            d = parse_telemetry(ln)
            if d:
                self.on_data(d)
        now = time.time()
        ok = self.link is not None and now - self.last_rx < 1.0
        if ok:
            self.conn.setText("● Bağlı")
            self.conn.setStyleSheet("color:#4DA3FF; font-weight:600;")
        else:
            self.conn.setText("● Bağlantı yok")
            self.conn.setStyleSheet("color:#FF6B6B; font-weight:600;")
            if self.source != FAKE and now - self.last_try > 1.5:   # auto-reconnect
                self.open_link(self.source)

    def on_data(self, d):
        self.last_rx = time.time()
        for b in self.modes.buttons():
            if b.property("mode") == d["mode"]:
                b.setChecked(True)
        st = d["state"]
        name, col = STATES.get(st, (st, "#E8ECF1"))
        self.state.setText(name)
        self.state.setStyleSheet(f"font-size:44px; font-weight:700; color:{col};")
        if st == "SLEW" and self.prev_state != "SLEW":
            self.slew_ms = d["ms"]
        if st == "TRACK" and self.prev_state == "SLEW" and self.slew_ms is not None:
            s = (d["ms"] - self.slew_ms) / 1000
            self.v["relock"].setText(f"{f(s)} s / {RELOCK_LIMIT_S:.0f} s")
            self.relbar.setValue(int(min(100, s / RELOCK_LIMIT_S * 100)))
            self.track_ms = d["ms"]
        if st != "TRACK":
            self.track_ms = None
        if self.track_ms is not None:
            s = int((d["ms"] - self.track_ms) / 1000)
            self.sub.setText(f"Kilitte · {s // 60:02d}:{s % 60:02d}")
        else:
            self.sub.setText("Kilitte değil")
        self.prev_state = st
        self.v["az"].setText(f"{f(d['cmd_az'])}° / {f(d['act_az'])}°")
        self.v["el"].setText(f"{f(d['cmd_el'])}° / {f(d['act_el'])}°")
        self.v["err"].setText(f(d["err"], 2) + "°")
        self.errbar.setValue(int(min(100, d["err"] / TOL_DEG * 100)))
        self.v["roll"].setText(f"{d['roll']:+.1f}°".replace(".", ","))
        self.v["pitch"].setText(f"{d['pitch']:+.1f}°".replace(".", ","))
        self.v["yaw"].setText(f"{d['yaw']:+.1f}°".replace(".", ","))
        for bit, key in enumerate(("h_az", "h_el", "h_imu", "h_drv")):
            bad = bool(d["flags"] >> bit & 1)
            self.v[key].setText("HATA" if bad else "Tamam")
            self.v[key].setStyleSheet("color:#FF6B6B;" if bad else "")
        self.hx.append(d["ms"] / 1000)
        self.hy.append(d["err"])

    def redraw(self):
        if self.hx:
            last = self.hx[-1]
            self.curve.setData([x - last for x in self.hx], list(self.hy))

    def closeEvent(self, e):
        if self.link:
            self.link.close()
        super().closeEvent(e)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
