# 📋 Cahier des charges rétroactif — Application "Mes Recettes"

*Document généré par rétro-ingénierie du code existant (webapp.py, base_nutrition.py, static/*, nutrition.db) le 15 juillet 2026.*

---

## 1. Objectif du produit

Application web personnelle de gestion de recettes de cuisine, couplée à une base
nutritionnelle scientifique (Ciqual ANSES 2025), pensée pour une utilisation
familiale (mère + filles) sur réseau local domestique (Raspberry Pi).

**Objectifs métier :**
- Centraliser les recettes familiales (carnet, sites, souvenirs) en fichiers Markdown éditables.
- Calculer automatiquement les apports nutritionnels réels des recettes, sans saisie manuelle grammes par grammes.
- Aider à composer des menus équilibrés selon des objectifs nutritionnels personnalisés.
- Gérer un stock de frigo simple pour suggérer des recettes réalisables.
- Offrir une interface mobile-first, simple, intuitive, pensée "portions" plutôt que "grammes".

---

## 2. Périmètre technique

| Aspect | Choix retenu |
|---|---|
| Backend | Python 3.13 + Flask (mono-fichier `webapp.py`, ~1400 lignes) |
| Frontend | SPA vanilla JS (`app.js`, ~2400 lignes) + HTML/CSS statiques, sans framework |
| Stockage recettes | Fichiers `.md` avec frontmatter YAML (1 fichier = 1 recette) |
| Base nutritionnelle | SQLite (`nutrition.db`) alimentée depuis `ciqual_2025.xlsx` (ANSES) — 3 484 aliments |
| Persistance légère | `favoris.json`, `planning_semaine.json`, `localStorage` navigateur (frigo, profils de menu) |
| Déploiement | Service systemd (`mes-recettes.service`) sur Raspberry Pi, écoute `0.0.0.0:8000` |
| Réseau | Accessible en LAN via `http://192.168.1.137:8000` |
| Supervision | Watchdog cron (toutes les 2 min) qui vérifie le port 8000 et relance si besoin |
| IA / Vision | Analyse d'image de plat (Mistral Pixtral 12B en priorité, fallback Gemini 2.0/2.5 Flash) pour estimer ingrédients + grammages depuis une photo |
| Voix | Génération audio (gTTS) pour lecture à voix haute d'une recette |

---

## 3. Fonctionnalités livrées (état des lieux du code)

### 3.1 Gestion des recettes (CRUD complet)
- **Lister** toutes les recettes (`GET /api/recettes`)
- **Consulter** le détail complet : ingrédients mappés Ciqual, profil nutritionnel total et /100g, métadonnées (`GET /api/recettes/{fichier}`)
- **Créer** une recette via formulaire → génération d'un fichier `.md` depuis un template YAML (`POST /api/recettes`)
- **Créer via assistant texte libre** : coller un texte brut de recette (copié d'un carnet/site) → parsing automatique en Markdown structuré (`POST /api/assistant/recette`)
- **Éditer** le Markdown brut directement (`GET/PUT /api/recettes/{fichier}/raw` et `/api/recettes/{fichier}`)
- **Modifier les métadonnées** : tags, portions, temps de cuisson/préparation, source, sans toucher au corps de la recette (`PATCH /api/recettes/{fichier}`)
- **Supprimer** une recette et nettoyer les entrées associées en base (`DELETE /api/recettes/{fichier}`)
- **Associer une photo** à une recette (`POST /api/recettes/{fichier}/photo`, upload multipart)

### 3.2 Moteur nutritionnel (Ciqual ANSES 2025)
- Base de **3 484 aliments** avec profils nutritionnels complets, importée depuis le fichier officiel ANSES.
- **Parser de quantités** intelligent : reconnaît les unités courantes ("1 oignon", "2 œufs", "500g", "1 cs d'huile"…) et les convertit en grammes via une table de poids standards intégrée (oignon = 150g, œuf = 60g, etc.).
- **Alignement automatique** ingrédient → aliment Ciqual, avec score de confiance et détection **brut vs transformé** (préférence donnée aux aliments bruts en cas d'ambiguïté).
- **Mapping manuel** : possibilité de corriger/forcer le rapprochement ingrédient ↔ aliment Ciqual via un panneau de recherche dans l'interface (`PATCH /api/recettes/{fichier}/ingredients/{id}/mapping`).
- Eau et sel/poivre exclus volontairement du calcul (poids négligeable, non pertinent nutritionnellement à ce niveau de précision).
- **Recherche nutritionnelle** : trouver une recette "riche en X" / "pauvre en X" avec comparateurs (`GET /api/recherche/nutrition?champ=X&comparateur=>&valeur=5`).
- **Recherche par ingrédient(s)** combinés (`GET /api/recherche/ingredient/{terme}`).
- **Exploration de la base Ciqual** brute, indépendamment des recettes (`GET /api/aliments/chercher/{terme}`, `GET /api/aliments/profil/{code}`).

### 3.3 Menus & objectifs nutritionnels
- **Mode menu combiné** : sélectionner plusieurs recettes/portions pour calculer le total nutritionnel d'un repas ou d'une journée (`POST /api/menu`).
- **Profils de cibles nutritionnelles personnalisables** stockés en `localStorage` (plusieurs profils possibles — ex: un par personne), avec cibles par nutriment ET par groupe d'aliments/portions.
- Comparaison automatique menu réalisé vs cibles (barres de progression, code couleur).

### 3.4 Planning hebdomadaire
- Planning semaine (lundi→dimanche) × créneaux repas (petit-déjeuner, déjeuner, dîner, collation).
- Ajout de recettes ou d'ingrédients libres par créneau.
- Suivi d'activité physique par jour (durée).
- Sauvegarde serveur (`POST /api/planning/save`) + export.

### 3.5 Gestion du frigo
- Stock d'ingrédients disponibles, persistant en `localStorage` (`frigo_stock`), avec quantités ajustables (+/−).
- Chips dynamiques générées à partir des ingrédients réellement utilisés dans les recettes (pas de liste figée) — auto-nettoyage des entrées invalides.
- Fonction **"j'ai dans mon frigo"** : suggère les recettes réalisables avec le stock actuel (`GET /api/frigo?ingredients=...`).
- Génération de liste de courses à partir du planning/menu.

### 3.6 Analyse visuelle de plats (IA Vision)
- Upload d'une photo d'assiette → estimation automatique des ingrédients visibles et de leur grammage (`POST /api/vision/analyze`, `POST /api/vision/estimate_portion`, `POST /api/analyze_plate`).
- Double moteur : **Mistral Pixtral 12B** en priorité si clé configurée, sinon **Gemini 2.0/2.5 Flash** en repli.
- Règles de grammage par familles d'aliments intégrées au prompt (légumes verts, féculents, viandes, matières grasses…) pour affiner l'estimation.
- Composants front dédiés : `plate-analyzer.js`, `plate-simulate.js`.

### 3.7 Favoris, tags, recherche transverse
- Marquage favori par recette (`GET/POST/DELETE /api/favoris`).
- Tags libres par recette, agrégation globale (`GET /api/tags`).
- Barre de recherche globale par ingrédient depuis l'écran d'accueil.

### 3.8 Lecture à voix haute (TTS)
- Génération d'un MP3 (gTTS, français) lisant titre + ingrédients + étapes d'une recette (`GET /api/tts/{fichier}`), pour cuisiner sans les mains sur l'écran.

### 3.9 Interface (SPA mobile-first)
7 onglets navigables (barre du haut + barre de navigation basse) :
1. 📖 **Recettes** — liste, recherche, détail, édition, suppression
2. 🍽️ **Menu** — composition combinée + suivi des cibles
3. 🔬 **Nutri** — recherche nutritionnelle par critères
4. 🧊 **Frigo** — stock et suggestions
5. 📚 **Ciqual** — exploration libre de la base nutritionnelle
6. 📅 **Semaine** — planning hebdomadaire
7. 🍽️ **Analyser** — analyse de plat par photo (IA vision)

Thème visuel : palette vert sapin / beige. Design pensé pour utilisation tactile (mobile/tablette) en cuisine.

---

## 4. Modèle de données

### 4.1 Recette (fichier `.md`)
```yaml
---
tags: [légumes, été, mijoté]
portions: 6
temps_cuisson: "1h"
temps_preparation: "20 min"
source: carnet
photos:
  original: photos/recette_scan.jpg
  plated: photos/recette_plat.jpg
---
# Titre
## 📋 Ingrédients
| Ingrédient | Quantité |
## 👨‍🍳 Préparation
1. ...
```

### 4.2 Base SQLite `nutrition.db`
Tables : `aliments` (3 484 lignes Ciqual), `recettes`, `recette_ingredients`, `sqlite_sequence`.

### 4.3 Réponse API type (détail recette)
```json
{
  "titre": "🌭 Saucisses aux Lentilles",
  "fichier": "saucisses_lentilles",
  "poids_total": 2002,
  "match_pct": 78,
  "favori": false,
  "meta": {"tags": [...], "portions": 5, ...},
  "profil_100g": {...},
  "total_recette": {"energie_kcal": 6066.3, ...},
  "ingredients": [{"id": 42, "ingredient": "...", "aliment": "...", "confiance": 0.85, "brut": true, "nutriments": {...}}]
}
```

---

## 5. Contraintes & exigences non-fonctionnelles observées
- **Simplicité d'usage** avant exhaustivité : penser en portions/aliments plutôt qu'en grammes précis.
- **Résilience réseau LAN Pi** : tolérance aux redémarrages, watchdog automatique, pas de dépendance cloud pour les fonctions cœur (recettes, nutrition).
- **Dégradation propre en absence de clé API vision** : l'app doit rester utilisable sans IA vision configurée.
- **Édition sans perte** : toute modification manuelle du mapping Ciqual doit être conservée après ré-alignement automatique.
- **Pas de compte utilisateur / auth** — usage familial de confiance sur réseau local fermé.

## 6. Dette technique identifiée (points à surveiller)
- Fichiers dupliqués/obsolètes dans `/opt/data/home/recettes/` : `webapp_new.py`, `webapp_patch_api.py`, `webapp.py.broken_vision_only`, `webapp.py.bak_fix_attempt`, `fix_webapp_patch.py` — à nettoyer pour éviter toute confusion sur la version de référence.
- Pas de `systemctl` disponible dans l'environnement conteneurisé courant → le service `mes-recettes.service` documenté ne peut pas être géré nativement ; lancement actuel en process manuel/background, ce qui explique les pannes récurrentes signalées ("l'app ne répond pas").
- `api_update_ingredient_mapping()` utilise `sqlite3.connect()` sans `row_factory` → accès aux résultats par index, piège documenté dans le README mais fragile si le schéma évolue.
- Pas de tests automatisés identifiés dans le dépôt.

---

*Ce document reflète l'état du code au 15/07/2026. Il ne préjuge pas des évolutions futures — à mettre à jour si de nouvelles fonctionnalités sont ajoutées.*
