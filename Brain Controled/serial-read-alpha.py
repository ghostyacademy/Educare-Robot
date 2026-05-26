import serial
import time
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, lfilter
from collections import deque

sampling_rate = 256
sampling_interval = 1.0 / sampling_rate
window_size = 2048

lowcut = 8.0
highcut = 12.0

serial_port = "COM16"  # Change to your port
baudrate = 115200
timeout = 1

AMPLITUDE_THRESHOLD_LOW = 8.0  # adjust to calibrate against your own brain
AMPLITUDE_THRESHOLD_HIGH = 8.7

def butter_bandpass(lowcut, highcut, fs, order=4):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    return butter(order, [low, high], btype='band')

def apply_filter(data, lowcut, highcut, fs):
    b, a = butter_bandpass(lowcut, highcut, fs)
    return lfilter(b, a, data)

try:
    ser = serial.Serial(serial_port, baudrate, timeout=timeout)
    print(f"Connected to serial port: {serial_port}")
except Exception as e:
    print(f"Could not open serial port: {e}")
    exit(1)

data_buffer = deque(maxlen=window_size)
last_command_time = time.time()

plt.ion()
fig, ax = plt.subplots()
x_vals = []
y_vals = []
line, = ax.plot([], [], lw=2)
ax.set_xlim(0, 60)
ax.set_ylim(8, 9)
ax.set_xlabel("Time (s)")
ax.set_ylabel("Alpha Amplitude (RMS)")
ax.set_title("Real-Time Alpha Oscillation Amplitude")
fig.tight_layout()

start_plot_time = time.time()



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

        if len(data_buffer) == window_size:
            raw_data = np.array(data_buffer)
            filtered = apply_filter(raw_data, lowcut, highcut, sampling_rate)

            # Use RMS as amplitude measure
            alpha_amplitude = np.sqrt(np.mean(filtered**2))

            # Determine command
            if alpha_amplitude < AMPLITUDE_THRESHOLD_LOW or alpha_amplitude > AMPLITUDE_THRESHOLD_HIGH:
                command = "stop"
                print(f"STOP -- Alpha amplitude: {alpha_amplitude:.1f}")
            else:
                command = "go"
                print(f"GO -- Alpha amplitude: {alpha_amplitude:.1f}")

            with open("motor_command.txt", "w") as f:
                f.write(command)



            current_time = time.time() - start_plot_time
            x_vals.append(current_time)
            y_vals.append(alpha_amplitude)

            if x_vals[-1] > 60:
                x_vals = [t for t in x_vals if t >= x_vals[-1] - 60]
                y_vals = y_vals[-len(x_vals):]
                ax.set_xlim(x_vals[0], x_vals[-1])

            line.set_data(x_vals, y_vals)


            plt.pause(0.001)

        time.sleep(sampling_interval)

except KeyboardInterrupt:
    print("Program stopped by user.")

finally:
    ser.close()
    print("Serial port closed.")