"""
EEG session launcher — calibrates, updates thresholds, and starts both scripts.
Calibration is now fully self-contained inside serial-read-alpha.py --calibrate.
"""
import subprocess
import sys
import os

HERE         = os.path.dirname(os.path.abspath(__file__))
ALPHA_SCRIPT = os.path.join(HERE, "serial-read-alpha.py")
PYTHON       = sys.executable

print()
print("=" * 52)
print("  EEG Robot Control — Auto Setup & Launch")
print("=" * 52)
print()
print("Before continuing, make sure:")
print("  - The EEG electrodes are on your head")
print("  - The Arduino (COM5) is plugged in")
print("  - The mBot is on and connected via USB (COM6)")
print()
input("Press Enter when ready...")
print()

# Calibration handles everything: record both phases, update thresholds,
# and launch the EEG reader + robot controller windows.
result = subprocess.run(
    [PYTHON, ALPHA_SCRIPT, "COM5", "--calibrate"],
    cwd=HERE
)

if result.returncode != 0:
    print("\nSomething went wrong — check the messages above.")
    input("Press Enter to exit.")
    sys.exit(1)
