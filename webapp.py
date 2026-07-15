#!/usr/bin/env python3
"""🧑‍🍳 Mes Recettes — Serveur Web
Accessible sur http://192.168.1.137:8000
"""

import os
import sys
import sqlite3
import re
import json
from pathlib import Path
from datetime import datetime

# Chargement précoce du .env
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'), override=True)
except ImportError:
    pass  # Ignoré si python-dotenv pas installé (fallback environnement direct)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request, send_from_directory
from base_nutrition import (
    chercher_aliments, profil_aliment, profil_recette, aligner_recettes,
    parser_quantite, CHAMPS_AFFICHAGE, MAPPING_MANUEL, DB_PATH, RECETTES_DIR,
    est_aliment_brut, parse_frontmatter
)

app = Flask(__name__, template_folder=str(RECETTES_DIR / 'templates'))
UPLOAD_DIR = RECETTES_DIR / 'uploads'
PHOTOS_DIR = RECETTES_DIR / 'photos'
FAVORITES_FILE = RECETTES_DIR / 'favoris.json'

UPLOAD_DIR.mkdir(exist_ok=True)
PHOTOS_DIR.mkdir(exist_ok=True)

# ── Gemini Vision ──────────────────────────────────────────────────

def _load_env_vars(env_file: str = None) -> dict:
    """Charge les variables d'environnement depuis un fichier .env."""
    if not env_file:
        # Cherche dans le profil gastro par défaut
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'profiles', 'gastro', '.env'),
            os.path.join('/opt/data', 'profiles', 'gastro', '.env'),
        ]
        for c in candidates:
            if os.path.exists(c):
                env_file = c
                break
        if not env_file:
            return {}
    
    env_vars = {}
    try:
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env_vars[k.strip()] = v.strip()
    except Exception:
        pass
    return env_vars

# Les clés sont maintenant trouvées dans l'environnement système global
# l'ordre est : Variable d'env système > MISTRAL_API_KEY dans /opt/data/.profile > pas de .env spécifique

MISTRAL_ENV_KEY = os.environ.get('MISTRAL_API_KEY', '')
GEMINI_FALLBACK_KEY = os.environ.get('GEMINI_API_KEY') or os.environ.get('GEMINI_NUTRI_VISION', '')

# Mode proximal : utiliser Mistral direct si disponible, sinon OpenRouter fallback
USE_MISTRAL_DIRECT = bool(MISTRAL_ENV_KEY and MISTRAL_ENV_KEY.startswith('ks-'))
VISION_DEFAULT_KEY = MISTRAL_ENV_KEY or GEMINI_FALLBACK_KEY
def gemini_vision_analyse_image(image_bytes: bytes, api_key: str = None, mode: str = 'food') -> dict:
    """Analyse une image avec Mistral Vision (priorité) ou Gemini Vision.
    Retourne les ingrédients + quantités en grammes.
    """
    # Préfère l'API key passée, sinon utilise la clé par défaut
    if not api_key:
        api_key = VISION_DEFAULT_KEY
    
    if not api_key:
        return {'error': 'Aucune clé API configuée pour la vision (nécessite MISTRAL_API_KEY ou clés Gemini)'}
    
    import base64
    try:
        # Upscale l'image pour améliorer la reconnaissance (max 2048px)
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(image_bytes))
        if img.width > 2048 or img.height > 2048:
            img.thumbnail((2048, 2048), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=90)
            buf.seek(0)
            image_bytes = buf.read()
    except Exception:
        # Si erreur (pas de PIL), utilise l'image brute
        pass
    
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    # System prompt polyvalent pour les différents modes
    if mode == 'food':
        system_prompt = f"""Tu es un assistant nutritionniste expert. Analyse cette photo d'un plat dressé dans une assiette et retourne UN JSON avec la liste des ingrédients visibles et leurs quantités ESTIMÉES EN GRAMMES.

Consignes rigoureuses :
1. Pour LES LÉGUMES VERTS (haricots verts, brocoli, épinards, courgettes, courgette, concombre) : pense à 100–150g par portion moyenne.
2. Pour LES LÉGUMES-ROOTS/FRUITS (carottes, pommes de terre, betterave, patate douce, oignon) : ~120g par portion.
3. Pour LA VIANDE/FISH/POULTRY (poulet, bœuf, porc, poisson, saucisse, lardons, jambon) : 120–180g par portion.
4. Pour LES ŒUFS : une unité = ~50–60g.
5. Pour LE RIZ/QUINOA/PÂTES/FÉCULENTS cuits : ~150–180g cuits = 50–60g crus.
6. Pour LES FROMAGES : portion standard = ~30–50g.
7. Pour LES MATIÈRES GRASSES (huile, beurre, crème) : cuillère à soupe = ~15g. Une noix de beurre = ~10g.
8. Pour LES LÉGUMINEUSES cuites (lentilles, pois chiches, haricots rouges/marron) : portion = ~150g cuits.
9. Ignore les ingrédients non visibles.
10. Retourne EXACTEMENT ce JSON : {{ingrédients:[{{nom: '', quantite_g: 0, certitude: 'haute|moyenne|basse'}}], total_estime_g: X, description: '...', notes: '...'}}

Pays/portion : France/Europe.
"""
    elif mode == 'recipe':
        system_prompt = """Identifie les ingrédients dans cette photo d'une recette (ingrédients crus ou en préparation) et retourne un JSON avec les ingrédients et éventuellement les étapes visibles.
Json : {{ingredients:[{{nom, quantite_g, certitude}}], etapes: [], description, notes}}"""
    else:
        system_prompt = "Analyse l'image et retourne un JSON avec les éléments visibles."
    
    # Base de l'URL : détecte si c'est une URL Mistral ou un Payload OpenRouter
    if USE_MISTRAL_DIRECT and api_key.startswith('ks-') and len(api_key) > 15:
        # Méthode Mistral Pro API (vision) : POST /image/generate
        url = "https://api.mistral.ai/v1/image/generate"
        payload = {
            "model": "pixtral-12b-2409",
            "prompt": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": system_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.3,
            "max_tokens": 2048
        }
    else:
        # Méthode fallback : Gemini 2.0 Flash via OpenRouter fallback
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": system_prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64_image
                        }
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 2048,
            }
        }
    
    try:
        if USE_MISTRAL_DIRECT and api_key.startswith('ks-'):
            import requests
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            resp = requests.post(url, json=payload, timeout=30, headers=headers)
            result = resp.json()
            text = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        else:
            import urllib.request
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        
        # Parse le JSON de la réponse
        import re
        json_match = re.search(r'\{[\s\S]*"ingrédients"[\s\S]*\}', text, re.IGNORECASE)
        if not json_match:
            json_match = re.search(r'\{[\s\S]*"ingredients"[\s\S]*\}', text, re.IGNORECASE)
        
        if json_match:
            parsed = json.loads(json_match.group())
            parsed['source'] = 'mistral' if USE_MISTRAL_DIRECT else 'gemini'
            return parsed
        
        return {'raw': text, 'error': 'Impossible de parser le JSON retour'} 
    
    except Exception as e:
        return {'error': f'Analyse visuelle échouée : {str(e)[:100]}'}


# -- Remplacement des endpoints avec la nouvelle fonction --

@app.route('/api/vision/analyze', methods=['POST'])
def api_vision_analyze():
    """Appelle Mistral ou Gemini Vision selon disponibilité clé."""
    if 'image' not in request.files:
        return jsonify({'error': 'Aucune image fournie'}), 400
    fichier = request.files['image']
    if not fichier.filename:
        return jsonify({'error': 'Fichier vide'}), 400
    model = request.form.get('model', 'mistral')
    image_bytes = fichier.read()
    try:
        result = generate_requested_image_analysis(model, image_bytes)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Erreur: {str(e)[:100]}'})

@app.route('/api/vision/estimate_portion', methods=['POST'])
def api_vision_estimate_portion():
    """Endpoint web app : analyse et retourne portions/ingredients avec emojis."""
    if 'image' not in request.files:
        return jsonify({'error': 'Aucune image fournie'}), 400
    fichier = request.files['image']
    if not fichier.filename:
        return jsonify({'error': 'Fichier vide'}), 400
    image_bytes = fichier.read()

    result = generate_requested_image_analysis('mistral', image_bytes)

    ingredients = result.get('ingredients', [])
    retour = {
        'total_estime_g': result.get('total_estime_g', 0),
        'description': result.get('description', ''),
        'ingredient': [
            {
                'nom': ing.get('nom', ''),
                'quantite_g': ing.get('quantite_g', 0),
                'certitude': ing.get('certitude', 'moyenne')
            }
            for ing in ingredients
        ],
        'notes': result.get('notes', ''),
        'source': result.get('source', 'fallback'),
        'suggestions_recettes': []
    }
    return jsonify(retour)



def generate_requested_image_analysis(model_provider: str, image_bytes: bytes) -> dict:
    """
    Analyse une image avec le bon endpoint selon le provider.
    Retourne les ingrédients + quantités en grammes.
    """
    import base64
    import json
    model_provider = model_provider or os.environ.get('VISION_MODEL', 'mistral')

    try:
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(image_bytes))
        if img.width > 2048 or img.height > 2048:
            img.thumbnail((2048, 2048), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=90)
            buf.seek(0)
            image_bytes = buf.read()
    except Exception:
        pass  # Garde l'image brute si erreur

    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    API_KEY = os.environ.get('MISTRAL_API_KEY', '')
    if not API_KEY:
        API_KEY = os.environ.get('GEMINI_VISION_API_KEY', '')

    if model_provider == 'mistral' and API_KEY and API_KEY.startswith('ks-'):
        system_prompt = """Tu es un assistant nutritionniste expert analysant des photos de plats françaises.Listes les ingrédients ET leurs quantités en grammes avec certitude.Format JSON: {\"ingredients\":[{\"nom\":\"tomate\",\"quantite_g\":120,\"certitude\":\"haute\"}],\"total_estime_g\":X,\"description\":\"...\",\"notes\":\"...\"}"""
        url = "https://api.mistral.ai/v1/image/generate"
        payload = {
            "model": "pixtral-12b-2409",
            "prompt": system_prompt,
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": system_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]}
            ],
            "temperature": 0.3,
            "max_tokens": 2048
        }
        try:
            import requests
            headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
            r = requests.post(url, json=payload, headers=headers, timeout=30)
            text = r.json().get('choices', [{}])[0].get('message', {}).get('content', '')
        except Exception as e:
            return {'error': f'Mistral Vision: {str(e)[:100]}'}
    else:
        GOOGLE_KEY = API_KEY
        if GOOGLE_KEY:
            system_prompt = """Analyse cette photo d'un plat français et retourne un JSON minimal: {\"ingredients\":[{\"nom\":\"carottes râpées\",\"quantite_g\":90,\"certitude\":\"haute\"}], \"total_estime_g\":200, \"description\":\"assiette repas\", \"notes\":\"quantités estimées\"}"""
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_KEY}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": system_prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}
                    ]
                }],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024}
            }
            try:
                import urllib.request
                req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    text = json.loads(resp.read().decode())['candidates'][0]['content']['parts'][0]['text']
            except Exception as e:
                return {'error': f'Gemini Vision API: {str(e)[:100]}'}
        else:
            return {
                "ingredients": [
                    {"nom": "aubergines rôties", "quantite_g": 200, "certitude": "haute"},
                    {"nom": "fromage gratiné", "quantite_g": 45, "certitude": "moyenne"},
                    {"nom": "huile d'olive", "quantite_g": 6, "certitude": "basse"}
                ],
                "total_estime_g": 251,
                "description": "Plat méditerranéen : aubergines rôties et fromage fondu accompagnées d'huile d'olive sur assiette.",
                "notes": "Quantités estimées pour une portion adulte. Analyse locale pour l'interface.",
                "source": "simulé (pas de clé API valide)"
            }

    import re
    match = re.search(r'\{[\s\S]*[\"\'ingredients\"\][\s\S]*\}', text, re.IGNORECASE)
    if match:
        try:
            parsed = json.loads(match.group())
            parsed['source'] = 'mistral' if model_provider == 'mistral' and API_KEY.startswith('ks-') else 'gemini'
            return parsed
        except Exception:
            pass

    return {'error': 'Réponse Vision non interprétable'}

@app.route('/api/analyze_plate', methods=['POST'])
def api_analyze_plate():
    """Analyser l'assiette depuis une photo: ingrédients + quantités."""
    if 'image' not in request.files:
        return jsonify({'error': 'Aucune image fournie'}), 400
    fichier = request.files['image']
    if not fichier.filename:
        return jsonify({'error': 'Fichier vide'}), 400
    image_bytes = fichier.read()
    try:
        import re
        res = generate_requested_image_analysis('mistral', image_bytes)
        ingredients = res.get('ingredients', [])
        ingredient_names = [i.get('nom','').lower() for i in ingredients]
        recettes = []
        if ingredient_names:
            for r in allRecettes:
                titre = r.get('titre','').lower()
                if any(needle in titre for needle in ingredient_names):
                    recettes.append({
                        'fichier': r.get('fichier',''),
                        'titre': r.get('titre',''),
                        'kcal_100g': r.get('kcal_100g'),
                        'match_pct': r.get('match_pct', 0)
                    })
        recettes.sort(key=lambda x: x.get('kcal_100g', 0) or 9999)
        retour = {**res, 'suggestions_recettes': recettes[:6]}
        return jsonify(retour)
    except Exception as e:
        return jsonify({'error': f'Erreur: {str(e)[:100]}'}), 500


def lire_favoris():
    if FAVORITES_FILE.exists():
        return json.loads(FAVORITES_FILE.read_text())
    return []

def ecrire_favoris(favs):
    FAVORITES_FILE.write_text(json.dumps(favs, indent=2))


# ── Pages ─────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(str(RECETTES_DIR / 'static'), 'index.html')

@app.route('/vision-test')
def vision_test_page():
    """Affiche la page de test visuel intégré."""
    return send_from_directory(str(RECETTES_DIR / 'static'), 'vision-test.html')

@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory(str(RECETTES_DIR / 'static'), path)


# ── API Recettes ─────────────────────────────────────────────────

@app.route('/api/recettes')
def api_recettes():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT fichier, titre FROM recettes ORDER BY titre").fetchall()
    conn.close()

    recettes = []
    for r in rows:
        profil = profil_recette(r['fichier'])
        kcal = profil['total'].get('energie_kcal') if profil else None
        recettes.append({
            'fichier': r['fichier'].replace('.md', ''),
            'titre': r['titre'],
            'kcal_100g': round(kcal, 1) if kcal else None,
            'nb_ingredients': profil['nb_ingredients'] if profil else 0,
            'match_pct': profil['match_pct'] if profil else 0,
        })
    return jsonify(recettes)


# ── API Menu ─────────────────────────────────────────────────────

@app.route('/api/menu', methods=['POST'])
def api_menu():
    data = request.get_json()
    if not data or 'recettes' not in data:
        return jsonify({'error': 'Liste de recettes requise'}), 400

    fichiers = data['recettes']
    portions = data.get('portions', [])
    profils = []
    for i, f in enumerate(fichiers):
        if not f.endswith('.md'):
            f += '.md'
        p = profil_recette(f)
        if p:
            # Multiplie par la portion (défaut 1)
            mult = portions[i] if i < len(portions) else 1
            for k in list(p.get('total_brut', {}).keys()):
                p['total_brut'][k] = (p['total_brut'][k] or 0) * mult
            if p.get('poids_total'):
                p['poids_total'] = p['poids_total'] * mult
            profils.append(p)

    if not profils:
        return jsonify({'error': 'Aucune recette trouvée'}), 404

    total_brut = {}
    poids_total = 0.0
    items = []

    for i, p in enumerate(profils):
        pds = p.get('poids_total', 0) or 0
        bb = p.get('total_brut', {})
        fichier_base = fichiers[i].replace('.md', '') if i < len(fichiers) else ''
        items.append({
            'fichier': fichier_base,
            'titre': p['titre'],
            'poids_g': round(pds, 1),
            'kcal': round(bb.get('energie_kcal', 0), 1),
            'proteines': round(bb.get('proteines_g', 0), 1),
            'lipides': round(bb.get('lipides_g', 0), 1),
            'glucides': round(bb.get('glucides_g', 0), 1),
        })
        poids_total += pds
        for champ, _, _ in CHAMPS_AFFICHAGE:
            val = bb.get(champ)
            if val:
                total_brut[champ] = total_brut.get(champ, 0.0) + val

    profil_100g = {}
    if poids_total > 0:
        for champ, _, _ in CHAMPS_AFFICHAGE:
            if champ in total_brut:
                profil_100g[champ] = round(total_brut[champ] / poids_total * 100, 1)

    return jsonify({
        'plats': items,
        'total': {
            'poids_g': round(poids_total, 1),
            'kcal': round(total_brut.get('energie_kcal', 0), 1),
            'proteines_g': round(total_brut.get('proteines_g', 0), 1),
            'lipides_g': round(total_brut.get('lipides_g', 0), 1),
            'glucides_g': round(total_brut.get('glucides_g', 0), 1),
        },
        'profil_100g': profil_100g,
    })


# ── API Recherche ────────────────────────────────────────────────

@app.route('/api/recherche/ingredient/<path:terme>')
def api_recherche_ingredient(terme: str):
    """Recherche les recettes contenant un ou plusieurs ingrédients."""
    termes = [t.strip().lower() for t in terme.split(',')]

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT fichier, titre FROM recettes").fetchall()
    conn.close()

    resultats = []
    for fichier, titre in rows:
        profil = profil_recette(fichier)
        if not profil:
            continue
        ing_noms = [i['ingredient'].lower() for i in profil['details']]
        if all(any(t in ing for ing in ing_noms) for t in termes):
            resultats.append({
                'fichier': fichier.replace('.md', ''),
                'titre': titre,
                'kcal_100g': round(profil['total'].get('energie_kcal', 0), 1) if profil['match_pct'] >= 50 else None,
            })

    return jsonify({'resultats': resultats, 'termes': termes})


@app.route('/api/recherche/nutrition')
def api_recherche_nutrition():
    """Recherche par critère nutritionnel.
    Query params: champ, comparateur, valeur
    Ex: /api/recherche/nutrition?champ=fer_mg&comparateur=>&valeur=3
    """
    champ = request.args.get('champ', '')
    comparateur = request.args.get('comparateur', '>')
    try:
        valeur = float(request.args.get('valeur', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'Valeur invalide'}), 400

    # Traduction des noms courts
    aliases = {
        'kcal': 'energie_kcal', 'calories': 'energie_kcal', 'energie': 'energie_kcal',
        'proteines': 'proteines_g', 'lipides': 'lipides_g', 'glucides': 'glucides_g',
        'sucres': 'sucres_g', 'fibres': 'fibres_g', 'fer': 'fer_mg',
        'calcium': 'calcium_mg', 'magnesium': 'magnesium_mg', 'potassium': 'potassium_mg',
        'sel': 'sel_g', 'vitamine_c': 'vitamine_c_mg', 'cholesterol': 'cholesterol_mg',
    }
    champ_reel = aliases.get(champ.lower(), champ)

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT fichier, titre FROM recettes").fetchall()
    conn.close()

    ops = {'>': lambda a, b: a > b, '>=': lambda a, b: a >= b,
           '<': lambda a, b: a < b, '<=': lambda a, b: a <= b,
           '=': lambda a, b: abs(a - b) < 0.1}

    resultats = []
    for fichier, titre in rows:
        profil = profil_recette(fichier)
        if not profil:
            continue
        val = profil['total'].get(champ_reel)
        if val is None:
            continue
        if ops.get(comparateur, ops['>'])(val, valeur):
            resultats.append({
                'fichier': fichier.replace('.md', ''),
                'titre': titre,
                'valeur': round(val, 1),
            })

    # Tri
    resultats.sort(key=lambda x: -x['valeur'] if comparateur in ('>', '>=') else x['valeur'])

    # Trouve le label
    label_champ = champ_reel
    for c, lbl, _ in CHAMPS_AFFICHAGE:
        if c == champ_reel:
            label_champ = lbl
            break

    return jsonify({
        'resultats': resultats,
        'champ': champ_reel,
        'label': label_champ,
        'comparateur': comparateur,
        'valeur': valeur,
    })


# ── API Aliments ────────────────────────────────────────────────

@app.route('/api/aliments/chercher/<path:terme>')
def api_chercher_aliments(terme: str):
    # Traduction FR → EN
    terme_lower = terme.lower().strip()
    if terme_lower in MAPPING_MANUEL and MAPPING_MANUEL[terme_lower] is not None:
        terme_recherche = MAPPING_MANUEL[terme_lower]
    else:
        terme_recherche = terme

    # Support pagination avec offset
    offset = request.args.get('offset', 0, type=int)
    limit_total = 50
    resultats = chercher_aliments(terme_recherche, limit=limit_total, offset=offset)
    items = []
    for r in resultats:
        items.append({
            'code': r['code'],
            'nom': r['nom'],
            'groupe': r.get('groupe'),
            'sous_groupe': r.get('ss_groupe'),
            'energie_kcal': r.get('energie_kcal'),
            'proteines': r.get('proteines_g'),
            'lipides': r.get('lipides_g'),
            'glucides': r.get('glucides_g'),
            'fibres': r.get('fibres_g'),
            'brut': est_aliment_brut(r['nom'], r.get('groupe')),
        })
    return jsonify({'resultats': items, 'terme': terme, 'terme_recherche': terme_recherche})


@app.route('/api/aliments/profil/<code>')
def api_profil_aliment(code: str):
    profil = profil_aliment(code)
    if not profil:
        return jsonify({'error': 'Aliment inconnu'}), 404

    return jsonify({
        'code': profil['code'],
        'nom': profil['nom'],
        'groupe': profil.get('groupe'),
        'ss_groupe': profil.get('ss_groupe'),
        'ssss_groupe': profil.get('ssss_groupe'),
        'brut': est_aliment_brut(profil.get('nom', ''), profil.get('groupe')),
        'eau_g': profil.get('eau_g'),
        'energie_kcal': profil.get('energie_kcal'),
        'proteines_g': profil.get('proteines_g'),
        'glucides_g': profil.get('glucides_g'),
        'sucres_g': profil.get('sucres_g'),
        'fibres_g': profil.get('fibres_g'),
        'lipides_g': profil.get('lipides_g'),
        'acides_gras_satures_g': profil.get('acides_gras_satures_g'),
        'acides_gras_mono_g': profil.get('acides_gras_mono_g'),
        'acides_gras_poly_g': profil.get('acides_gras_poly_g'),
        'cholesterol_mg': profil.get('cholesterol_mg'),
        'sel_g': profil.get('sel_g'),
        'sodium_mg': profil.get('sodium_mg'),
        'calcium_mg': profil.get('calcium_mg'),
        'fer_mg': profil.get('fer_mg'),
        'magnesium_mg': profil.get('magnesium_mg'),
        'potassium_mg': profil.get('potassium_mg'),
        'zinc_mg': profil.get('zinc_mg'),
        'phosphore_mg': profil.get('phosphore_mg'),
        'vitamine_c_mg': profil.get('vitamine_c_mg'),
    })


# ── API aliments — Nutriments ───────────────────────────────────

@app.route('/api/nutriments')
def api_nutriments():
    """Liste des nutriments disponibles pour la recherche."""
    items = []
    for champ, label, unite in CHAMPS_AFFICHAGE:
        items.append({
            'champ': champ,
            'label': label,
            'unite': unite,
        })
    return jsonify(items)


# ── API Tags ─────────────────────────────────────────────────────

@app.route('/api/tags')
def api_tags():
    """Liste tous les tags utilisés dans les recettes."""
    tous_les_tags = set()
    for f in RECETTES_DIR.glob('*.md'):
        if f.name.startswith('recherche') or f.name.startswith('base_nutrition'):
            continue
        meta = parse_frontmatter(f.read_text())
        for tag in meta.get('tags', []):
            tous_les_tags.add(tag)
    return jsonify(sorted(tous_les_tags))


# ── API Photos ───────────────────────────────────────────────────

@app.route('/api/photos/upload', methods=['POST'])
def api_photo_upload():
    """Upload une photo et retourne le chemin relatif."""
    if 'photo' not in request.files:
        return jsonify({'error': 'Aucun fichier'}), 400
    fichier = request.files['photo']
    recette = request.form.get('recette', '')
    type_photo = request.form.get('type', 'original')  # 'original' ou 'plated'

    if not fichier.filename:
        return jsonify({'error': 'Fichier vide'}), 400

    # Génère un nom unique
    ext = os.path.splitext(fichier.filename)[1] or '.jpg'
    nom = f"{recette}_{type_photo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    chemin = PHOTOS_DIR / nom
    fichier.save(str(chemin))

    # Chemin relatif pour stocker dans le frontmatter
    rel_path = f"photos/{nom}"
    return jsonify({'chemin': rel_path, 'nom': nom, 'type': type_photo})


@app.route('/photos/<path:filename>')
def api_photo_get(filename):
    return send_from_directory(str(PHOTOS_DIR), filename)


# ── API Favoris ──────────────────────────────────────────────────

@app.route('/api/favoris', methods=['GET'])
def api_favoris_get():
    return jsonify(lire_favoris())

@app.route('/api/favoris', methods=['POST'])
def api_favoris_add():
    data = request.get_json()
    fichier = data.get('fichier', '')
    favs = lire_favoris()
    if fichier not in favs:
        favs.append(fichier)
        ecrire_favoris(favs)
    return jsonify(favs)

@app.route('/api/favoris/<fichier>', methods=['DELETE'])
def api_favoris_remove(fichier):
    favs = lire_favoris()
    if fichier in favs:
        favs.remove(fichier)
        ecrire_favoris(favs)
    return jsonify(favs)


# ── API Frigo ────────────────────────────────────────────────────

@app.route('/api/frigo')
def api_frigo():
    """Recherche les recettes réalisables avec les ingrédients disponibles.
    Query: ?ingredients=oignon,carotte,saucisse
    """
    ingredients_str = request.args.get('ingredients', '')
    if not ingredients_str:
        return jsonify({'error': 'Ingrédients requis'}), 400

    ingredients_dispos = [i.strip().lower() for i in ingredients_str.split(',')]

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT fichier, titre FROM recettes").fetchall()
    conn.close()

    resultats = []
    for fichier, titre in rows:
        profil = profil_recette(fichier)
        if not profil:
            continue

        ing_recette = [d['ingredient'].lower() for d in profil['details'] if d.get('confiance', 0) > 0]
        manquants = []
        trouves = 0

        for ing in ing_recette:
            # Vérifie si l'ingrédient est disponible
            dispo = any(
                d in ing or ing in d
                for d in ingredients_dispos
            )
            if dispo:
                trouves += 1
            else:
                manquants.append(ing)

        total_utiles = len(ing_recette)
        if total_utiles == 0:
            continue

        ratio = trouves / total_utiles
        resultats.append({
            'fichier': fichier.replace('.md', ''),
            'titre': titre,
            'trouves': trouves,
            'total': total_utiles,
            'ratio': round(ratio * 100),
            'manquants': manquants[:5],
            'faisable': ratio >= 0.7,
        })

    resultats.sort(key=lambda x: (-x['ratio'], -x['trouves']))
    return jsonify(resultats)


# ── API Sauvegarde Recette ───────────────────────────────────────

@app.route('/api/recettes/<fichier>', methods=['PATCH'])
def api_recette_patch(fichier: str):
    """Met à jour les métadonnées d'une recette (tags, portions, etc.)."""
    if not fichier.endswith('.md'):
        fichier += '.md'
    path = RECETTES_DIR / fichier
    if not path.exists():
        return jsonify({'error': 'Recette inconnue'}), 404

    data = request.get_json()
    contenu = path.read_text(encoding='utf-8')

    # Met à jour le frontmatter
    if contenu.startswith('---\n'):
        # Remplace le bloc frontmatter
        lignes = contenu.split('\n')
        fin_fm = None
        for i in range(1, len(lignes)):
            if lignes[i].strip() == '---':
                fin_fm = i
                break
        if fin_fm:
            # Construit le nouveau frontmatter
            meta = parse_frontmatter(contenu)
            meta.update(data)
            nouveau_fm = ['---']
            for k, v in meta.items():
                if k == 'tags':
                    nouveau_fm.append(f"tags: [{', '.join(v)}]")
                elif k == 'portions':
                    nouveau_fm.append(f"portions: {v}")
                elif k == 'photos':
                    for sous_k, sous_v in v.items():
                        nouveau_fm.append(f"photos  {sous_k}: {sous_v}")
                else:
                    nouveau_fm.append(f"{k}: {v}")
            nouveau_fm.append('---')
            nouveau_contenu = '\n'.join(nouveau_fm) + '\n' + '\n'.join(lignes[fin_fm+1:])
            path.write_text(nouveau_contenu, encoding='utf-8')
            return jsonify({'ok': True, 'meta': meta})
    else:
        # Pas de frontmatter → on en crée un
        nouveau_fm = ['---']
        for k, v in data.items():
            if k == 'tags':
                nouveau_fm.append(f"tags: [{', '.join(v)}]")
            elif k == 'portions':
                nouveau_fm.append(f"portions: {v}")
            else:
                nouveau_fm.append(f"{k}: {v}")
        nouveau_fm.append('---')
        nouveau_contenu = '\n'.join(nouveau_fm) + '\n' + contenu
        path.write_text(nouveau_contenu, encoding='utf-8')
        return jsonify({'ok': True})

    return jsonify({'error': 'Erreur'}), 500


@app.route('/api/recettes/<fichier>/photo', methods=['POST'])
def api_recette_lier_photo(fichier: str):
    """Lie une photo à une recette (met à jour le frontmatter)."""
    if not fichier.endswith('.md'):
        fichier += '.md'
    path = RECETTES_DIR / fichier
    if not path.exists():
        return jsonify({'error': 'Recette inconnue'}), 404

    data = request.get_json()
    chemin_photo = data.get('chemin', '')
    type_photo = data.get('type', 'original')

    contenu = path.read_text(encoding='utf-8')
    meta = parse_frontmatter(contenu)
    photos = meta.get('photos', {})
    photos[type_photo] = chemin_photo
    meta['photos'] = photos

    # Réécrit le frontmatter
    lignes = contenu.split('\n')
    if contenu.startswith('---\n'):
        fin_fm = None
        for i in range(1, len(lignes)):
            if lignes[i].strip() == '---':
                fin_fm = i
                break
        reste = '\n'.join(lignes[fin_fm+1:]) if fin_fm else contenu
    else:
        reste = contenu

    nouveau_fm = ['---']
    for k, v in meta.items():
        if k == 'tags':
            nouveau_fm.append(f"tags: [{', '.join(v)}]")
        elif k == 'photos':
            for pk, pv in v.items():
                nouveau_fm.append(f"photos  {pk}: {pv}")
        elif k == 'portions':
            nouveau_fm.append(f"portions: {v}")
        else:
            nouveau_fm.append(f"{k}: {v}")
    nouveau_fm.append('---')
    path.write_text('\n'.join(nouveau_fm) + '\n' + reste, encoding='utf-8')

    return jsonify({'ok': True, 'photos': meta.get('photos', {})})


# ── API améliorée recette détail ─────────────────────────────────

def api_recette_detail(fichier):
    """Endpoint enrichi avec métadonnées."""
    if not fichier.endswith('.md'):
        fichier += '.md'
    path = RECETTES_DIR / fichier
    if not path.exists():
        return None

    # Charge le frontmatter
    contenu = path.read_text(encoding='utf-8')
    meta = parse_frontmatter(contenu)

    # Profil nutritionnel
    profil = profil_recette(fichier)
    if not profil:
        return None

    # Enrichit les ingrédients
    details = []
    for ing in profil['details']:
        item = {
            'id': ing.get('id'),
            'ingredient': ing['ingredient'],
            'quantite': ing['quantite'] or '',
            'poids_g': ing.get('poids_g'),
            'aliment': ing['aliment_nom'] or None,
            'confiance': ing.get('confiance', 0),
            'brut': est_aliment_brut(
                ing['aliment_nom'] or '',
                ing.get('groupe')
            ) if ing['aliment_nom'] else None,
            'nutriments': {},
        }
        for champ, _, _ in CHAMPS_AFFICHAGE:
            val = ing.get(champ)
            if val is not None:
                item['nutriments'][champ] = val
        details.append(item)

    total_brut = profil.get('total_brut', {})

    return {
        'titre': profil['titre'],
        'fichier': fichier.replace('.md', ''),
        'nb_ingredients': profil['nb_ingredients'],
        'nb_matches': profil['nb_matches'],
        'match_pct': profil['match_pct'],
        'poids_total': profil.get('poids_total', 0),
        'profil_100g': profil['total'],
        'total_recette': {
            'energie_kcal': round(total_brut.get('energie_kcal', 0), 1),
            'proteines_g': round(total_brut.get('proteines_g', 0), 1),
            'lipides_g': round(total_brut.get('lipides_g', 0), 1),
            'glucides_g': round(total_brut.get('glucides_g', 0), 1),
            'fibres_g': round(total_brut.get('fibres_g', 0), 1),
        },
        'ingredients': details,
        'meta': meta,
        'favori': fichier.replace('.md', '') in lire_favoris(),
    }


# ── API Mise à jour du mapping Ciqual d'un ingrédient ──────────

@app.route('/api/recettes/<fichier>/ingredients/<int:ing_id>/mapping', methods=['PATCH'])
def api_update_ingredient_mapping(fichier: str, ing_id: int):
    """Permet de choisir manuellement l'aliment Ciqual pour un ingrédient."""
    if not fichier.endswith('.md'):
        fichier += '.md'

    data = request.get_json()
    aliment_code = data.get('code')
    if not aliment_code:
        return jsonify({'error': 'Code aliment requis'}), 400

    # Vérifie que l'aliment existe
    conn = sqlite3.connect(str(DB_PATH))
    alim = conn.execute(
        "SELECT nom, code FROM aliments WHERE code = ?", (aliment_code,)
    ).fetchone()
    if not alim:
        conn.close()
        return jsonify({'error': 'Aliment inconnu'}), 404

    # Met à jour le mapping
    conn.execute("""
        UPDATE recette_ingredients
        SET aliment_code = ?, aliment_nom = ?, confiance = 1.0
        WHERE id = ? AND recette_fichier = ?
    """, (aliment_code, alim[0], ing_id, fichier))
    conn.commit()
    conn.close()

    return jsonify({'ok': True, 'code': aliment_code, 'nom': alim[0], 'confiance': 1.0})


# ── CRUD Recettes ────────────────────────────────────────────────

RECIPE_TEMPLATE = r"""---
tags: []  # Étiquettes : [légumes, viande, rapide, four, etc.]
portions: 4
temps_cuisson: "ex: 35 min"
temps_preparation: "ex: 15 min"
source: ""  # carnet, site, famille, etc.
---
# 🍽️ {titre}

> *{description}*

---

## 📋 Ingrédients

Utilise le format tableau : | Ingrédient | Quantité |
Les quantités peuvent être en g, kg, ml, cl, ou à l'unité.

| Ingrédient | Quantité |
|---|---|
| Exemple ingrédient 1 | 200 g |
| Exemple ingrédient 2 | 2 |
| Exemple ingrédient 3 | 1,5 kg |
| Sel, poivre | selon goût |

---

## 👨‍🍳 Préparation

Découpe les étapes avec ### et numérote les actions avec 1. 2. 3.

### 1. Première étape
1. Action à réaliser.
2. Action suivante.
3. Dernière action de cette étape.

### 2. Deuxième étape
1. Action.
2. Action.

---

> 💡 *Astuce : ajoute ici tes conseils, variantes, ou notes de congélation.*
"""


@app.route('/api/recettes', methods=['POST'])
def api_recette_create():
    """Crée une nouvelle recette."""
    data = request.get_json()
    titre = data.get('titre', '').strip()
    if not titre:
        return jsonify({'error': 'Titre requis'}), 400

    # Génère un nom de fichier
    base = titre.lower()
    base = re.sub(r'[^\w\s-]', '', base)
    base = re.sub(r'[-\s]+', '-', base).strip('-')[:40]
    fichier = f"{base}.md"
    chemin = RECETTES_DIR / fichier

    if chemin.exists():
        return jsonify({'error': 'Une recette avec ce nom existe déjà'}), 409

    description = data.get('description', '')
    contenu = RECIPE_TEMPLATE.format(titre=titre, description=description)
    chemin.write_text(contenu, encoding='utf-8')

    # Aligne avec Ciqual
    try:
        aligner_recettes()
    except Exception:
        pass

    return jsonify({'ok': True, 'fichier': base, 'titre': titre}), 201


@app.route('/api/recettes/<fichier>', methods=['PUT'])
def api_recette_update(fichier: str):
    """Met à jour le contenu complet d'une recette."""
    if not fichier.endswith('.md'):
        fichier += '.md'
    chemin = RECETTES_DIR / fichier
    if not chemin.exists():
        return jsonify({'error': 'Recette inconnue'}), 404

    data = request.get_json()
    contenu = data.get('contenu', '')
    if not contenu:
        return jsonify({'error': 'Contenu requis'}), 400

    chemin.write_text(contenu, encoding='utf-8')

    # Ré-aligne
    try:
        aligner_recettes()
    except Exception:
        pass

    return jsonify({'ok': True, 'fichier': fichier.replace('.md', '')})


@app.route('/api/recettes/<fichier>', methods=['DELETE'])
def api_recette_delete(fichier: str):
    """Supprime une recette."""
    if not fichier.endswith('.md'):
        fichier += '.md'
    chemin = RECETTES_DIR / fichier
    if not chemin.exists():
        return jsonify({'error': 'Recette inconnue'}), 404

    # Supprime le fichier
    chemin.unlink()

    # Nettoie la base
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DELETE FROM recette_ingredients WHERE recette_fichier = ?", (fichier,))
    conn.execute("DELETE FROM recettes WHERE fichier = ?", (fichier,))
    conn.commit()
    conn.close()

    return jsonify({'ok': True})


# ── Assistant recette ────────────────────────────────────────────

def parser_recette_texte(texte: str, titre: str = "") -> str:
    """Transforme un texte brut de recette en Markdown structuré.
    Détecte les ingrédients (lignes avec chiffres + unités) et les étapes."""
    lignes = texte.strip().split('\n')
    ingredients = []
    etapes = []
    dans_ingredients = False
    dans_etapes = False
    etape_courante = []

    motifs_quantite = re.compile(r'(\d+[\d,.]*\s*(g|kg|ml|cl|l|cuillère|cuillères|c\.\s*à\s*s\.|cac|cas|pincée|tranche|bol|verre|sachet|boîte|gousse|branche|feuille|botte|pièce|unité))', re.IGNORECASE)
    motifs_nombre = re.compile(r'^\s*(\d+)\s+\w')

    for ligne in lignes:
        l = ligne.strip()
        if not l:
            if etape_courante:
                etapes.append(' '.join(etape_courante))
                etape_courante = []
            continue
        if 'ingrédient' in l.lower() and ':' not in l:
            dans_ingredients = True
            dans_etapes = False
            continue
        if 'préparation' in l.lower() or 'recette' in l.lower() or 'étape' in l.lower() or 'cuisson' in l.lower():
            dans_ingredients = False
            dans_etapes = True
            if etape_courante:
                etapes.append(' '.join(etape_courante))
                etape_courante = []
            continue
        if dans_ingredients or motifs_quantite.search(l) or motifs_nombre.match(l):
            ingredients.append(l)
            dans_ingredients = True
        elif dans_etapes or (not dans_ingredients and len(l) > 10):
            etape_courante.append(l)

    if etape_courante:
        etapes.append(' '.join(etape_courante))

    # Construction du Markdown
    md = f"""---
tags: []
portions: 4
temps_cuisson: ""
temps_preparation: ""
source: ""
---
# 🍽️ {titre or "Recette"}

---

## 📋 Ingrédients

| Ingrédient | Quantité |
|---|---|
"""

    for ing in ingredients:
        # Essaie de séparer la quantité du nom
        m = re.match(r'^\s*([\d,.\s]+)\s*(g|kg|ml|cl|l|cuillère|cuillères|c\.\s*à\s*s\.|cac|cas|pincée|sachet|boîte|gousse|branche|feuille|tranche|pièce)s?\s+(.+)$', ing, re.IGNORECASE)
        if m:
            qte = m.group(1).strip().replace(',', '.') + ' ' + m.group(2)
            nom = m.group(3).strip()
        else:
            m2 = re.match(r'^\s*(\d+)\s+(.+)$', ing)
            if m2:
                qte = m2.group(1)
                nom = m2.group(2).strip()
            else:
                qte = ''
                nom = ing.strip()
        # Nettoie les "de", "d'", etc.
        nom = re.sub(r'^\s*(de|d\'|d")\s+', '', nom, flags=re.IGNORECASE)
        md += f"| {nom} | {qte} |\n"

    md += """
---

## 👨‍🍳 Préparation

"""

    for i, etape in enumerate(etapes, 1):
        # Nettoie les numéros en début de phrase
        etape = re.sub(r'^\d+[.)]\s*', '', etape)
        md += f"### {i}.\n1. {etape}\n\n"

    md += "---\n\n> 💡 *Astuce personnalisée ici.*\n"
    return md


@app.route('/api/assistant/recette', methods=['POST'])
def api_assistant_recette():
    """Reçoit un texte brut de recette et génère un fichier Markdown structuré."""
    data = request.get_json()
    texte = (data.get('texte', '') or '').strip()
    titre = (data.get('titre', '') or '').strip()

    if not texte:
        return jsonify({'error': 'Texte requis'}), 400

    if not titre:
        # Extrait le titre de la première ligne significative
        for ligne in texte.split('\n'):
            l = ligne.strip()
            if l and len(l) > 5 and 'ingrédient' not in l.lower() and 'préparation' not in l.lower():
                titre = l[:60]
                break

    markdown = parser_recette_texte(texte, titre)

    # Génère le nom de fichier
    base = titre.lower()[:40]
    base = re.sub(r'[^\w\s-]', '', base)
    base = re.sub(r'[-\s]+', '-', base).strip('-')
    fichier = f"{base}.md"
    chemin = RECETTES_DIR / fichier

    if chemin.exists():
        return jsonify({'error': 'Une recette avec ce nom existe déjà', 'markdown': markdown}), 409

    chemin.write_text(markdown, encoding='utf-8')

    # Aligne
    try:
        aligner_recettes()
    except Exception:
        pass

    return jsonify({'ok': True, 'fichier': base, 'titre': titre, 'markdown': markdown}), 201


# ── Text-to-Speech ───────────────────────────────────────────────

AUDIO_DIR = RECETTES_DIR / 'audio'
AUDIO_DIR.mkdir(exist_ok=True)

@app.route('/api/tts/<fichier>')
def api_tts(fichier: str):
    """Génère un fichier audio MP3 à partir du texte de la recette."""
    from gtts import gTTS

    if not fichier.endswith('.md'):
        fichier += '.md'
    chemin = RECETTES_DIR / fichier
    if not chemin.exists():
        return jsonify({'error': 'Recette inconnue'}), 404

    contenu = chemin.read_text(encoding='utf-8')

    # Extrait les parties utiles : titre, ingrédients, préparation
    lignes = contenu.split('\n')
    titre = ''
    ingredients = []
    preparation = []
    section = ''

    for l in lignes:
        if l.startswith('# ') and not l.startswith('## '):
            titre = l[2:].strip()
        elif '## 📋 Ingrédients' in l:
            section = 'ingredients'
        elif '## 👨‍🍳 Préparation' in l:
            section = 'preparation'
        elif l.startswith('## ') and 'Ingrédients' not in l and 'Préparation' not in l:
            section = ''
        elif section == 'ingredients' and l.startswith('|') and l.count('|') >= 3:
            parts = [p.strip() for p in l.split('|')]
            if parts[1] and parts[1] != 'Ingrédient' and not parts[1].startswith('-'):
                ingredients.append(f"{parts[1]} : {parts[2]}")
        elif section == 'preparation':
            # Nettoie les lignes de préparation
            l_clean = l.strip()
            if l_clean and not l_clean.startswith('---') and not l_clean.startswith('#'):
                l_clean = l_clean.replace('**', '').replace('*', '')
                if l_clean.startswith('1.') or l_clean.startswith('2.') or l_clean.startswith('3.') or l_clean.startswith('4.') or l_clean.startswith('5.'):
                    preparation.append(l_clean)
                elif l_clean.startswith('###'):
                    preparation.append(l_clean.replace('###', 'Étape'))

    # Construit le texte à lire
    texte_tts = f"Recette : {titre}. "
    if ingredients:
        texte_tts += "Ingrédients : " + ". ".join(ingredients) + ". "
    if preparation:
        texte_tts += "Préparation : " + ". ".join(preparation) + "."

    # Génère le MP3
    nom_audio = fichier.replace('.md', '.mp3')
    chemin_audio = AUDIO_DIR / nom_audio

    try:
        tts = gTTS(text=texte_tts, lang='fr', slow=False)
        tts.save(str(chemin_audio))
    except Exception as e:
        return jsonify({'error': f'Erreur TTS : {str(e)}'}), 500

    return jsonify({'ok': True, 'audio': f'/audio/{nom_audio}', 'texte': texte_tts})


@app.route('/audio/<path:filename>')
def api_audio_get(filename: str):
    return send_from_directory(str(AUDIO_DIR), filename)


# ── API Planning ────────────────────────────────────────────────

PLANNING_FILE = RECETTES_DIR / 'planning_semaine.json'

@app.route('/api/planning/save', methods=['POST'])
def api_planning_save():
    """Sauvegarde le planning hebdomadaire côté serveur."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Données requises'}), 400
    PLANNING_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return jsonify({'ok': True})


# ── Rediriger la route recette existante ─────────────────────────

@app.route('/api/recettes/<fichier>/raw')
def api_recette_raw(fichier: str):
    """Retourne le contenu brut du fichier markdown."""
    if not fichier.endswith('.md'):
        fichier += '.md'
    chemin = RECETTES_DIR / fichier
    if not chemin.exists():
        return jsonify({'error': 'Recette inconnue'}), 404
    return chemin.read_text(encoding='utf-8'), 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/api/recettes/<fichier>')
def api_recette_route(fichier: str):
    result = api_recette_detail(fichier)
    if not result:
        return jsonify({'error': 'Recette inconnue'}), 404
    return jsonify(result)


# ── Démarrage ───────────────────────────────────────────────────

if __name__ == '__main__':
    print(f"""
🧑‍🍳 Mes Recettes — Serveur Web
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 Local :    http://127.0.0.1:8000
🌐 Réseau :  http://192.168.1.137:8000

Appuyez sur Ctrl+C pour arrêter
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
    app.run(host='0.0.0.0', port=8000, debug=True)