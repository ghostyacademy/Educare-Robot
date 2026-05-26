"""
voice_controller.py
───────────────────
Commandes : AVANT · ARRIÈRE · STOP
FR + EN simultané · Vérification de l'identité vocale

Structure :
    voice/
    ├── enregistrer_voix.py      ← lancer en premier !
    ├── voice_controller.py
    ├── mbot_controller.py
    ├── voix_reference.npy       ← créé par enregistrer_voix.py
    ├── voix_reference.wav
    ├── model_fr/
    └── model_en/
"""

import time, json, threading, queue, os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.animation import FuncAnimation
from collections import deque

try:
    from vosk import Model, KaldiRecognizer
    import sounddevice as sd
    VOSK_OK = True
except ImportError:
    VOSK_OK = False

try:
    import torch
    from speechbrain.inference.speaker import EncoderClassifier
    SB_OK = True
except ImportError:
    SB_OK = False

# ─── Configuration ────────────────────────────────────────────
MODEL_PATH_FR  = "model_fr"
MODEL_PATH_EN  = "model_en"
VOICE_EMB_PATH = "voix_reference.npy"

SAMPLE_RATE = 16000
BLOCK_SIZE  = 1600

# Seuil similarité cosinus  (0.0 → 1.0)
# Moyen : 0.60 — ajustez si trop strict (baissez) ou trop souple (montez)
SIMILARITY_THRESHOLD = 2

# Taille du buffer audio pour la vérification vocale (~2 secondes)
VERIFY_BUFFER_SIZE = SAMPLE_RATE * 2

GO_KEYWORDS   = ["go", "avance", "avant", "départ", "start", "forward", "marche"]
BACK_KEYWORDS = ["arrière", "recule", "back", "backward", "reculer", "behind"]
STOP_KEYWORDS = ["stop", "arrête", "arrêt", "halt", "stoppe"]

COMMAND_TIMEOUT = 4.0
DEVICE_INDEX    = None

CMD_COLORS = {"go": "#00e676", "back": "#ffaa00", "stop": "#ff1744"}
CMD_LABELS = {"go": "▶  AVANT",  "back": "◀  ARRIÈRE", "stop": "■  STOP"}
CMD_VAL    = {"go": 2,           "back": 1,             "stop": 0}

# ─── État partagé ─────────────────────────────────────────────
audio_q_fr   = queue.Queue(maxsize=20)
audio_q_en   = queue.Queue(maxsize=20)
state        = {"cmd": "stop", "ts": time.time() - 10}
volume_buf   = deque(maxlen=600)
cmd_log      = deque(maxlen=100)
state_lock   = threading.Lock()

# Buffer audio brut pour vérification vocale
verify_buf   = deque(maxlen=VERIFY_BUFFER_SIZE)
verify_lock  = threading.Lock()

# Dernier résultat de vérification (pour l'affichage)
speaker_info = {"score": 0.0, "authorized": False, "checked": False}

# ─── Chargement empreinte + modèle speaker ────────────────────
reference_embedding = None
speaker_classifier  = None

def load_speaker_model():
    global reference_embedding, speaker_classifier
    if not SB_OK:
        print("⚠ SpeechBrain non installé → vérification vocale désactivée")
        print("  pip install speechbrain torch")
        return False

    if not os.path.exists(VOICE_EMB_PATH):
        print(f"⚠ Empreinte vocale introuvable : '{VOICE_EMB_PATH}'")
        print("  Lancez d'abord : python enregistrer_voix.py")
        return False

    try:
        reference_embedding = np.load(VOICE_EMB_PATH)
        print(f"✅ Empreinte vocale chargée ({reference_embedding.shape})")

        speaker_classifier = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts={"device": "cpu"}
        )
        print("✅ Modèle speaker chargé")
        return True
    except Exception as e:
        print(f"❌ Erreur chargement speaker : {e}")
        return False

# ─── Vérification d'identité ──────────────────────────────────
def cosine_similarity(a, b):
    a = a.flatten(); b = b.flatten()
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

def is_authorized_speaker():
    """Retourne (autorisé, score). Bloquant ~100ms."""
    if reference_embedding is None or speaker_classifier is None:
        return True, 1.0   # si pas de modèle → tout passe

    with verify_lock:
        buf = list(verify_buf)

    if len(buf) < SAMPLE_RATE:     # moins d'1 seconde → skip
        return True, 1.0

    audio_np = np.array(buf, dtype=np.float32) / 32768.0
    audio_t  = torch.tensor(audio_np).unsqueeze(0)

    try:
        with torch.no_grad():
            emb = speaker_classifier.encode_batch(audio_t).squeeze().numpy()
        score = cosine_similarity(emb, reference_embedding)
        authorized = score >= SIMILARITY_THRESHOLD
        with state_lock:
            speaker_info["score"]      = score
            speaker_info["authorized"] = authorized
            speaker_info["checked"]    = True
        return authorized, score
    except Exception:
        return True, 1.0

# ─── Fichier partagé ──────────────────────────────────────────
def write_command(cmd):
    with state_lock:
        state["cmd"] = cmd
        state["ts"]  = time.time()
    with open("motor_command.txt", "w") as f:
        f.write(f"{cmd},{time.time():.6f}")

# ─── Callback audio ───────────────────────────────────────────
def audio_callback(indata, frames, t_info, status):
    raw = bytes(indata)
    if not audio_q_fr.full(): audio_q_fr.put_nowait(raw)
    if not audio_q_en.full(): audio_q_en.put_nowait(raw)

    arr = np.frombuffer(raw, dtype=np.int16)
    with verify_lock:
        verify_buf.extend(arr.tolist())

    rms = float(np.sqrt(np.mean(arr.astype(np.float32)**2))) if arr.size > 0 else 0.0
    volume_buf.append((time.time(), min(rms, 8000)))

# ─── Détection mot-clé ────────────────────────────────────────
def detect_command(text):
    for kw in GO_KEYWORDS:
        if kw in text: return "go"
    for kw in BACK_KEYWORDS:
        if kw in text: return "back"
    for kw in STOP_KEYWORDS:
        if kw in text: return "stop"
    return None

def process_text(text, lang, partial=False):
    if not text: return
    tag = f"[{lang}{'~' if partial else ''}]"
    cmd = detect_command(text)
    if not cmd: 
        if not partial:
            print(f'🎙 {tag} "{text}" (non reconnu)')
            cmd_log.append((time.time(), f"{tag} {text}", None))
        return

    # ── Vérification identité vocale ──────────────────────────
    authorized, score = is_authorized_speaker()
    score_str = f"{score:.2f}"

    if authorized:
        write_command(cmd)
        print(f"✅ {tag} \"{text}\" → {cmd.upper()}  (score={score_str})")
        cmd_log.append((time.time(), f"✅{tag} {text}", cmd))
    else:
        print(f"🚫 {tag} \"{text}\" REFUSÉ — voix non autorisée (score={score_str} < {SIMILARITY_THRESHOLD})")
        cmd_log.append((time.time(), f"🚫{tag} {text}", None))

# ─── Thread Vosk ──────────────────────────────────────────────
def recognition_thread(model_path, audio_queue, lang):
    try:
        print(f"⏳ Chargement modèle {lang}...")
        model = Model(model_path)
        rec   = KaldiRecognizer(model, SAMPLE_RATE)
        print(f"✅ Modèle {lang} prêt")
    except Exception as e:
        print(f"❌ Modèle {lang} introuvable dans '{model_path}' : {e}")
        return

    while True:
        data = audio_queue.get()
        if rec.AcceptWaveform(data):
            text = json.loads(rec.Result()).get("text", "").lower().strip()
            process_text(text, lang, partial=False)
        else:
            partial = json.loads(rec.PartialResult()).get("partial", "").lower().strip()
            process_text(partial, lang, partial=True)

# ─── Dashboard matplotlib ─────────────────────────────────────
def run_dashboard():
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(14, 8), facecolor="#0a0a0f")
    fig.canvas.manager.set_window_title("mBot — Contrôle Vocal Sécurisé")
    gs = gridspec.GridSpec(4, 3, figure=fig,
                           hspace=0.65, wspace=0.4,
                           left=0.06, right=0.97,
                           top=0.93, bottom=0.07)

    C_PANEL = "#141420"; C_VOL = "#40c4ff"
    C_GRID  = "#1e1e2e"; C_TEXT = "#9e9ebc"

    def style_ax(ax, title):
        ax.set_facecolor(C_PANEL)
        ax.set_title(title, color=C_TEXT, fontsize=9, pad=7, fontfamily="monospace")
        ax.tick_params(colors="#444466", labelsize=7)
        for s in ax.spines.values(): s.set_edgecolor(C_GRID)

    # ── Volume ────────────────────────────────────────────────
    ax_v = fig.add_subplot(gs[0, :])
    style_ax(ax_v, "▌ VOLUME MICRO")
    ax_v.set_ylabel("RMS", color=C_TEXT, fontsize=8)
    ax_v.set_xlim(0, 60); ax_v.set_ylim(0, 8000)
    ax_v.yaxis.grid(True, color=C_GRID, lw=0.5)
    vol_fill_ref = [ax_v.fill_between([], [], alpha=0.2, color=C_VOL)]
    vol_line, = ax_v.plot([], [], color=C_VOL, lw=1.2)

    # ── État robot ────────────────────────────────────────────
    ax_s = fig.add_subplot(gs[1:3, 1])
    ax_s.set_facecolor(C_PANEL)
    ax_s.set_title("▌ ÉTAT ROBOT", color=C_TEXT, fontsize=9, pad=7,
                   fontfamily="monospace")
    ax_s.set_xlim(0, 1); ax_s.set_ylim(0, 1); ax_s.axis("off")
    circle = plt.Circle((0.5, 0.58), 0.28, color=CMD_COLORS["stop"], zorder=2)
    halo   = plt.Circle((0.5, 0.58), 0.33, color=CMD_COLORS["stop"], alpha=0.12, zorder=1)
    ax_s.add_patch(circle); ax_s.add_patch(halo)
    s_txt = ax_s.text(0.5, 0.59, "STOP", ha="center", va="center",
                      fontsize=18, fontweight="bold", color="white",
                      fontfamily="monospace", zorder=3)
    s_sub = ax_s.text(0.5, 0.22, "", ha="center", fontsize=7,
                      color="#666688", fontfamily="monospace")
    ax_s.text(0.5, 0.93, "FR + EN", ha="center", fontsize=7.5,
              color="#ffcc00", fontfamily="monospace",
              bbox=dict(boxstyle="round,pad=0.3", facecolor="#222233",
                        edgecolor="#ffcc00", linewidth=0.8))

    # ── Vérification vocale (badge) ───────────────────────────
    speaker_badge = ax_s.text(0.5, 0.08, "● En écoute...", ha="center",
                              fontsize=8, fontfamily="monospace", color="#888899")

    # ── Commandes dispo ───────────────────────────────────────
    ax_cmds = fig.add_subplot(gs[1, 0])
    style_ax(ax_cmds, "▌ COMMANDES")
    ax_cmds.axis("off")
    ax_cmds.text(0.05, 0.95,
        "▶  AVANT\n   go · avance · avant\n   start · forward\n\n"
        "◀  ARRIÈRE\n   arrière · recule · back\n   backward · reculer\n\n"
        "■  STOP\n   stop · arrête · arrêt\n   halt · stoppe",
        transform=ax_cmds.transAxes, va="top", ha="left",
        fontsize=7.5, color="#ccccdd", fontfamily="monospace", linespacing=1.6)

    # ── Log vocal ─────────────────────────────────────────────
    ax_l = fig.add_subplot(gs[1, 2])
    style_ax(ax_l, "▌ LOG VOCAL")
    ax_l.axis("off")
    log_txt = ax_l.text(0.04, 0.97, "", transform=ax_l.transAxes,
                        va="top", ha="left", fontsize=7.5,
                        color="#ccccdd", fontfamily="monospace", linespacing=1.7)

    # ── Score similarité (jauge) ──────────────────────────────
    ax_score = fig.add_subplot(gs[2, 0])
    style_ax(ax_score, "▌ SCORE VOIX")
    ax_score.set_xlim(0, 1); ax_score.set_ylim(0, 1); ax_score.axis("off")
    # Fond barre
    ax_score.add_patch(plt.Rectangle((0.05, 0.35), 0.9, 0.25,
                                      color="#1e1e2e", zorder=1))
    # Seuil
    ax_score.axvline(x=0.05 + SIMILARITY_THRESHOLD * 0.9,
                     ymin=0.32, ymax=0.65, color="#ffcc00",
                     lw=1.5, ls="--", zorder=3)
    score_bar = ax_score.add_patch(
        plt.Rectangle((0.05, 0.35), 0.0, 0.25, color="#888899", zorder=2))
    score_pct = ax_score.text(0.5, 0.72, "—", ha="center", fontsize=11,
                               fontfamily="monospace", color="white")
    score_lbl = ax_score.text(0.5, 0.15, "En attente...", ha="center",
                               fontsize=8, fontfamily="monospace", color="#666688")
    ax_score.text(0.05 + SIMILARITY_THRESHOLD * 0.9, 0.68,
                  f"seuil\n{SIMILARITY_THRESHOLD:.2f}", ha="center",
                  fontsize=6.5, color="#ffcc00", fontfamily="monospace")

    # ── Compteurs ─────────────────────────────────────────────
    ax_cnt = fig.add_subplot(gs[2, 2])
    style_ax(ax_cnt, "▌ COMPTEURS")
    ax_cnt.axis("off")
    cnt = {"go": 0, "back": 0, "stop": 0, "refused": 0}
    cnt_txt = ax_cnt.text(0.5, 0.6, "", ha="center", va="center",
                          fontsize=11, fontfamily="monospace", color="white",
                          linespacing=2.0)

    # ── Timeline ──────────────────────────────────────────────
    ax_t = fig.add_subplot(gs[3, :])
    style_ax(ax_t, "▌ TIMELINE (60s)")
    ax_t.set_ylim(-0.5, 2.5)
    ax_t.set_yticks([0, 1, 2])
    ax_t.set_yticklabels(["STOP", "ARRIÈRE", "AVANT"],
                         color=C_TEXT, fontsize=8, fontfamily="monospace")
    ax_t.set_xlabel("secondes", color=C_TEXT, fontsize=7)
    ax_t.set_xlim(0, 60)
    ax_t.yaxis.grid(True, color=C_GRID, lw=0.5)
    tl_line, = ax_t.step([], [], where="post", lw=2.5, color=CMD_COLORS["stop"])
    ax_t.legend(
        handles=[mpatches.Patch(color=CMD_COLORS["go"],   label="AVANT"),
                 mpatches.Patch(color=CMD_COLORS["back"], label="ARRIÈRE"),
                 mpatches.Patch(color=CMD_COLORS["stop"], label="STOP")],
        fontsize=8, facecolor=C_PANEL, edgecolor=C_GRID,
        labelcolor="white", loc="upper right"
    )

    timeline = deque(maxlen=1200)
    prev_cmd = [None]
    start_t  = time.time()

    def update(_):
        now     = time.time()
        elapsed = now - start_t

        # Volume
        if volume_buf:
            vd   = list(volume_buf)
            t0   = vd[0][0]
            vx   = [v[0] - t0 for v in vd]
            vy   = [v[1] for v in vd]
            win  = max(0, vx[-1] - 60)
            vx_c = [x - win for x in vx if x >= win]
            vy_c = vy[-len(vx_c):]
            vol_line.set_data(vx_c, vy_c)
            vol_fill_ref[0].remove()
            vol_fill_ref[0] = ax_v.fill_between(vx_c, vy_c, alpha=0.18, color=C_VOL)
            ax_v.set_ylim(0, max(2000, max(vy_c, default=500) * 1.25))

        # État robot
        with state_lock:
            cmd  = state["cmd"]
            age  = now - state["ts"]
            sc   = speaker_info["score"]
            auth = speaker_info["authorized"]
            chk  = speaker_info["checked"]

        timeout = age > COMMAND_TIMEOUT
        cmd_disp = "stop" if timeout else cmd
        col  = "#444466" if timeout else CMD_COLORS.get(cmd, CMD_COLORS["stop"])
        lbl  = CMD_LABELS.get(cmd_disp, "■  STOP")

        circle.set_color(col); halo.set_color(col)
        s_txt.set_text(lbl.split()[-1])
        s_sub.set_text(f"{'timeout' if timeout else cmd} · {age:.1f}s")
        s_sub.set_color(col)

        # Badge speaker
        if chk:
            if auth:
                speaker_badge.set_text(f"✅ Voix autorisée  ({sc:.2f})")
                speaker_badge.set_color("#00e676")
            else:
                speaker_badge.set_text(f"🚫 Voix refusée  ({sc:.2f})")
                speaker_badge.set_color("#ff1744")
        else:
            speaker_badge.set_text("● En écoute...")
            speaker_badge.set_color("#888899")

        # Jauge score
        if chk:
            bar_w = min(sc, 1.0) * 0.9
            score_bar.set_width(bar_w)
            bar_col = "#00e676" if auth else "#ff1744"
            score_bar.set_color(bar_col)
            score_pct.set_text(f"{sc:.2f}")
            score_pct.set_color(bar_col)
            score_lbl.set_text("AUTORISÉ ✅" if auth else "REFUSÉ 🚫")
            score_lbl.set_color(bar_col)

        # Compteurs
        if cmd != prev_cmd[0] and not timeout:
            if cmd in cnt: cnt[cmd] += 1
            prev_cmd[0] = cmd
        refused = sum(1 for _, _, c in cmd_log if c is None)
        cnt_txt.set_text(
            f"▶  AVANT    {cnt['go']:>3}\n"
            f"◀  ARRIÈRE  {cnt['back']:>3}\n"
            f"■  STOP     {cnt['stop']:>3}\n"
            f"🚫 REFUS    {refused:>3}"
        )

        # Timeline
        val = CMD_VAL.get(cmd_disp, 0)
        timeline.append((elapsed, val))
        if timeline:
            td   = list(timeline)
            tx   = [d[0] for d in td]
            ty   = [d[1] for d in td]
            win  = max(0, tx[-1] - 60)
            tx_c = [x - win for x in tx if x >= win]
            ty_c = ty[-len(tx_c):]
            tl_line.set_data(tx_c, ty_c)
            tl_line.set_color(CMD_COLORS.get(cmd_disp, CMD_COLORS["stop"]))

        # Log
        if cmd_log:
            lines = []
            for ts, txt_r, c in list(cmd_log)[-8:]:
                a   = now - ts
                ico = "▶" if c=="go" else ("◀" if c=="back" else ("■" if c=="stop" else "🚫"))
                lines.append(f'{ico} {a:5.1f}s "{txt_r}"')
            log_txt.set_text("\n".join(reversed(lines)))

        fig.canvas.draw_idle()

    ani = FuncAnimation(fig, update, interval=100, cache_frame_data=False)
    plt.show()

# ─── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    if not VOSK_OK:
        print("pip install vosk sounddevice matplotlib numpy"); exit(1)

    speaker_ok = load_speaker_model()
    if not speaker_ok:
        print("\n⚠ Vérification vocale désactivée — toutes les voix seront acceptées.")
        print("  Lancez enregistrer_voix.py pour activer la sécurité.\n")
        time.sleep(2)

    import sounddevice as sd
    print("\nMicros disponibles :")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            ext = " ← externe?" if any(
                k in d["name"].lower()
                for k in ["usb","headset","casque","external","blue","rode","hyperx"]
            ) else ""
            print(f"  [{i}] {d['name']}{ext}")

    print(f"\nMicro : {DEVICE_INDEX if DEVICE_INDEX is not None else 'défaut'}")
    print(f"Seuil similarité : {SIMILARITY_THRESHOLD}")
    print(f"AVANT   → {GO_KEYWORDS}")
    print(f"ARRIÈRE → {BACK_KEYWORDS}")
    print(f"STOP    → {STOP_KEYWORDS}\n")

    t_fr = threading.Thread(target=recognition_thread,
                            args=(MODEL_PATH_FR, audio_q_fr, "FR"), daemon=True)
    t_en = threading.Thread(target=recognition_thread,
                            args=(MODEL_PATH_EN, audio_q_en, "EN"), daemon=True)
    t_fr.start(); t_en.start()

    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                           device=DEVICE_INDEX, dtype="int16",
                           channels=1, callback=audio_callback):
        run_dashboard()