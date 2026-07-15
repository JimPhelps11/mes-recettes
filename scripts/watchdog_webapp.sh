#!/usr/bin/env bash
# Watchdog pour le serveur web des recettes
# Vérifie toutes les 2 minutes si le serveur tourne, sinon le lance
PORT=8000
RECETTES_DIR="/opt/data/home/recettes"

if ! curl -sf --max-time 3 http://127.0.0.1:$PORT/api/recettes > /dev/null 2>&1; then
  echo "[$(date)] Serveur web des recettes down — redémarrage..."
  cd "$RECETTES_DIR"
  nohup "$RECETTES_DIR/.venv/bin/python3" webapp.py > "$RECETTES_DIR/webapp.log" 2>&1 &
  disown
  echo "[$(date)] Lancement effectué (PID $!)"
  # Vérification après 4 secondes (le temps que Flask boote)
  sleep 4
  if curl -sf --max-time 3 http://127.0.0.1:$PORT/api/recettes > /dev/null 2>&1; then
    echo "[$(date)] ✅ Serveur OK"
  else
    echo "[$(date)] ❌ Échec du démarrage — voir $RECETTES_DIR/webapp.log"
  fi
else
  echo "[$(date)] ✅ Serveur OK"
fi