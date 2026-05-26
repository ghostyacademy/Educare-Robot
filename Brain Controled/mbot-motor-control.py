import serial
import time


serial_port = "COM15"  # Change this to your port
baudrate = 115200

try:
    mbot = serial.Serial(serial_port, baudrate, timeout=1)
    print(f"Connected to mBot on {serial_port}")
except Exception as e:
    print(f"Error opening serial port: {e}")
    exit(1)



def run_motor(port, speed):
    """
    port: 0x09 = left motor, 0x0A = right motor
    speed: -255 to 255
    """
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

    print(f"Sent to port {hex(port)}: {list(packet)} (speed {speed})")

def move_forward():
    run_motor(0x09, 100)  
    run_motor(0x0A, -100)

def stop_motors():
    run_motor(0x09, 0)  
    run_motor(0x0A, 0)





last_command = None

try:
    while True:
        try:
            with open("motor_command.txt", "r") as f:
                command = f.read().strip().lower()
        except FileNotFoundError:
            command = None

        if command in ["go", "stop"]:
            if command == "go":
                move_forward()
                print("GO")
            elif command == "stop":
                stop_motors()
                print("STOP")
                time.sleep(1)
            last_command = command

        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nProgram interrupted! Stopping motors...")
    stop_motors()
    mbot.close()