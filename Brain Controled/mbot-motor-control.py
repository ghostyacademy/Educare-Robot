import serial
import time

serial_port = "COM15"
baudrate    = 115200

try:
    mbot = serial.Serial(serial_port, baudrate, timeout=1)
    print(f"Connected to mBot on {serial_port}")
except Exception as e:
    print(f"Error opening serial port: {e}")
    exit(1)

def run_motor(port, speed):
    speed_bytes = speed.to_bytes(2, byteorder='little', signed=True)
    packet = bytearray([
        0xFF, 0x55,
        0x07,
        0x00,
        0x02,
        0x0A,
        port,
        speed_bytes[0],
        speed_bytes[1]
    ])
    checksum = sum(packet[2:]) % 256
    packet.append(checksum)
    mbot.write(packet)

def move_forward():
    run_motor(0x09, 100)
    run_motor(0x0A, -100)

def stop_motors():
    run_motor(0x09, 0)
    run_motor(0x0A, 0)

last_command = None
STOP_RESEND_INTERVAL = 1.0       # Re-send STOP every second as a safety heartbeat
last_stop_time = 0

try:
    while True:
        try:
            with open("motor_command.txt", "r") as f:
                command = f.read().strip().lower().split(',')[0]
        except FileNotFoundError:
            command = "stop"     # Safe default if file missing

        now = time.time()

        if command == "go":
            move_forward()
            if last_command != "go":
                print(">>> MOVING FORWARD")
            last_command = "go"

        elif command == "stop":
            # Always re-send STOP periodically — don't rely on a single packet
            if last_command != "stop" or (now - last_stop_time) >= STOP_RESEND_INTERVAL:
                stop_motors()
                last_stop_time = now
                if last_command != "stop":
                    print(">>> STOPPED")
            last_command = "stop"

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nInterrupted — stopping motors.")
    stop_motors()
    mbot.close()