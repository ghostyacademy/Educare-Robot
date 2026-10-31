# 👁️ EOG mBot Controller

<div align="center">

**Contrôlez un robot mBot 1 par vos seuls mouvements oculaires**

[![Arduino](https://img.shields.io/badge/Arduino-Uno%20R3-00979D?style=flat-square&logo=arduino&logoColor=white)](https://www.arduino.cc/)
[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Educare-Robot](https://img.shields.io/badge/Projet-Educare--Robot%202025-0D8FBF?style=flat-square)](https://github.com/ghostyacademy/Educare-Robot)

*Une interface humain-machine basée sur l'électro-oculographie (EOG)*

</div>

---

## 🧠 Principe

Des électrodes placées autour des yeux captent les **courants électriques** générés par les mouvements oculaires. Ces signaux sont amplifiés par le **BioAMP EXG Pill**, analysés en temps réel par l'**Arduino Uno R3**, puis traduits en commandes moteur pour piloter un **mBot 1**.

```
Yeux  →  Électrodes EOG  →  Arduino  →  Python Bridge  →  mBot 1
         (signal µV)        (100 Hz)    (fichier IPC)    (moteurs)
```

| Geste oculaire | Commande | Action |
|:---:|:---:|:---:|
| ▲ Regard vers le **HAUT** | `go` | Moteurs en avant — vitesse 150 |
| ▼ Regard vers le **BAS** | `stop` | Moteurs arrêtés |
| ◉ **Clignement** volontaire | `toggle` | Bascule GO/STOP *(optionnel)* |

---

## 🔧 Matériel requis

| Composant | Modèle | Qté | Notes |
|---|---|:---:|---|
| Microcontrôleur | Arduino Uno R3 | 1 | Tout clone 5V compatible |
| Capteur EOG | BioAMP EXG Pill — Upside Down Labs | 1 | Fournit A0 (vertical) et A1 (horizontal) |
| Électrodes | Ag/AgCl jetables | 4 | Qualité médicale recommandée |
| Câbles | Snap-to-pin | 3 | Vertical, horizontal, référence |
| Robot | mBot 1 — Makeblock | 1 | Connexion **USB obligatoire** (pas Bluetooth) |
| PC | Windows 10 / 11 | 1 | Deux ports USB disponibles |

---

## 🗂️ Structure du projet

```
eog-controller/
├── eog_arduino/
│   └── eog_arduino.ino      # Sketch Arduino — lecture EOG & détection des gestes
├── serial-read-eog.py       # Pont Arduino → fichier commande (+ mode calibration)
├── serial-read-alpha.py     # Variante expérimentale : ondes alpha EEG (8–12 Hz)
├── mbot-motor-control.py    # Fichier commande → paquets moteur mBot (+ watchdog)
├── _run_eog_reader.bat      # Lanceur Windows du lecteur EOG
├── _run_robot_ctrl.bat      # Lanceur Windows du contrôleur mBot
└── motor_command.txt        # Généré à l'exécution (IPC) — non versionné
```

---

## ⚙️ Installation

### Prérequis logiciels

| Logiciel | Version minimale |
|---|---|
| Python | ≥ 3.9 |
| Arduino IDE | ≥ 2.0 |

### Installation des dépendances Python

```bash
pip install -r requirements.txt
```

### Cloner le dépôt

```bash
git clone https://github.com/ghostyacademy/Educare-Robot.git
cd Educare-Robot
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## 🔌 Placement des électrodes

```
Canal A0 — axe VERTICAL (Haut / Bas)
  +  →  Front, directement au-dessus de l'œil droit   →  broche A0+
  −  →  Pommette, sous le même œil                    →  broche A0−

Canal A1 — axe HORIZONTAL (Gauche / Droite)
  +  →  Canthus externe de l'œil gauche               →  broche A1+
  −  →  Canthus externe de l'œil droit                →  broche A1−

REF →  Lobe d'oreille (masse commune)
```

> **⚠️ Conseil :** Nettoyez la peau avec un coton alcoolisé avant de poser les électrodes. Un mauvais contact est la cause n°1 des faux positifs.

---

## 📡 Identifier les ports COM

Ouvrez le **Gestionnaire de périphériques** Windows → **Ports (COM & LPT)** :

- Arduino + BioAMP → ex. `COM16`
- mBot 1 via USB → ex. `COM15`

> Ces numéros varient d'un PC à l'autre. Passez-les en argument aux scripts (voir [Utilisation](#-utilisation)) — inutile de modifier le code.

---

## 🎯 Calibration

La calibration mesure votre valeur de repos et identifie les seuils optimaux.

```bash
# 1. Uploadez le sketch avec CALIBRATE_MODE true dans l'IDE Arduino

# 2. Lancez la calibration
python serial-read-eog.py COM16 --calibrate

# 3. Bougez les yeux haut / bas / gauche / droite pendant 30 secondes
# 4. Notez les seuils recommandés (UP_THRESH…)
# 5. Mettez à jour UP_THRESH / DOWN_THRESH dans eog_arduino/eog_arduino.ino
# 6. Remettez CALIBRATE_MODE false et ré-uploadez
```

> La baseline (valeur de repos) est mesurée automatiquement au démarrage de l'Arduino (50 échantillons) puis ajustée en continu. **Gardez le regard droit devant pendant la première demi-seconde** après le reset.

### Paramètres Arduino

| Paramètre | Défaut | Description |
|---|:---:|---|
| `UP_THRESH` | 90 | Déviation minimale pour valider "Haut" |
| `DOWN_THRESH` | 90 | Déviation minimale pour valider "Bas" |
| `CONFIRM_SAMPLES` | 5 | Échantillons consécutifs requis avant émission |
| `GESTURE_COOLDOWN_MS` | 800 | Délai minimum entre deux gestes (ms) |
| `BASELINE_ALPHA` | 0.002 | Vitesse d'adaptation automatique de la baseline |

---

## 🚀 Utilisation

Ouvrez **deux terminaux séparés** dans le dossier `eog-controller/` :

**Terminal 1 — Contrôleur mBot (lancer en premier)**

```bash
cd eog-controller
python mbot-motor-control.py COM15
# → Connecte au mBot sur COM15
```

**Terminal 2 — Lecteur EOG (lancer en second)**

```bash
python serial-read-eog.py COM16
# → Connecte a COM16 a 115200 baud
```

Sous Windows, vous pouvez aussi double-cliquer sur `_run_robot_ctrl.bat` puis `_run_eog_reader.bat`, ou les lancer avec le port en argument : `_run_robot_ctrl.bat COM15`.

### 🛡️ Sécurité — watchdog

Le lecteur EOG réécrit `motor_command.txt` toutes les 200 ms (heartbeat). Si le contrôleur ne reçoit plus de heartbeat pendant **1 seconde** (lecteur planté, Arduino débranché, fenêtre fermée…), il **arrête le mBot**.

Après un arrêt watchdog, le robot ne repart pas tout seul : regardez **en BAS** puis **en HAUT** pour relancer.

---

## 🔄 Flux de données complet

```
[1] BioAMP EXG Pill
    └─ Amplifie le potentiel oculaire EOG sur A0 (vertical) et A1 (horizontal)

[2] Arduino Uno R3
    └─ Lit A0/A1 à 100 Hz
    └─ Calcule la déviation par rapport à la baseline dynamique
    └─ Valide après 5 échantillons consécutifs

[3] serial-read-eog.py
    └─ Reçoit "Up" ou "Down"
    └─ Écrit "go" ou "stop" (+ timestamp) dans motor_command.txt
    └─ Réécrit le fichier toutes les 200 ms (heartbeat)

[4] mbot-motor-control.py
    └─ Interroge motor_command.txt à 20 Hz
    └─ Envoie le paquet Makeblock via USB dès un changement détecté
    └─ Arrête le robot si le timestamp a plus d'1 s (watchdog)

[5] mBot 1
    └─ Exécute l'ordre moteur : ports 0x09 (gauche) et 0x0A (droit), vitesse ±150
```

---

## ⚙️ Paramètres avancés

### Régler la sensibilité

```cpp
// Plus réactif
#define CONFIRM_SAMPLES      3
#define GESTURE_COOLDOWN_MS  400

// Moins de faux positifs
#define CONFIRM_SAMPLES      8
#define UP_THRESH           120
#define DOWN_THRESH         120
```

### Activer le contrôle par clignement

Dans `serial-read-eog.py` :

```python
BLINK_TOGGLE = True   # Un clignement lent bascule GO ↔ STOP
```

### Ajuster la vitesse du robot

Dans `mbot-motor-control.py` (valeur entre 0 et 255) :

```python
SPEED = 200   # Augmenter pour aller plus vite
```

---

## 🛠️ Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| Faux gestes en continu | Seuils trop bas ou électrodes mal posées | Augmentez `UP/DOWN_THRESH`. Nettoyez la peau et relancez la calibration. |
| "Up" jamais détecté | Électrodes inversées ou baseline faussée au démarrage | Vérifiez la polarité A0+/A0−. Resettez l'Arduino en regardant droit devant. |
| Une seule roue tourne | Paquets moteur trop rapprochés | Vérifiez le délai 20 ms dans `run_motor()`. Augmentez la vitesse à 200. |
| mBot ne répond pas | Mauvais port COM ou IDE Arduino ouvert | Vérifiez COM15. Fermez l'IDE Arduino (libère le port). |
| `WATCHDOG → pas de heartbeat` | Lecteur EOG arrêté ou Arduino muet | Vérifiez que `serial-read-eog.py` tourne et que l'Arduino est branché. Les deux scripts doivent être dans le même dossier. |
| `ModuleNotFoundError` ou `serial.Serial` introuvable | Le paquet `serial` (différent de `pyserial`) est installé | `pip uninstall serial` puis `pip install pyserial`. |
| Signal fixe V=512 | BioAMP mal alimenté ou électrodes débranchées | Vérifiez l'alimentation 3.3V/5V du BioAMP et toutes les connexions. |

---

## 📦 Dépendances & licences

| Composant | Auteur / Organisation | Licence |
|---|---|---|
| BioAMP EXG Pill | Upside Down Labs | MIT License |
| mBot 1 | Makeblock Co., Ltd. | Propriétaire |
| pyserial | Chris Liechti | BSD License |
| numpy | NumPy Developers | BSD License |
| matplotlib | Matplotlib Developers | BSD License |
| scipy | SciPy Developers | BSD License |
| Arduino IDE | Arduino LLC | GPL v2 |

---

## 📄 Licence

Ce projet est distribué sous licence **MIT**. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

---

<div align="center">

*Projet Educare-Robot — 2025*

</div>
