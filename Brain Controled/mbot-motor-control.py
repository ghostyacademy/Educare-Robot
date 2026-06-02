import serial
import time

serial_port = "COM3"   # mBot Bluetooth — try COM4 if COM3 fails
baudrate    = 115200

def connect():
    while True:
        try:
            bot = serial.Serial(serial_port, baudrate, timeout=1)
            print(f"Connected to mBot on {serial_port}")
            return bot
        except Exception as e:
            print(f"Could not connect to {serial_port}: {e}")
            print("Retrying in 3 seconds... (make sure mBot is on)")
            time.sleep(3)

def run_motor(bot, port, speed):
    speed_bytes = speed.to_bytes(2, byteorder="little", signed=True)
    packet = bytearray([0xFF, 0x55, 0x07, 0x00, 0x02, 0x0A,
                        port, speed_bytes[0], speed_bytes[1]])
    packet.append(sum(packet[2:]) % 256)
    bot.write(packet)

def move_forward(bot):
    run_motor(bot, 0x09,  100)
    run_motor(bot, 0x0A, -100)

def stop_motors(bot):
    run_motor(bot, 0x09, 0)
    run_motor(bot, 0x0A, 0)

mbot        = connect()
last_command = None

try:
    while True:
        # Read command file
        try:
            with open("motor_command.txt", "r") as f:
                command = f.read().strip().lower().split(",")[0]
        except FileNotFoundError:
            command = None

        # Only send a packet when the command actually changes — sending
        # every 100ms floods the Bluetooth link and causes disconnects.
        if command in ("go", "stop") and command != last_command:
            try:
                if command == "go":
                    move_forward(mbot)
                    print("GO  → motors forward")
                else:
                    stop_motors(mbot)
                    print("STOP → motors off")
                last_command = command
            except (serial.SerialException, OSError) as e:
                print(f"Bluetooth dropped: {e}. Reconnecting...")
                try:
                    mbot.close()
                except Exception:
                    pass
                mbot = connect()
                last_command = None   # resend command after reconnect

        time.sleep(0.2)

except KeyboardInterrupt:
    print("\nStopping motors and closing connection...")
    try:
        stop_motors(mbot)
        time.sleep(0.3)
    except Exception:
        pass
    mbot.close()
