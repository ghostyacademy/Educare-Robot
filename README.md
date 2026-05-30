# Educare EEG Robot Control

A brain-computer interface (BCI) project that controls an **mBot Makeblock robot** using EEG (electroencephalography) brain signals. The robot responds to changes in alpha wave activity — the electrical pattern the brain produces when you relax and close your eyes.

---

## How It Works

1. The EEG sensor reads electrical signals from the user's scalp.
2. The software filters those signals to isolate **alpha waves (8–12 Hz)**.
3. It measures the amplitude (strength) of those waves in real time.
4. If the amplitude falls inside a calibrated "go" range → the robot moves forward.
5. If the amplitude is outside that range → the robot stops.

The key insight: alpha wave amplitude rises when you **close your eyes and relax**, and drops when you **open your eyes or concentrate**. This difference is what drives the robot.

---

## Hardware Required

| Component | Details |
|-----------|---------|
| EEG module | DIY serial COM port module (ordered from project author) |
| mBot robot | Makeblock mBot, Bluetooth or USB connection |
| Computer | Windows with Python 3.x |

**COM port assignments (update these if your ports differ):**

| Device | Default port | Where to change it |
|--------|-------------|-------------------|
| EEG sensor | `COM16` | `serial-read-alpha.py` line 1 or CLI argument |
| mBot robot | `COM15` | `mbot-motor-control.py` line 5 |

---

## Project Structure

```
Educare-Robot/
└── Brain Controled/
    ├── test_sensor.py          ← START HERE: verifies the EEG sensor works
    ├── serial-read-alpha.py    ← reads EEG, writes commands to motor_command.txt
    ├── mbot-motor-control.py   ← reads motor_command.txt, drives the robot
    └── motor_command.txt       ← shared file between the two scripts (auto-created)
```

---

## Step 1 — Install Dependencies

Open a terminal in the project folder and run:

```bash
pip install pyserial numpy scipy matplotlib
```

---

## Step 2 — Verify the EEG Sensor Works

Before anything else, confirm the sensor is actually sending data.

Plug in the EEG sensor, then run:

```bash
cd "Brain Controled"
python test_sensor.py
```

The script will:
- List all available COM ports on your computer
- Connect to `COM16` and listen for 15 seconds
- Print every line of data it receives
- Report whether the format looks correct

**If no data appears:** try other ports by running `python test_sensor.py COM5` (replace COM5 with each port listed at startup until you find the right one). Once found, update `serial_port` in `serial-read-alpha.py`.

**Expected output when sensor is working:**
```
[OK] 512.3
[OK] 498.7
[OK] 523.1
...
RESULT: Sensor is working! Data rate: 256 lines/sec
```

---

## Step 3 — Calibrate the Thresholds

Every person's brain produces different alpha wave amplitudes. The thresholds **must be calibrated** for each user before the system will work reliably.

```bash
python serial-read-alpha.py COM16 --calibrate
```

**During calibration (30 seconds):**
- First 15 seconds: **close your eyes and relax**
- Last 15 seconds: **open your eyes and focus on something**

At the end, the script prints something like:

```
--- Calibration Results ---
  Min   : 6.241
  Max   : 14.873
  Mean  : 9.105
  Std   : 2.341

  Suggested thresholds:
    AMPLITUDE_THRESHOLD_LOW  = 7.93
    AMPLITUDE_THRESHOLD_HIGH = 10.28
```

Open `serial-read-alpha.py` and update lines near the top:

```python
AMPLITUDE_THRESHOLD_LOW  = 7.93   # ← your calibrated value
AMPLITUDE_THRESHOLD_HIGH = 10.28  # ← your calibrated value
```

> **Tip:** If the robot goes when you want it to stop (or vice versa), you may need to swap the logic. The "go" zone is *inside* the LOW–HIGH range (eyes closed = high alpha = go). If your sensor/setup produces the opposite pattern, swap the command assignment in `serial-read-alpha.py`.

---

## Step 4 — Run the System

You need **two terminals open at the same time**, both inside the `Brain Controled/` folder.

**Terminal 1 — EEG reader:**
```bash
python serial-read-alpha.py COM16
```

**Terminal 2 — Robot controller:**
```bash
python mbot-motor-control.py
```

The EEG reader detects your brain state and writes a command (`go` or `stop`) to `motor_command.txt`. The robot controller reads that file every 100ms and sends the appropriate motor command to the mBot.

A live graph will appear showing your alpha wave amplitude in real time, with the threshold lines drawn on it.

---

## Troubleshooting

### "Could not open serial port"
- Wrong COM port. Run `python test_sensor.py` — it lists all available ports at startup.
- Device not plugged in, or Bluetooth not paired.

### Robot doesn't move
- Make sure `mbot-motor-control.py` is also running (it's a separate process).
- Check that `motor_command.txt` is being created in the `Brain Controled/` folder.
- Verify the mBot port in `mbot-motor-control.py` matches the actual COM port.

### Robot always stops / always goes
- Thresholds are wrong for this user. Run `--calibrate` again.
- The graph in the EEG reader shows your live amplitude — compare it to the threshold lines (orange and red dashed lines). The amplitude should visibly shift between eyes-open and eyes-closed states.

### Graph is blank or shows a flat line
- Amplitude values are outside the visible range. This was a known bug — it is now fixed with auto-scaling.
- If still blank: check the console for `Collecting... N/2048` progress messages.

### Data rate is not ~256 Hz
- The sensor may be configured differently. Note the actual rate printed by `test_sensor.py` and update `sampling_rate` in `serial-read-alpha.py`.

---

## What Has Been Done

| Item | Status |
|------|--------|
| EEG signal reading from serial port | Done |
| Alpha band filtering (8–12 Hz Butterworth) | Done |
| Go/stop command generation from amplitude | Done |
| mBot motor control via serial protocol | Done |
| Real-time graph with threshold lines | Done (fixed) |
| Sensor diagnostic tool (`test_sensor.py`) | Done (new) |
| Calibration mode (`--calibrate`) | Done (new) |
| COM port as CLI argument | Done (new) |
| Fix: extra sleep causing timing drift | Fixed |
| Fix: y-axis locked to [8,9] hiding data | Fixed |
| Fix: command file format consistency | Fixed |

---

## What Still Needs Work

- **Only forward/stop:** The robot can only go forward or stop. Backward, left, and right are not implemented in brain control mode.
- **Single-channel EEG:** The code reads one channel. Multi-channel would improve reliability.
- **Latency:** There is a ~8-second startup delay while the buffer fills (2048 samples at 256 Hz). Consider reducing `window_size` once thresholds are calibrated, to get faster response at the cost of slightly noisier decisions.
- **No timeout on the robot:** If the EEG reader crashes, the robot keeps running its last command. Add a timestamp check in `mbot-motor-control.py` to stop the robot if no new command arrives within a few seconds.

---

## Key Parameters (quick reference)

All in `serial-read-alpha.py`:

| Parameter | Default | What it does |
|-----------|---------|-------------|
| `serial_port` | `"COM16"` | COM port of the EEG sensor |
| `baudrate` | `115200` | Must match the sensor's baud rate |
| `sampling_rate` | `256` | Hz — must match the sensor |
| `window_size` | `2048` | Samples per decision (~8s). Lower = faster but noisier |
| `lowcut / highcut` | `8.0 / 12.0` | Alpha band limits in Hz. Do not change without reason |
| `AMPLITUDE_THRESHOLD_LOW` | `8.0` | Calibrate this per user |
| `AMPLITUDE_THRESHOLD_HIGH` | `8.7` | Calibrate this per user |

---

## Contact / Reference

Original project: https://khushee-g.github.io/EEG-Robot-Control/  
Contact (project author): goelkhushee@gmail.com
