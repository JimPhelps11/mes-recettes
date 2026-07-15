#!/bin/bash
# Script de lancement canonique — Mes Recettes
# Usage: bash start.sh
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"

# Charge la clé Gemini/Mistral si présente dans .env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs -d '\n' 2>/dev/null || true)
fi

exec .venv/bin/python3 webapp.py
