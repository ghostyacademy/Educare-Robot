"""
EEG Alpha-wave Robot Controller

Usage:
    python serial-read-alpha.py              # normal mode, COM5
    python serial-read-alpha.py COM5         # normal mode, explicit port
    python serial-read-alpha.py COM5 --calibrate   # calibration mode
"""
import sys
import os
import re
import time
import subprocess
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, lfilter
from collections import deque

# ── Configuration ─────────────────────────────────────────────────────────────
sampling_rate = 169          # measured from Arduino Uno on COM5
window_size   = 1024         # ~6 seconds of data before first decision

lowcut  = 8.0                # alpha band Hz
highcut = 12.0

# How often to evaluate and how long to sustain a decision before acting.
# Alpha naturally oscillates every few seconds; these two settings prevent
# a single spike from flipping the robot command.
UPDATE_EVERY  = sampling_rate  # re-evaluate once per second (not every sample)
CONFIRM_COUNT = 1              # require N consecutive same-zone readings to act

# Single threshold + hysteresis (run --calibrate to set these per user)
#
# GO   when alpha >  THRESHOLD + HYSTERESIS   (eyes closed = high alpha)
# STOP when alpha <  THRESHOLD - HYSTERESIS   (eyes open   = low alpha)
# HOLD (no change)   when alpha is in the dead band
#
THRESHOLD  = 9.76            # midpoint between eyes-closed (~18) and eyes-open (~9.7)
HYSTERESIS = 0.18            # narrower dead band for faster reaction

# Minimum signal level — below this the electrodes have lost contact
NO_CONTACT_LIMIT = 2.0

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
        amp = np.sqrt(np.mean(filtered ** 2))
        amps.append(amp)
        print(f"    alpha={amp:.2f}", end="\r", flush=True)  # live readout

    print()  # newline after the live readout
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
    hysteresis  = round(max(diff / 6, 0.18), 2)
    confirm_count = 1 if diff < 1.0 else 2

    print(f"\n--- Calibration Results ---")
    print(f"  Eyes CLOSED mean : {mean_closed:.3f}")
    print(f"  Eyes OPEN   mean : {mean_open:.3f}")
    print(f"  Difference       : {diff:.3f}")

    if diff < 0.5:
        print("\n  WARNING: very small difference between states.")
        print("  Check electrode contact on the scalp.")

    print(f"\n  Applied settings:")
    print(f"    THRESHOLD  = {threshold}")
    print(f"    HYSTERESIS = {hysteresis}")
    print(f"    CONFIRM    = {confirm_count}")

    # Self-update: write new threshold values back into this file
    this_file = os.path.abspath(__file__)
    with open(this_file, "r", encoding="utf-8") as f:
        code = f.read()
    code = re.sub(r"THRESHOLD\s*=\s*[\d.]+",  f"THRESHOLD  = {threshold}",  code)
    code = re.sub(r"HYSTERESIS\s*=\s*[\d.]+", f"HYSTERESIS = {hysteresis}", code)
    code = re.sub(r"CONFIRM_COUNT\s*=\s*\d+", f"CONFIRM_COUNT = {confirm_count}", code)
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
current_command  = "stop"   # persists through the dead band
pending_command  = "stop"   # candidate that must be confirmed
pending_count    = 0        # how many consecutive readings support pending
samples_since_update = 0    # counts toward next evaluation
zone_first_seen_time = None  # when current pending zone was first detected

go_line   = THRESHOLD + HYSTERESIS
stop_line = THRESHOLD - HYSTERESIS

_win_s = window_size / sampling_rate
print(f"\nLatency budget (estimates):")
print(f"  Window averaging : ~{_win_s/2:.1f}s  (buffer={_win_s:.1f}s, signal fills half on average)")
print(f"  Evaluation rate  :  up to {UPDATE_EVERY/sampling_rate:.1f}s")
print(f"  Confirmation     :  {CONFIRM_COUNT} × {UPDATE_EVERY/sampling_rate:.1f}s = {CONFIRM_COUNT * UPDATE_EVERY/sampling_rate:.1f}s")
print(f"  File IPC polling :  up to 0.2s")
print(f"  ─────────────────────────────────────────")
print(f"  Est. total       : ~{_win_s/2 + CONFIRM_COUNT * UPDATE_EVERY/sampling_rate + 0.2:.1f}s  (measured below)\n")

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
        samples_since_update += 1

        if len(data_buffer) < window_size:
            filled = len(data_buffer)
            if filled % 256 == 0:
                print(f"  Collecting... {filled}/{window_size}")
            continue

        # Only evaluate once per second — alpha naturally oscillates every
        # few seconds; evaluating every sample just amplifies that noise.
        if samples_since_update < UPDATE_EVERY:
            continue
        samples_since_update = 0

        filtered        = apply_filter(np.array(data_buffer), lowcut, highcut, sampling_rate)
        alpha_amplitude = np.sqrt(np.mean(filtered ** 2))

        # Electrode contact lost — near-zero signal means nothing is connected
        if alpha_amplitude < NO_CONTACT_LIMIT:
            print(f"NOCONTACT  alpha={alpha_amplitude:.3f}  (check electrodes!)")
            continue

        # Artifact rejection: spikes > 4× threshold are almost certainly
        # movement or electrode noise, not real brain signal — skip them.
        artifact_limit = THRESHOLD * 4
        if alpha_amplitude > artifact_limit:
            print(f"ARTFCT  alpha={alpha_amplitude:.1f}  (movement artifact — ignored)")
            continue

        # Determine which zone we are in
        if alpha_amplitude > go_line:
            zone = "go"
        elif alpha_amplitude < stop_line:
            zone = "stop"
        else:
            zone = "hold"

        # Confirmation: only count toward a change when the zone differs from
        # the current command. If the separation is weak, keep the reaction
        # fast by using fewer consecutive samples before switching.
        if zone == "hold":
            pending_count = 0
        elif zone == current_command:
            # Already in this state — nothing to do, keep counter clean
            pending_count = 0
            pending_command = zone
        else:
            # Trying to change — accumulate consecutive same-zone readings
            if zone == pending_command:
                pending_count += 1
            else:
                pending_command      = zone
                pending_count        = 1
                zone_first_seen_time = time.time()  # start latency clock

            required_confirm = CONFIRM_COUNT
            if pending_count >= required_confirm:
                det_lag = time.time() - zone_first_seen_time if zone_first_seen_time else 0
                print(f"  >> {zone.upper()} confirmed — EEG detection lag: {det_lag:.1f}s")
                current_command      = zone
                pending_count        = 0
                zone_first_seen_time = None

        confirm_str = (f"{pending_count}/{CONFIRM_COUNT}"
                       if zone not in ("hold",) and zone != current_command
                       else "---")
        label = {"go": "GO  ", "stop": "STOP", "hold": "HOLD"}[zone]
        print(f"{label}  alpha={alpha_amplitude:.3f}  confirm={confirm_str}  cmd={current_command}")

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
