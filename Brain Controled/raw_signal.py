"""
Raw EEG Signal Viewer — see exactly what the electrodes are sending.

Usage:
    python raw_signal.py          # COM5
    python raw_signal.py COM5

Two live plots:
  TOP    — raw ADC values straight from the sensor (no filtering)
  BOTTOM — alpha-band amplitude (8-12 Hz, same as the main script)

Watch the TOP plot:
  - Good contact  : signal oscillates around ~512, visible wave activity
  - No contact    : flat line at 0, 512, or 1023 (rail)
  - Bad contact   : random large spikes, very noisy
"""
import sys
import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.signal import butter, lfilter
from collections import deque
import serial

PORT         = sys.argv[1] if len(sys.argv) > 1 else "COM5"
BAUDRATE     = 115200
SAMPLING_RATE = 169
WINDOW_RAW   = SAMPLING_RATE * 4   # 4 seconds of raw signal
WINDOW_AMP   = 1024                # 6 seconds for amplitude

lowcut, highcut = 8.0, 12.0

def butter_bandpass(lc, hc, fs, order=4):
    nyq = 0.5 * fs
    return butter(order, [lc / nyq, hc / nyq], btype="band")

def apply_filter(data):
    b, a = butter_bandpass(lowcut, highcut, SAMPLING_RATE)
    return lfilter(b, a, data)

# ── Connect ────────────────────────────────────────────────────────────────────
try:
    ser = serial.Serial(PORT, BAUDRATE, timeout=1)
    print(f"Connected to {PORT}")
except Exception as e:
    print(f"Cannot open {PORT}: {e}")
    sys.exit(1)

# ── Buffers ────────────────────────────────────────────────────────────────────
raw_buf = deque(maxlen=WINDOW_RAW)
amp_buf = deque(maxlen=WINDOW_AMP)
amp_vals  = []
amp_times = []

samples_since_amp = 0

# ── Plot setup ─────────────────────────────────────────────────────────────────
plt.ion()
fig = plt.figure(figsize=(12, 6))
gs  = gridspec.GridSpec(2, 1, hspace=0.4)

# Top: raw ADC
ax_raw = fig.add_subplot(gs[0])
raw_line, = ax_raw.plot([], [], lw=1, color="steelblue")
ax_raw.set_ylim(0, 1023)
ax_raw.set_xlim(0, WINDOW_RAW)
ax_raw.set_ylabel("ADC value (0-1023)")
ax_raw.set_title(f"RAW signal — {PORT}  (good contact ≈ oscillating around 512)")
ax_raw.axhline(512, color="gray", lw=0.5, linestyle=":")

# Bottom: alpha amplitude
ax_amp = fig.add_subplot(gs[1])
amp_line,  = ax_amp.plot([], [], lw=2, color="darkorange")
ax_amp.set_ylim(0, 40)
ax_amp.set_xlim(0, 60)
ax_amp.set_ylabel("Alpha amplitude (RMS)")
ax_amp.set_xlabel("Time (s)")
ax_amp.set_title("ALPHA amplitude — eyes open ≈ low  |  eyes closed ≈ high")

fig.tight_layout()

start = time.time()
print("Watching signal — close/open your eyes and observe both plots.")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        raw = ser.readline().decode("utf-8", errors="replace").strip()
        if not raw:
            continue
        try:
            val = float(raw.split(",")[0])
        except (ValueError, IndexError):
            continue

        raw_buf.append(val)
        amp_buf.append(val)
        samples_since_amp += 1

        # Update raw plot every sample
        raw_line.set_data(range(len(raw_buf)), list(raw_buf))

        # Update alpha amplitude once per second
        if len(amp_buf) == WINDOW_AMP and samples_since_amp >= SAMPLING_RATE:
            samples_since_amp = 0
            filtered = apply_filter(np.array(amp_buf))
            amp = np.sqrt(np.mean(filtered ** 2))
            t   = time.time() - start
            amp_vals.append(amp)
            amp_times.append(t)

            # Keep 60-second window
            if amp_times[-1] > 60:
                cutoff    = amp_times[-1] - 60
                keep      = [i for i, v in enumerate(amp_times) if v >= cutoff]
                amp_times = [amp_times[i] for i in keep]
                amp_vals  = [amp_vals[i]  for i in keep]
                ax_amp.set_xlim(amp_times[0], amp_times[-1])

            amp_line.set_data(amp_times, amp_vals)
            ax_amp.set_ylim(0, max(40, max(amp_vals) * 1.1))

            # Console summary
            mean_raw = np.mean(list(raw_buf))
            print(f"alpha={amp:6.2f}  |  raw mean={mean_raw:.0f}  "
                  f"raw range={min(raw_buf):.0f}-{max(raw_buf):.0f}")

        plt.pause(0.001)

except KeyboardInterrupt:
    print("\nStopped.")
finally:
    ser.close()
