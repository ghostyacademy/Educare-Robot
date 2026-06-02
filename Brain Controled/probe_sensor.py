"""Probe the EEG sensor to find what start command it needs."""
import serial
import time

PORT = "COM6"
BAUD = 115200

s = serial.Serial(PORT, BAUD, timeout=2)
print(f"Connected to {PORT}\n")

# Read initial greeting
line = s.readline().decode(errors="replace").strip()
print(f"Device says: {line}\n")

commands = [b"b", b"s", b"r", b"d", b"start\r\n", b"\r\n", b"1", b"go\r\n"]

for cmd in commands:
    print(f"Sending {cmd!r} ...")
    s.write(cmd)
    time.sleep(1.0)
    received = []
    while True:
        raw = s.readline()
        if not raw:
            break
        received.append(raw.decode(errors="replace").strip())
    if received:
        for r in received[:5]:
            print(f"  << {r}")
        print(f"  ({len(received)} line(s) received)\n")
    else:
        print("  (no response)\n")

s.close()
print("Done.")
