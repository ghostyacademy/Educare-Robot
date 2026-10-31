"""
EEG Alpha-wave Robot Controller

Usage:
    python serial-read-alpha.py              # normal mode, COM16
    python serial-read-alpha.py COM5         # normal mode, COM5
    python serial-read-alpha.py COM16 --calibrate   # calibration mode
"""
import os
import sys
import time
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, lfilter
from collections import deque

# ── Configuration ────────────────────────────────────────────────────────────
sampling_rate = 256
window_size = 2048          # 8 seconds of data before first decision
decision_step = 32          # re-evaluate every 32 samples (~8 Hz) — filtering
                            # and plotting on every sample can't keep up at 256 Hz

# Same file as mbot-motor-control.py (relative to this script)
COMMAND_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "motor_command.txt")

lowcut = 8.0                # alpha band Hz
highcut = 12.0

# Adjust these after running --calibrate
AMPLITUDE_THRESHOLD_LOW  = 8.0
AMPLITUDE_THRESHOLD_HIGH = 8.7

# ── Parse CLI args ────────────────────────────────────────────────────────────
args = sys.argv[1:]
calibrate_mode = "--calibrate" in args
port_args = [a for a in args if not a.startswith("--")]
serial_port = port_args[0] if port_args else "COM16"
baudrate = 115200

# ── Signal processing helpers ─────────────────────────────────────────────────
def butter_bandpass(lowcut, highcut, fs, order=4):
    nyq = 0.5 * fs
    return butter(order, [lowcut / nyq, highcut / nyq], btype='band')

def apply_filter(data, lowcut, highcut, fs):
    b, a = butter_bandpass(lowcut, highcut, fs)
    return lfilter(b, a, data)

# ── Connect to serial port ────────────────────────────────────────────────────
import serial
try:
    ser = serial.Serial(serial_port, baudrate, timeout=1)
    print(f"Connected to {serial_port} at {baudrate} baud")
except Exception as e:
    print(f"Could not open {serial_port}: {e}")
    print("Check Device Manager > Ports (COM & LPT) for the right port.")
    sys.exit(1)

def write_command(cmd):
    # Atomic write (temp file + rename) so the motor controller never reads
    # a half-written file
    tmp = COMMAND_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write(f"{cmd},{time.time():.3f}")
        os.replace(tmp, COMMAND_FILE)
    except OSError:
        pass  # file briefly locked by the reader (Windows) — next step retries

# ── Calibration mode ──────────────────────────────────────────────────────────
if calibrate_mode:
    print("\n=== CALIBRATION MODE ===")
    print("Keep your eyes CLOSED and relax for 15 seconds, then OPEN your eyes.")
    print(f"Collecting {window_size} samples before first reading...")

    amplitudes = []
    data_buffer = deque(maxlen=window_size)
    cal_start = time.time()
    cal_duration = 30

    try:
        while time.time() - cal_start < cal_duration:
            line_data = ser.readline().decode("utf-8", errors="replace").strip()
            if not line_data:
                continue
            try:
                eeg_value = float(line_data.split(',')[0])
            except (ValueError, IndexError):
                continue

            data_buffer.append(eeg_value)

            if len(data_buffer) < window_size:
                filled = len(data_buffer)
                if filled % 256 == 0:
                    print(f"  Collecting... {filled}/{window_size}")
                continue

            filtered = apply_filter(np.array(data_buffer), lowcut, highcut, sampling_rate)
            amp = np.sqrt(np.mean(filtered ** 2))
            amplitudes.append(amp)
            remaining = cal_duration - (time.time() - cal_start)
            print(f"  Alpha amplitude: {amp:.3f}  ({remaining:.0f}s remaining)")

    except KeyboardInterrupt:
        print("\nCalibration stopped early.")

    ser.close()

    if len(amplitudes) < 3:
        print("Not enough data collected. Check sensor connection.")
        sys.exit(1)

    arr = np.array(amplitudes)
    mn, mx, mean, std = arr.min(), arr.max(), arr.mean(), arr.std()
    print(f"\n--- Calibration Results ---")
    print(f"  Min   : {mn:.3f}")
    print(f"  Max   : {mx:.3f}")
    print(f"  Mean  : {mean:.3f}")
    print(f"  Std   : {std:.3f}")
    suggested_low  = round(mean - 0.5 * std, 2)
    suggested_high = round(mean + 0.5 * std, 2)
    print(f"\n  Suggested thresholds:")
    print(f"    AMPLITUDE_THRESHOLD_LOW  = {suggested_low}")
    print(f"    AMPLITUDE_THRESHOLD_HIGH = {suggested_high}")
    print("\nUpdate these values in serial-read-alpha.py, then run without --calibrate.")
    sys.exit(0)

# ── Normal mode ───────────────────────────────────────────────────────────────
data_buffer = deque(maxlen=window_size)

plt.ion()
fig, ax = plt.subplots()
x_vals = []
y_vals = []
line_plot, = ax.plot([], [], lw=2)
ax.axhline(AMPLITUDE_THRESHOLD_LOW,  color='orange', linestyle='--', label='Threshold LOW')
ax.axhline(AMPLITUDE_THRESHOLD_HIGH, color='red',    linestyle='--', label='Threshold HIGH')
ax.set_xlim(0, 60)
ax.set_ylim(0, 30)      # wide initial range; auto-scales once data arrives
ax.set_xlabel("Time (s)")
ax.set_ylabel("Alpha Amplitude (RMS)")
ax.set_title(f"Real-Time Alpha Oscillation — {serial_port}")
ax.legend(loc='upper right')
fig.tight_layout()

start_plot_time = time.time()
samples_since_decision = decision_step   # decide as soon as the buffer is full
write_command("stop")

print(f"Collecting {window_size} samples ({window_size // sampling_rate}s) before first command...")

try:
    while True:
        line_data = ser.readline().decode("utf-8", errors="replace").strip()
        if not line_data:
            continue

        try:
            eeg_value = float(line_data.split(',')[0])
        except (ValueError, IndexError):
            continue

        data_buffer.append(eeg_value)

        # Progress feedback while buffer fills
        if len(data_buffer) < window_size:
            filled = len(data_buffer)
            if filled % 256 == 0:
                print(f"  Collecting... {filled}/{window_size}")
            continue

        samples_since_decision += 1
        if samples_since_decision < decision_step:
            continue
        samples_since_decision = 0

        raw_data = np.array(data_buffer)
        filtered = apply_filter(raw_data, lowcut, highcut, sampling_rate)
        alpha_amplitude = np.sqrt(np.mean(filtered ** 2))

        if alpha_amplitude < AMPLITUDE_THRESHOLD_LOW or alpha_amplitude > AMPLITUDE_THRESHOLD_HIGH:
            command = "stop"
            print(f"STOP  alpha={alpha_amplitude:.3f}")
        else:
            command = "go"
            print(f"GO    alpha={alpha_amplitude:.3f}")

        # Written every step (~8 Hz) — also serves as the watchdog heartbeat
        write_command(command)

        # Update plot
        current_time = time.time() - start_plot_time
        x_vals.append(current_time)
        y_vals.append(alpha_amplitude)

        if x_vals[-1] > 60:
            cutoff = x_vals[-1] - 60
            keep = [i for i, t in enumerate(x_vals) if t >= cutoff]
            x_vals = [x_vals[i] for i in keep]
            y_vals = [y_vals[i] for i in keep]
            ax.set_xlim(x_vals[0], x_vals[-1])

        # Auto-scale y with a bit of padding
        if y_vals:
            lo = max(0, min(y_vals) * 0.8)
            hi = max(y_vals) * 1.2
            ax.set_ylim(lo, hi)

        line_plot.set_data(x_vals, y_vals)
        plt.pause(0.001)

except KeyboardInterrupt:
    print("Stopped by user.")
finally:
    write_command("stop")
    ser.close()
    print("Serial port closed.")