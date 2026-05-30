"""
EEG Sensor Diagnostic Tool
Usage:
    python test_sensor.py           # tests default port COM16
    python test_sensor.py COM5      # tests COM5
"""
import sys
import time
import serial
import serial.tools.list_ports

DURATION = 15  # seconds to listen
DEFAULT_PORT = "COM16"
BAUDRATE = 115200


def list_ports():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("  (no COM ports found)")
        return
    for p in ports:
        print(f"  {p.device:<10} {p.description}")


def test_port(port):
    print(f"\nConnecting to {port} at {BAUDRATE} baud...")
    try:
        ser = serial.Serial(port, BAUDRATE, timeout=2)
    except Exception as e:
        print(f"  ERROR: could not open port — {e}")
        return

    print(f"  Connected. Listening for {DURATION} seconds...\n")

    line_count = 0
    numeric_count = 0
    start = time.time()

    try:
        while time.time() - start < DURATION:
            raw = ser.readline()
            if not raw:
                continue

            try:
                text = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                text = repr(raw)

            line_count += 1

            # Check if first token is a number (expected EEG format)
            first_token = text.split(',')[0]
            is_numeric = False
            try:
                float(first_token)
                is_numeric = True
                numeric_count += 1
            except ValueError:
                pass

            tag = "[OK]" if is_numeric else "[??]"
            print(f"  {tag} {text}")

    except KeyboardInterrupt:
        print("\n  Stopped by user.")
    finally:
        ser.close()

    elapsed = time.time() - start
    print(f"\n--- Summary ---")
    print(f"  Duration       : {elapsed:.1f}s")
    print(f"  Lines received : {line_count}")
    print(f"  Numeric lines  : {numeric_count}")

    if line_count == 0:
        print("\n  RESULT: No data received. Check that the sensor is plugged in,")
        print("          powered on, and connected to this port.")
    elif numeric_count == 0:
        print("\n  RESULT: Data is arriving but lines are not numbers.")
        print("          The sensor may use a different protocol or baud rate.")
        print("          Try other baud rates: 9600, 57600, 115200.")
    else:
        rate = line_count / elapsed
        print(f"\n  RESULT: Sensor is working! Data rate: {rate:.0f} lines/sec")
        if abs(rate - 256) < 30:
            print("          Rate matches expected 256 Hz — sensor looks correct.")
        else:
            print(f"          Expected ~256 Hz. Actual {rate:.0f} Hz.")
            print("          Verify sampling_rate in serial-read-alpha.py matches the device.")


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PORT

    print("=== EEG Sensor Diagnostic ===")
    print("\nAvailable COM ports:")
    list_ports()

    test_port(port)


if __name__ == "__main__":
    main()
