"""
EOG Eye-Movement Robot Controller — version finale
───────────────────────────────────────────────────
Lit les gestes depuis l'Arduino EOG et ecrit motor_command.txt
pour que mbot-motor-control.py puisse piloter le mBot.

PROBLEME CORRIGE : l'Arduino envoie maintenant UNE seule valeur par ligne
("Up", "Down", "0") sans les valeurs brutes — le parsing est plus simple
et plus robuste.

Mapping :
  Up   → GO   (mBot avance)
  Down → STOP (mBot s'arrete)

Usage :
  python serial-read-eog.py COM16
  python serial-read-eog.py COM16 --calibrate
"""

import sys
import os
import time
import serial
import matplotlib.pyplot as plt
from collections import deque

# ── Chemin absolu — IDENTIQUE dans les deux scripts Python ───────────────────
COMMAND_FILE = r"C:\Users\USER\Desktop\Educare-Robot\Brain Controled\motor_command.txt"

# ── Configuration ─────────────────────────────────────────────────────────────
BLINK_TOGGLE = False   # True → clignement bascule GO/STOP

# ── CLI args ──────────────────────────────────────────────────────────────────
args           = sys.argv[1:]
calibrate_mode = "--calibrate" in args
port_args      = [a for a in args if not a.startswith("--")]
serial_port    = port_args[0] if port_args else "COM16"
baudrate       = 115200

# ── Ecriture fichier de commande ──────────────────────────────────────────────
def write_command(cmd):
    with open(COMMAND_FILE, "w") as f:
        f.write(f"{cmd},{time.time():.3f}")
    print(f"\n  >>> COMMANDE : {cmd.upper()} ecrite dans le fichier")

# ── Connexion serie ───────────────────────────────────────────────────────────
try:
    ser = serial.Serial(serial_port, baudrate, timeout=1)
    print(f"Connecte a {serial_port} a {baudrate} baud")
except Exception as e:
    print(f"Impossible d'ouvrir {serial_port}: {e}")
    sys.exit(1)

time.sleep(2)
ser.reset_input_buffer()

# ── Mode calibration ──────────────────────────────────────────────────────────
if calibrate_mode:
    print("\n=== CALIBRATION — 30 secondes ===")
    print("Uploadez eog_arduino.ino avec CALIBRATE_MODE true d'abord.")
    print("Bougez les yeux haut/bas/gauche/droite pendant la mesure.\n")
    v_vals, h_vals = [], []
    end_time = time.time() + 30
    try:
        while time.time() < end_time:
            raw = ser.readline().decode("utf-8", errors="replace").strip()
            if not raw or "," not in raw:
                continue
            parts = raw.split(",")
            try:
                v, h = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            v_vals.append(v)
            h_vals.append(h)
            print(f"  V={v:4d}  H={h:4d}   ({end_time-time.time():.0f}s restant)", end="\r", flush=True)
    except KeyboardInterrupt:
        pass
    print()
    if v_vals:
        print(f"\nVertical  A0 : min={min(v_vals)}  max={max(v_vals)}  mean={sum(v_vals)//len(v_vals)}")
        print(f"Horizontal A1: min={min(h_vals)}  max={max(h_vals)}  mean={sum(h_vals)//len(h_vals)}")
        print(f"\nRecommande dans le .ino :")
        print(f"  V_BASELINE  {sum(v_vals)//len(v_vals)}")
        print(f"  H_BASELINE  {sum(h_vals)//len(h_vals)}")
        swing_v = max(max(v_vals) - sum(v_vals)//len(v_vals), sum(v_vals)//len(v_vals) - min(v_vals))
        swing_h = max(max(h_vals) - sum(h_vals)//len(h_vals), sum(h_vals)//len(h_vals) - min(h_vals))
        print(f"  UP_THRESH   {int(swing_v * 0.4)}  (40% du swing max={swing_v})")
        print(f"  RIGHT_THRESH {int(swing_h * 0.4)}  (40% du swing max={swing_h})")
    ser.close()
    sys.exit(0)

# ── Etat initial ──────────────────────────────────────────────────────────────
current_command = "stop"
write_command("stop")

# ── Mapping geste → commande ──────────────────────────────────────────────────
def geste_vers_commande(geste, cmd_actuelle):
    if geste == "Up":
        return "go"
    if geste == "Down":
        return "stop"
    if geste == "Blink" and BLINK_TOGGLE:
        return "stop" if cmd_actuelle == "go" else "go"
    return None

# ── Plot temps reel ───────────────────────────────────────────────────────────
plt.ion()
fig, ax = plt.subplots(figsize=(10, 3))
fig.suptitle(f"EOG — {serial_port}  |  Haut=GO  Bas=STOP", fontsize=11)

PLOT_LEN  = 200
gest_hist = deque(["0"] * PLOT_LEN, maxlen=PLOT_LEN)
x_arr     = list(range(PLOT_LEN))

# Encode les gestes en valeurs numeriques pour le plot
def encode(g):
    return {"Up": 1.0, "Down": -1.0, "Blink": 0.8,
            "Left": -0.5, "Right": 0.5}.get(g, 0.0)

y_vals = [encode(g) for g in gest_hist]
line_g, = ax.plot(x_arr, y_vals, lw=1.5, color="steelblue")
ax.axhline(0, color="gray", lw=0.5, linestyle=":")
ax.axhline( 1.0, color="green", lw=1, linestyle="--", label="Up (GO)")
ax.axhline(-1.0, color="red",   lw=1, linestyle="--", label="Down (STOP)")
ax.set_xlim(0, PLOT_LEN)
ax.set_ylim(-1.5, 1.5)
ax.set_yticks([-1, 0, 1])
ax.set_yticklabels(["Down", "0", "Up"])
ax.legend(fontsize=8, loc="upper right")
ax.grid(True, alpha=0.2)
titre = ax.set_title("En attente...", fontsize=9, loc="left")
fig.tight_layout()

plot_counter = 0

# ── Boucle principale ─────────────────────────────────────────────────────────
print(f"\nLecture des gestes EOG (Arduino sur {serial_port})")
print(f"Regard HAUT → GO   |   Regard BAS → STOP")
print(f"Commande actuelle : STOP\n")

try:
    while True:
        raw_line = ser.readline().decode("utf-8", errors="replace").strip()

        # Ignorer les lignes vides ou parasites
        if not raw_line:
            continue

        # L'Arduino envoie UNE seule valeur par ligne : "Up", "Down", "0", etc.
        # On retire tout espace/retour chariot residuel
        geste = raw_line.strip()

        # Securite : si la ligne contient une virgule c'est du mode calibration
        # on l'ignore en mode normal
        if "," in geste:
            continue

        # Affichage continu
        cmd_label = "GO  " if current_command == "go" else "STOP"
        if geste != "0":
            print(f"  GESTE DETECTE : {geste}  (cmd actuelle={cmd_label})")
        else:
            print(f"  geste=0   cmd={cmd_label}", end="\r", flush=True)

        # Mise a jour commande
        nouvelle_cmd = geste_vers_commande(geste, current_command)

        if nouvelle_cmd is not None and nouvelle_cmd != current_command:
            current_command = nouvelle_cmd
            write_command(current_command)

        # Plot
        gest_hist.append(geste)
        plot_counter += 1
        if plot_counter % 10 == 0:
            line_g.set_ydata([encode(g) for g in gest_hist])
            cmd_str = "▶ GO" if current_command == "go" else "■ STOP"
            titre.set_text(f"Dernier geste : {geste}   Commande : {cmd_str}")
            titre.set_color("green" if current_command == "go" else "red")
            plt.pause(0.001)

except KeyboardInterrupt:
    print("\nArret par l'utilisateur.")
finally:
    write_command("stop")
    ser.close()
    print("Port serie ferme. STOP ecrit dans le fichier.")