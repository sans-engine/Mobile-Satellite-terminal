"""Transports. The UI only uses send(line), poll() and close().

FakeTransport imitates the board. SerialTransport talks to the real STM32.
"""
import math
import queue
import threading
import time

from satellite import SATS, look_angles

SLEW_SPEED = 40.0   # deg/s, fake axes


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


class FakeTransport:
    def __init__(self, rate_hz=20):
        self.dt = 1.0 / rate_hz
        self.t0 = time.perf_counter()
        self.next = self.t0
        self.mode, self.state, self.sat = "SAT", "IDLE", "4B"
        self.site = [36.90, 30.70, 30.0, 0.0]
        self.man = [0.0, 30.0]
        self.act = [0.0, 0.0]
        self.out = queue.Queue()

    def cmd(self):
        if self.mode == "SAT":
            return look_angles(SATS[self.sat], self.site[0], self.site[1], self.site[3])
        if self.mode == "TGT":
            return 0.0, 30.0          # placeholder target direction
        return self.man[0], self.man[1]

    def send(self, line):
        p = line.strip().split(",")
        try:
            if p[0] == "PING":
                self.out.put("PONG")
            elif p[0] == "MODE":
                self.mode = p[1]
                if self.state != "IDLE":
                    self.state = "SLEW"
            elif p[0] == "AZEL":
                self.man = [float(p[1]), float(p[2])]
                if self.mode == "MAN" and self.state != "IDLE":
                    self.state = "SLEW"
            elif p[0] == "SAT":
                self.sat = p[1]
            elif p[0] == "SITE":
                self.site = [float(x) for x in p[1:5]]
            elif p[0] == "START":
                self.state = "SLEW"
            elif p[0] == "STOP":
                self.state = "IDLE"
            else:
                self.out.put("ERR")
                return
            self.out.put("OK")
        except (IndexError, ValueError, KeyError):
            self.out.put("ERR")

    def step(self, t):
        ca, ce = self.cmd()
        w = 2 * math.pi / 10                        # 10 s platform period
        roll = 8 * math.sin(w * t)
        pitch = 8 * math.sin(w * t + 1.0)
        yaw = 2 * math.sin(w * t + 2.0)
        if self.state == "SLEW":
            da, de = wrap(ca - self.act[0]), ce - self.act[1]
            n = max(abs(da), abs(de), 1e-9)
            k = min(1.0, SLEW_SPEED * self.dt / n)
            self.act[0] = (self.act[0] + da * k) % 360.0
            self.act[1] += de * k
            if n < 0.3:
                self.state = "TRACK"
        if self.state == "TRACK":
            e = 0.15 * math.sin(2 * math.pi * t / 3)
            self.act = [(ca + e) % 360.0, ce - e]
        err = math.hypot(wrap(ca - self.act[0]), ce - self.act[1])
        self.out.put(
            f"T,{int(t * 1000)},{self.mode},{self.state},{ca:.2f},{ce:.2f},"
            f"{self.act[0]:.2f},{self.act[1]:.2f},{roll:.2f},{pitch:.2f},{yaw:.2f},{err:.2f},0")

    def poll(self):
        now = time.perf_counter()
        while self.next <= now:
            self.step(self.next - self.t0)
            self.next += self.dt
        lines = []
        while not self.out.empty():
            lines.append(self.out.get())
        return lines

    def close(self):
        pass


class SerialTransport:
    def __init__(self, port, baud=115200):
        import serial
        self.s = serial.Serial(port, baud, timeout=0.2)
        self.q = queue.Queue()
        self.run = True
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while self.run:
            try:
                ln = self.s.readline().decode(errors="ignore").strip()
            except Exception:
                self.q.put("#LOST")
                return
            if ln:
                self.q.put(ln)

    def send(self, line):
        try:
            self.s.write((line + "\n").encode())
        except Exception:
            self.q.put("#LOST")

    def poll(self):
        lines = []
        while not self.q.empty():
            lines.append(self.q.get())
        return lines

    def close(self):
        self.run = False
        try:
            self.s.close()
        except Exception:
            pass
