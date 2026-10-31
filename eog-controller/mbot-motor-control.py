"""
mBot Motor Controller — version stable

Lit motor_command.txt (ecrit par serial-read-eog.py) et pilote le mBot.

SECURITE (watchdog) :
  Le lecteur EOG reecrit le fichier toutes les ~200 ms (heartbeat).
  Si le timestamp a plus de WATCHDOG_TIMEOUT secondes (lecteur plante,
  Arduino debranche...), le mBot est arrete. Apres un arret watchdog,
  un "go" n'est accepte qu'apres avoir revu un "stop" frais
  (= regarder en BAS puis en HAUT pour repartir).

Usage :
  python mbot-motor-control.py           # port par defaut COM17
  python mbot-motor-control.py COM15
"""
import sys
import time
import os
import serial

# ── Configuration ─────────────────────────────────────────────────────────────
args             = [a for a in sys.argv[1:] if not a.startswith("--")]
serial_port      = args[0] if args else "COM17"
baudrate         = 115200
SPEED            = 150    # vitesse 150 pour garantir le demarrage des 2 roues
WATCHDOG_TIMEOUT = 1.0    # secondes sans heartbeat avant arret force

# Chemin relatif au script — IDENTIQUE dans les scripts Python
COMMAND_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "motor_command.txt")

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
    run_motor(bot, 0x09, -SPEED)
    run_motor(bot, 0x0A,  SPEED)
    # Renvoyer une 2e fois pour confirmer — certains firmwares ignorent le 1er paquet
    time.sleep(0.05)
    run_motor(bot, 0x09, -SPEED)
    run_motor(bot, 0x0A,  SPEED)

def arreter(bot):
    run_motor(bot, 0x09, 0)
    run_motor(bot, 0x0A, 0)
    time.sleep(0.05)
    run_motor(bot, 0x09, 0)
    run_motor(bot, 0x0A, 0)

def lire_commande():
    """Retourne (commande, timestamp) ou (None, None) si illisible."""
    try:
        with open(COMMAND_FILE, "r") as f:
            content = f.read().strip().lower()
        parts = content.split(",")
        return parts[0].strip(), float(parts[1])
    except (OSError, ValueError, IndexError):
        # Fichier absent, verrouille par l'ecrivain, ou ancien format sans timestamp
        return None, None

mbot             = connect()
last_command     = "stop"
watchdog_tripped = False

# Stop initial garanti
arreter(mbot)
print(f"Surveillance : {COMMAND_FILE}")
print(f"Watchdog     : arret si aucun heartbeat pendant {WATCHDOG_TIMEOUT}s\n")

try:
    while True:
        command, file_ts = lire_commande()
        stale = file_ts is None or (time.time() - file_ts) > WATCHDOG_TIMEOUT

        # Etat voulu pour les moteurs
        if stale or command not in ("go", "stop"):
            wanted = "stop"
            if last_command == "go":
                watchdog_tripped = True
                print("WATCHDOG → pas de heartbeat du lecteur EOG, arret force")
        elif watchdog_tripped:
            # Apres un arret watchdog, attendre un "stop" frais avant de repartir
            if command == "stop":
                watchdog_tripped = False
                print("Heartbeat retabli — regardez en HAUT pour repartir")
            wanted = "stop"
        else:
            wanted = command

        if wanted != last_command:
            lag_str = f"  (lag: {time.time()-file_ts:.2f}s)" if file_ts and not stale else ""
            try:
                if wanted == "go":
                    avancer(mbot)
                    print(f"GO   → moteurs avant{lag_str}")
                else:
                    arreter(mbot)
                    print(f"STOP → moteurs off{lag_str}")
                last_command = wanted
            except (serial.SerialException, OSError) as e:
                print(f"Erreur serie: {e}. Reconnexion...")
                try:
                    mbot.close()
                except Exception:
                    pass
                mbot = connect()
                arreter(mbot)
                last_command = "stop"

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
