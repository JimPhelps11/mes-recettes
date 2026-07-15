#!/usr/bin/env python3
"""
🥗 Base nutritionnelle Ciqual ANSES — alignée avec les recettes
Source : Table Ciqual 2025 (ANSES) — https://ciqual.anses.fr/

Usage :
  python3 base_nutrition.py init              # Initialise la base SQLite (1 fois)
  python3 base_nutrition.py chercher <terme>   # Chercher des aliments
  python3 base_nutrition.py profil <nom>       # Profil nutritionnel complet
  python3 base_nutrition.py aligner            # Aligner les recettes avec la base
  python3 base_nutrition.py recette <fichier>  # Profil nutritionnel d'une recette
  python3 base_nutrition.py menu <r1.md> [r2.md]  # Menu : combine plusieurs plats
  python3 base_nutrition.py recherche <requête>    # Recherche nutritionnelle
"""

import sys
import re
import sqlite3
import json
from pathlib import Path
from collections import defaultdict

RECETTES_DIR = Path(__file__).parent
DB_PATH = RECETTES_DIR / "nutrition.db"
CIQUAL_XLSX = RECETTES_DIR / "ciqual_2025.xlsx"

# ── Mapping des colonnes utiles Ciqual → noms courts ─────────────────

COLUMNS = {
    'alim_grp_code': (1, str),
    'alim_ssgrp_code': (2, str),
    'alim_ssssgrp_code': (3, str),
    'groupe': (4, str),
    'ss_groupe': (5, str),
    'ssss_groupe': (6, str),
    'code': (7, str),
    'nom': (8, str),
    'nom_sci': (9, str),
    'energie_kj': (10, float),
    'energie_kcal': (11, float),
    'eau_g': (14, float),
    'proteines_g': (15, float),
    'glucides_g': (17, float),
    'lipides_g': (18, float),
    'sucres_g': (19, float),
    'fibres_g': (27, float),
    'sel_g': (50, float),
    'acides_gras_satures_g': (32, float),
    'acides_gras_mono_g': (33, float),
    'acides_gras_poly_g': (34, float),
    'cholesterol_mg': (49, float),
    'calcium_mg': (51, float),
    'fer_mg': (54, float),
    'magnesium_mg': (56, float),
    'phosphore_mg': (58, float),
    'potassium_mg': (59, float),
    'sodium_mg': (61, float),
    'zinc_mg': (62, float),
    'vitamine_c_mg': (73, float),
}

# Champs à exporter pour les recettes (les plus parlants)
CHAMPS_AFFICHAGE = [
    ('energie_kcal', '🔥 Énergie', 'kcal/100g'),
    ('proteines_g', '🥩 Protéines', 'g/100g'),
    ('lipides_g', '🧈 Lipides', 'g/100g'),
    ('glucides_g', '🍚 Glucides', 'g/100g'),
    ('sucres_g', '🍬 Sucres', 'g/100g'),
    ('fibres_g', '🌾 Fibres', 'g/100g'),
    ('sel_g', '🧂 Sel', 'g/100g'),
    ('acides_gras_satures_g', '🥓 AG saturés', 'g/100g'),
    ('cholesterol_mg', '🫀 Cholestérol', 'mg/100g'),
    ('fer_mg', '🩸 Fer', 'mg/100g'),
    ('calcium_mg', '🦴 Calcium', 'mg/100g'),
    ('magnesium_mg', '⚡ Magnésium', 'mg/100g'),
    ('potassium_mg', '🍌 Potassium', 'mg/100g'),
    ('vitamine_c_mg', '🍊 Vitamine C', 'mg/100g'),
]

# ── Parseur de quantités ────────────────────────────────────────────

# Poids standards pour les aliments à l'unité (en grammes)
POIDS_STANDARDS = {
    'oignon': 150, 'oignons': 150,
    'carotte': 100, 'carottes': 100,
    'poireau': 200, 'poireaux': 200,
    'tomate': 100, 'tomates': 100,
    'aubergine': 200, 'aubergines': 200,
    'poivron': 150, 'poivrons': 150,
    'gousse': 5, 'gousses': 5,
    "gousse d'ail": 5, "gousses d'ail": 5,
    'œuf': 60, 'œufs': 60,
    'rouleau': 250,
    'pincée': 0.5,
    'branche': 2,
    'feuille': 0.5,
}


def parser_quantite(quantite_str: str, ingredient_nom: str) -> float | None:
    """Convertit une chaîne de quantité en grammes."""
    if not quantite_str or quantite_str.lower() in (
        'selon goût', 'selon gout', 'pour déglacer', 'pour le fond', 'à volonté', ''
    ):
        return None

    qte = quantite_str.strip().lower()
    qte = re.sub(r'\(.*?\)', '', qte).strip()
    qte = qte.replace(',', '.')

    # 1) "125 g" / "500 gr" / "1,5 kg"  (unités explicites seulement)
    m = re.match(r'([\d.]+)\s*(kg|kilo|k|g|gr|ml|cl|l|litre|litres)\s*$', qte)
    if m:
        valeur = float(m.group(1))
        unite = m.group(2) or ''
        if unite in ('kg', 'kilo', 'k'):
            return valeur * 1000
        elif unite in ('ml',):
            return valeur
        elif unite in ('cl',):
            return valeur * 10
        elif unite in ('l', 'litre', 'litres'):
            return valeur * 1000
        else:
            return valeur

    # 2) Nombre + mot-clé avec poids standard "1 oignon", "2 gousses d'ail"
    #    ou "2 gros" (gros = 1× portion)
    for mot, poids in sorted(POIDS_STANDARDS.items(), key=lambda x: -len(x[0])):
        pat = re.compile(rf'([\d.]+)\s*{re.escape(mot)}')
        m_std = pat.search(qte)
        if m_std:
            return float(m_std.group(1)) * poids

    # 2b) Nombre + mot qualificatif ("2 gros", "3 moyens") → extrait le nombre
    m_qual = re.match(r'([\d.]+)\s*\w+', qte)
    if m_qual:
        nombre = float(m_qual.group(1))
        nom_ing = ingredient_nom.lower().strip()
        mots_ing = re.findall(r'[\wàâäéèêëîïôöùûüç\']+', nom_ing)
        for mot, poids in POIDS_STANDARDS.items():
            # Vérifie que mot correspond à un mot entier de l'ingrédient (pas une sous-chaîne)
            for mi in mots_ing:
                if mi == mot or mi.startswith(mot) or mot.startswith(mi):
                    return nombre * poids

    # 3) Juste un nombre "3", "12"
    m = re.match(r'^([\d.]+)$', qte)
    if m:
        nombre = float(m.group(1))
        nom_ing = ingredient_nom.lower().strip()
        mots_ing = re.findall(r'[\wàâäéèêëîïôöùûüç\']+', nom_ing)
        for mot, poids in POIDS_STANDARDS.items():
            for mi in mots_ing:
                if mi == mot or mi.startswith(mot) or mot.startswith(mi):
                    return nombre * poids
        return None

    return None


# ── Frontmatter / Métadonnées ─────────────────────────────────────

def parse_frontmatter(contenu: str) -> dict:
    """Parse le frontmatter YAML-like d'une recette.
    Retourne un dict avec les métadonnées, vide si pas de frontmatter.
    """
    meta = {}
    if not contenu.startswith('---\n'):
        return meta

    # Extrait le bloc entre les deux ---
    lignes = contenu.split('\n')
    fin = None
    for i in range(1, len(lignes)):
        if lignes[i].strip() == '---':
            fin = i
            break
    if fin is None:
        return meta

    for ligne in lignes[1:fin]:
        ligne = ligne.strip()
        if not ligne or ligne == '---':
            continue
        # Clé: valeur
        if ':' in ligne:
            cle, _, val = ligne.partition(':')
            cle = cle.strip()
            val = val.strip()
            if cle == 'tags':
                # [tag1, tag2, ...]
                if val.startswith('[') and val.endswith(']'):
                    meta['tags'] = [t.strip().strip("'\"") for t in val[1:-1].split(',')]
                else:
                    meta['tags'] = [val.strip("'\"")]
            elif cle in ('portions',):
                try:
                    meta[cle] = int(val)
                except ValueError:
                    meta[cle] = val.strip("\"'")
            elif cle == 'photos':
                # Sous-éléments sur les lignes suivantes (indentés)
                continue
            else:
                meta[cle] = val.strip("'\"")

    return meta


def extraire_titre(contenu: str) -> str:
    """Extrait le titre (# ...) d'une recette en ignorant le frontmatter."""
    import re
    m = re.search(r'^#\s+(.+)', contenu, re.MULTILINE)
    return m.group(1).strip() if m else '(sans titre)'


# ── Parsing Ciqual ──────────────────────────────────────────────────

def parse_ciqual():
    """Parse le fichier Excel Ciqual et retourne une liste de dicts."""
    import openpyxl
    wb = openpyxl.load_workbook(CIQUAL_XLSX, read_only=True, data_only=True)
    ws = wb.active

    aliments = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        if row[7] is None:  # pas de code aliment
            continue
        aliment = {}
        for name, (col_idx, caster) in COLUMNS.items():
            val = row[col_idx - 1] if col_idx - 1 < len(row) else None
            if val is None or val == '-' or val == '':
                aliment[name] = None
            elif caster == float:
                try:
                    # Gère les valeurs comme '< 0,2' ou 'traces'
                    s = str(val).strip()
                    if s.lower() in ('traces', 'non', ''):
                        aliment[name] = None
                    elif s.startswith('<'):
                        aliment[name] = 0.0  # sous le seuil de détection
                    else:
                        aliment[name] = float(s.replace(',', '.'))
                except (ValueError, TypeError):
                    aliment[name] = None
            else:
                aliment[name] = str(val).strip() if val else None
        aliments.append(aliment)

    wb.close()
    return aliments


def nettoyer_nom(nom: str) -> str:
    """Nettoie un nom d'aliment Ciqual pour le matching."""
    n = nom.lower()
    n = re.sub(r'\(.*?\)', '', n)  # enlève (xxx)
    n = re.sub(r', with.*', '', n)  # enlève ", with xxx"
    n = re.sub(r', pre.*', '', n)  # ", prepacked"
    n = re.sub(r', raw', '', n)
    n = re.sub(r', cooked', '', n)
    n = re.sub(r', canned', '', n)
    n = re.sub(r', dried', '', n)
    n = re.sub(r', frozen', '', n)
    n = re.sub(r', smoked', '', n)
    n = re.sub(r', boiled', '', n)
    n = re.sub(r', steamed', '', n)
    n = re.sub(r', grilled', '', n)
    n = re.sub(r' without.*', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


# ── Base SQLite ──────────────────────────────────────────────────────

def creer_db(aliments):
    """Crée la base SQLite et importe les données Ciqual."""
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")

    # Table des aliments Ciqual
    cols_def = ', '.join(f'{k} REAL' if caster == float else f'{k} TEXT'
                         for k, (_, caster) in COLUMNS.items())
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS aliments (
            id INTEGER PRIMARY KEY,
            {cols_def},
            nom_nettoye TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS recettes (
            fichier TEXT PRIMARY KEY,
            titre TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS recette_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recette_fichier TEXT REFERENCES recettes(fichier),
            ingredient TEXT NOT NULL,
            quantite TEXT,
            aliment_code TEXT REFERENCES aliments(code),
            aliment_nom TEXT,
            confiance REAL DEFAULT 0.0,
            proportion REAL DEFAULT 1.0
        )
    """)

    # Insertion des aliments
    placeholders = ', '.join(['?'] * (len(COLUMNS) + 1))
    cols_list = list(COLUMNS.keys())
    conn.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_aliments_nom_nettoye ON aliments(nom_nettoye)
    """)

    for alim in aliments:
        values = [alim.get(c) for c in cols_list]
        nom_nettoye = nettoyer_nom(alim.get('nom', ''))
        values.append(nom_nettoye)
        conn.execute(
            f"INSERT INTO aliments ({', '.join(cols_list)}, nom_nettoye) VALUES ({placeholders})",
            values
        )

    conn.commit()
    conn.close()
    return True


# ── Recherche d'aliments ─────────────────────────────────────────────

def chercher_aliments(terme: str, limit: int = 30, offset: int = 0) -> list[dict]:
    """Cherche des aliments par mot-clé dans la base."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Normalise le terme de recherche
    terme_norm = terme.replace(',', ' ').strip()
    terme_norm = re.sub(r'\s+', ' ', terme_norm)

    rows = conn.execute("""
        SELECT code, nom, groupe, ss_groupe, energie_kcal, proteines_g,
               lipides_g, glucides_g
        FROM aliments
        WHERE nom_nettoye LIKE ?
           OR nom LIKE ?
           OR LOWER(nom) LIKE ?
           OR LOWER(REPLACE(nom, ',', ' ')) LIKE ?
        ORDER BY
            CASE WHEN LOWER(nom) = LOWER(?) THEN 0
                 WHEN LOWER(REPLACE(nom, ',', ' ')) = ? THEN 1
                 WHEN LENGTH(nom) < 30 THEN 2
                 ELSE 3 END,
            LENGTH(nom) ASC,
            energie_kcal
        LIMIT ? OFFSET ?
    """, (f'%{terme}%', f'%{terme}%', f'%{terme.lower()}%',
          f'%{terme_norm}%', terme, terme_norm, limit, offset)).fetchall()

    resultats = [dict(r) for r in rows]
    conn.close()
    return resultats


def profil_aliment(code: str) -> dict | None:
    """Retourne le profil nutritionnel complet d'un aliment."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM aliments WHERE code = ?", (code,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Matching recettes ↔ Ciqual ───────────────────────────────────────

# Dictionnaire de correspondance manuelle ingrédient → terme Ciqual
MAPPING_MANUEL = {
    'pâte brisée': 'pâte brisée',
    'poireaux': 'poireau',
    'lardons fumés': 'lardon fumé',
    'lardons': 'lardon',
    'oignon': 'oignon',
    'oignons': 'oignon',
    'œufs': 'œuf',
    'crème': 'crème liquide',
    'crème liquide': 'crème liquide',
    'crème épaisse': 'crème liquide',
    'cumin': 'cumin',
    'aubergines': 'aubergine',
    'aubergines moyennes': 'aubergine',
    'tomates': 'tomate',
    'tomates rondes': 'tomate ronde',
    'tomate': 'tomate',
    'poivrons': 'poivron',
    'poivrons rouges': 'poivron rouge',
    'ail': 'ail',
    'gousses d\'ail': 'ail',
    'thym': 'thym',
    'origan': 'origan',
    'laurier': 'laurier',
    'huile d\'olive': 'huile d\'olive',
    'saucisses': 'saucisse',
    'saucisse': 'saucisse',
    'saucisses de toulouse': 'saucisse de toulouse',
    'saucisse de toulouse': 'saucisse de toulouse',
    'lentilles vertes': 'lentille verte',
    'lentilles': 'lentille',
    'carottes': 'carotte',
    'carotte': 'carotte',
    'vin blanc': 'vin blanc',
    'chair à saucisse': 'porc',
    'riz cru': 'riz',
    'riz': 'riz',
    'herbes': 'herbes de provence',
    'persil': 'persil',
    'pâte': 'pâtes',
    'sel': None,
    'poivre': 'poivre',
    'sel, poivre': None,
    'gruyère': 'gruyère',
    'noix de muscade': 'noix de muscade',
    'eau': None,
}


def trouver_aliment_ciqual(ingredient_nom: str) -> tuple[str | None, str | None, float]:
    """
    Trouve le meilleur aliment Ciqual pour un ingrédient.
    Préfère les aliments bruts (raw, fresh) aux transformés.
    Retourne (code, nom_ciqual, confiance).
    """
    nom = ingredient_nom.lower().strip()

    # 0. Extrait le mot principal
    nom_base = re.sub(r'[\(,].*$', '', nom).strip()
    mots_cles = re.findall(r"[\wàâäéèêëîïôöùûüç']+", nom_base)

    def meilleur_resultat(resultats):
        """Parmi les résultats, préfère le brut, sinon le premier."""
        if not resultats:
            return None
        for r in resultats:
            if est_aliment_brut(r['nom'], r.get('groupe')):
                return r
        return resultats[0]

    # 1. Mapping manuel
    if nom in MAPPING_MANUEL:
        terme = MAPPING_MANUEL[nom]
        if terme is None:
            return None, None, 0.0
        resultats = chercher_aliments(terme, limit=8)
        if resultats:
            r = meilleur_resultat(resultats)
            conf = 0.95 if est_aliment_brut(r['nom'], r.get('groupe')) else 0.85
            return r['code'], r['nom'], conf

    # 2. Mapping manuel — avec le mot principal (sans parenthèses)
    for mot in [nom_base] + mots_cles:
        if mot in MAPPING_MANUEL:
            terme = MAPPING_MANUEL[mot]
            if terme is None:
                return None, None, 0.0
            resultats = chercher_aliments(terme, limit=8)
            if resultats:
                r = meilleur_resultat(resultats)
                conf = 0.85 if est_aliment_brut(r['nom'], r.get('groupe')) else 0.75
                return r['code'], r['nom'], conf

    # 3. Cherche par mot-clé dans Ciqual
    for mot in mots_cles:
        if len(mot) > 3:
            resultats = chercher_aliments(mot, limit=5)
            if resultats:
                r = meilleur_resultat(resultats)
                conf = 0.6 if est_aliment_brut(r['nom'], r.get('groupe')) else 0.4
                return r['code'], r['nom'], conf

    return None, None, 0.0


def aligner_recettes():
    """Aligne tous les ingrédients des recettes avec la base Ciqual.
    Préserve les associations faites manuellement (confiance = 1.0)."""
    fichiers_md = sorted(RECETTES_DIR.glob('*.md'))

    conn = sqlite3.connect(str(DB_PATH))

    # Sauvegarde les mappings manuels avant de tout recréer
    manuels = {}
    rows = conn.execute("""
        SELECT recette_fichier, ingredient, quantite, aliment_code, aliment_nom
        FROM recette_ingredients WHERE confiance = 1.0
    """).fetchall()
    for (fichier, ing, qte, code, nom) in rows:
        manuels[(fichier, ing, qte)] = (code, nom)

    conn.execute("DELETE FROM recettes")
    conn.execute("DELETE FROM recette_ingredients")

    stats = {'recettes': 0, 'ingredients': 0, 'matches': 0, 'no_match': 0, 'preserves': len(manuels)}

    for fpath in fichiers_md:
        if fpath.name == 'recherche_ingredients.py' or fpath.name == 'base_nutrition.py':
            continue
        fichier = fpath.name
        contenu = fpath.read_text(encoding='utf-8')

        titre = ''
        for line in contenu.splitlines():
            if line.startswith('# '):
                titre = line[2:].strip()
                break

        conn.execute("INSERT OR REPLACE INTO recettes (fichier, titre) VALUES (?, ?)",
                     (fichier, titre))
        stats['recettes'] += 1

        # Parse le tableau des ingrédients
        dans_section = False
        dans_tableau = False
        for line in contenu.splitlines():
            if '##' in line and 'Ingrédients' in line:
                dans_section = True
                continue
            if not dans_section:
                continue
            if '| Ingrédient |' in line:
                dans_tableau = True
                continue
            if not dans_tableau:
                continue
            if line.startswith('---') or line.startswith('##') or not line.strip():
                break
            if re.match(r'^\|[\s\-:]+\|', line):
                continue
            if line.startswith('|') and line.endswith('|'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 3 and parts[1] and parts[1] != 'Ingrédient' and parts[1] != '---':
                    ing_nom = parts[1]
                    ing_qte = parts[2]

                    # Vérifie si un mapping manuel existe
                    cle = (fichier, ing_nom, ing_qte)
                    if cle in manuels:
                        code, nom_ciqual = manuels[cle]
                        conf = 1.0
                    else:
                        code, nom_ciqual, conf = trouver_aliment_ciqual(ing_nom)

                    conn.execute("""
                        INSERT INTO recette_ingredients
                        (recette_fichier, ingredient, quantite, aliment_code, aliment_nom, confiance)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (fichier, ing_nom, ing_qte, code, nom_ciqual, conf))

                    stats['ingredients'] += 1
                    if code:
                        stats['matches'] += 1
                    else:
                        stats['no_match'] += 1

    conn.commit()
    conn.close()
    return stats


def profil_recette(fichier: str) -> dict | None:
    """Calcule le profil nutritionnel d'une recette (pondéré par les quantités)."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    recette = conn.execute(
        "SELECT * FROM recettes WHERE fichier = ?", (fichier,)
    ).fetchone()
    if not recette:
        conn.close()
        return None

    ingredients = conn.execute("""
        SELECT ri.*, a.*
        FROM recette_ingredients ri
        LEFT JOIN aliments a ON ri.aliment_code = a.code
        WHERE ri.recette_fichier = ?
    """, (fichier,)).fetchall()

    conn.close()

    if not ingredients:
        return {'titre': recette['titre'], 'details': [], 'total': {},
                'nb_ingredients': 0, 'nb_matches': 0,
                'poids_total': 0, 'match_pct': 0}

    total_nutriments = {}
    poids_total = 0.0
    nb_matches = 0
    details = []

    for ing in ingredients:
        ing_dict = dict(ing)
        ing_nom = ing_dict['ingredient']
        ing_qte = ing_dict.get('quantite', '')

        # Poids en grammes
        poids_g = parser_quantite(ing_qte, ing_nom)
        ing_dict['poids_g'] = poids_g

        if ing_dict.get('energie_kcal') is not None:
            nb_matches += 1
            if poids_g and poids_g > 0:
                poids_total += poids_g
                for champ, _, _ in CHAMPS_AFFICHAGE:
                    val = ing_dict.get(champ)
                    if val is not None:
                        # Nutriments pour la portion : (valeur pour 100g) * (poids / 100)
                        contrib = val * (poids_g / 100.0)
                        total_nutriments[champ] = total_nutriments.get(champ, 0.0) + contrib

        details.append(ing_dict)

    # Ramène à /100g
    total_par_100g = {}
    if poids_total > 0:
        for champ, _, _ in CHAMPS_AFFICHAGE:
            if champ in total_nutriments:
                total_par_100g[champ] = round(total_nutriments[champ] / poids_total * 100, 1)

    match_pct = round(nb_matches / len(ingredients) * 100) if ingredients else 0

    return {
        'titre': recette['titre'],
        'nb_ingredients': len(ingredients),
        'nb_matches': nb_matches,
        'match_pct': match_pct,
        'total': total_par_100g,
        'total_brut': total_nutriments,
        'poids_total': round(poids_total, 1),
        'details': details,
    }


# ── Classification brut/transformé ───────────────────────────────────
def est_aliment_brut(nom: str, groupe: str | None) -> bool:
    """Détermine si un aliment Ciqual est un ingrédient de base (brut)
    ou un produit déjà transformé. Version française."""
    nom_lower = nom.lower()
    groupe_lower = (groupe or '').lower()

    # Indices de transformation (français)
    mots_transformes = [
        'préemballé', 'conserve', 'déshydraté', 'reconstitué',
        'préparé', 'maison', 'à emporter', 'surgelé',
        'soupe', 'ragoût', 'sauce', 'salade', 'pâté', 'terrine',
        'sandwich', 'pizza', 'tarte', 'quiche', 'gâteau',
        'biscuit', 'pain', 'croissant', 'viennoiserie', 'flan',
        'yaourt', 'fromage', 'crème', 'beurre', 'margarine', 'huile',
        'ravioli', 'pâtes', 'nouille',
        'chocolat', 'bonbon', 'confiserie',
        'glace', 'sorbet', 'mousse',
        'chips', 'frites', 'chips',
        'rôti', 'grillé', 'frit', 'braisé', 'bouilli',
        'cuit', 'sauté', 'poêlé',
        'fumé', 'salé', 'mariné',
        'aromatisé', 'assaisonné',
        'aliment bébé', 'nourrisson',
        'bière', 'vin', 'spiritueux', 'liqueur',
        'saucisse', 'jambon', 'bacon', 'lardon',
        'farce', 'pané',
    ]

    mots_bruts = ['cru', 'frais', 'naturel', 'entier']

    groupes_bruts = [
        'fruits, légumes, légumineuses et oléagineux',
        'viandes, œufs et poissons',
        'lait et produits laitiers',
        'matières grasses',
    ]

    for mot in mots_transformes:
        if mot in nom_lower:
            return False

    for mot in mots_bruts:
        if mot in nom_lower:
            return True

    for g in groupes_bruts:
        if g in groupe_lower and len(nom) < 30:
            return True

    if 'entrées et plats composés' in groupe_lower or 'aliment bébé' in groupe_lower:
        return False

    return len(nom) < 25


# ── Affichage ────────────────────────────────────────────────────────

def afficher_profil_recette(profil: dict):
    print(f"\n{'='*55}")
    print(f"  🍽️  {profil['titre']}")
    print(f"{'='*55}")

    print(f"\n  📊 Alignement Ciqual : {profil['nb_matches']}/{profil['nb_ingredients']} "
          f"ingrédients ({profil['match_pct']}%)")

    poids = profil.get('poids_total', 0)
    if poids:
        total_brut = profil.get('total_brut', {})
        kcal_total = total_brut.get('energie_kcal', 0)
        proteines_total = total_brut.get('proteines_g', 0)
        print(f"  ⚖️  Poids total estimé : {poids:.0f}g"
              + (f"  |  🔥 {kcal_total:.0f} kcal  |  🥩 {proteines_total:.0f}g prot." if kcal_total else ""))

    if profil['match_pct'] >= 50:
        print(f"\n  🔥 Profil nutritionnel pour 100g :")
        for champ, label, unite in CHAMPS_AFFICHAGE:
            val = profil['total'].get(champ)
            if val is not None:
                print(f"    {label:<20} {val:>8.1f}  {unite}")

    print(f"\n  📋 Ingrédients :")
    for ing in profil['details']:
        nom = ing['ingredient']
        qte = ing['quantite'] or ''
        aliment = ing['aliment_nom'] or '—'
        confiance = ing.get('confiance', 0)
        icone = '✅' if confiance >= 0.8 else ('⚠️' if confiance >= 0.3 else '❌')
        kcal = ing.get('energie_kcal')
        kcal_str = f"{kcal:.0f} kcal/100g" if kcal is not None else '—'
        poids_g = ing.get('poids_g')
        poids_str = f"  ~{poids_g:.0f}g" if poids_g else ''
        print(f"    {icone} {nom:<20} {poids_str:<12} → {aliment:<35} {kcal_str}")
    print()


# ── CLI ──────────────────────────────────────────────────────────────

def cmd_init():
    print("📦 Importation de la table Ciqual 2025...")
    import openpyxl  # vérifie dispo
    aliments = parse_ciqual()
    creer_db(aliments)
    print(f"✅ {len(aliments)} aliments importés dans {DB_PATH.name}")

    # Stats par groupe
    groupes = defaultdict(int)
    for a in aliments:
        g = a.get('groupe', '?')
        groupes[g] += 1
    print(f"\n📂 Répartition par groupe :")
    for g, count in sorted(groupes.items(), key=lambda x: (x[0] or '')):
        print(f"  • {g}: {count} aliments")

    print(f"\n💡 Lancez maintenant : python3 base_nutrition.py aligner")


def cmd_chercher(termes: list[str]):
    terme = ' '.join(termes).lower().strip()

    # Traduction FR → EN via le dictionnaire de mapping
    if terme in MAPPING_MANUEL and MAPPING_MANUEL[terme] is not None:
        terme_recherche = MAPPING_MANUEL[terme]
        print(f"🔀 Traduction : '{terme}' → '{terme_recherche}'")
        terme = terme_recherche

    resultats = chercher_aliments(terme)
    if not resultats:
        print(f"😕 Aucun aliment trouvé pour '{terme}'")
        return
    print(f"\n{'='*55}")
    print(f"  🔍 Résultats pour '{terme}' : {len(resultats)} aliment(s)")
    print(f"{'='*55}\n")
    for r in resultats:
        kcal = r.get('energie_kcal') or '—'
        proteines = r.get('proteines_g') or '—'
        lipides = r.get('lipides_g') or '—'
        glucides = r.get('glucides_g') or '—'
        print(f"  📄 [{r['code']}] {r['nom']}")
        print(f"     ├─ Groupe : {r.get('groupe', '?')} > {r.get('ss_groupe', '?')}")
        print(f"     ├─ 🔥 {kcal} kcal")
        print(f"     ├─ 🥩 {proteines}g P  |  🧈 {lipides}g L  |  🍚 {glucides}g G")
        print()


def cmd_profil(termes: list[str]):
    terme = ' '.join(termes).lower().strip()

    # Traduction FR → EN
    if terme in MAPPING_MANUEL and MAPPING_MANUEL[terme] is not None:
        terme_recherche = MAPPING_MANUEL[terme]
        print(f"🔀 Traduction : '{terme}' → '{terme_recherche}'")
        terme = terme_recherche

    # Cherche par terme
    resultats = chercher_aliments(terme, limit=1)
    if resultats:
        code = resultats[0]['code']
    else:
        # Sinon cherche par terme
        resultats = chercher_aliments(terme, limit=1)
        if not resultats:
            print(f"😕 Aliment '{terme}' introuvable")
            return
        code = resultats[0]['code']

    profil = profil_aliment(code)
    if not profil:
        print("😕 Aliment introuvable")
        return

    print(f"\n{'='*55}")
    print(f"  📊 {profil['nom']} ({profil['code']})")
    print(f"  {profil.get('groupe', '?')} > {profil.get('ss_groupe', '?')}")
    print(f"{'='*55}\n")

    print(f"  🔥 Profil nutritionnel pour 100g :")
    for champ, label, unite in CHAMPS_AFFICHAGE:
        val = profil.get(champ)
        if val is not None:
            print(f"    {label:<20} {val:>8.1f}  {unite}")
        else:
            print(f"    {label:<20} {'—':>8}  {unite}")
    print()

    print(f"  🧪 Minéraux :")
    for champ in ['calcium_mg', 'fer_mg', 'magnesium_mg', 'phosphore_mg', 'potassium_mg', 'sodium_mg', 'zinc_mg']:
        val = profil.get(champ)
        if val is not None:
            label = champ.replace('_mg', '').replace('_', ' ').title()
            print(f"    {label:<20} {val:>8.1f}  mg/100g")

    print(f"\n  💧 Eau : {profil.get('eau_g', '—')} g/100g")
    print(f"  🫀 Cholestérol : {profil.get('cholesterol_mg', '—')} mg/100g")


def cmd_aligner():
    if not DB_PATH.exists():
        print("❌ Base non initialisée. Lancez d'abord : python3 base_nutrition.py init")
        return
    print("🔄 Alignement des recettes avec la base Ciqual...")
    stats = aligner_recettes()
    print(f"\n✅ Terminé !")
    print(f"  📚 {stats['recettes']} recettes")
    print(f"  📝 {stats['ingredients']} ingrédients")
    print(f"  ✅ {stats['matches']} matchés avec Ciqual")
    print(f"  🔒 {stats['preserves']} mappings manuels préservés")
    print(f"  ❌ {stats['no_match']} non matchés")
    print(f"  📊 Taux d'alignement : {stats['matches']/max(stats['ingredients'],1)*100:.0f}%")


def cmd_recette(termes: list[str]):
    fichier = ' '.join(termes)
    if not fichier.endswith('.md'):
        fichier += '.md'
    path = RECETTES_DIR / fichier
    if not path.exists():
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT fichier FROM recettes WHERE fichier LIKE ?", (f'%{fichier}%',)
        ).fetchall()
        conn.close()
        if not rows:
            print(f"😕 Recette '{fichier}' introuvable")
            return
        fichier = rows[0][0]

    profil = profil_recette(fichier)
    if not profil:
        print(f"😕 Recette '{fichier}' introuvable")
        return
    afficher_profil_recette(profil)


# ── Mode Menu ──────────────────────────────────────────────────────

def cmd_menu(termes: list[str]):
    """Combine plusieurs recettes et affiche le profil nutritionnel complet du menu."""
    if not termes:
        print("Usage : python3 base_nutrition.py menu <recette1.md> [recette2.md] ...")
        return

    profils = []
    for terme in termes:
        fichier = terme if terme.endswith('.md') else terme + '.md'
        path = RECETTES_DIR / fichier
        if not path.exists():
            conn = sqlite3.connect(str(DB_PATH))
            rows = conn.execute(
                "SELECT fichier FROM recettes WHERE fichier LIKE ?", (f'%{fichier}%',)
            ).fetchall()
            conn.close()
            if not rows:
                print(f"⚠️  Recette '{fichier}' introuvable, ignorée")
                continue
            fichier = rows[0][0]

        profil = profil_recette(fichier)
        if profil:
            profils.append(profil)
        else:
            print(f"⚠️  Impossible de charger '{fichier}'")

    if not profils:
        print("😕 Aucune recette valide")
        return

    # Fusion des profils
    total_brut = {}
    poids_total = 0.0
    nb_ingredients = 0
    nb_matches = 0

    print(f"\n{'='*55}")
    print(f"  🍽️  MENU — {len(profils)} plat(s)")
    print(f"{'='*55}")

    for p in profils:
        nom_plat = p['titre']
        pds = p.get('poids_total', 0) or 0
        kcal = p.get('total_brut', {}).get('energie_kcal', 0) or 0
        proteines = p.get('total_brut', {}).get('proteines_g', 0) or 0
        lipides = p.get('total_brut', {}).get('lipides_g', 0) or 0
        glucides = p.get('total_brut', {}).get('glucides_g', 0) or 0
        print(f"\n  📄 {nom_plat}")
        print(f"     ⚖️  {pds:.0f}g  |  🔥 {kcal:.0f} kcal  |  🥩 {proteines:.0f}g prot.  |  🧈 {lipides:.0f}g lip.  |  🍚 {glucides:.0f}g gluc.")

        nb_ingredients += p['nb_ingredients']
        nb_matches += p['nb_matches']
        poids_total += pds
        for champ, _, _ in CHAMPS_AFFICHAGE:
            val = p.get('total_brut', {}).get(champ)
            if val:
                total_brut[champ] = total_brut.get(champ, 0.0) + val

    # Total du menu
    print(f"\n{'─'*55}")
    print(f"  📊 TOTAL DU MENU")
    print(f"{'─'*55}")
    kcal_menu = total_brut.get('energie_kcal', 0)
    proteines_menu = total_brut.get('proteines_g', 0)
    lipides_menu = total_brut.get('lipides_g', 0)
    glucides_menu = total_brut.get('glucides_g', 0)
    print(f"     ⚖️  {poids_total:.0f}g  |  🔥 {kcal_menu:.0f} kcal  |  🥩 {proteines_menu:.0f}g prot.")
    print(f"     🧈 {lipides_menu:.0f}g lip.  |  🍚 {glucides_menu:.0f}g gluc.")

    if poids_total > 0:
        print(f"\n  🔥 Profil nutritionnel moyen pour 100g :")
        for champ, label, unite in CHAMPS_AFFICHAGE:
            val = total_brut.get(champ)
            if val is not None:
                v_100g = val / poids_total * 100
                print(f"    {label:<20} {v_100g:>8.1f}  {unite}")

    # Comparatif nutri
    print(f"\n  📊 Répartition des calories par plat :")
    for p in profils:
        kcal_p = p.get('total_brut', {}).get('energie_kcal', 0) or 0
        pct = kcal_p / max(kcal_menu, 1) * 100
        barre = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
        print(f"    {p['titre'][:25]:<25} {barre} {kcal_p:.0f} kcal ({pct:.0f}%)")

    print(f"\n  ✅ Alignement : {nb_matches}/{nb_ingredients} ingrédients"
          f" ({round(nb_matches/max(nb_ingredients,1)*100)}%)")
    print()


# ── Recherche nutritionnelle ───────────────────────────────────────

def cmd_recherche(termes: list[str]):
    """Recherche des recettes par profil nutritionnel.

    Exemples :
      riche en fer
      pauvre en lipides
      proteines > 20
      fibres >= 5
      kcal < 200
    """
    requete = ' '.join(termes).lower().strip()

    # Analyse la requête
    # Pattern: <nutriment> <comparateur> <valeur>
    # ou: "riche en <nutriment>" / "pauvre en <nutriment>"
    nutriments_map = {
        'calories': 'energie_kcal', 'kcal': 'energie_kcal', 'energie': 'energie_kcal',
        'proteines': 'proteines_g', 'proteine': 'proteines_g', 'prot': 'proteines_g',
        'lipides': 'lipides_g', 'lipide': 'lipides_g', 'gras': 'lipides_g', 'graisse': 'lipides_g',
        'glucides': 'glucides_g', 'glucide': 'glucides_g', 'sucre': 'sucres_g', 'sucres': 'sucres_g',
        'fibres': 'fibres_g', 'fibre': 'fibres_g',
        'sel': 'sel_g',
        'fer': 'fer_mg',
        'calcium': 'calcium_mg',
        'magnesium': 'magnesium_mg', 'magnésium': 'magnesium_mg',
        'potassium': 'potassium_mg',
        'vitamine c': 'vitamine_c_mg', 'vitamine_c': 'vitamine_c_mg', 'vit c': 'vitamine_c_mg',
        'cholesterol': 'cholesterol_mg', 'cholestérol': 'cholesterol_mg',
    }

    # 1) "riche en <nutriment>" → nutriment > seuil_haut
    # 2) "pauvre en <nutriment>" → nutriment < seuil_bas
    m_riche = re.match(r'riche\s+en\s+(.+)', requete)
    m_pauvre = re.match(r'pauvre\s+en\s+(.+)', requete)
    m_compare = re.match(r'(\w+(?:\s+\w+)?)\s*([><=!]+)\s*([\d.]+)', requete)

    champ = None
    comparateur = None
    valeur = None

    if m_riche:
        nutr = m_riche.group(1).strip()
        if nutr in nutriments_map:
            champ = nutriments_map[nutr]
            comparateur = '>'
            # Seuils "riche" par nutriment
            SEUILS_RICHE = {
                'energie_kcal': 300, 'proteines_g': 15, 'lipides_g': 20,
                'glucides_g': 30, 'sucres_g': 15, 'fibres_g': 5,
                'fer_mg': 3, 'calcium_mg': 150, 'magnesium_mg': 50,
                'potassium_mg': 300, 'vitamine_c_mg': 20,
            }
            valeur = SEUILS_RICHE.get(champ, 10)
    elif m_pauvre:
        nutr = m_pauvre.group(1).strip()
        if nutr in nutriments_map:
            champ = nutriments_map[nutr]
            comparateur = '<'
            SEUILS_PAUVRE = {
                'energie_kcal': 100, 'lipides_g': 5, 'glucides_g': 10,
                'sucres_g': 5, 'sel_g': 0.3,
            }
            valeur = SEUILS_PAUVRE.get(champ, 5)
    elif m_compare:
        nutr = m_compare.group(1).strip()
        comparateur = m_compare.group(2)
        valeur = float(m_compare.group(3))
        if nutr in nutriments_map:
            champ = nutriments_map[nutr]

    if not champ or valeur is None:
        print(__doc__)
        print("\nExemples :")
        print("  python3 base_nutrition.py recherche riche en fer")
        print("  python3 base_nutrition.py recherche pauvre en lipides")
        print("  python3 base_nutrition.py recherche proteines > 20")
        print("  python3 base_nutrition.py recherche \"kcal < 200\"")
        print("  python3 base_nutrition.py recherche fibres >= 5")
        return

    # Évalue toutes les recettes
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT fichier FROM recettes").fetchall()
    conn.close()

    resultats = []
    for (fichier,) in rows:
        profil = profil_recette(fichier)
        if not profil:
            continue
        val_nutri = profil.get('total', {}).get(champ)
        if val_nutri is None:
            continue

        match = False
        if comparateur == '>':
            match = val_nutri > valeur
        elif comparateur == '>=':
            match = val_nutri >= valeur
        elif comparateur == '<':
            match = val_nutri < valeur
        elif comparateur == '<=':
            match = val_nutri <= valeur
        elif comparateur in ('=', '=='):
            match = abs(val_nutri - valeur) < 0.1

        if match:
            # Trouve le label du champ
            label_champ = champ
            for _, lbl, _ in CHAMPS_AFFICHAGE:
                if champ in _:
                    label_champ = lbl
                    break
            resultats.append((profil['titre'], fichier, label_champ, val_nutri))

    # Affichage
    resultats.sort(key=lambda x: -x[3] if comparateur in ('>', '>=') else x[3])

    if not resultats:
        label_champ = champ
        for _, lbl, _ in CHAMPS_AFFICHAGE:
            if champ in _:
                label_champ = lbl
                break
        print(f"😕 Aucune recette avec {label_champ} {comparateur} {valeur}")
        return

    label_champ = champ
    for _, lbl, _ in CHAMPS_AFFICHAGE:
        if champ in _:
            label_champ = lbl
            break

    print(f"\n{'='*55}")
    print(f"  🔍 Recettes : {label_champ} {comparateur} {valeur}")
    print(f"{'='*55}")
    print(f"  {len(resultats)} résultat(s)\n")

    for titre, fichier, _, val in resultats:
        if comparateur in ('>', '>='):
            icone = '⬆️'
        else:
            icone = '⬇️'
        barre = '█' * int(min(val / max(valeur, 1), 3) * 5) if valeur > 0 else ''
        print(f"  {icone} {titre}")
        fichier_short = fichier.replace('.md', '')
        print(f"     └─ {label_champ} : {val:.1f}  {barre}")
        print(f"     └─ fichier : {fichier_short}")
    print()


# ── Main ─────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0]
    cmd_args = args[1:]

    if cmd == 'init':
        cmd_init()
    elif cmd == 'chercher':
        if not cmd_args:
            print("Usage : python3 base_nutrition.py chercher <terme>")
            return
        cmd_chercher(cmd_args)
    elif cmd == 'profil':
        if not cmd_args:
            print("Usage : python3 base_nutrition.py profil <terme>")
            return
        cmd_profil(cmd_args)
    elif cmd == 'aligner':
        cmd_aligner()
    elif cmd == 'recette':
        if not cmd_args:
            print("Usage : python3 base_nutrition.py recette <fichier.md>")
            return
        cmd_recette(cmd_args)
    elif cmd == 'menu':
        cmd_menu(cmd_args)
    elif cmd == 'recherche':
        cmd_recherche(cmd_args)
    else:
        print(f"❌ Commande inconnue : {cmd}")
        print(__doc__)


if __name__ == '__main__':
    main()
