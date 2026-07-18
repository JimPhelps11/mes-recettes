#!/usr/bin/env python3
"""Exporte le planning hebdomadaire sauvegardé et le délivre sur Telegram."""

import sys
import os
import json
from datetime import datetime, timedelta

sys.path.insert(0, '/opt/data/home/recettes')
from base_nutrition import RECETTES_DIR

PLANNING_FILE = RECETTES_DIR / 'planning_semaine.json'
JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
SLOT_ICONS = {'petit-dejeuner': '🌅', 'dejeuner': '☀️', 'diner': '🌙', 'collation': '🍪'}
SLOT_LABELS = {'petit-dejeuner': 'Petit-déjeuner', 'dejeuner': 'Déjeuner', 'diner': 'Dîner', 'collation': 'Collation'}

if not PLANNING_FILE.exists():
    print("📅 Aucun planning sauvegardé.")
    sys.exit(0)

data = json.loads(PLANNING_FILE.read_text(encoding='utf-8'))

# Génère le texte d'export
semaine = datetime.now().strftime('%d/%m/%Y')
texte = f"📅 PLANNING HEBDOMADAIRE — semaine du {semaine}\n"
texte += "═" * 40 + "\n\n"

total_actif = 0
total_minutes = 0

for jour in JOURS:
    entries = {k: v for k, v in data.get(jour, {}).items() if isinstance(v, list)}
    a_qch = any(len(v) > 0 for v in entries.values())
    if not a_qch:
        continue

    texte += f"📆 {jour.capitalize()}\n"
    texte += "─" * 30 + "\n"

    for repas in ['petit-dejeuner', 'dejeuner', 'diner', 'collation']:
        items = entries.get(repas, [])
        icone = SLOT_ICONS.get(repas, '🍽️')
        label = SLOT_LABELS.get(repas, repas)
        if not items:
            texte += f"  {icone} {label} : —\n"
        else:
            noms = []
            for i in items:
                if i.get('type') == 'recette':
                    noms.append(i.get('titre', '?'))
                else:
                    noms.append(f"🧊 {i.get('nom', '?')} ({i.get('qte', 1)})")
            texte += f"  {icone} {label} : {' + '.join(noms)}\n"

    # Activité
    actif = data.get(jour, {}).get('activite', {})
    if actif.get('fait'):
        duree = actif.get('duree', 30)
        total_actif += 1
        total_minutes += duree
        texte += f"  🏃 Activité : ✅ {duree} min\n"
    texte += "\n"

if total_actif > 0:
    texte += "═" * 40 + "\n"
    texte += f"🏃 Activité : {total_actif} jour(s) — {total_minutes} min total\n\n"

texte += "═" * 40 + "\n"
texte += "📝 Bon appétit et belle semaine ! 😊"

print(texte)