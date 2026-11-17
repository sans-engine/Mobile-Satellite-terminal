"""File based views. They are clearly marked as NOT live data."""
import math
import os

import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

import measurement as m


def f(x, n=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x:.{n}f}".replace(".", ",")


class FileBase(QtWidgets.QWidget):
    TITLE = ""
    BADGE = ("", "#9AA6B5")

    def __init__(self):
        super().__init__()
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)
        top = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(self.TITLE)
        title.setObjectName("title")
        badge = QtWidgets.QLabel(self.BADGE[0])
        badge.setStyleSheet(f"background:{self.BADGE[1]}; color:#0B1118; font-weight:700;"
                            "padding:4px 10px; border-radius:6px;")
        self.fname = QtWidgets.QLabel("Henüz dosya seçilmedi")
        self.fname.setObjectName("m")
        btn = QtWidgets.QPushButton("Dosya aç…")
        btn.clicked.connect(self.pick)
        top.addWidget(title)
        top.addWidget(badge)
        top.addStretch()
        top.addWidget(self.fname)
        top.addWidget(btn)
        lay.addLayout(top)
        self.status = QtWidgets.QLabel("")
        self.status.setObjectName("m")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.body = QtWidgets.QVBoxLayout()
        lay.addLayout(self.body, 1)

    def set_status(self, text, error=False):
        self.status.setText(text)
        self.status.setStyleSheet("color:#FF6B6B;" if error else "color:#9AA6B5;")

    def pick(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Dosya seç", "", "CSV (*.csv *.txt);;Tüm dosyalar (*)")
        if path:
            self.load(path)

    def load(self, path):
        self.fname.setText(os.path.basename(path))
        try:
            self._load(path)
        except Exception as e:            # a bad file must never crash the app
            self.set_status(f"Dosya işlenemedi: {e}", error=True)
            self.clear()

    def counts(self, res):
        return f"{res['skipped']} bozuk satır atlandı · {res['blank']} boş satır"


class StaticView(FileBase):
    TITLE = "F407 statik ölçüm kaydı"
    BADGE = ("DOSYA · canlı bağlantı değil", "#9AA6B5")

    def __init__(self):
        super().__init__()
        self.recs = []
        self.res = None
        row = QtWidgets.QHBoxLayout()
        self.list = QtWidgets.QListWidget()
        self.list.setMaximumWidth(220)
        self.list.currentRowChanged.connect(self.select)
        row.addWidget(self.list)

        right = QtWidgets.QVBoxLayout()
        panel = QtWidgets.QFrame()
        panel.setObjectName("panel")
        pv = QtWidgets.QVBoxLayout(panel)
        self.v = {}
        for key, name in (("ax", "Ham ax"), ("ay", "Ham ay"), ("az", "Ham az"),
                          ("ref", "Yaklaşık referans eğim"),
                          ("file", "Kart eğimi (dosyadaki tilt_signed_deg)"),
                          ("calc", "Hesaplanan eğim (uygulama)"),
                          ("d_ref", "Hesaplanan − referans"),
                          ("d_file", "Hesaplanan − dosyadaki")):
            r = QtWidgets.QHBoxLayout()
            a = QtWidgets.QLabel(name)
            a.setObjectName("m")
            b = QtWidgets.QLabel("–")
            r.addWidget(a)
            r.addStretch()
            r.addWidget(b)
            pv.addLayout(r)
            self.v[key] = b
        fr = QtWidgets.QHBoxLayout()
        a = QtWidgets.QLabel("Formül")
        a.setObjectName("m")
        self.formula = QtWidgets.QComboBox()
        self.formula.addItems(list(m.FORMULAS))
        self.formula.currentIndexChanged.connect(self.formula_changed)
        fr.addWidget(a)
        fr.addStretch()
        fr.addWidget(self.formula)
        pv.addLayout(fr)
        right.addWidget(panel)

        self.plot = pg.PlotWidget(background="#1A2028")
        self.plot.addLegend()
        self.plot.setLabel("left", "Eğim", units="°")
        self.plot.setLabel("bottom", "Ölçüm numarası")
        self.marker = pg.InfiniteLine(angle=90, pen=pg.mkPen("#E8ECF1", style=QtCore.Qt.DashLine))
        self.plot.addItem(self.marker)
        self.marker.hide()
        self.c_ref = self.plot.plot(pen=pg.mkPen("#9AA6B5", width=2), symbol="o",
                                    symbolSize=6, name="Referans")
        self.c_file = self.plot.plot(pen=pg.mkPen("#4DA3FF", width=2), symbol="o",
                                     symbolSize=6, name="Dosyadaki eğim")
        self.c_calc = self.plot.plot(pen=pg.mkPen("#FFB454", width=2, style=QtCore.Qt.DashLine),
                                     symbol="t", symbolSize=7, name="Hesaplanan eğim")
        right.addWidget(self.plot, 1)
        row.addLayout(right, 1)
        self.body.addLayout(row)

    def clear(self):
        self.recs = []
        self.list.clear()
        for k in self.v:
            self.v[k].setText("–")
        for c in (self.c_ref, self.c_file, self.c_calc):
            c.setData([], [])
        self.marker.hide()

    def _load(self, path):
        res = self.res = m.load_static(path)
        self.clear()
        if res["error"]:
            self.set_status(res["error"], error=True)
            return
        self.recs = res["records"]
        if not self.recs:
            self.set_status("Dosyada geçerli ölçüm satırı yok · " + self.counts(res), error=True)
            return
        for r in self.recs:
            self.list.addItem(f"{r['test_id']}  (no {r['no']})")
        msg = f"{len(self.recs)} ölçüm yüklendi · " + self.counts(res)
        self.formula.blockSignals(True)
        if res["formula"]:
            self.formula.setCurrentText(res["formula"])
            msg += f" · dosyaya en yakın formül: {res['formula']} (RMS {f(res['rms'], 3)}°)"
        else:
            self.formula.setCurrentText(m.DEFAULT_FORMULA)
            msg += " · dosyada karşılaştırılacak eğim sütunu yok, varsayılan formül kullanıldı"
        self.formula.blockSignals(False)
        self.set_status(msg)
        self.draw()
        self.list.setCurrentRow(0)

    def calc(self, r):
        return m.tilt(self.formula.currentText(), r["ax"], r["ay"], r["az"])

    def draw(self):
        x = [r["no"] for r in self.recs]
        self.c_ref.setData(x, [r["ref"] for r in self.recs], connect="finite")
        self.c_file.setData(x, [r["file_tilt"] for r in self.recs], connect="finite")
        self.c_calc.setData(x, [self.calc(r) for r in self.recs], connect="finite")

    def formula_changed(self):
        if self.recs:
            self.draw()
            self.select(self.list.currentRow())

    def select(self, i):
        if i < 0 or i >= len(self.recs):
            return
        r = self.recs[i]
        c = self.calc(r)
        self.v["ax"].setText(f(r["ax"], 0))
        self.v["ay"].setText(f(r["ay"], 0))
        self.v["az"].setText(f(r["az"], 0))
        self.v["ref"].setText(f(r["ref"]) + "°" if not math.isnan(r["ref"]) else "–")
        self.v["file"].setText(f(r["file_tilt"]) + "°" if not math.isnan(r["file_tilt"]) else "–")
        self.v["calc"].setText(f(c) + "°")
        self.v["d_ref"].setText(f(c - r["ref"]) + "°" if not math.isnan(r["ref"]) else "–")
        self.v["d_file"].setText(f(c - r["file_tilt"]) + "°" if not math.isnan(r["file_tilt"]) else "–")
        self.marker.setValue(r["no"])
        self.marker.show()


class SimView(FileBase):
    TITLE = "Simülasyon sonuçları"
    BADGE = ("SİMÜLASYON · gerçek ölçüm değil", "#FFB454")

    def __init__(self):
        super().__init__()
        self.plot = pg.PlotWidget(background="#1A2028")
        self.plot.addLegend()
        self.body.addWidget(self.plot, 1)
        self.set_status("MATLAB/Simulink sonuçlarını CSV olarak dışa aktarıp buradan açın "
                        "(ilk sütun x ekseni, diğerleri çizilir).")

    def clear(self):
        self.plot.clear()

    def _load(self, path):
        res = m.load_series(path)
        self.plot.clear()
        if res["error"]:
            self.set_status(res["error"], error=True)
            return
        colors = ["#FFB454", "#4DA3FF", "#E8ECF1", "#9AA6B5", "#FF6B6B"]
        for k, (name, vals) in enumerate(res["series"]):
            self.plot.plot(res["x"], vals, connect="finite", name=name,
                           pen=pg.mkPen(colors[k % len(colors)], width=2))
        self.plot.setLabel("bottom", res["xname"])
        names = ", ".join(n for n, _ in res["series"])
        self.set_status(f"{len(res['x'])} nokta · sütunlar: {names} · " + self.counts(res))
