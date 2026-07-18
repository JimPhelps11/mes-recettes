#!/usr/bin/env python3
import sys, sqlite3
DB='/opt/data/home/recettes/objectives.db'

def customise(profil, **kw):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    row = cur.execute('SELECT * FROM objectifs WHERE profil=?', (profil,)).fetchone()
    if row is None:
        print(f'⚠️  Création du profil {profil}...')
        vals = [profil]
        default = {
            'energie_max':2100, 'energie_min':1600, 'proteines_g':90, 'lipides_g':70,
            'glucides_g':250, 'fibres_g':30, 'fer_mg':16, 'calcium_mg':1000,
            'magnesium_mg':360, 'potassium_mg':3500, 'vitamine_c_mg':110,
            'sel_min':5000, 'commentaire':f'Custom profil {profil}'
        }
        for k in default:
            vals.append(kw.get(k, default[k]))
        cur.execute('''
            INSERT INTO objectifs
            (profil, energie_max, energie_min, proteines_g, lipides_g, glucides_g, fibres_g,
             fer_mg, calcium_mg, magnesium_mg, potassium_mg, vitamine_c_mg, sel_min, commentaire)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', vals)
        conn.commit(); conn.close()
        afficher(profil); return

    desc = [d[0] for d in cur.description]
    old_dict = dict(zip(desc, row))
    modifications = []
    for k in old_dict.keys():
        new_val = kw.get(k, old_dict[k])
        if new_val != old_dict[k]:
            modifications.append((k, old_dict[k], new_val))

    if modifications:
        set_clause = ', '.join([f"{k}=?" for k, _, _ in modifications])
        values = [nv for _, _, nv in modifications] + [profil]
        cur.execute(f"UPDATE objectifs SET {set_clause} WHERE profil=?", values)
        conn.commit()
        print('✅ Mise à jour appliquée')
        for k, old_v, new_v in modifications:
            print(f"   {k}: {old_v} → {new_v}")
    else:
        print('✅ Aucune modification nécessaire')

    conn.close()
    afficher(profil)


def afficher(profil):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM objectifs WHERE profil=?', (profil,)).fetchone()
    conn.close()
    if not row:
        print(f'❌ Profil "{profil}" introuvable')
        return
    obj = dict(row)
    print('')
    print('📊 Profil '+profil)
    print('-'*50)
    for k, v in obj.items():
        print(f"   {k:18s} : {v}")

if __name__ == '__main__':
    print('\n' + '='*65)
    print('🛠️  Profile Personalizer — Modifie ENFIN un profil utilisateur')
    print('='*65)
    if len(sys.argv) < 3:
        print('\n📖 Usage :')
        print('  python3 user-profile-customizer.py <profil> proteines_g=95 commentaire="Voici mon tableau"')
        print('\nExemple:')
        print('  python3 user-profile-customizer.py moimeme proteines_g=85 commentaire="Photo 19-07"')
        customise('demo', proteines_g=40)
        sys.exit(0)
    profil = sys.argv[1]
    overrides = {}
    for arg in sys.argv[2:]:
        if '=' in arg:
            k, v = arg.split('=', 1)
            try:
                if '.' in v:
                    overrides[k] = float(v)
                else:
                    overrides[k] = int(v)
            except:
                overrides[k] = v
    customise(profil, **overrides)
