"""
EEG Alpha-wave Robot Controller

Usage:
    python serial-read-alpha.py              # normal mode, COM5
    python serial-read-alpha.py COM5         # normal mode, explicit port
    python serial-read-alpha.py COM5 --calibrate   # calibration mode
"""
import sys
import time
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, lfilter
from collections import deque

# ── Configuration ─────────────────────────────────────────────────────────────
sampling_rate = 169          # measured from Arduino Uno on COM5
window_size   = 1024         # ~6 seconds of data before first decision

lowcut  = 8.0                # alpha band Hz
highcut = 12.0

# Single threshold + hysteresis (run --calibrate to get right values per user)
#
# GO   when alpha >  THRESHOLD + HYSTERESIS   (eyes closed = high alpha)
# STOP when alpha <  THRESHOLD - HYSTERESIS   (eyes open   = low alpha)
# HOLD (no change)   when alpha is between the two  ← prevents jitter
#
THRESHOLD  = 13.59            # midpoint between eyes-closed and eyes-open mean
HYSTERESIS = 0.37             # dead band on each side of the midpoint

# ── Parse CLI args ─────────────────────────────────────────────────────────────
args           = sys.argv[1:]
calibrate_mode = "--calibrate" in args
port_args      = [a for a in args if not a.startswith("--")]
serial_port    = port_args[0] if port_args else "COM5"
baudrate       = 115200

# ── Signal processing ──────────────────────────────────────────────────────────
def butter_bandpass(lowcut, highcut, fs, order=4):
    nyq = 0.5 * fs
    return butter(order, [lowcut / nyq, highcut / nyq], btype="band")

def apply_filter(data, lowcut, highcut, fs):
    b, a = butter_bandpass(lowcut, highcut, fs)
    return lfilter(b, a, data)

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
def collect_amplitudes(duration_s, label):
    """Read EEG for duration_s seconds, return list of alpha amplitudes."""
    buf = deque(maxlen=window_size)
    amps = []
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
            print(f"  [{label}] {end_time - time.time():.0f}s left  "
                  f"(buffer {len(buf)}/{window_size})")
            last_progress = time.time()

        if len(buf) < window_size:
            continue

        filtered = apply_filter(np.array(buf), lowcut, highcut, sampling_rate)
        amps.append(np.sqrt(np.mean(filtered ** 2)))

    return amps

# ── Calibration mode ───────────────────────────────────────────────────────────
if calibrate_mode:
    print("\n=== CALIBRATION — two phases, 20 seconds each ===\n")

    input("Phase 1 — Close your eyes and RELAX. Press Enter when ready...")
    print("  Recording eyes-CLOSED for 20 seconds...")
    closed_amps = collect_amplitudes(20, "EYES CLOSED")

    print()
    input("Phase 2 — Open your eyes and FOCUS on something. Press Enter when ready...")
    print("  Recording eyes-OPEN for 20 seconds...")
    open_amps = collect_amplitudes(20, "EYES OPEN")

    ser.close()

    if len(closed_amps) < 3 or len(open_amps) < 3:
        print("\nNot enough data — check sensor connection and try again.")
        sys.exit(1)

    mean_closed = np.mean(closed_amps)
    mean_open   = np.mean(open_amps)
    diff        = abs(mean_closed - mean_open)
    threshold   = round((mean_closed + mean_open) / 2, 2)
    hysteresis  = round(max(diff / 4, 0.3), 2)

    print(f"\n--- Calibration Results ---")
    print(f"  Eyes CLOSED mean : {mean_closed:.3f}")
    print(f"  Eyes OPEN   mean : {mean_open:.3f}")
    print(f"  Difference       : {diff:.3f}")

    if diff < 0.5:
        print("\n  WARNING: very small difference between states.")
        print("  Check electrode contact on the scalp.")

    print(f"\n  Suggested settings:")
    print(f"    THRESHOLD  = {threshold}")
    print(f"    HYSTERESIS = {hysteresis}")
    print("\nUpdate these in serial-read-alpha.py, then run without --calibrate.")
    sys.exit(0)

# ── Normal mode ────────────────────────────────────────────────────────────────
data_buffer     = deque(maxlen=window_size)
current_command = "stop"    # persists through the hysteresis dead band

go_line   = THRESHOLD + HYSTERESIS
stop_line = THRESHOLD - HYSTERESIS

plt.ion()
fig, ax = plt.subplots(figsize=(10, 4))
x_vals, y_vals = [], []
line_plot, = ax.plot([], [], lw=2, color="steelblue")
ax.axhline(go_line,   color="green",  linestyle="--", lw=1.5, label=f"GO above {go_line:.2f}")
ax.axhline(stop_line, color="red",    linestyle="--", lw=1.5, label=f"STOP below {stop_line:.2f}")
ax.axhline(THRESHOLD, color="orange", linestyle=":",  lw=1,   label=f"Midpoint {THRESHOLD:.2f}", alpha=0.6)
ax.fill_between([0, 60], stop_line, go_line, alpha=0.07, color="orange", label="Hold zone")
ax.set_xlim(0, 60)
ax.set_ylim(max(0, THRESHOLD - 5), THRESHOLD + 5)
ax.set_xlabel("Time (s)")
ax.set_ylabel("Alpha Amplitude (RMS)")
ax.set_title(f"EEG — {serial_port}  |  GO > {go_line:.2f}  |  STOP < {stop_line:.2f}")
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

        if len(data_buffer) < window_size:
            filled = len(data_buffer)
            if filled % 256 == 0:
                print(f"  Collecting... {filled}/{window_size}")
            continue

        filtered        = apply_filter(np.array(data_buffer), lowcut, highcut, sampling_rate)
        alpha_amplitude = np.sqrt(np.mean(filtered ** 2))

        if alpha_amplitude > go_line:
            current_command = "go"
            label = "GO  "
        elif alpha_amplitude < stop_line:
            current_command = "stop"
            label = "STOP"
        else:
            label = "HOLD"    # in dead band — keep previous command

        print(f"{label}  alpha={alpha_amplitude:.3f}  cmd={current_command}")

        with open("motor_command.txt", "w") as f:
            f.write(f"{current_command},{time.time():.3f}")

        # Update plot
        t = time.time() - start_plot_time
        x_vals.append(t)
        y_vals.append(alpha_amplitude)

        if t > 60:
            cutoff = t - 60
            keep   = [i for i, v in enumerate(x_vals) if v >= cutoff]
            x_vals = [x_vals[i] for i in keep]
            y_vals = [y_vals[i] for i in keep]
            ax.set_xlim(x_vals[0], x_vals[-1])

        if y_vals:
            lo = max(0, min(y_vals) * 0.95)
            hi = max(y_vals) * 1.05
            ax.set_ylim(lo, hi)

        line_plot.set_data(x_vals, y_vals)
        plt.pause(0.001)

except KeyboardInterrupt:
    print("Stopped by user.")
finally:
    ser.close()
    print("Serial port closed.")
