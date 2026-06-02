"""
EEG Alpha-wave Robot Controller

Usage:
    python serial-read-alpha.py              # normal mode, COM5
    python serial-read-alpha.py COM5         # normal mode, explicit port
    python serial-read-alpha.py COM5 --calibrate   # calibration mode

Detection method: FFT band-power ratio.
  Instead of comparing absolute alpha amplitude to a fixed threshold (fragile,
  varies with electrode contact quality), we compute what fraction of total EEG
  power (0.5-30 Hz) falls in the alpha band (8-12 Hz).  This ratio is
  self-normalizing — a loose electrode gives a weaker signal overall, but the
  *ratio* between alpha and the other bands stays meaningful.
"""
import sys
import os
import re
import time
import subprocess
import numpy as np
import matplotlib.pyplot as plt
from collections import deque

# ── Configuration ─────────────────────────────────────────────────────────────
sampling_rate = 169    # measured from Arduino Uno on COM5
window_size   = 512    # ~3 s buffer — enough FFT resolution, lower latency

UPDATE_EVERY  = sampling_rate  # evaluate once per second
CONFIRM_COUNT = 2              # consecutive same-zone readings before acting

# Alpha ratio thresholds (alpha power / total EEG power, range 0-1)
#
# GO   when alpha_ratio >  ALPHA_GO_RATIO    (eyes closed = high alpha fraction)
# STOP when alpha_ratio <  ALPHA_STOP_RATIO  (eyes open   = low alpha fraction)
# HOLD when ratio is in the dead band between the two lines
#
# Run --calibrate to set these automatically for each user.
ALPHA_GO_RATIO   = 0.30   # go when alpha > 30% of total EEG power
ALPHA_STOP_RATIO = 0.18   # stop when alpha < 18% of total EEG power

# ── Parse CLI args ─────────────────────────────────────────────────────────────
args           = sys.argv[1:]
calibrate_mode = "--calibrate" in args
port_args      = [a for a in args if not a.startswith("--")]
serial_port    = port_args[0] if port_args else "COM5"
baudrate       = 115200

# ── Signal processing — FFT band-power ────────────────────────────────────────
def compute_band_powers(data):
    """
    Return (delta, theta, alpha, beta, total) absolute band powers via FFT.
    Call with a list/deque of raw ADC samples.
    """
    arr  = np.array(data, dtype=float)
    arr -= np.mean(arr)                          # remove DC offset
    win  = np.hanning(len(arr))
    spec = np.abs(np.fft.rfft(arr * win))
    freqs = np.fft.rfftfreq(len(arr), d=1.0 / sampling_rate)
    power = spec ** 2

    def bp(lo, hi):
        return float(np.sum(power[(freqs >= lo) & (freqs <= hi)]))

    delta = bp(0.5,  4.0)
    theta = bp(4.0,  8.0)
    alpha = bp(8.0, 12.0)
    beta  = bp(12.0, 30.0)
    total = delta + theta + alpha + beta
    return delta, theta, alpha, beta, total

# ── Connect ────────────────────────────────────────────────────────────────────
import serial
try:
    ser = serial.Serial(serial_port, baudrate, timeout=1)
    print(f"Connected to {serial_port} at {baudrate} baud")
except Exception as e:
    print(f"Could not open {serial_port}: {e}")
    print("Run 'python test_sensor.py' to see available ports.")
    sys.exit(1)

# ── Collect helper ─────────────────────────────────────────────────────────────
def collect_ratios(duration_s, label):
    """Read EEG for duration_s seconds; return list of alpha_ratio values."""
    buf = deque(maxlen=window_size)
    ratios = []
    end_time      = time.time() + duration_s
    last_progress = time.time()

    while time.time() < end_time:
        raw = ser.readline().decode("utf-8", errors="replace").strip()
        if not raw:
            continue
        try:
            val = float(raw.split(",")[0])
        except (ValueError, IndexError):
            continue

        buf.append(val)

        if time.time() - last_progress >= 3:
            remaining = end_time - time.time()
            print(f"  [{label}] {remaining:.0f}s left  (buffer {len(buf)}/{window_size})")
            last_progress = time.time()

        if len(buf) < window_size:
            continue

        _, _, alpha, _, total = compute_band_powers(buf)
        if total > 0:
            ratio = alpha / total
            ratios.append(ratio)
            print(f"    alpha_ratio={ratio:.3f}", end="\r", flush=True)

    print()
    return ratios

# ── Calibration mode ───────────────────────────────────────────────────────────
if calibrate_mode:
    print("\n=== CALIBRATION — two phases, 20 seconds each ===\n")

    input("Phase 1 — Close your eyes and RELAX. Press Enter when ready...")
    print("  Recording eyes-CLOSED for 20 seconds...")
    closed_ratios = collect_ratios(20, "EYES CLOSED")

    print()
    input("Phase 2 — Open your eyes and FOCUS on something. Press Enter when ready...")
    print("  Recording eyes-OPEN for 20 seconds...")
    open_ratios = collect_ratios(20, "EYES OPEN")

    ser.close()

    if len(closed_ratios) < 3 or len(open_ratios) < 3:
        print("\nNot enough data — check sensor connection and try again.")
        sys.exit(1)

    mean_closed = np.mean(closed_ratios)
    mean_open   = np.mean(open_ratios)
    diff        = abs(mean_closed - mean_open)
    midpoint    = (mean_closed + mean_open) / 2
    margin      = max(diff / 4, 0.03)
    go_ratio    = round(midpoint + margin, 3)
    stop_ratio  = round(midpoint - margin, 3)
    confirm_count = 1 if diff < 0.05 else 2

    print(f"\n--- Calibration Results ---")
    print(f"  Eyes CLOSED alpha ratio : {mean_closed:.3f}  ({mean_closed*100:.1f}%)")
    print(f"  Eyes OPEN   alpha ratio : {mean_open:.3f}  ({mean_open*100:.1f}%)")
    print(f"  Difference              : {diff:.3f}  ({diff*100:.1f}%)")

    if diff < 0.05:
        print("\n  WARNING: very small difference between states (<5%).")
        print("  Try firmer electrode contact or adjust placement.")

    print(f"\n  Applied settings:")
    print(f"    ALPHA_GO_RATIO   = {go_ratio}  (GO when alpha > {go_ratio*100:.1f}%)")
    print(f"    ALPHA_STOP_RATIO = {stop_ratio}  (STOP when alpha < {stop_ratio*100:.1f}%)")
    print(f"    CONFIRM_COUNT    = {confirm_count}")

    # Self-update: write new values back into this file
    this_file = os.path.abspath(__file__)
    with open(this_file, "r", encoding="utf-8") as f:
        code = f.read()
    code = re.sub(r"ALPHA_GO_RATIO\s*=\s*[\d.]+",   f"ALPHA_GO_RATIO   = {go_ratio}",   code)
    code = re.sub(r"ALPHA_STOP_RATIO\s*=\s*[\d.]+", f"ALPHA_STOP_RATIO = {stop_ratio}", code)
    code = re.sub(r"CONFIRM_COUNT\s*=\s*\d+",        f"CONFIRM_COUNT = {confirm_count}", code)
    with open(this_file, "w", encoding="utf-8") as f:
        f.write(code)
    print("\n  serial-read-alpha.py updated.")

    # Write helper runner bats (handles the space in 'Brain Controled')
    here = os.path.dirname(this_file)
    eeg_runner   = os.path.join(here, "_run_eeg_reader.bat")
    motor_runner = os.path.join(here, "_run_robot_ctrl.bat")
    with open(eeg_runner, "w") as f:
        f.write(f'@echo off\ncd /d "{here}"\npython serial-read-alpha.py COM5\npause\n')
    with open(motor_runner, "w") as f:
        f.write(f'@echo off\ncd /d "{here}"\npython mbot-motor-control.py\npause\n')

    print("\n  Launching EEG reader and robot controller...")
    subprocess.Popen(f'start "EEG Reader" "{eeg_runner}"', shell=True)
    time.sleep(1)
    subprocess.Popen(f'start "Robot Controller" "{motor_runner}"', shell=True)
    print("  Done — check the two new windows.")
    sys.exit(0)

# ── Normal mode ────────────────────────────────────────────────────────────────
data_buffer      = deque(maxlen=window_size)
current_command  = "stop"
pending_command  = "stop"
pending_count    = 0
samples_since_update = 0
zone_first_seen_time = None

_win_s = window_size / sampling_rate
print(f"\nLatency budget (estimates):")
print(f"  Window averaging : ~{_win_s/2:.1f}s  (buffer={_win_s:.1f}s)")
print(f"  Evaluation rate  :  up to {UPDATE_EVERY/sampling_rate:.1f}s")
print(f"  Confirmation     :  {CONFIRM_COUNT} × {UPDATE_EVERY/sampling_rate:.1f}s = {CONFIRM_COUNT*UPDATE_EVERY/sampling_rate:.1f}s")
print(f"  File IPC polling :  up to 0.2s")
print(f"  Est. total       : ~{_win_s/2 + CONFIRM_COUNT*UPDATE_EVERY/sampling_rate + 0.2:.1f}s\n")
print(f"GO when alpha_ratio > {ALPHA_GO_RATIO:.2f} ({ALPHA_GO_RATIO*100:.0f}%)  |  "
      f"STOP when alpha_ratio < {ALPHA_STOP_RATIO:.2f} ({ALPHA_STOP_RATIO*100:.0f}%)\n")

# ── Plot ───────────────────────────────────────────────────────────────────────
plt.ion()
fig, ax = plt.subplots(figsize=(10, 4))
x_vals, y_vals = [], []
line_plot, = ax.plot([], [], lw=2, color="steelblue")
ax.axhline(ALPHA_GO_RATIO,   color="green", linestyle="--", lw=1.5,
           label=f"GO  > {ALPHA_GO_RATIO:.2f}")
ax.axhline(ALPHA_STOP_RATIO, color="red",   linestyle="--", lw=1.5,
           label=f"STOP < {ALPHA_STOP_RATIO:.2f}")
_mid = (ALPHA_GO_RATIO + ALPHA_STOP_RATIO) / 2
ax.axhline(_mid, color="orange", linestyle=":", lw=1, alpha=0.6,
           label=f"Mid {_mid:.2f}")
ax.fill_between([0, 60], ALPHA_STOP_RATIO, ALPHA_GO_RATIO,
                alpha=0.08, color="orange", label="Hold zone")
ax.set_xlim(0, 60)
ax.set_ylim(0, 0.6)
ax.set_xlabel("Time (s)")
ax.set_ylabel("Alpha ratio  (alpha / total EEG power)")
ax.set_title(f"EEG — {serial_port}  |  GO > {ALPHA_GO_RATIO:.2f}  |  STOP < {ALPHA_STOP_RATIO:.2f}")
ax.legend(loc="upper right", fontsize=8)
fig.tight_layout()

start_plot_time = time.time()
print(f"Collecting {window_size} samples (~{window_size // sampling_rate}s) before first command...")

try:
    while True:
        raw = ser.readline().decode("utf-8", errors="replace").strip()
        if not raw:
            continue
        try:
            eeg_value = float(raw.split(",")[0])
        except (ValueError, IndexError):
            continue

        data_buffer.append(eeg_value)
        samples_since_update += 1

        if len(data_buffer) < window_size:
            filled = len(data_buffer)
            if filled % 128 == 0:
                print(f"  Collecting... {filled}/{window_size}")
            continue

        if samples_since_update < UPDATE_EVERY:
            continue
        samples_since_update = 0

        _, _, alpha_pow, _, total = compute_band_powers(data_buffer)

        if total < 1e-6:
            print("NOCONTACT  (check electrodes!)")
            continue

        alpha_ratio = alpha_pow / total

        if alpha_ratio > ALPHA_GO_RATIO:
            zone = "go"
        elif alpha_ratio < ALPHA_STOP_RATIO:
            zone = "stop"
        else:
            zone = "hold"

        if zone == "hold":
            pending_count = 0
        elif zone == current_command:
            pending_count   = 0
            pending_command = zone
        else:
            if zone == pending_command:
                pending_count += 1
            else:
                pending_command      = zone
                pending_count        = 1
                zone_first_seen_time = time.time()

            if pending_count >= CONFIRM_COUNT:
                det_lag = time.time() - zone_first_seen_time if zone_first_seen_time else 0
                print(f"  >> {zone.upper()} confirmed — detection lag: {det_lag:.1f}s")
                current_command      = zone
                pending_count        = 0
                zone_first_seen_time = None

        confirm_str = (f"{pending_count}/{CONFIRM_COUNT}"
                       if zone != "hold" and zone != current_command else "---")
        label = {"go": "GO  ", "stop": "STOP", "hold": "HOLD"}[zone]
        print(f"{label}  ratio={alpha_ratio:.3f} ({alpha_ratio*100:.1f}%)  "
              f"confirm={confirm_str}  cmd={current_command}")

        with open("motor_command.txt", "w") as f:
            f.write(f"{current_command},{time.time():.3f}")

        t = time.time() - start_plot_time
        x_vals.append(t)
        y_vals.append(alpha_ratio)

        if t > 60:
            cutoff = t - 60
            keep   = [i for i, v in enumerate(x_vals) if v >= cutoff]
            x_vals = [x_vals[i] for i in keep]
            y_vals = [y_vals[i] for i in keep]
            ax.set_xlim(x_vals[0], x_vals[-1])

        if y_vals:
            lo = max(0, min(y_vals) * 0.9)
            hi = max(max(y_vals) * 1.1, ALPHA_GO_RATIO * 1.5)
            ax.set_ylim(lo, hi)

        line_plot.set_data(x_vals, y_vals)
        plt.pause(0.001)

except KeyboardInterrupt:
    print("Stopped by user.")
finally:
    ser.close()
    print("Serial port closed.")
