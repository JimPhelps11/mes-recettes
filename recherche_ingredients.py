#!/usr/bin/env python3
"""Recherche de recettes par ingrédients — utilisable directement depuis le terminal.
Usage : python3 scripts/recherche_ingredients.py <ingrédient1> [ingrédient2] ...
Voir le README de la skill recipe-management pour plus de détails."""
# Le vrai fichier est /opt/data/home/recettes/recherche_ingredients.py
# Ceci est un pointeur — l'agent doit exécuter le fichier dans recettes/
import sys
import subprocess
RECETTES_DIR = "/opt/data/home/recettes"
sys.exit(subprocess.call([sys.executable, f"{RECETTES_DIR}/recherche_ingredients.py"] + sys.argv[1:]))