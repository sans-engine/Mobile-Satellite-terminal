# SoTM (Moving Satellite Terminal) – Software Outline, Draft v0.1

Scope of this document: the **UI**, the **laser/target locking logic** and the **satellite pointing logic**.
Motors, drivers, encoders, power and the pulley measurement setup belong to the electricians.

---

## 1. Requirements from the spec that touch software

| # | Requirement (spec page) | Software meaning |
|---|---|---|
| 1 | Azimuth 0–360° continuous, elevation 0–90° (p.8) | Az unwrapping / shortest-path logic, elevation clamp |
| 2 | Platform roll ±8°, pitch ±8°, yaw, period 10 s (p.8) | Stabilization must hold a world-fixed line of sight |
| 3 | Target: 4 m range, 30° elevation, 2 m high; circles Ø10–100 cm (p.7) | Target geometry + accuracy goal (see §8) |
| 4 | Laser replaces the feed, fixed on the boresight (p.8) | Laser always points along antenna boresight; we point the boresight |
| 5 | Re-acquire target within **8 s** after manual re-pointing / tracking stopped, no fault (p.8) | Fast boot + fast slew + autonomous resume |
| 6 | 5 min continuous stable tracking on the Stewart platform (p.8) | Long-run stability, no drift, no crash |
| 7 | Software pointing at the target during assembly (p.8) | "Calibrate/Set target" function |
| 8 | Two modes: Manual (type angles) and Automatic (sensor-based) (p.9) | Mode state machine + UI |
| 9 | Satellite pointing from computed az/el, results shown in UI (p.9) | Look-angle calculation + display |
| 10 | GPS entered manually in UI / microcontroller (p.9) | Site settings panel |
| 11 | Wired **or wireless** access to the MCU while moving (p.9) | Transport-agnostic protocol |
| 12 | All parameters persist across power off/on (p.9) | Non-volatile storage in firmware (not only in the UI) |
| 13 | UI on computer/tablet; can drop tracking, set limits manually (p.9) | UI features |
| 14 | Stewart interface details come at the critical design stage (p.9) | Leave a hook for platform data |

## 2. Things to verify before building (spec vs. what we said)

1. **Satellite:** the spec lists **Türksat 4B and 5A**, not 4A. We said 4A. Confirm with the team or the committee. Keep the satellite selectable in the UI (4A ≈ 42°E, 4B ≈ 50°E, 5A ≈ 31°E – double-check longitudes).
2. **Target geometry:** the spec says range 4 m at 30° elevation, which gives **2.0 m height and about 3.46 m horizontal** (Fig. 2 matches this). Saying "2 m up, 4 m horizontal" would be elevation ≈ 26.6° and range ≈ 4.47 m. Agree on one version. Source: spec p.7 text plus Figure 2 (title "4 m Mesafe, 30° Elevasyon ile 2 m Yükseklikte Hedef"; the dashed line labeled "Mesafe = 4 m" is the line of sight, target centre at about x = 3.5 m, y = 2 m). If the committee says otherwise verbally, get it in writing via the competition group or iletisim@teknofest.org. Keep range, elevation and height as UI/config parameters so either version works.
3. **Dates:** the PDF calendar ends with the festival on 30 Sep – 4 Oct 2026. Confirm which edition/dates we are actually working toward.
4. **Yaw reference after a power cycle:** if power is lost, the integrated gyro yaw reference is lost. Ask the committee whether the platform is stationary or moving during the re-lock, and whether the Stewart interface (given at the critical design stage) provides pose data.
5. **Absolute position at boot:** if the jury turns the head by hand while unplugged, stored angles are stale. We need **absolute encoders** (or homing, which eats the 8 s budget). Electricians to confirm.
6. **Pulley (clarified):** it is the belt/pulley drive that connects the head to the body and moves the axes, not a measurement device. Software implications:
   - Keep the gear/belt ratio as a config parameter (motor angle ≠ head angle).
   - Put the **absolute encoder on the head (output) axis**, not on the motor. Belt slip or a hand-turned head while unplugged would otherwise make the stored position wrong, and a motor-side encoder with a ratio above 1 is ambiguous after power-off.
   - Expect backlash and belt elasticity: tune the loops on the output-axis encoder, keep belt tension consistent.
   - **Status:** the electricians currently plan the encoder on the motor. Recommendation: keep it for the control loops, and add one small absolute encoder (e.g. magnetic, single-turn) on each head axis for power-up position. Without it, every boot needs a homing sweep, which can use most of the 8 s budget (a 360° azimuth search at 60°/s alone is up to 6 s) and breaks if the belt slips.
   - Slew speed: motor speed = head speed × ratio (e.g. 90°/s at head with 3:1 is only 45 rpm at the motor).

## 3. Architecture

```
 [ UI (PC/tablet) ] <--- link (USB / Bluetooth / Wi-Fi bridge) ---> [ STM32 firmware ]
        |                                                              |
   settings, commands,                              absolute encoders, IMU(s), motor drivers,
   telemetry plots                                  control loops, NVM (flash/FRAM)
        |                                                              |
   Python simulator (digital twin) <---- shared portable C "core" ----+
```

Principle: the firmware must work **without the UI**. After power-up it restores the last mode and target from NVM and locks by itself. The UI only commands and observes.

## 4. Languages and tools (proposal)

| Area | Choice | Why / alternatives |
|---|---|---|
| Firmware | **C** on STM32 (STM32CubeIDE + CubeMX, HAL/LL; FreeRTOS optional) | Electricians already use it. C++ only if SimpleFOC is chosen |
| Portable core | **C** (no hardware calls): attitude estimator, LOS to az/el, satellite look angles, trajectory generator | Same code runs on PC (tests, sim) and on STM32 |
| Math prototype + simulator | **Python** (NumPy, SciPy, matplotlib) | Tune the algorithm before hardware exists |
| UI | **Python + PySide6 (Qt) + pyserial + pyqtgraph** | Fast to build, good live plots. Alt: web UI (TypeScript/React + WebSocket) if a tablet is mandatory |
| Link | **USB-CDC (decided)**: UART-style protocol over a USB cable routed together with the axis cables | Protocol stays transport-agnostic, so Bluetooth/Wi-Fi remains a cheap fallback. Notes: keep the cable away from the motor wires, use a shielded cable with strain relief and slack, and power the STM32 from the terminal supply (not only from USB) so a real power cut really reboots it. Optional USB isolator. Ask the electricians where the STM32 sits relative to the azimuth slip ring |
| Tests | pytest (Python), Unity/Ceedling (C), recorded-IMU replay | Catch bugs without the Stewart platform |
| Simulation of MCU logic | Wokwi (assumed this is what "wokewei" meant; check that our exact STM32 part is supported) | Optional |
| Version control | Git (GitHub/GitLab), one repo | Layout in §9 |

### 4.1 Hardware assumptions (to be confirmed by the electricians)

- **Motors:** NEMA 17 / NEMA 23 steppers, so there is no FOC. Step/dir drivers (e.g. TMC2209 for NEMA 17, DM556/TMC5160-class for NEMA 23), microstepping 8–16.
- **MCU board:** STM32F407G-DISC1, MCU **STM32F407VGTx** (168 MHz Cortex-M4F with FPU), the board the team already has. Not connected while we build the telemetry screen (fake device first). A Nucleo-F446RE would also work.
- **Step generation:** hardware timers (PWM/DMA), with acceleration ramps in firmware; never bit-banged in the main loop.
- **Resolution check:** 1.8° / 16 microsteps / 3:1 belt = 0.0375° of head angle per microstep, far finer than the ±0.7° needed for the Ø10 cm circle.
- **Lost steps:** steppers can skip steps if overloaded or forced by hand. The head-axis absolute encoder detects this and lets the firmware re-sync.
- **Driver enable pin:** firmware must be able to release the motors (Stop) so the head can be turned by hand without fighting the holding torque.
- **Vibration:** use microstepping/silent mode and check laser jitter at 4 m (0.1° is about 7 mm at the target).

## 5. UI outline

1. **Connection:** port/IP, connect/disconnect, link status, last-packet age.
2. **Mode selector:** Manual / Auto-Target (laser lock) / Satellite.
3. **Manual panel:** az and el input, Go, limit settings (min/max), jog buttons.
4. **Target panel:** "Set target here" (assembly calibration, saves az/el in base frame), target geometry parameters (range, elevation, height), Lock / Release.
5. **Satellite panel:** satellite dropdown, site lat/lon/alt (manual GPS), heading offset, computed az/el shown, Lock / Release.
6. **Start / Stop:** Start = resume the selected mode. Stop = drop tracking and hold. This is a software stop only; the jury's power cut is the real safety stop.
7. **Status:** state (BOOT, SLEW, TRACK, HOLD, FAULT), commanded vs actual az/el, IMU roll/pitch/yaw, pointing error, **re-lock stopwatch** (time from start of slew to "in tolerance").
8. **Plots:** live error and attitude, 5-minute rolling window.
9. **Settings and logs:** save/load config, gains, offsets, CSV logging, event log.

## 6. Firmware behavior (state machine)

```
BOOT -> LOAD_CONFIG (CRC check, backup copy) -> READ_ENCODERS -> INIT_IMU
     -> RESTORE_LAST_MODE -> SLEW (trapezoidal profile) -> TRACK <-> HOLD
                                         any state -> FAULT (safe stop, report)
```

Proposed 8 s budget (to be confirmed with the electricians):

| Step | Budget |
|---|---|
| Boot + config + sensor init | ≤ 1.0 s |
| Slew (worst case 180° in azimuth) | ≤ 4.5 s, so peak speed of roughly 60–90°/s is needed |
| Settle inside the tolerance circle | ≤ 1.0 s |
| Margin | ≥ 1.5 s |

NVM: write only on change, CRC plus double buffer, external FRAM/EEPROM preferred over flash wear.

### 6.1 Jury scenarios (design for the worst, the rest come for free)

Design rule: **store the target, never trust a stored position.** NVM keeps mode, target (az/el in the base frame), site, satellite and offsets. The current head angle is always read from the sensors at boot. Every scenario then follows the same path: read position, slew, track.

| # | Scenario | Needs |
|---|---|---|
| A | Power on, nothing touched | Normal start |
| B | Head turned by hand while powered, or tracking stopped and re-pointed (the case the spec's 8 s describes) | Torque release / Stop, then re-slew |
| C | Power off, head turned by hand, power on (worst case, what the jury may do) | Head-axis absolute encoders, auto-resume at boot, NVM target |
| D | Any of the above while the Stewart platform is moving | IMU attitude at boot; yaw reference open question (§2.4) |
| E | Power off/on repeatedly in a row | Safe NVM writes (CRC, double buffer), boot must be repeatable |

Extra points: auto-resume on boot should be a config flag (on for the competition); the head must be safe to turn by hand when unpowered (check the drive, hard stops, azimuth slip ring); no fault latch after a forced move.

## 7. Command protocol (draft)

Line-based ASCII with checksum first (easy to debug), binary frames later if needed.

- Commands: `PING`, `GET_STATUS`, `SET_MODE`, `SET_ANGLES`, `SET_LIMITS`, `SET_SITE`, `SET_SAT`, `SET_TARGET`, `START`, `STOP`, `SAVE`, `RELOAD`
- Telemetry stream: 20–50 Hz (time, mode, state, cmd az/el, actual az/el, roll/pitch/yaw, error, flags)
- A **fake device** in Python implements the same protocol, so the UI can be built and tested before any hardware exists.

## 8. Math notes

- **Accuracy goal:** half-angle of the circle at 4 m: Ø10 cm gives ±0.72°, Ø100 cm gives ±7.1°. Aim for under ±0.5° if we want the smallest circle.
- **Platform dynamics:** peak rate ≈ 8°·2π/10 ≈ 5°/s, peak acceleration ≈ 3.2°/s². Modest, so gyro feedforward plus PI/PID is likely enough.
- **Stabilization:** fixed world line of sight → rotate into the base frame with the IMU attitude (quaternion; Madgwick/Mahony or EKF) → az = atan2, el = asin → unwrap az → send to axis loops.
- **Lever arm:** if the laser sits d above the platform's rotation center, roll of 8° shifts it laterally by about 0.14·d (30 cm gives about 4 cm, close to the Ø10 cm circle radius). Measure the laser offset and compensate.
- **Satellite look angles (geostationary, northern hemisphere):**
  Δ = sat_lon − site_lon (east positive), φ = site latitude, Re/r ≈ 6378/42164.
  cosγ = cosφ·cosΔ, El = atan((cosγ − Re/r) / sinγ), Az = 180° − atan(tanΔ / sinφ).
  Add the heading offset of the terminal base. Unit-test against a reference calculator.

## 9. Repo layout (proposal)

```
sotm/
  core/       portable C (estimator, geometry, look angles, trajectory) + unit tests
  firmware/   STM32 project (electricians) that includes core/
  ui/         PySide6 app + fake device
  sim/        Python digital twin (Stewart motion, error vs circles)
  docs/       this outline, protocol spec, test logs
```

## 10. Plan

1. Settle the open items in §2.
2. Python math + simulation: look angles, LOS geometry, attitude compensation, error vs circles.
3. Protocol spec + UI skeleton running against the fake device.
4. Port `core/` to C, integrate with the electricians' firmware, replay recorded IMU data.
5. Bench test, then Stewart platform tests (interface arrives at the critical design stage).
6. Rehearsals of the jury scenarios: 5 min tracking, manual deflection then 8 s re-lock, unplug/replug, power-cycle persistence.
