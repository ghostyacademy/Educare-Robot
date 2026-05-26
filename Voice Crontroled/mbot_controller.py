"""
mbot_controller.py — AVANT · ARRIÈRE · STOP
"""

import serial
import serial.tools.list_ports
import time

SERIAL_PORT     = "COM17"      # ex: "COM5" — None = détection auto
BAUDRATE        = 115200
COMMAND_TIMEOUT = 4.0
SPEED           = 120       # 0–255

def find_mbot_port():
    ports = serial.tools.list_ports.comports()
    print("Ports disponibles :")
    for p in ports:
        print(f"  {p.device:8s} → {p.description}")
    for p in ports:
        desc = (p.description or "").lower()
        if any(k in desc for k in ["mbot","makeblock","bluetooth","btspp","rfcomm"]):
            print(f"\n✅ mBot détecté : {p.device}")
            return p.device
    print("\n⚠ mBot non détecté. Changez SERIAL_PORT dans le script.")
    return None

def connect(port):
    try:
        ser = serial.Serial(port, BAUDRATE, timeout=1, write_timeout=1)
        time.sleep(2)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        print(f"✅ Connecté sur {port}\n")
        return ser
    except Exception as e:
        print(f"❌ Connexion échouée sur {port} : {e}")
        return None

def run_motor(ser, port, speed):
    sb  = speed.to_bytes(2, byteorder="little", signed=True)
    pkt = bytearray([0xFF, 0x55, 0x07, 0x00, 0x02, 0x0A, port, sb[0], sb[1]])
    pkt.append(sum(pkt[2:]) % 256)
    try:
        ser.write(pkt)
        return True
    except serial.SerialException as e:
        print(f"❌ Erreur écriture : {e}")
        return False

def move_forward(ser):
    ok  = run_motor(ser, 0x09,  SPEED)
    ok &= run_motor(ser, 0x0A, -SPEED)
    if ok: print("▶  AVANT")
    return ok

def move_backward(ser):
    ok  = run_motor(ser, 0x09, -SPEED)
    ok &= run_motor(ser, 0x0A,  SPEED)
    if ok: print("◀  ARRIÈRE")
    return ok

def stop_motors(ser):
    ok  = run_motor(ser, 0x09, 0)
    ok &= run_motor(ser, 0x0A, 0)
    if ok: print("■  STOP")
    return ok

def read_command():
    try:
        with open("motor_command.txt", "r") as f:
            parts = f.read().strip().split(",")
        cmd = parts[0].lower()
        ts  = float(parts[1]) if len(parts) > 1 else 0.0
        return cmd, time.time() - ts
    except FileNotFoundError:
        return None, float("inf")
    except Exception:
        return None, float("inf")

def reconnect(port):
    print("🔄 Reconnexion...")
    time.sleep(2)
    return connect(port)

# ─── Main ─────────────────────────────────────────────────────
port = SERIAL_PORT or find_mbot_port()
if not port: exit(1)

mbot = connect(port)
if not mbot: exit(1)

stop_motors(mbot)   # sécurité au démarrage
print("En attente des commandes vocales...\n")

ACTIONS = {
    "go":   move_forward,
    "back": move_backward,
    "stop": stop_motors,
}

last = None

try:
    while True:
        cmd, age = read_command()

        if age > COMMAND_TIMEOUT:
            if last != "timeout":
                print(f"⚠ Timeout ({age:.1f}s) → arrêt sécurité")
                stop_motors(mbot)
                last = "timeout"
            time.sleep(0.01)
            continue

        if cmd in ACTIONS and cmd != last:
            ok = ACTIONS[cmd](mbot)
            if not ok:
                mbot = reconnect(port)
                if mbot:
                    ACTIONS[cmd](mbot)
            last = cmd

        time.sleep(0.01)

except KeyboardInterrupt:
    print("\nArrêt...")
    stop_motors(mbot)
    mbot.close()
    print("Déconnecté.")