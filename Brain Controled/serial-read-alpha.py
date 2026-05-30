import serial
import time
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, lfilter
from collections import deque

# ── Signal config ──────────────────────────────────────────────────────────────
sampling_rate     = 256
sampling_interval = 1.0 / sampling_rate
window_size       = 512          # Reduced: 2048 = 8s lag, 512 = 2s → much more responsive

lowcut  = 8.0
highcut = 12.0                   # Alpha band: eyes closed → high alpha → STOP
                                 #             eyes open  → low alpha  → GO

# ── CALIBRATION GUIDE ─────────────────────────────────────────────────────────
# Step 1: Run the script, close your eyes for 10s → note the average amplitude
# Step 2: Open your eyes for 10s → note the average amplitude
# Step 3: Set THRESHOLD to the midpoint between those two values
# Example: eyes closed = 25, eyes open = 10 → set threshold to 17.5
ALPHA_THRESHOLD = 15.0           # <-- YOU MUST CALIBRATE THIS (see guide above)

# ── Debounce config ───────────────────────────────────────────────────────────
# Prevents flickering: command only changes after N consecutive same readings
DEBOUNCE_COUNT = 4               # Require 4 stable readings before switching

# ── Serial ────────────────────────────────────────────────────────────────────
serial_port = "COM16"
baudrate    = 115200

def butter_bandpass(lowcut, highcut, fs, order=4):
    nyq  = 0.5 * fs
    low  = lowcut / nyq
    high = highcut / nyq
    return butter(order, [low, high], btype='band')

def apply_filter(data, lowcut, highcut, fs):
    b, a = butter_bandpass(lowcut, highcut, fs)
    return lfilter(b, a, data)

try:
    ser = serial.Serial(serial_port, baudrate, timeout=1)
    print(f"Connected to EEG on {serial_port}")
except Exception as e:
    print(f"Could not open serial port: {e}")
    exit(1)

# ── State ─────────────────────────────────────────────────────────────────────
data_buffer     = deque(maxlen=window_size)
current_command = "stop"
pending_command = "stop"
debounce_streak = 0              # How many consecutive readings match pending_command

# ── Plot setup ────────────────────────────────────────────────────────────────
plt.ion()
fig, ax = plt.subplots()
x_vals, y_vals = [], []
line, = ax.plot([], [], lw=2)
threshold_line = ax.axhline(y=ALPHA_THRESHOLD, color='r', linestyle='--', label=f'Threshold ({ALPHA_THRESHOLD})')
ax.set_xlim(0, 60)
ax.set_ylim(0, 50)               # Wide Y range — you'll see where your signal actually lives
ax.set_xlabel("Time (s)")
ax.set_ylabel("Alpha Amplitude (RMS)")
ax.set_title("Real-Time Alpha — Eyes OPEN=low, Eyes CLOSED=high")
ax.legend()
fig.tight_layout()

start_time = time.time()

print("\n── CALIBRATION MODE ──────────────────────────────────────────────")
print("Watch the plot. Note the RMS value when eyes OPEN vs CLOSED.")
print(f"Current threshold: {ALPHA_THRESHOLD}  (edit ALPHA_THRESHOLD in the script)")
print("─────────────────────────────────────────────────────────────────\n")

try:
    while True:
        raw_line = ser.readline().decode("utf-8", errors="replace").strip()
        if not raw_line:
            continue

        try:
            eeg_value = float(raw_line.split(',')[0])
        except (ValueError, IndexError):
            continue

        data_buffer.append(eeg_value)

        if len(data_buffer) < window_size:
            continue                         # Wait until buffer is full before deciding

        # ── Filter & measure ──────────────────────────────────────────────────
        raw_data       = np.array(data_buffer)
        filtered       = apply_filter(raw_data, lowcut, highcut, sampling_rate)
        alpha_amplitude = np.sqrt(np.mean(filtered**2))

        # ── Classify eye state ────────────────────────────────────────────────
        # High alpha = eyes CLOSED = STOP the robot
        # Low alpha  = eyes OPEN   = GO
        raw_decision = "stop" if alpha_amplitude > ALPHA_THRESHOLD else "go"

        # ── Debounce ──────────────────────────────────────────────────────────
        if raw_decision == pending_command:
            debounce_streak += 1
        else:
            pending_command = raw_decision
            debounce_streak = 1              # Reset streak on direction change

        if debounce_streak >= DEBOUNCE_COUNT and raw_decision != current_command:
            current_command = raw_decision
            with open("motor_command.txt", "w") as f:
                f.write(current_command)
            print(f">>> COMMAND CHANGED TO: {current_command.upper()}  (alpha={alpha_amplitude:.2f})")
        else:
            print(f"    {'EYES OPEN ' if raw_decision == 'go' else 'EYES CLOSED'} | alpha={alpha_amplitude:.2f} | streak={debounce_streak}/{DEBOUNCE_COUNT} | active={current_command.upper()}")

        # ── Plot ──────────────────────────────────────────────────────────────
        t = time.time() - start_time
        x_vals.append(t)
        y_vals.append(alpha_amplitude)

        if t > 60:
            cutoff = t - 60
            trim   = next(i for i, v in enumerate(x_vals) if v >= cutoff)
            x_vals = x_vals[trim:]
            y_vals = y_vals[trim:]
            ax.set_xlim(x_vals[0], x_vals[-1])

        line.set_data(x_vals, y_vals)
        plt.pause(0.001)

        time.sleep(sampling_interval)

except KeyboardInterrupt:
    print("\nStopped. Writing final STOP command.")
    with open("motor_command.txt", "w") as f:
        f.write("stop")

finally:
    ser.close()
    print("Serial port closed.")