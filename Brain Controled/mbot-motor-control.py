"""
mBot Motor Controller — version stable
"""
import serial
import time
import os

serial_port  = "COM15"
baudrate     = 115200
COMMAND_FILE = r"C:\Users\USER\Desktop\Educare-Robot\Brain Controled\motor_command.txt"

def connect():
    while True:
        try:
            bot = serial.Serial(serial_port, baudrate, timeout=1)
            print(f"Connecte au mBot sur {serial_port}")
            return bot
        except Exception as e:
            print(f"Impossible de connecter {serial_port}: {e}")
            print("Retry dans 3s...")
            time.sleep(3)

def run_motor(bot, port, speed):
    speed_bytes = speed.to_bytes(2, byteorder="little", signed=True)
    packet = bytearray([0xFF, 0x55, 0x07, 0x00, 0x02, 0x0A,
                        port, speed_bytes[0], speed_bytes[1]])
    packet.append(sum(packet[2:]) % 256)
    bot.write(packet)
    time.sleep(0.02)   # 20ms entre chaque paquet moteur — evite les collisions

def avancer(bot):
    run_motor(bot, 0x09, -150)   # vitesse 150 pour garantir le demarrage des 2 roues
    run_motor(bot, 0x0A,  150)
    # Renvoyer une 2e fois pour confirmer — certains firmwares ignorent le 1er paquet
    time.sleep(0.05)
    run_motor(bot, 0x09, -150)
    run_motor(bot, 0x0A,  150)

def arreter(bot):
    run_motor(bot, 0x09, 0)
    run_motor(bot, 0x0A, 0)
    time.sleep(0.05)
    run_motor(bot, 0x09, 0)
    run_motor(bot, 0x0A, 0)

mbot         = connect()
last_command = None
last_ts      = None

# Stop initial garanti
arreter(mbot)
print(f"Surveillance : {COMMAND_FILE}\n")

try:
    while True:
        try:
            with open(COMMAND_FILE, "r") as f:
                content = f.read().strip().lower()
            parts   = content.split(",")
            command = parts[0].strip()
            file_ts = float(parts[1]) if len(parts) > 1 else None
        except FileNotFoundError:
            time.sleep(0.1)
            continue
        except (ValueError, IndexError):
            time.sleep(0.1)
            continue

        if command in ("go", "stop"):
            if command != last_command or file_ts != last_ts:
                lag_str = f"  (lag: {time.time()-file_ts:.2f}s)" if file_ts else ""
                try:
                    if command == "go":
                        avancer(mbot)
                        print(f"GO   → moteurs avant{lag_str}")
                    else:
                        arreter(mbot)
                        print(f"STOP → moteurs off{lag_str}")
                    last_command = command
                    last_ts      = file_ts
                except (serial.SerialException, OSError) as e:
                    print(f"Erreur serie: {e}. Reconnexion...")
                    try:
                        mbot.close()
                    except Exception:
                        pass
                    mbot = connect()
                    last_command = None
                    last_ts      = None

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nArret...")
finally:
    try:
        arreter(mbot)
        time.sleep(0.3)
        mbot.close()
    except Exception:
        pass
    print("mBot deconnecte.")
