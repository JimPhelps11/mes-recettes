# 🧑‍🍳 Mes Recettes

Application web personnelle de gestion de recettes de cuisine + calcul nutritionnel (Ciqual ANSES 2025).

![Static Badge](https://img.shields.io/badge/python-3.13-green?logo=python&logoColor=white)
![Static Badge](https://img.shields.io/badge/flask-lightgrey?logo=flask&logoColor=white)
![Static Badge](https://img.shields.io/badge/sqlite3-lightgrey?logo=sqlite&logoColor=white)

---

## 📦 Installation rapide

```bash
# 1. Cloner le dépôt
cd /opt/data/home/GitHub
git clone https://github.com/JimPhelps11/mes-recettes.git
cd mes-recettes

# 2. Créer le venv de l'application (¬ de dépendances système)
/opt/data/home/.venv/bin/python3 -m venv .venv 2>/dev/null || uv venv .venv

# 3. Activer le venv et installer dépendances
source .venv/bin/activate
# Option A: uv pip install flask gtts python-dotenv pillow requests || pip install -r requirements.txt
# Option B (rapide) :
uv pip install flask gtts python-dotenv pillow requests

# 4. Importer la base Ciqual 2025 (si base nutrition.db absent)
# Vous devez avoir le fichier xlsx d'origine Ciqual 2025 disponible localement
# puis dans la repo:
# python3 base_nutrition.py init
# python3 base_nutrition.py aligner

# 5. Démarrer l'application
./start.sh

# → Serveur disponible sur
# http://127.0.0.1:8000
# http://192.168.1.137:8000 (sur le Pi)
```

## 🚀 Démarrage & supervision

### Lancement
```bash
./start.sh  # ou `.venv/bin/python3 webapp.py` directement
```
Le script démarrera sur port 8000, en écoute sur 0.0.0.0 (réseau local).

### Redémarrage/debug (à la main)
```bash
pkill -f webapp.py || true
./start.sh > /tmp/webapp.log 2>&1 &
disown
```

### Supervision automatique (cron)
Un watchdog Hermès (fichier `scripts/watchdog_recettes.sh` dans la repo) vérifie toutes les 2 minutes le port 8000 et relance automatiquement si le serveur n'est pas joignable.

Vérification manuelle :
```bash
curl -s http://127.0.0.1:8000/api/recettes | head -c 100
```

## 📁 Structure du projet

```
mes-recettes/
├── CAHIER_DES_CHARGES.md     # Spécifications produit
├── README.md                # Ce fichier
├── start.sh                 # Script de démarrage canonique
├── webapp.py                # Serveur Flask (monolithique)
├── base_nutrition.py       # Base de données nutrition Ciqual 2025
├── recherche_ingredients.py # CLI de recherche nutritionnelle (stub)
├── mes-recettes.service    # fichier systemd (placer dans /etc/systemd/system/)
├── scripts/
│   └── watchdog_recettes.sh # Script Hermès (cron)
└── .gitignore
```

## 🧮 Serveurs

- **Local** : `http://127.0.0.1:8000`
- **Réseau Pi** : `http://192.168.1.137:8000`

## 🔧 Configuration

- **Port** : 8000 (modifiable dans `start.sh` et `webapp.py`)
- **Base** : `nutrition.db` (autogénérée à partir de `ciqual_2025.xlsx` via `base_nutrition.py init`)
- **Déploiement** : Sur Raspberry Pi 48h/7, ou machine Linux personnelle.

## 📚 Documentation produit

Le fichier `CAHIER_DES_CHARGES.md` détaille :

- Les 9 fonctionnalités centrales (CRUD recettes, menus, frigo, Ciqual explorer, vision IA, TTS, favori/tags, planning, recherche nutritionnelle)
- Spécifications techniques : Flask monolithique, SPA vanilla JS, base Ciqual 3484 aliments
- Savoir critique : en cas de corruption, restaurer `base_nutrition.py` depuis `ciqual-fr.md` et la sauvegarde `/opt/data/recettes-sauvegarde-20260709_*.tar.gz`.

## ⚠️ Problèmes connus & dépannage

### Erreur "ImportError: No module named 'flask'"
→ Vérifie que tu utilises **le venv local de la repo** : `.venv/bin/python3` ou `source .venv/bin/activate`.
Ne pas utiliser `/opt/data/home/.venv` qui ne contient pas les bonnes libs.

### `/api/recettes` bloque ou connexion refusée
→ Voir que :
1. `./start.sh` tourne (`ps aux | grep webapp.py`).
2. Le watchdog est activé (`cron list | grep watchdog`).
3. Aucun autre process n’écoute sur 8000 (`ss -tlnp | grep 8000`).

> Cas extrême : `base_nutrition.py` a été écrasé → restaurer depuis sauvegarde ou le stub auto-boucle.

## 🐛 Historique des incidents
- 15/07/2026 : restauration indispensable après corruption: `base_nutrition.py` auto-bouclé (`subprocess` → récursif) → crash toutes imports → l’app ne démarrait plus. Sauvegarde récupérée depuis `/opt/data/recettes-sauvegarde-20260709_1547.tar.gz`.

## 🛠️ Roadmap produit

- [ ] Ajouter une migration facile pour mise à jour fields Ciqual 2028
- [ ] Tests automatisés basiques (pytest)
- [ ] Dockerisation complète (image ~150MB)
- [ ] UI avancée : filtres par temps, tags intelligents, scoring équilibre
- [ ] Sauvegarde cloud optionnelle (GitHub releases assets auto)

---

🌐 [Consulter le cahier des charges complet](./CAHIER_DES_CHARGES.md)
📅 Dernière mise à jour : 15 juillet 2026
👤 Auteur : JimPhelps

