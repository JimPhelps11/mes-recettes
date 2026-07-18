#!/bin/bash
# Script de lancement canonique — Mes Recettes
# Usage: bash start.sh
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"

# Charge la clé Gemini/Mistral si présente dans .env (gère les commentaires en fin de ligne)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

exec .venv/bin/python3 webapp.py
