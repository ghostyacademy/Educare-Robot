# """
# enregistrer_voix.py
# ───────────────────
# Lance ce script UNE SEULE FOIS pour enregistrer votre empreinte vocale.
# Parlez pendant 5 secondes (dites n'importe quoi : comptez, lisez un texte...).
# Crée le fichier  voix_reference.npy  utilisé par voice_controller.py.

# Installation :
#     pip install speechbrain sounddevice numpy scipy
# """

# import numpy as np
# import sounddevice as sd
# from scipy.io.wavfile import write as wav_write
# import time, os

# # ─── Config ───────────────────────────────────────────────────
# SAMPLE_RATE    = 16000
# DUREE          = 6          # secondes d'enregistrement
# OUTPUT_WAV     = "voix_reference.wav"

# OUTPUT_EMB     = "voix_reference.npy"
# DEVICE_INDEX   = None       # None = micro par défaut

# # ─── Enregistrement ───────────────────────────────────────────
# print("=" * 52)
# print("  ENREGISTREMENT DE VOTRE EMPREINTE VOCALE")
# print("=" * 52)
# print(f"\nParlez pendant {DUREE} secondes après le signal.")
# print("Dites les mots de commande, ou comptez, ou lisez...")
# print("\nPrêt ? Appuyez sur Entrée pour commencer.")
# input()

# print("\n🔴 ENREGISTREMENT EN COURS...\n")
# for i in range(3, 0, -1):
#     print(f"  {i}...")
#     time.sleep(1)
# print("  GO ! Parlez maintenant.\n")

# audio = sd.rec(int(DUREE * SAMPLE_RATE),
#                samplerate=SAMPLE_RATE,
#                channels=1,
#                dtype="int16",
#                device=DEVICE_INDEX)
# sd.wait()
# print("✅ Enregistrement terminé.\n")

# # Sauvegarde WAV
# wav_write(OUTPUT_WAV, SAMPLE_RATE, audio)
# print(f"💾 Audio sauvegardé : {OUTPUT_WAV}")

# # ─── Extraction empreinte vocale ──────────────────────────────
# print("\n⏳ Extraction de l'empreinte vocale...")

# try:
#     import torch
#     from speechbrain.inference.speaker import EncoderClassifier

#     classifier = EncoderClassifier.from_hparams(
#         source="speechbrain/spkrec-ecapa-voxceleb",
#         savedir="pretrained_models/spkrec-ecapa-voxceleb",
#         run_opts={"device": "cpu"}
#     )

#     # Charger audio en float32 normalisé [-1, 1]
#     audio_float = audio.astype(np.float32).flatten() / 32768.0
#     audio_tensor = torch.tensor(audio_float).unsqueeze(0)

#     with torch.no_grad():
#         embedding = classifier.encode_batch(audio_tensor)

#     emb_np = embedding.squeeze().numpy()
#     np.save(OUTPUT_EMB, emb_np)

#     print(f"✅ Empreinte vocale sauvegardée : {OUTPUT_EMB}")
#     print(f"   Dimension : {emb_np.shape}")
#     print("\n🎉 Vous pouvez maintenant lancer voice_controller.py !")

# except ImportError:
#     print("❌ SpeechBrain non installé.")
#     print("   pip install speechbrain torch")
# except Exception as e:
#     print(f"❌ Erreur : {e}")


"""
trouver_port_mbot.py v2
────────────────────────
Teste COM6, COM7, COM10, COM11 avec différents baudrates
et sans write_timeout pour éviter le crash immédiat.
"""

import serial
import time

PORTS_A_TESTER = ["COM6", "COM7", "COM10", "COM11"]
BAUDRATES       = [115200, 57600, 38400]   # le mBot HC-05 peut être sur 57600 aussi

def run_motor(ser, port_id, speed):
    sb  = speed.to_bytes(2, byteorder="little", signed=True)
    pkt = bytearray([0xFF, 0x55, 0x07, 0x00, 0x02, 0x0A, port_id, sb[0], sb[1]])
    pkt.append(sum(pkt[2:]) % 256)
    ser.write(pkt)
    ser.flush()

def stop_motors(ser):
    run_motor(ser, 0x09, 0)
    run_motor(ser, 0x0A, 0)

def test_port(com, baud):
    print(f"\n🔍 Test {com} @ {baud} baud...")
    try:
        ser = serial.Serial(
            com,
            baud,
            timeout=3,
            write_timeout=None,   # ← pas de timeout écriture
            dsrdtr=False,         # ← désactive handshake hardware
            rtscts=False,
            xonxoff=False
        )
        print(f"   Port ouvert. Attente initialisation BT (3s)...")
        time.sleep(3)
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # Stop d'abord
        try:
            stop_motors(ser)
            print(f"   ✅ Écriture OK sur {com}")
        except Exception as e:
            print(f"   ❌ Écriture échouée : {e}")
            ser.close()
            return False

        time.sleep(0.5)

        # Avancer
        print(f"   ▶  Envoi AVANT...")
        run_motor(ser, 0x09,  120)
        run_motor(ser, 0x0A, -120)
        time.sleep(2)
        stop_motors(ser)
        ser.close()

        rep = input(f"\n   ❓ Le robot a bougé ? (o/n) : ").strip().lower()
        return rep == "o"

    except serial.SerialException as e:
        print(f"   ❌ Impossible d'ouvrir {com} : {e}")
        return False

# ─── Main ─────────────────────────────────────────────────────
print("=" * 52)
print("  TEST PORTS BLUETOOTH mBot  (v2)")
print("=" * 52)
print("\n• mBot allumé et jumelé ?")
print("• Posé sur surface plane ?")
print("\nEntrée pour commencer.")
input()

bon_port = None
bon_baud = None

for com in PORTS_A_TESTER:
    for baud in BAUDRATES:
        if test_port(com, baud):
            bon_port = com
            bon_baud = baud
            break
    if bon_port:
        break
    time.sleep(1)

print("\n" + "=" * 52)
if bon_port:
    print(f"🎉 BON PORT TROUVÉ !")
    print(f"\nModifiez mbot_controller.py :")
    print(f'   SERIAL_PORT = "{bon_port}"')
    print(f'   BAUDRATE    = {bon_baud}')
else:
    print("❌ Aucun port ne répond.\n")
    print("Causes possibles :")
    print("  1. Le mBot est connecté à un autre appareil (téléphone ?)")
    print("     → Éteignez tous les autres appareils jumelés au mBot")
    print("  2. Le module BT n'est pas bien enfoncé sur la carte")
    print("     → Débranchez/rebranchez le module")
    print("  3. Le port COM est le port Entrant (pas Sortant)")
    print("     → Allez dans Paramètres Bluetooth → Autres paramètres")
    print("       Bluetooth → onglet Ports COM → vérifiez Entrant/Sortant")
print("=" * 52)