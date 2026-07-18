# Base d'objectifs nutritionnels

## Concept
Une base SQLite simple qui stocke des objectifs macro/micro nutritionnels **par profil utilisateur**, avec :
- Objectifs journalier (en grammes ou micro-quantité)
- Historique de suivi (date + atteinte)
- Points de repère (pregnant, sportif, sédentaire, enfant)

## Structure

```bash
/opt/data/home/recettes/
├── objectives.db           # Nouvelle base SQLite pour objectifs
└── objectives_schema.sql
```

## Profils par défaut (version 1.0)

### 🔹 Profil "Femme active 30-50 ans"
- Besoins estimés : 2000 kcal/jour
- **Protéines** : 90g (45% VNR)
- **Glucides** : 250g (≈ 35% plat)
- **Lipides** : 70g (35% plat) - dont saturés < 20g
- **Fibres** : 30g
- **Fer** : 16mg
- **Calcium** : 1000mg
- **Potassium** : 3500mg
- **Magnésium** : 360mg
- **Vitamine C** : 110mg

### 🔹 Profil "Enfant 7-12 ans"
- **Protéines** : 45g
- **Calcium** : 1000mg
- **Fer** : 10mg
- **Fibres** : 15g
- **Sucre ajouté** : < 25g

### 🔹 Profil "Sportif endurance 5x/semaine"
- **Protéines** : 130g
- **Glucides** : 350g (stratégie pré/post effort)
- **Sodium** : 5000mg (activité intense)
- **Magnésium** : 420mg (crampe musculaire)

## Géométrie des cibles

| Nutriment | Pondere Moyen | Élevé | Modèle standard | Unité |
|-----------|---------------|-------|------------------|-------|
| Energie   | 2000          | 2400  | Femme active      | kcal  |
| Protéines | 75g           | 110g  | Végétarien sportif| g     |
| Lipides   | 60g           | 85g   | 30% énergie       | g     |
| Glucides  | 250g          | 350g  | Sportif           | g     |
| Fibres    | 25g           | 30g   | All              | g     |
| Fer       | 14mg          | 18mg  | Femme réglage     | mg    |

## Journal de bord

### Tableau unique : `journal`
```sql
CREATE TABLE journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    profil TEXT NOT NULL DEFAULT 'par_defaut',
    kcal_total REAL DEFAULT 0,
    proteines_g REAL DEFAULT 0,
    lipides_g REAL DEFAULT 0,
    glucides_g REAL DEFAULT 0,
    fibres_g REAL DEFAULT 0,
    sel_mg REAL DEFAULT 0,
    fer_mg REAL DEFAULT 0,
    calcium_mg REAL DEFAULT 0,
    magnesium_mg REAL DEFAULT 0,
    potassium_mg REAL DEFAULT 0,
    vitamine_c_mg DEFAULT 0,
    -- Métadonnées
    nb_plats INTEGER DEFAULT 0,
    recettes_name TEXT DEFAULT ''
);
```

### Objectif : `objectifs`
```sql
CREATE TABLE objectifs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profil TEXT NOT NULL UNIQUE,
    energie_max REAL DEFAULT 2000,
    energie_min REAL DEFAULT 1500,
    proteines_g REAL DEFAULT 80,
    lipides_g REAL DEFAULT 70,
    glucides_g REAL DEFAULT 250,
    fibres_g REAL DEFAULT 25,
    fer_mg DEFAULT 16,
    calcium_mg DEFAULT 1000,
    magnesium_mg DEFAULT 375,
    potassium_mg DEFAULT 3500,
    vitamine_c_mg DEFAULT 110,
    commentaire TEXT
);

-- Valeurs par défaut pour 4 profils principaux
INSERT INTO objectifs (profil, energie_max, energie_min, proteines_g, lipides_g, glucides_g, 
                      fibres_g, fer_mg, calcium_mg, magnesium_mg) VALUES
('femme_active', 2100, 1600, 90, 70, 250, 30, 16, 1000, 360),
('enfant_7_12', 1700, 1300, 45, 60, 220, 15, 10, 1000, 0),
('sportif', 2600, 2000, 130, 95, 300, 35, 14, 1200, 420),
('sédentaire', 1800, 1300, 65, 60, 225, 25, 14, 900, 350);
```

## API CLI

```python
import os, json, sqlite3
OBJECTIVES_DB = '/opt/data/home/recettes/objectives.db'

def db_exists():
    return os.path.exists(OBJECTIVES_DB)

def create_db():
    conn = sqlite3.connect(OBJECTIVES_DB)
    conn.execute(open('objectives_schema.sql').read())
    conn.commit()
    conn.close()
    return True

def log_journal(date: str, profil: str,
                kcal=None, proteines=None, lipides=None, glucides=None,
                fibres=None, fer=None, ...):
    conn = sqlite3.connect(OBJECTIVES_DB)
    conn.execute("""
        INSERT INTO journal (date, profil, kcal_total, proteines_g, lipides_g, glucides_g, 
                             fibres_g, fer_mg, ...) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ...)
    """)
    conn.commit()
    conn.close()

def get_objectif(profil: str):
    conn = sqlite3.connect(OBJECTIVES_DB)
    objectif = conn.execute(
        "SELECT * FROM objectifs WHERE profil = ?", (profil,)
    ).fetchone()
    conn.close()
    return dict(objectif) if objectif else None
```

## Phase 2 - commandes CLI futures

```bash
# Créer la base
python3 objectives_manager.py init

# Journaliser une journée
python3 objectives_manager.py journal 2026-07-18 femme_active \
  --recettes pizza-poivron-chorizo bolognaise \
  --profil femme_active

# Voir les stats du jour
python3 objectives_manager.py stats 2026-07-18 femme_active

# Comparer sur la semaine
python3 objectives_manager.py compare "2026-07-15 2026-07-21"
```

## Personnalisation
a vec liste standardisée de recettes/métriques.
---