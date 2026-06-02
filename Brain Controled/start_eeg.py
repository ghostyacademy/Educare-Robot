"""
Full EEG session launcher:
  1. Runs calibration (live output shown)
  2. Parses the suggested thresholds
  3. Updates serial-read-alpha.py automatically
  4. Opens EEG reader + robot controller in separate windows
"""
import subprocess
import sys
import re
import time
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ALPHA_SCRIPT = os.path.join(HERE, "serial-read-alpha.py")
MOTOR_SCRIPT  = os.path.join(HERE, "mbot-motor-control.py")
PYTHON = sys.executable

def banner(text):
    print()
    print("=" * 52)
    print(f"  {text}")
    print("=" * 52)

banner("EEG Robot Control — Auto Setup & Launch")
print()
print("This script will:")
print("  1. Run a 30-second calibration")
print("  2. Auto-update the thresholds in the code")
print("  3. Launch the EEG reader and robot controller")
print()
print("Before continuing, make sure:")
print("  - The EEG electrodes are on your head")
print("  - The Arduino (COM5) is plugged in")
print("  - The mBot is on and paired (COM15)")
print()
input("Press Enter when ready...")

# ── Step 1: Calibration ───────────────────────────────────────────────────────
banner("Step 1/3 — Calibration (30 seconds)")
print()
print("  Close your eyes and RELAX for the first 15 seconds.")
print("  Then open your eyes and FOCUS for the last 15 seconds.")
print()

proc = subprocess.Popen(
    [PYTHON, ALPHA_SCRIPT, "COM5", "--calibrate"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    cwd=HERE
)

lines = []
for line in proc.stdout:
    print(line, end="", flush=True)
    lines.append(line)
proc.wait()
output = "".join(lines)

if proc.returncode != 0:
    print("\nCalibration failed — check sensor connection and try again.")
    input("Press Enter to exit.")
    sys.exit(1)

# ── Step 2: Parse & apply thresholds ─────────────────────────────────────────
banner("Step 2/3 — Updating Thresholds")

threshold_match  = re.search(r"THRESHOLD\s*=\s*([\d.]+)", output)
hysteresis_match = re.search(r"HYSTERESIS\s*=\s*([\d.]+)", output)

if not threshold_match or not hysteresis_match:
    print("Could not read threshold values from calibration output.")
    print("Check that the sensor sent data during both phases.")
    input("Press Enter to exit.")
    sys.exit(1)

threshold  = threshold_match.group(1)
hysteresis = hysteresis_match.group(1)
print(f"\n  THRESHOLD  = {threshold}")
print(f"  HYSTERESIS = {hysteresis}")

with open(ALPHA_SCRIPT, "r", encoding="utf-8") as f:
    code = f.read()

code = re.sub(r"THRESHOLD\s*=\s*[\d.]+",  f"THRESHOLD  = {threshold}",  code)
code = re.sub(r"HYSTERESIS\s*=\s*[\d.]+", f"HYSTERESIS = {hysteresis}", code)

with open(ALPHA_SCRIPT, "w", encoding="utf-8") as f:
    f.write(code)

print("\n  serial-read-alpha.py updated successfully.")

# ── Step 3: Launch both scripts ───────────────────────────────────────────────
banner("Step 3/3 — Launching")

# Write tiny runner bats so paths with spaces don't break the start command
eeg_runner   = os.path.join(HERE, "_run_eeg_reader.bat")
motor_runner = os.path.join(HERE, "_run_robot_ctrl.bat")

with open(eeg_runner, "w") as f:
    f.write(f'@echo off\ncd /d "{HERE}"\npython serial-read-alpha.py COM5\npause\n')

with open(motor_runner, "w") as f:
    f.write(f'@echo off\ncd /d "{HERE}"\npython mbot-motor-control.py\npause\n')

print()
print("  Opening EEG reader in a new window...")
subprocess.Popen(f'start "EEG Reader" "{eeg_runner}"', shell=True)
time.sleep(1)

print("  Opening robot controller in a new window...")
subprocess.Popen(f'start "Robot Controller" "{motor_runner}"', shell=True)

print()
print("  Both scripts are running.")
print("  Close the EEG Reader and Robot Controller windows to stop.")
print()
input("Press Enter to close this launcher...")
