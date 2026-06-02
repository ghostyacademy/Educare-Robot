"""
EEG Full-Spectrum Analyzer — see every frequency the electrodes are sending.

Usage:
    python eeg_spectrum.py          # COM5
    python eeg_spectrum.py COM5

Three live panels:
  TOP    — raw ADC waveform (oscilloscope view)
  MIDDLE — FFT power spectrum 0-80 Hz  (spike at 50/60 Hz = powerline noise)
  BOTTOM — band power bars: Delta / Theta / Alpha / Beta

What to look for:
  - Electrodes off head : spectrum is flat or dominated by 50/60 Hz noise
  - Good contact, eyes open  : small bump in alpha (8-12 Hz), rest low
  - Good contact, eyes closed : alpha bar clearly grows, dominant=ALPHA in console
"""
import sys
import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from collections import deque
import serial

PORT         = sys.argv[1] if len(sys.argv) > 1 else "COM5"
BAUDRATE     = 115200
FS           = 169          # measured sampling rate from Arduino Uno on COM5
BUF_SIZE     = 512          # ~3 s — good FFT resolution down to ~0.33 Hz
RAW_SHOW     = FS * 3       # 3 s of raw waveform
UPDATE_EVERY = FS           # refresh plots once per second

# ── Connect ────────────────────────────────────────────────────────────────────
try:
    ser = serial.Serial(PORT, BAUDRATE, timeout=1)
    print(f"Connected to {PORT} at {BAUDRATE} baud")
except Exception as e:
    print(f"Cannot open {PORT}: {e}")
    sys.exit(1)

# ── Buffers ────────────────────────────────────────────────────────────────────
raw_buf = deque(maxlen=RAW_SHOW)
fft_buf = deque(maxlen=BUF_SIZE)
samples_since_update = 0

# ── Band power helper ──────────────────────────────────────────────────────────
BANDS = {
    "Delta": (0.5,  4.0, "steelblue"),
    "Theta": (4.0,  8.0, "cyan"),
    "Alpha": (8.0, 12.0, "limegreen"),
    "Beta":  (12.0, 30.0, "darkorange"),
}

def band_power(freqs, power, lo, hi):
    mask = (freqs >= lo) & (freqs <= hi)
    return float(np.sum(power[mask]))

# ── Plot setup ─────────────────────────────────────────────────────────────────
plt.ion()
fig = plt.figure(figsize=(13, 8))
fig.suptitle(f"EEG Full-Spectrum Analyzer — {PORT}", fontsize=13, fontweight="bold")
gs = gridspec.GridSpec(3, 1, hspace=0.55)

# Panel 1: raw waveform
ax_raw = fig.add_subplot(gs[0])
raw_line, = ax_raw.plot([], [], lw=1, color="steelblue")
ax_raw.set_ylim(0, 1023)
ax_raw.set_xlim(0, RAW_SHOW)
ax_raw.set_ylabel("ADC (0-1023)")
ax_raw.set_title("RAW waveform  |  good contact ≈ oscillating around 512")
ax_raw.axhline(512, color="gray", lw=0.6, linestyle=":")

# Panel 2: FFT spectrum
ax_fft = fig.add_subplot(gs[1])
fft_line, = ax_fft.plot([], [], lw=1.5, color="mediumpurple")
ax_fft.set_xlim(0, 80)
ax_fft.set_ylim(0, 1)          # auto-scaled each update
ax_fft.set_xlabel("Frequency (Hz)")
ax_fft.set_ylabel("Power (a.u.)")
ax_fft.set_title("SPECTRUM  |  alpha peak at 8-12 Hz = real EEG  |  50/60 Hz spike = powerline noise")

# Color the EEG bands on the spectrum
band_spans = {}
for name, (lo, hi, color) in BANDS.items():
    span = ax_fft.axvspan(lo, hi, alpha=0.15, color=color, label=name)
    band_spans[name] = span
ax_fft.legend(loc="upper right", fontsize=7, ncol=4)

# Panel 3: band bar chart
ax_bar = fig.add_subplot(gs[2])
band_names  = list(BANDS.keys())
band_colors = [BANDS[n][2] for n in band_names]
bars = ax_bar.bar(band_names, [0, 0, 0, 0], color=band_colors, edgecolor="white", width=0.5)
ax_bar.set_ylabel("Band power (a.u.)")
ax_bar.set_title("BAND POWER  |  alpha bar dominant = eyes closed state detected")
ax_bar.set_ylim(0, 1)
dominant_text = ax_bar.text(0.5, 0.92, "", transform=ax_bar.transAxes,
                             ha="center", fontsize=11, fontweight="bold", color="green")

fig.tight_layout(rect=[0, 0, 1, 0.96])

print(f"\nBuffering {BUF_SIZE} samples (~{BUF_SIZE//FS}s) before first spectrum...")
print("Close/open your eyes and watch the Alpha bar and spectrum peak.\n")
print(f"{'delta':>10} {'theta':>10} {'alpha':>10} {'beta':>10}   dominant")
print("-" * 60)

# ── Main loop ──────────────────────────────────────────────────────────────────
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
        fft_buf.append(val)
        samples_since_update += 1

        # Update raw waveform every sample
        raw_line.set_data(range(len(raw_buf)), list(raw_buf))

        # Update spectrum + bars once per second
        if len(fft_buf) == BUF_SIZE and samples_since_update >= UPDATE_EVERY:
            samples_since_update = 0

            data   = np.array(fft_buf, dtype=float)
            data  -= np.mean(data)                      # remove DC offset
            window = np.hanning(BUF_SIZE)
            spec   = np.abs(np.fft.rfft(data * window))
            freqs  = np.fft.rfftfreq(BUF_SIZE, d=1.0 / FS)
            power  = spec ** 2

            # Spectrum plot (limit x to 80 Hz)
            mask80 = freqs <= 80
            p_show = power[mask80]
            f_show = freqs[mask80]
            peak   = p_show.max() if p_show.max() > 0 else 1.0
            fft_line.set_data(f_show, p_show / peak)   # normalize to 0-1
            ax_fft.set_ylim(0, 1.05)

            # Band powers (normalized by total)
            bp = {n: band_power(freqs, power, lo, hi)
                  for n, (lo, hi, _) in BANDS.items()}
            total = sum(bp.values()) or 1.0
            bp_norm = {n: v / total for n, v in bp.items()}

            for bar, name in zip(bars, band_names):
                bar.set_height(bp_norm[name])
                bar.set_color("limegreen" if name == "Alpha" and
                              bp_norm["Alpha"] == max(bp_norm.values())
                              else BANDS[name][2])

            ax_bar.set_ylim(0, max(bp_norm.values()) * 1.25 + 0.05)

            dominant = max(bp_norm, key=bp_norm.get)
            if dominant == "Alpha":
                dominant_text.set_text(f"dominant = {dominant.upper()} ✓")
                dominant_text.set_color("green")
            else:
                dominant_text.set_text(f"dominant = {dominant.upper()}")
                dominant_text.set_color("gray")

            print(f"delta={bp_norm['Delta']:9.3f}  theta={bp_norm['Theta']:9.3f}  "
                  f"alpha={bp_norm['Alpha']:9.3f}  beta={bp_norm['Beta']:9.3f}   "
                  f"dominant={dominant.upper()}")

        plt.pause(0.001)

except KeyboardInterrupt:
    print("\nStopped.")
finally:
    ser.close()
