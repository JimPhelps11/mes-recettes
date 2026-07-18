// ── State ──
let allRecettes = [];
let favoris = [];
let menuJournalier = {
  'petit-dejeuner': [],
  'dejeuner': [],
  'diner': [],
  'collation': [],
};
let planningSemaine = {};
// Initialise la semaine
const JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'];
const REPAS = ['petit-dejeuner', 'dejeuner', 'diner', 'collation'];
const SLOT_ICONS = { 'petit-dejeuner': '🌅', 'dejeuner': '☀️', 'diner': '🌙', 'collation': '🍪' };
const SLOT_LABELS = { 'petit-dejeuner': 'Petit-déjeuner', 'dejeuner': 'Déjeuner', 'diner': 'Dîner', 'collation': 'Collation' };
// Charge depuis localStorage
try { planningSemaine = JSON.parse(localStorage.getItem('planning_semaine') || '{}'); } catch(e) {}
// Assure tous les jours
for (const j of JOURS) {
  if (!planningSemaine[j]) planningSemaine[j] = {};
  for (const r of REPAS) {
    if (!planningSemaine[j][r]) planningSemaine[j][r] = [];
  }
}
let frigoIngredients = [];

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
  frigoIngredients = (() => { try { return JSON.parse(localStorage.getItem('frigo_stock') || '[]'); } catch(e) { return []; } })();
  loadRecettes();
  loadFavoris();
function setupNutriSearch(){document.getElementById("search-input")?.addEventListener("input",()=>{clearTimeout(t);t=setTimeout(()=>loadRecettes(), 300)});var t=null}
  buildFrigoChips();
  setupTabs();
  setupNutriSearch();
});

function setupTabs() {
  document.querySelectorAll('.tab, .nav-item').forEach(el => {
    el.addEventListener('click', () => {
      const tab = el.dataset.tab;
      if (!tab) return;
      switchTab(tab);
    });
  });
}

function switchTab(tab) {
  document.querySelectorAll('.tab, .nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === tab);
  });
  document.querySelectorAll('.tab-content').forEach(el => {
    el.classList.toggle('active', el.id === 'tab-' + tab);
  });
  if (tab === 'menu') renderMenu();
  if (tab === 'nutri') renderNutriResults();
  if (tab === 'frigo') renderFrigo();
  if (tab === 'ciqual') renderCiqualExplorer();
  if (tab === 'semaine') renderPlanning();
  if (tab === 'menu') loadMenu();
}

// ── Load Recipes ──
async function loadRecettes() {
  try {
    const res = await fetch('/api/recettes');
    allRecettes = await res.json();
    renderRecettes(allRecettes);
    document.getElementById('header-sub').textContent =
      allRecettes.length + ' recettes · base Ciqual 2025';
    buildFrigoChips(); // Génère les chips après le chargement
  } catch(e) {
    document.getElementById('recipes-list').innerHTML =
      '<div class="loading" style="color:#d97a5e">❌ Erreur de chargement<br><small style="font-size:11px;opacity:0.8">' +
      (e && e.message ? e.message.replace(/</g,'&lt;') : String(e)) + '<br>UA: ' + navigator.userAgent.slice(0,60) + '</small></div>';
  }
}

// ── Emoji helper (mapping par mot-clé du titre) ──
const EMOJI_MAP = [
  [/b(œ|oe)uf|steak|bavette|entrec[ôo]te/i, '🥩'],
  [/poulet|volaille|dinde/i, '🍗'],
  [/poisson|saumon|thon|cabillaud|colin/i, '🐟'],
  [/pâtes|spaghetti|lasagne|macaroni/i, '🍝'],
  [/pizza/i, '🍕'],
  [/soupe|velouté|potage/i, '🍲'],
  [/salade/i, '🥗'],
  [/gâteau|tarte|cake|dessert|crème|tiramisu/i, '🍰'],
  [/pain|brioche/i, '🍞'],
  [/oeuf|œuf|omelette|quiche/i, '🥚'],
  [/riz/i, '🍚'],
  [/légume|gratin|ratatouille/i, '🥦'],
  [/soupe|bouillon/i, '🍜'],
  [/fromage/i, '🧀'],
];
function getEmoji(titre) {
  if (!titre) return '🍽️';
  for (const [regex, emoji] of EMOJI_MAP) {
    if (regex.test(titre)) return emoji;
  }
  return '🍽️';
}

// ── Tags helper (badges basés sur les données de la recette) ──
function getTags(r) {
  const tags = [];
  if (r.kcal_100g != null) {
    if (r.kcal_100g < 100) tags.push('🍃 léger');
    else if (r.kcal_100g > 250) tags.push('🔥 riche');
  }
  if (r.match_pct >= 90) tags.push('✅ Ciqual complet');
  else if (r.match_pct > 0 && r.match_pct < 60) tags.push('⚠️ partiel');
  if (r.nb_ingredients && r.nb_ingredients <= 5) tags.push('⚡ rapide');
  return tags.map(t => `<span class="tag">${t}</span>`).join('');
}

function renderRecettes(list) {
  const container = document.getElementById('recipes-list');
  if (!list.length) {
    container.innerHTML = '<div class="loading">😕 Aucune recette trouvée</div>';
    return;
  }
  container.innerHTML = list.map(r => {
    const kcal = r.kcal_100g ? `<span>🔥 ${r.kcal_100g} kcal/100g</span>` : '';
    const isFav = favoris.includes(r.fichier);
    return `
      <div class="recipe-card" onclick="openDetail('${r.fichier}')">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div>
            <div class="emoji">${getEmoji(r.titre)}</div>
            <h3>${r.titre}</h3>
          </div>
          <span class="fav-star" onclick="event.stopPropagation();toggleFavori('${r.fichier}')" style="font-size:20px;cursor:pointer">${isFav ? '⭐' : '☆'}</span>
        </div>
        <div class="meta">
          <span>📝 ${r.nb_ingredients} ingrédients</span>
          ${kcal}
          <span>✅ ${r.match_pct}%</span>
        </div>
        <div class="recipe-tags">${getTags(r)}</div>
      </div>
    `;
  }).join('');

  // Bouton nouvelle recette + assistant
    if (list.length === allRecettes.length) {
      container.innerHTML += `<div class="menu-add" onclick="openNewRecipe()" style="margin-top:4px">➕ Nouvelle recette</div>`;
      container.innerHTML += `<div class="menu-add" onclick="openAssistant()" style="margin-top:4px;border:2px dashed #4a7c5e;color:#4a7c5e">🎤 Assistant recette (texte, dictée, photo)</div>`;
    }
}

// ── Favoris ──
async function loadFavoris() {
  try {
    const res = await fetch('/api/favoris');
    favoris = await res.json();
  } catch(e) { favoris = []; }
}

async function toggleFavori(fichier) {
  const isFav = favoris.includes(fichier);
  try {
    if (isFav) {
      await fetch(`/api/favoris/${fichier}`, { method: 'DELETE' });
      favoris = favoris.filter(f => f !== fichier);
    } else {
      await fetch('/api/favoris', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({fichier}),
      });
      favoris.push(fichier);
    }
  } catch(e) {}
  renderRecettes(allRecettes);
}

// ── Search --
let searchTimeout = null;
function onSearchInput() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(doSearch, 300);
}

async function doSearch() {
  const q = document.getElementById('search-input').value.trim().toLowerCase();
  if (!q) { renderRecettes(allRecettes); return; }
  try {
    const res = await fetch(`/api/recherche/ingredient/${encodeURIComponent(q)}`);
    const data = await res.json();
    const found = data.resultats || [];
    const filtered = allRecettes.filter(r => found.some(f => f.fichier === r.fichier));
    renderRecettes(filtered);
  } catch(e) { renderRecettes(allRecettes); }
}

// ── Detail ---
let currentFichier = null;

async function openDetail(fichier) {
  currentFichier = fichier;
  try {
    const res = await fetch(`/api/recettes/${fichier}`);
    const data = await res.json();
    renderDetail(data);
  } catch(e) { alert('Erreur de chargement'); }
}

function renderDetail(data) {
  const dv = document.getElementById('detail-view');
  const kcalTotal = data.total_recette?.energie_kcal || 0;
  const pds = data.poids_total || 0;
  const meta = data.meta || {};
  const tags = meta.tags || [];
  const isFav = favoris.includes(data.fichier);
  const photos = meta.photos || {};
  const portions = meta.portions || '—';
  const temps = meta.temps_cuisson || '—';

  // Parse les étapes depuis le markdown (récupéré en async)
  fetchSteps(data.fichier).then(stepsHtml => {
    let html = `
    <div class="detail-header">
      <button class="back" onclick="closeDetail()">←</button>
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div class="emoji-big">${getEmoji(data.titre)}</div>
          <h2>${data.titre}</h2>
        </div>
        <span onclick="toggleFavoriDetail('${data.fichier}')" style="font-size:28px;cursor:pointer">${isFav ? '⭐' : '☆'}</span>
      </div>
      <div class="meta-row">
        <span>👥 ${portions} parts</span>
        <span>⏱️ ${temps}</span>
        <span>⚖️ ${pds > 0 ? '~' + Math.round(pds) + 'g' : '—'}</span>
        <span>🔥 ${Math.round(kcalTotal)} kcal</span>
      </div>
      ${tags.length ? `<div style="display:flex;gap:5px;margin-top:8px;flex-wrap:wrap">${tags.map(t => `<span class="tag" style="background:rgba(255,255,255,0.2);color:#fff">${t}</span>`).join('')}</div>` : ''}
      <div style="display:flex;gap:6px;margin-top:10px">
        <button onclick="editRecipe('${data.fichier}')" class="action-btn" style="background:rgba(255,255,255,0.2);color:#fff;font-size:12px">✏️ Modifier</button>
        <button onclick="deleteRecipe('${data.fichier}')" class="action-btn" style="background:rgba(217,122,94,0.3);color:#fff;font-size:12px">🗑️ Supprimer</button>
      </div>
    </div>
    <div class="detail-body">

    <!-- Photo -->
    ${(photos.original || photos.plated) ? `<div class="nutri-card" style="padding:0;overflow:hidden;border-radius:14px"><img src="/${photos.original || photos.plated}" style="width:100%;display:block;max-height:300px;object-fit:cover" alt="Photo recette"></div>` : ''}

    <!-- Ingrédients -->
    <div class="nutri-card"><h4>📋 Ingrédients <span style="font-size:11px;font-weight:400;color:#8a8580">(clique pour ajuster le Ciqual)</span></h4>`;
    for (let i = 0; i < data.ingredients.length; i++) {
      const ing = data.ingredients[i];
      const dotColor = ing.confiance >= 0.8 ? 'green' : ing.confiance >= 0.3 ? 'orange' : 'gray';
      const pdsStr = ing.poids_g ? `~${Math.round(ing.poids_g)}g` : '';
      const alim = ing.aliment || '—';
      html += `<div class="ingr-item" style="cursor:pointer" onclick="openCiqualPicker('${data.fichier}','${ing.id}','${ing.ingredient.replace(/'/g,"\\'")}')"
        title="${ing.aliment ? '✅ ' + ing.aliment + '&#10;&#10;' : ''}${ing.nutriments ? '🔥 ' + (ing.nutriments.energie_kcal || '—') + ' kcal/100g&#10;🥩 ' + (ing.nutriments.proteines_g || '—') + 'g prot.&#10;🧈 ' + (ing.nutriments.lipides_g || '—') + 'g lip.&#10;🍚 ' + (ing.nutriments.glucides_g || '—') + 'g gluc.&#10;🌾 ' + (ing.nutriments.fibres_g || '—') + 'g fib.&#10;🧂 ' + (ing.nutriments.sel_g || '—') + 'g sel' : ''}">
        <span class="dot ${dotColor}"></span>
        <span class="name">${ing.ingredient}</span>
        <span class="qty">${ing.quantite} ${pdsStr}</span>
        <span style="font-size:10px;color:#8a8580;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${alim}</span>
      </div>`;
    }
    html += `</div>

    <!-- Étapes -->
    ${stepsHtml}

    <!-- Photo upload + tags -->
    <div class="nutri-card"><h4>📸 Photo & infos</h4>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <input type="file" accept="image/*" id="photo-input" style="display:none" onchange="uploadPhoto('${data.fichier}')">
      <button class="action-btn" onclick="document.getElementById('photo-input').click()">📷 Ajouter une photo</button>
      <button class="action-btn" onclick="addTag('${data.fichier}')">🏷️ Ajouter un tag</button>
      <button class="action-btn" onclick="playRecipe('${data.fichier}')">🔊 Lire la recette</button>
      <button class="action-btn" onclick="addToMenuFromDetail('${data.fichier}')" style="background:#e8a838;color:#fff">🍽️ Au menu</button>
    </div>
    <div id="upload-status" style="font-size:12px;color:#8a8580;margin-top:6px"></div>
    <div id="audio-player" style="margin-top:6px;display:none"></div></div>

    <!-- Total recette -->
    <div class="nutri-card"><h4>📊 Total pour la recette</h4>`;
    const t = data.total_recette || {};
    for (const [e, l, k] of [['🔥','Calories','energie_kcal'],['🥩','Protéines','proteines_g'],['🧈','Lipides','lipides_g'],['🍚','Glucides','glucides_g']]) {
      html += `<div style="display:flex;justify-content:space-between;padding:5px 0;font-size:13px"><span>${e} ${l}</span><span style="font-weight:700">${(t[k] || 0).toFixed(1)} ${k.includes('_mg') ? 'mg' : 'g'}</span></div>`;
    }
    html += `</div>`;

    // Nutrition per 100g (tout en bas)
    if (data.profil_100g && Object.keys(data.profil_100g).length > 0) {
      html += `<div class="nutri-card"><h4>🔥 Profil nutritionnel (pour 100g) <span style="font-weight:400;font-size:11px;color:#8a8580">— max = 100%</span></h4>`;
      for (const [champ, val] of Object.entries(data.profil_100g)) {
        const info = NUTRIMENTS[champ] || {};
        const pct = calcBarWidth(champ, val);
        const color = COLORS[champ] || '#8a8580';
        html += `<div class="nutri-row"><span class="label">${info.emoji || '•'} ${info.label || champ}</span>
          <div class="bar-bg"><div class="bar-fill" style="width:${pct}%;background:${color}"></div></div>
          <span class="value">${val} <span class="unit">${info.unite || ''}</span></span></div>`;
      }
      html += `<div style="font-size:10px;color:#c4bfb8;margin-top:4px;text-align:center">⚡ Énergie max 500 kcal · Protéines/Lipides max 30g · Fibres max 10g · Sel max 3g</div></div>`;
    }

    // Contribution par ingrédient
    const totalFibres = data.total_recette?.fibres_g || 0;
    const totalProteines = data.total_recette?.proteines_g || 0;
    if (totalFibres > 0 || totalProteines > 0) {
      html += `<div class="nutri-card"><h4>🥩 Répartition par ingrédient</h4><table style="width:100%;font-size:12px;border-collapse:collapse"><tr style="border-bottom:1px solid #f0ede8;color:#8a8580">
        <th style="text-align:left;padding:4px 0;font-weight:500">Ingrédient</th>
        ${totalProteines > 0 ? '<th style="text-align:right;padding:4px 0;font-weight:500">🥩 Protéines</th>' : ''}
        ${totalFibres > 0 ? '<th style="text-align:right;padding:4px 0;font-weight:500">🌾 Fibres</th>' : ''}</tr>`;
      const contribs = data.ingredients.map(ing => {
        const poids = ing.poids_g || 0;
        return { nom: ing.ingredient, prot_contrib: poids > 0 ? ((ing.nutriments?.proteines_g || 0) * poids / 100) : 0, fib_contrib: poids > 0 ? ((ing.nutriments?.fibres_g || 0) * poids / 100) : 0 };
      });
      const totalProtContrib = contribs.reduce((s, c) => s + c.prot_contrib, 0) || 1;
      const totalFibContrib = contribs.reduce((s, c) => s + c.fib_contrib, 0) || 1;
      for (const c of contribs) {
        const pctProt = (c.prot_contrib / totalProtContrib * 100);
        const pctFib = (c.fib_contrib / totalFibContrib * 100);
        if (pctProt < 2 && pctFib < 2) continue;
        html += `<tr style="border-bottom:1px solid #f5f3f0"><td style="padding:6px 0;font-weight:500">${c.nom.slice(0,25)}</td>
          ${totalProteines > 0 ? `<td style="text-align:right">${pctProt.toFixed(0)}%</td>` : ''}
          ${totalFibres > 0 ? `<td style="text-align:right">${pctFib.toFixed(0)}%</td>` : ''}</tr>`;
      }
      html += `</table><div style="font-size:10px;color:#c4bfb8;margin-top:4px">Part de chaque ingrédient dans le total</div></div>`;
    }

    html += `</div>`;
    dv.innerHTML = html;
    dv.classList.add('show');
    document.body.style.overflow = 'hidden';
  });
}

function fetchSteps(fichier) {
  return fetch(`/api/recettes/${fichier}/raw`).then(r => r.text()).then(md => {
    // Extrait les étapes entre "## 👨‍🍳 Préparation" et "---" ou "## Astuce"
    const section = md.split('## 👨‍🍳 Préparation')[1] || md.split('## Préparation')[1] || '';
    const bloc = section.split('---')[0] || section.split('## ')[0];
    if (!bloc.trim()) {
      return `<div class="nutri-card"><h4>👨‍🍳 Préparation</h4><p style="font-size:13px;color:#8a8580">(Détails dans l'éditeur)</p></div>`;
    }
    // Parse les ### et les 1. 2. 3.
    const etapes = bloc.split('\n');
    let currentTitle = '';
    let stepNum = 0;
    let html = `<div class="nutri-card"><h4>👨‍🍳 Préparation</h4>`;
    for (const ligne of etapes) {
      const l = ligne.trim();
      const mTitle = l.match(/^###\s+(.+)/);
      const mStep = l.match(/^\d+\.\s+(.+)/);
      if (mTitle) {
        if (currentTitle) html += `</div>`;
        currentTitle = mTitle[1];
        stepNum = 0;
        html += `<div style="margin-bottom:8px"><div style="font-weight:600;font-size:14px;margin-bottom:4px">${currentTitle}</div>`;
      } else if (mStep && currentTitle) {
        stepNum++;
        html += `<div style="display:flex;gap:8px;padding:3px 0"><span style="font-weight:700;color:#4a7c5e;min-width:20px">${stepNum}.</span><span>${mStep[1]}</span></div>`;
      }
    }
    if (currentTitle) html += `</div>`;
    html += `</div>`;
    return html;
  }).catch(() => `<div class="nutri-card"><h4>👨‍🍳 Préparation</h4><p style="font-size:13px;color:#8a8580">(Détails dans l'éditeur)</p></div>`);
}

function closeDetail() {
  document.getElementById('detail-view').classList.remove('show');
  document.body.style.overflow = '';
  renderRecettes(allRecettes);
}

async function toggleFavoriDetail(fichier) {
  await toggleFavori(fichier);
  if (currentFichier) openDetail(currentFichier);
}

async function uploadPhoto(fichier) {
  const input = document.getElementById('photo-input');
  if (!input.files.length) return;
  const status = document.getElementById('upload-status');
  status.textContent = '⏳ Upload…';
  const fd = new FormData();
  fd.append('photo', input.files[0]);
  fd.append('recette', fichier);
  fd.append('type', 'original');
  try {
    const r1 = await fetch('/api/photos/upload', { method: 'POST', body: fd });
    const d1 = await r1.json();
    await fetch(`/api/recettes/${fichier}/photo`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({chemin: d1.chemin, type: 'original'}),
    });
    status.textContent = '✅ Photo enregistrée !';
    setTimeout(() => openDetail(fichier), 1000);
  } catch(e) { status.textContent = '❌ Erreur upload'; }
}

async function playRecipe(fichier) {
  const player = document.getElementById('audio-player');
  player.innerHTML = '⏳ Génération de l\'audio…';
  player.style.display = 'block';
  try {
    const res = await fetch(`/api/tts/${fichier}`);
    const data = await res.json();
    if (data.ok) {
      player.innerHTML = `<audio controls autoplay style="width:100%"><source src="${data.audio}" type="audio/mpeg"></audio>`;
    } else {
      player.innerHTML = '❌ ' + (data.error || 'Erreur');
    }
  } catch(e) {
    player.innerHTML = '❌ Erreur réseau';
  }
}

async function addTag(fichier) {
  const tag = prompt('Nouveau tag (ex: vite-fait, veggie, budget) :');
  if (!tag) return;
  try {
    const res = await fetch(`/api/recettes/${fichier}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({tags: tag.split(',').map(t => t.trim())}),
    });
    const d = await res.json();
    openDetail(fichier);
  } catch(e) { alert('Erreur'); }
}

// ── Ciqual Picker ──
let pickerFichier = null;
let pickerIngId = null;
let pickerTimeout = null;

function openCiqualPicker(fichier, ingId, ingName) {
  pickerFichier = fichier;
  pickerIngId = ingId;
  const overlay = document.createElement('div');
  overlay.id = 'ciqual-picker';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:100;background:rgba(0,0,0,0.4);display:flex;align-items:flex-end';
  overlay.onclick = (e) => { if (e.target === overlay) closeCiqualPicker(); };

  overlay.innerHTML = `
    <div style="background:#fff;border-radius:16px 16px 0 0;width:100%;max-height:80vh;overflow-y:auto;padding:16px;animation:slideUp 0.2s ease">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <h4 style="font-size:16px">🔍 Choisir l'aliment Ciqual</h4>
        <span onclick="closeCiqualPicker()" style="font-size:22px;cursor:pointer">✕</span>
      </div>
      <p style="font-size:13px;color:#6b6560;margin-bottom:8px">Pour « <strong>${ingName}</strong> »</p>
      <input type="text" id="ciqual-search" placeholder="Chercher dans Ciqual…" style="width:100%;padding:10px 12px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none;margin-bottom:10px">
      <div id="ciqual-results"><div style="text-align:center;color:#8a8580;padding:20px;font-size:13px">Tape un nom pour chercher dans la base Ciqual (3 384 aliments) 🏪</div></div>
    </div>
  `;
  document.body.appendChild(overlay);
  document.body.style.overflow = 'hidden';

  document.getElementById('ciqual-search').focus();
  document.getElementById('ciqual-search').addEventListener('input', () => {
    clearTimeout(pickerTimeout);
    pickerTimeout = setTimeout(doCiqualSearch, 300);
  });
  document.getElementById('ciqual-search').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doCiqualSearch();
  });
}

function closeCiqualPicker() {
  const el = document.getElementById('ciqual-picker');
  if (el) el.remove();
  document.body.style.overflow = '';
}

async function doCiqualSearch() {
  const q = document.getElementById('ciqual-search').value.trim();
  const results = document.getElementById('ciqual-results');
  if (!q) {
    results.innerHTML = '<div style="text-align:center;color:#8a8580;padding:20px;font-size:13px">Tape un nom pour chercher</div>';
    return;
  }
  results.innerHTML = '<div class="loading">🔍 Recherche…</div>';
  try {
    const res = await fetch(`/api/aliments/chercher/${encodeURIComponent(q)}`);
    const data = await res.json();
    if (!data.resultats || !data.resultats.length) {
      results.innerHTML = '<div style="text-align:center;color:#8a8580;padding:20px;font-size:13px">😕 Aucun résultat</div>';
      return;
    }
    results.innerHTML = data.resultats.map(r => {
      const kcal = r.energie_kcal != null ? `🔥 ${r.energie_kcal} kcal` : '';
      return `<div class="ciqual-item" onclick="selectCiqual('${r.code}')" style="cursor:pointer;padding:10px;border-bottom:1px solid #f0ede8;transition:background 0.15s" onmouseover="this.style.background='#f8f6f2'" onmouseout="this.style.background=''">
        <div style="font-weight:600;font-size:14px">${r.brut ? '✅ ' : '⚙️ '} ${r.nom}</div>
        <div style="font-size:12px;color:#8a8580;margin-top:2px">${r.groupe || ''} · ${kcal} · ${r.brut ? 'Brut' : 'Transformé'}</div>
      </div>`;
    }).join('');
  } catch(e) {
    results.innerHTML = '<div style="text-align:center;color:#d97a5e;padding:20px">❌ Erreur</div>';
  }
}

async function selectCiqual(code) {
  if (!pickerFichier || !pickerIngId) return;
  try {
    const res = await fetch(`/api/recettes/${pickerFichier}/ingredients/${pickerIngId}/mapping`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({code}),
    });
    const data = await res.json();
    if (data.ok) {
      closeCiqualPicker();
      openDetail(pickerFichier);
    } else {
      alert('Erreur : ' + (data.error || 'Échec inconnu'));
    }
  } catch(e) { alert('Erreur : ' + e.message); }
}

// ── CRUD Recettes ---

async function openNewRecipe() {
  const titre = prompt('Nom de la nouvelle recette :');
  if (!titre) return;
  try {
    const res = await fetch('/api/recettes', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({titre, description: 'À compléter…'}),
    });
    const data = await res.json();
    if (data.ok) {
      editRecipe(data.fichier);
      loadRecettes();
    } else {
      alert('Erreur : ' + (data.error || ''));
    }
  } catch(e) { alert('Erreur réseau'); }
}

// ══════════════════════════════════════════════════════════════════
// ── Fonctions restaurées (12 fonctions manquantes + helpers) ──
// Reconstruites à partir de l'ancienne sauvegarde /tmp/recheck/...
// et adaptées aux routes RÉELLES de webapp.py actuel.
// ══════════════════════════════════════════════════════════════════

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

// ── 1) editRecipe(fichier) ──
// Ouvre un éditeur Markdown brut.
// Routes utilisées : GET /api/recettes/<f>/raw, PUT /api/recettes/<f>
async function editRecipe(fichier) {
  try {
    const mdRes = await fetch(`/api/recettes/${fichier}/raw`);
    if (!mdRes.ok) { alert('Impossible de charger la recette'); return; }
    const markdown = await mdRes.text();

    const overlay = document.createElement('div');
    overlay.id = 'recipe-editor-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:100;background:#f8f6f2;overflow-y:auto';
    overlay.innerHTML = `
      <div style="max-width:640px;margin:0 auto;padding:16px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <h3 style="font-size:18px">✏️ Édition</h3>
          <span onclick="if(confirm('Fermer sans enregistrer ?'))closeEditor()" style="font-size:24px;cursor:pointer">✕</span>
        </div>
        <p style="font-size:12px;color:#8a8580;margin-bottom:8px">Édite la recette en Markdown (frontmatter, ingrédients, préparation…)</p>
        <textarea id="recipe-editor" style="width:100%;height:60vh;padding:12px;border:1px solid #ddd;border-radius:8px;font-size:13px;font-family:monospace;line-height:1.6;resize:vertical">${escapeHtml(markdown)}</textarea>
        <div style="display:flex;gap:6px;margin-top:10px">
          <button onclick="saveRecipe('${fichier}')" style="flex:1;background:#4a7c5e;color:#fff;border:none;padding:12px;border-radius:8px;font-weight:700;font-size:14px;cursor:pointer">💾 Enregistrer</button>
          <button onclick="if(confirm('Annuler les modifications ?'))closeEditor()" style="background:#8a8580;color:#fff;border:none;padding:12px;border-radius:8px;font-weight:600;font-size:14px;cursor:pointer">Annuler</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    document.getElementById('recipe-editor').focus();
  } catch(e) { alert('Erreur : ' + e.message); }
}

function closeEditor() {
  const el = document.getElementById('recipe-editor-overlay');
  if (el) el.remove();
}

async function saveRecipe(fichier) {
  const editor = document.getElementById('recipe-editor');
  if (!editor) return;
  const contenu = editor.value;
  try {
    const res = await fetch(`/api/recettes/${fichier}`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({contenu}),
    });
    const data = await res.json();
    if (data.ok) {
      closeEditor();
      closeDetail();
      loadRecettes();
      setTimeout(() => openDetail(fichier), 400);
    } else {
      alert('Erreur : ' + (data.error || ''));
    }
  } catch(e) { alert('Erreur réseau'); }
}

// ── 2) deleteRecipe(fichier) ──
// Route utilisée : DELETE /api/recettes/<f>
async function deleteRecipe(fichier) {
  if (!confirm('⚠️ Supprimer définitivement cette recette ?\n\nCette action est irréversible.')) return;
  try {
    const res = await fetch(`/api/recettes/${fichier}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.ok) {
      closeDetail();
      loadRecettes();
    } else {
      alert('Erreur : ' + (data.error || ''));
    }
  } catch(e) { alert('Erreur réseau'); }
}

// ── 3) openAssistant() ──
// Route utilisée : POST /api/assistant/recette
function openAssistant() {
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;z-index:100;background:#f8f6f2;overflow-y:auto';
  overlay.id = 'assistant-overlay';
  overlay.innerHTML = `
    <div style="max-width:640px;margin:0 auto;padding:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3 style="font-size:18px">🎤 Assistant recette</h3>
        <span onclick="closeAssistant()" style="font-size:24px;cursor:pointer">✕</span>
      </div>
      <div class="nutri-card">
        <h4>📝 Texte de la recette</h4>
        <p style="font-size:12px;color:#6b6560;margin-bottom:6px">Colle ici ta recette — dictée, copiée d'un site, écrite à la main. Je la structure automatiquement !</p>
        <textarea id="assistant-text" placeholder="Ex: Dhal de lentilles
200g lentilles corail
1 oignon
2 gousses d'ail
Éplucher et couper l'oignon. Faire revenir. Ajouter les lentilles. Laisser cuire 20 min."
style="width:100%;min-height:200px;padding:12px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none;resize:vertical;font-family:inherit"></textarea>
      </div>
      <div style="display:flex;gap:6px;margin-top:6px">
        <button onclick="submitAssistant()" style="flex:1;background:#4a7c5e;color:#fff;border:none;padding:12px;border-radius:8px;font-weight:700;font-size:14px;cursor:pointer">✨ Générer la recette</button>
        <button onclick="closeAssistant()" style="background:#8a8580;color:#fff;border:none;padding:12px;border-radius:8px;font-weight:600;font-size:14px;cursor:pointer">Annuler</button>
      </div>
      <div id="assistant-status" style="font-size:13px;color:#8a8580;margin-top:8px;text-align:center"></div>
    </div>`;
  document.body.appendChild(overlay);
}

function closeAssistant() {
  const el = document.getElementById('assistant-overlay');
  if (el) el.remove();
}

async function submitAssistant() {
  const texte = document.getElementById('assistant-text').value.trim();
  if (!texte) { alert("Colle d'abord le texte de ta recette !"); return; }
  const status = document.getElementById('assistant-status');
  status.textContent = '⏳ Génération de la recette…';
  try {
    const res = await fetch('/api/assistant/recette', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({texte}),
    });
    const data = await res.json();
    if (data.ok) {
      status.textContent = '✅ Recette créée !';
      closeAssistant();
      loadRecettes();
      setTimeout(() => editRecipe(data.fichier), 300);
    } else if (data.markdown) {
      alert('Une recette avec ce nom existe déjà. Voir la console pour le markdown généré.');
      console.log(data.markdown);
    } else {
      alert('Erreur : ' + (data.error || ''));
    }
  } catch(e) { alert('Erreur réseau : ' + e.message); }
}

// ── 4) calcBarWidth(champ, val) ──
// Calcule la largeur (%) d'une barre de progression nutritionnelle.
function calcBarWidth(champ, val) {
  const max = { energie_kcal: 500, lipides_g: 30, acides_gras_satures_g: 30, proteines_g: 30, fibres_g: 10, sel_g: 3, sucres_g: 20 };
  return Math.min((val / (max[champ] || 100)) * 100, 100);
}

// ── Table des nutriments (utilisée par calcBarWidth/renderDetail/renderNutriResults) ──
const NUTRIMENTS = {
  energie_kcal: { label: 'Énergie', emoji: '🔥', unite: 'kcal/100g' },
  proteines_g: { label: 'Protéines', emoji: '🥩', unite: 'g/100g' },
  lipides_g: { label: 'Lipides', emoji: '🧈', unite: 'g/100g' },
  glucides_g: { label: 'Glucides', emoji: '🍚', unite: 'g/100g' },
  sucres_g: { label: 'Sucres', emoji: '🍬', unite: 'g/100g' },
  fibres_g: { label: 'Fibres', emoji: '🌾', unite: 'g/100g' },
  sel_g: { label: 'Sel', emoji: '🧂', unite: 'g/100g' },
  acides_gras_satures_g: { label: 'AG saturés', emoji: '🥓', unite: 'g/100g' },
  fer_mg: { label: 'Fer', emoji: '🩸', unite: 'mg/100g' },
  calcium_mg: { label: 'Calcium', emoji: '🦴', unite: 'mg/100g' },
  potassium_mg: { label: 'Potassium', emoji: '🍌', unite: 'mg/100g' },
  vitamine_c_mg: { label: 'Vitamine C', emoji: '🍊', unite: 'mg/100g' },
};
const COLORS = {
  energie_kcal: '#e8a838', proteines_g: '#4a7c5e', lipides_g: '#d97a5e',
  glucides_g: '#6b8fa3', sucres_g: '#d4a0a0', fibres_g: '#8faa6b',
  sel_g: '#c4bfb8', acides_gras_satures_g: '#c47a6b', fer_mg: '#c47a6b',
  calcium_mg: '#8fa3b8', potassium_mg: '#b8a36b', vitamine_c_mg: '#e8a838',
};

// ── 5) renderNutriResults(data) ──
// Appelée sans argument depuis switchTab('nutri') → initialise les chips.
// Appelée avec `data` après une recherche → affiche les résultats.
// Route utilisée : GET /api/recherche/nutrition
const NUTRI_PRESETS = [
  { champ: 'fibres_g', comp: '>', val: 5, label: '🌾 Riche en fibres' },
  { champ: 'lipides_g', comp: '<', val: 5, label: '⬇️ Pauvre en lipides' },
  { champ: 'proteines_g', comp: '>', val: 15, label: '🥩 Riche en protéines' },
  { champ: 'energie_kcal', comp: '<', val: 100, label: '🔥 Light (< 100 kcal)' },
];

function loadNutriChips() {
  const chipsEl = document.getElementById('nutri-chips');
  if (!chipsEl) return;
  chipsEl.innerHTML = NUTRI_PRESETS.map(p =>
    `<span class="nutri-chip" onclick="doNutriSearch('${p.champ}','${p.comp}',${p.val},this)">${p.label}</span>`
  ).join('');
}

async function doNutriSearch(champ, comp, val, el) {
  document.querySelectorAll('#nutri-chips .nutri-chip').forEach(c => c.classList.remove('active'));
  if (el) el.classList.add('active');
  const container = document.getElementById('nutri-results');
  container.innerHTML = '<div class="loading">🔍 Recherche…</div>';
  try {
    const res = await fetch(`/api/recherche/nutrition?champ=${encodeURIComponent(champ)}&comparateur=${encodeURIComponent(comp)}&valeur=${val}`);
    const data = await res.json();
    renderNutriResults(data);
  } catch(e) { container.innerHTML = '<div class="loading">❌ Erreur</div>'; }
}

function renderNutriResults(data) {
  const container = document.getElementById('nutri-results');
  if (!container) return;
  loadNutriChips();
  if (!data) {
    container.innerHTML = '<div class="nutri-card"><p style="font-size:13px;color:#8a8580">Choisis un critère ci-dessus pour lancer la recherche 🔬</p></div>';
    return;
  }
  if (!data.resultats || !data.resultats.length) {
    container.innerHTML = '<div class="loading">😕 Aucune recette ne correspond</div>';
    return;
  }
  let html = `<div class="nutri-card"><h4>${data.termes ? data.termes.join(', ') : ''}</h4>`;
  html += `<div style="font-size:12px;color:#8a8580;margin-bottom:6px">${data.resultats.length} résultat(s)</div>`;
  for (const r of data.resultats) {
    html += `<div class="nutri-result-item" onclick="openDetail('${r.fichier}')" style="cursor:pointer">
      <span>${r.titre}</span>
      <span class="nr-value">${r.kcal_100g != null ? r.kcal_100g + ' kcal/100g' : '—'}</span>
    </div>`;
  }
  html += `</div>`;
  container.innerHTML = html;
}

// ── 6) buildFrigoChips() ──
// Extrait les ingrédients des recettes chargées pour proposer des chips
// cliquables dans l'onglet Frigo. Route utilisée : GET /api/recettes/<f>
let FRIGO_CHIPS = [];
function buildFrigoChips() {
  const seen = new Set();
  FRIGO_CHIPS = [];
  if (!allRecettes.length) return;
  allRecettes.forEach(r => {
    fetch(`/api/recettes/${r.fichier}`).then(res => res.json()).then(data => {
      if (!data.ingredients) return;
      data.ingredients.forEach(ing => {
        const nom = (ing.ingredient || '').toLowerCase().trim();
        if (!nom || seen.has(nom)) return;
        seen.add(nom);
        FRIGO_CHIPS.push({ name: nom, confiance: ing.confiance });
      });
    }).catch(() => {});
  });
}

// ── Helpers Frigo (stockage local) ──
function getFrigoStock() {
  return Array.isArray(frigoIngredients) ? frigoIngredients : [];
}
function setFrigoStock(stock) {
  frigoIngredients = stock;
  localStorage.setItem('frigo_stock', JSON.stringify(stock));
}
function frigoAdd(nom) {
  const stock = getFrigoStock();
  if (!stock.some(s => s.nom === nom)) stock.push({ nom, qte: 1, unite: 'pièce' });
  setFrigoStock(stock);
}
function frigoRemove(nom) {
  setFrigoStock(getFrigoStock().filter(s => s.nom !== nom));
}
function frigoToggleChip(nom) {
  if (getFrigoStock().some(s => s.nom === nom)) frigoRemove(nom);
  else frigoAdd(nom);
  renderFrigo();
}
function frigoAdjustQty(idx, delta) {
  const stock = getFrigoStock();
  if (idx >= 0 && idx < stock.length) {
    stock[idx].qte = (stock[idx].qte || 1) + delta;
    if (stock[idx].qte <= 0) stock.splice(idx, 1);
    setFrigoStock(stock);
    renderFrigo();
  }
}
function frigoRemoveAt(idx) {
  const stock = getFrigoStock();
  if (idx >= 0 && idx < stock.length) {
    stock.splice(idx, 1);
    setFrigoStock(stock);
    renderFrigo();
  }
}
function frigoAddCustom() {
  const input = document.getElementById('frigo-input');
  if (!input) return;
  const val = input.value.trim();
  if (!val) return;
  const stock = getFrigoStock();
  val.split(',').map(s => s.trim().toLowerCase()).filter(Boolean).forEach(nom => {
    if (!stock.some(x => x.nom === nom)) stock.push({ nom, qte: 1, unite: 'pièce' });
  });
  setFrigoStock(stock);
  input.value = '';
  renderFrigo();
}
function frigoReset() {
  setFrigoStock([]);
  renderFrigo();
}

// ── 7) renderFrigo() ──
// Route utilisée : GET /api/frigo?ingredients=...
async function renderFrigo() {
  const container = document.getElementById('frigo-content');
  if (!container) return;
  const stock = getFrigoStock();

  if (!FRIGO_CHIPS.length && allRecettes.length) {
    container.innerHTML = '<div class="loading">⏳ Chargement des ingrédients…</div>';
    setTimeout(renderFrigo, 500);
    return;
  }

  container.innerHTML = `
    <div class="nutri-card">
      <h4>🧊 Mon frigo</h4>
      <p style="font-size:12px;color:#6b6560;margin-top:2px">Clique sur les ingrédients que t'as — ils deviennent verts ✅.</p>
      <div style="display:flex;gap:4px;flex-wrap:wrap;margin:8px 0;min-height:28px">
        ${stock.length === 0 ? "<span style=\"font-size:13px;color:#c4bfb8;font-style:italic\">Aucun ingrédient — clique sur ceux que t'as !</span>" :
          stock.map((s, idx) => `<span class="tag" style="background:#4a7c5e;color:#fff;cursor:default;display:inline-flex;align-items:center;gap:4px">
            ${s.nom}
            <span onclick="frigoAdjustQty(${idx},-1)" style="cursor:pointer;opacity:0.7">−</span>
            <span onclick="frigoAdjustQty(${idx},1)" style="cursor:pointer;opacity:0.7">+</span>
            <span onclick="frigoRemoveAt(${idx})" style="cursor:pointer;opacity:0.6">✕</span>
          </span>`).join('')}
      </div>
      <div style="display:flex;gap:4px;flex-wrap:wrap;margin:8px 0">${FRIGO_CHIPS.length ? FRIGO_CHIPS.map(c => {
        const actif = stock.some(s => s.nom === c.name);
        return `<span class="nutri-chip${actif ? ' active' : ''}" onclick="frigoToggleChip('${c.name.replace(/'/g,"\\'")}')">${actif ? '✅ ' : ''}${c.name}</span>`;
      }).join('') : '<span style="font-size:12px;color:#8a8580">Chargement des suggestions…</span>'}</div>
      <div style="display:flex;gap:4px;margin-top:6px">
        <input type="text" id="frigo-input" placeholder="Ajouter… ex: poivron, champignons" style="flex:1;padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:12px;outline:none">
        <button onclick="frigoAddCustom()" style="background:#4a7c5e;color:#fff;border:none;padding:6px 12px;border-radius:6px;font-weight:600;font-size:12px;cursor:pointer">➕</button>
        <button onclick="frigoReset()" style="background:#d97a5e;color:#fff;border:none;padding:6px 10px;border-radius:6px;font-size:12px;cursor:pointer">🗑️</button>
      </div>
    </div>
    <div id="frigo-results">${stock.length ? '<div class="loading">🔍 Recherche…</div>' : '<div class="nutri-card"><div style="font-size:13px;color:#8a8580;text-align:center">Ajoute des ingrédients pour voir les recettes possibles ✨</div></div>'}</div>
  `;

  const inputEl = document.getElementById('frigo-input');
  if (inputEl) inputEl.addEventListener('keydown', e => { if (e.key === 'Enter') frigoAddCustom(); });

  if (stock.length) doFrigoSearch();
}

async function doFrigoSearch() {
  const resultsDiv = document.getElementById('frigo-results');
  if (!resultsDiv) return;
  const stock = getFrigoStock();
  if (!stock.length) { resultsDiv.innerHTML = ''; return; }
  const ingredients = stock.map(s => s.nom).join(',');
  resultsDiv.innerHTML = '<div class="loading">🔍 Recherche…</div>';
  try {
    const res = await fetch(`/api/frigo?ingredients=${encodeURIComponent(ingredients)}`);
    const data = await res.json();
    resultsDiv.innerHTML = `<div class="nutri-card"><h4>🍽️ Avec ton frigo, tu peux faire…</h4></div>`;
    for (const r of data) {
      const icon = r.faisable ? '✅' : r.ratio >= 50 ? '⚠️' : '';
      const barW = Math.max(r.ratio, 3);
      resultsDiv.innerHTML += `
        <div class="recipe-card" onclick="openDetail('${r.fichier}')">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h3>${icon} ${r.titre}</h3>
            <span style="font-size:14px;font-weight:700;color:${r.faisable ? '#4a7c5e' : '#d97a5e'}">${r.ratio}%</span>
          </div>
          <div style="height:4px;background:#f0ede8;border-radius:2px;margin:6px 0;overflow:hidden">
            <div style="height:100%;width:${barW}%;background:${r.faisable ? '#4a7c5e' : '#e8a838'};border-radius:2px"></div>
          </div>
          <div style="font-size:12px;color:#8a8580">
            ${r.trouves}/${r.total} ingrédients
            ${r.manquants.length ? '· Il manque : ' + r.manquants.slice(0,4).join(', ') : ''}
          </div>
        </div>
      `;
    }
  } catch(e) { resultsDiv.innerHTML = '<div class="loading">❌ Erreur</div>'; }
}

// ── 8) renderCiqualExplorer() ──
// Route utilisée : GET /api/aliments/chercher/<terme>
function renderCiqualExplorer() {
  const container = document.getElementById('ciqual-content');
  if (!container) return;
  container.innerHTML = `
    <div class="nutri-card">
      <h4>📚 Base Ciqual</h4>
      <p style="font-size:12px;color:#6b6560;margin-top:2px">Cherche un aliment dans la base nutritionnelle de référence (ANSES 2025)</p>
      <div style="display:flex;gap:6px;margin-top:8px">
        <input type="text" id="ciqual-explorer-input" placeholder="Chercher un aliment… (ex: oignon, lentille, saumon)" style="flex:1;padding:8px 12px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none">
        <button onclick="doCiqualExplorerSearch()" style="background:#4a7c5e;color:#fff;border:none;padding:8px 16px;border-radius:8px;font-weight:600;cursor:pointer">🔍</button>
      </div>
      <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:8px">
        <span class="nutri-chip" onclick="quickCiqualSearch('légume')">🥬 Légumes</span>
        <span class="nutri-chip" onclick="quickCiqualSearch('fruit')">🍎 Fruits</span>
        <span class="nutri-chip" onclick="quickCiqualSearch('viande')">🥩 Viandes</span>
        <span class="nutri-chip" onclick="quickCiqualSearch('poisson')">🐟 Poissons</span>
        <span class="nutri-chip" onclick="quickCiqualSearch('lait')">🧀 Laitages</span>
        <span class="nutri-chip" onclick="quickCiqualSearch('pain')">🍞 Céréales</span>
      </div>
    </div>
    <div id="ciqual-explorer-results"></div>
  `;
  const inputEl = document.getElementById('ciqual-explorer-input');
  inputEl.addEventListener('keydown', e => { if (e.key === 'Enter') doCiqualExplorerSearch(); });
  inputEl.focus();
}

function quickCiqualSearch(terme) {
  document.getElementById('ciqual-explorer-input').value = terme;
  doCiqualExplorerSearch();
}

async function doCiqualExplorerSearch() {
  const q = document.getElementById('ciqual-explorer-input').value.trim();
  const results = document.getElementById('ciqual-explorer-results');
  if (!q) { results.innerHTML = ''; return; }
  results.innerHTML = '<div class="loading">🔍 Recherche…</div>';
  try {
    const res = await fetch(`/api/aliments/chercher/${encodeURIComponent(q)}`);
    const data = await res.json();
    if (!data.resultats || !data.resultats.length) {
      results.innerHTML = '<div style="text-align:center;color:#8a8580;padding:20px;font-size:13px">😕 Aucun résultat</div>';
      return;
    }
    results.innerHTML = data.resultats.map(r => {
      const kcal = r.energie_kcal != null ? `🔥 ${r.energie_kcal} kcal` : '';
      return `<div class="nutri-card" style="cursor:pointer;padding:10px" onclick="frigoAdd('${r.nom.toLowerCase().replace(/'/g,"\\'")}');switchTab('frigo')">
        <div style="font-weight:600;font-size:14px">${r.brut ? '✅ ' : '⚙️ '}${r.nom}</div>
        <div style="font-size:12px;color:#8a8580;margin-top:2px">${r.groupe || ''} · ${kcal} · ${r.brut ? 'Brut' : 'Transformé'}</div>
      </div>`;
    }).join('');
  } catch(e) {
    results.innerHTML = '<div style="text-align:center;color:#d97a5e;padding:20px">❌ Erreur</div>';
  }
}

// ── 9) renderMenu() + 10) loadMenu() ──
// Route utilisée : POST /api/menu
const NUTRI_TARGETS = {
  energie_kcal: { label: '🔥 Calories', cible: 600, unite: 'kcal', emoji: '🔥' },
  proteines_g: { label: '🥩 Protéines', cible: 20, unite: 'g', emoji: '🥩' },
  lipides_g: { label: '🧈 Lipides', cible: 22, unite: 'g', emoji: '🧈' },
  glucides_g: { label: '🍚 Glucides', cible: 75, unite: 'g', emoji: '🍚' },
};

function getAllMenuRecettes() {
  return [...menuJournalier['petit-dejeuner'], ...menuJournalier['dejeuner'], ...menuJournalier['diner'], ...menuJournalier['collation']];
}
function getTotalPlats() { return getAllMenuRecettes().length; }

function addToMenu(fichier) {
  const choix = prompt('Ajouter dans :\n1 = Petit-déjeuner\n2 = Déjeuner\n3 = Dîner\n4 = Collation');
  const map = { '1': 'petit-dejeuner', '2': 'dejeuner', '3': 'diner', '4': 'collation' };
  const slot = map[choix] || 'dejeuner';
  if (!menuJournalier[slot].includes(fichier)) menuJournalier[slot].push(fichier);
  renderMenu();
}

function removeFromMenu(fichier) {
  for (const slot of Object.keys(menuJournalier)) {
    menuJournalier[slot] = menuJournalier[slot].filter(f => f !== fichier);
  }
  renderMenu();
}

// addToMenuFromDetail : appelée depuis la fiche détail d'une recette
function addToMenuFromDetail(fichier) {
  closeDetail();
  addToMenu(fichier);
  switchTab('menu');
}

async function renderMenu() {
  const container = document.getElementById('menu-content');
  if (!container) return;

  let html = `<div class="nutri-card" style="padding:6px 10px;display:flex;align-items:center;gap:6px">
    <span style="font-size:14px;font-weight:600">🍽️ Menu du jour</span>
    <span style="flex:1"></span>
    <span style="font-size:11px;color:#8a8580">${getTotalPlats()} plat(s)</span>
    ${getTotalPlats() ? `<span class="tag" style="cursor:pointer;background:#d97a5e;color:#fff;font-size:11px" onclick="menuJournalier={'petit-dejeuner':[],'dejeuner':[],'diner':[],'collation':[]};renderMenu()">🗑️</span>` : ''}
  </div>`;

  if (!getTotalPlats()) {
    html += `<div class="nutri-card" style="text-align:center;padding:24px 16px">
      <div style="font-size:40px;margin-bottom:8px">🍽️</div>
      <div style="font-weight:600;font-size:16px">Ajoute des recettes à ton menu</div>
      <div style="font-size:13px;color:#8a8580;margin-top:4px">Objectifs par repas : 600 kcal · 20g protéines · 22g lipides</div>
    </div>`;
    html += allRecettes.map(r => `
      <div class="recipe-card" onclick="addToMenu('${r.fichier}')">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <h3>${getEmoji(r.titre)} ${r.titre}</h3>
          <span style="font-size:20px;color:#4a7c5e">➕</span>
        </div>
      </div>
    `).join('');
    container.innerHTML = html;
    return;
  }

  try {
    const res = await fetch('/api/menu', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({recettes: getAllMenuRecettes()}) });
    const data = await res.json();
    const t = data.total;

    html += `<div class="menu-summary">
      <div style="font-size:13px;opacity:0.9">🍽️ ${data.plats.length} plat(s)</div>
      <div class="big-num">${Math.round(t.kcal)} kcal</div>
      <div class="row">
        <div><div class="num">${Math.round(t.proteines_g)} g</div><div class="lbl">Protéines</div></div>
        <div><div class="num">${Math.round(t.lipides_g)} g</div><div class="lbl">Lipides</div></div>
        <div><div class="num">${Math.round(t.glucides_g)} g</div><div class="lbl">Glucides</div></div>
      </div>
    </div>`;

    html += `<div class="nutri-card"><h4>📈 Progrès vers mes objectifs</h4>`;
    for (const [champ, cfg] of Object.entries(NUTRI_TARGETS)) {
      const actuel = t[champ] || 0;
      const pct = Math.min(actuel / cfg.cible * 100, 100);
      const color = pct >= 100 ? '#4a7c5e' : pct >= 75 ? '#e8a838' : '#c4bfb8';
      html += `<div style="margin-bottom:6px">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px">
          <span>${cfg.emoji} ${cfg.label}</span>
          <span style="font-weight:600">${Math.round(actuel)} / ${cfg.cible} ${pct >= 100 ? '✅' : ''}</span>
        </div>
        <div style="height:6px;background:#f0ede8;border-radius:3px;overflow:hidden">
          <div style="height:100%;width:${pct}%;background:${color};border-radius:3px"></div>
        </div>
      </div>`;
    }
    html += `</div>`;

    for (const [slot, recettes] of Object.entries(menuJournalier)) {
      if (!recettes.length) continue;
      html += `<div class="nutri-card" style="background:#f0ede8;padding:8px 12px;font-weight:600;font-size:13px">${SLOT_ICONS[slot]} ${SLOT_LABELS[slot]}</div>`;
      for (const fic of recettes) {
        const p = data.plats.find(x => x.fichier === fic);
        if (!p) continue;
        html += `<div class="recipe-card" style="cursor:default">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h3>${p.titre}</h3>
            <span onclick="removeFromMenu('${fic}')" style="cursor:pointer;font-size:18px;opacity:0.5">✕</span>
          </div>
          <div style="display:flex;gap:12px;margin-top:4px;font-size:12px;color:#8a8580">
            <span>🔥 ${Math.round(p.kcal)} kcal</span>
            <span>🥩 ${Math.round(p.proteines)}g</span>
            <span>🧈 ${Math.round(p.lipides)}g</span>
            <span>🍚 ${Math.round(p.glucides)}g</span>
          </div>
        </div>`;
      }
    }

    html += `<div class="menu-add" onclick="switchTab('recipes')">➕ Ajouter une recette</div>`;
    container.innerHTML = html;
  } catch(e) { container.innerHTML = '<div class="loading">❌ Erreur</div>'; }
}

// loadMenu() : point d'entrée appelé depuis switchTab('menu').
// Le menu est stocké en mémoire (menuJournalier) — pas de persistance
// serveur dédiée (pas de route GET /api/menu), donc on délègue à renderMenu().
function loadMenu() {
  renderMenu();
}

// ── 11) renderPlanning() ──
// Route utilisée : POST /api/planning/save (sauvegarde optionnelle serveur)
function savePlanning() {
  localStorage.setItem('planning_semaine', JSON.stringify(planningSemaine));
}

function toggleActivite(jour, fait) {
  if (!planningSemaine[jour].activite) planningSemaine[jour].activite = { fait: false, duree: 30 };
  planningSemaine[jour].activite.fait = fait;
  savePlanning();
}
function setDureeActivite(jour, duree) {
  if (!planningSemaine[jour].activite) planningSemaine[jour].activite = { fait: false, duree: 30 };
  planningSemaine[jour].activite.duree = parseInt(duree) || 30;
  savePlanning();
}

function savePlanningToServer() {
  fetch('/api/planning/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(planningSemaine),
  }).then(r => r.json()).then(d => {
    if (d.ok) alert('✅ Planning sauvegardé sur le serveur !');
    else alert('❌ Erreur: ' + (d.error || ''));
  }).catch(() => alert('❌ Erreur réseau'));
}

function removeFromPlanning(jour, repas, idx) {
  if (idx >= 0 && idx < (planningSemaine[jour]?.[repas]?.length || 0)) {
    planningSemaine[jour][repas].splice(idx, 1);
    savePlanning();
    renderPlanning();
  }
}

function selectPlanningRecette(jour, repas, fichier, titre) {
  planningSemaine[jour][repas].push({ type: 'recette', titre, fichier });
  savePlanning();
  const sel = document.getElementById('planning-selector');
  if (sel) sel.remove();
  renderPlanning();
}

function selectPlanningIngredient(jour, repas, idx) {
  const stock = getFrigoStock();
  if (idx < 0 || idx >= stock.length) return;
  const ing = stock[idx];
  planningSemaine[jour][repas].push({ type: 'ingredient', nom: ing.nom });
  savePlanning();
  const sel = document.getElementById('planning-selector');
  if (sel) sel.remove();
  renderPlanning();
}

function showPlanningTab(el, tab) {
  document.querySelectorAll('#planning-selector .nutri-chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('planning-tab-recettes').style.display = tab === 'recettes' ? 'block' : 'none';
  document.getElementById('planning-tab-frigo').style.display = tab === 'frigo' ? 'block' : 'none';
}

function filterPlanningRecettes() {
  const q = (document.getElementById('planning-search')?.value || '').toLowerCase();
  document.querySelectorAll('#planning-recettes-list .recipe-card').forEach(card => {
    const titre = card.querySelector('h3')?.textContent?.toLowerCase() || '';
    card.style.display = titre.includes(q) ? '' : 'none';
  });
}

function addToPlanning(jour, repas) {
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;z-index:100;background:rgba(0,0,0,0.4);display:flex;align-items:flex-end';
  overlay.id = 'planning-selector';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

  const stock = getFrigoStock();
  overlay.innerHTML = `<div style="background:#fff;border-radius:16px 16px 0 0;width:100%;max-height:85vh;overflow-y:auto;padding:16px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
      <h4 style="font-size:16px">${SLOT_ICONS[repas]} Ajouter à ${SLOT_LABELS[repas]} — ${jour}</h4>
      <span onclick="document.getElementById('planning-selector').remove()" style="font-size:22px;cursor:pointer">✕</span>
    </div>
    <div style="display:flex;gap:6px;margin-bottom:10px">
      <span class="nutri-chip active" onclick="showPlanningTab(this,'recettes')">📖 Recettes</span>
      <span class="nutri-chip" onclick="showPlanningTab(this,'frigo')">🧊 Mon frigo</span>
    </div>
    <div id="planning-tab-recettes">
      <input type="text" id="planning-search" placeholder="Chercher une recette…" style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:8px;font-size:13px;outline:none;margin-bottom:8px" oninput="filterPlanningRecettes()">
      <div id="planning-recettes-list">${allRecettes.map(r => `
        <div class="recipe-card" onclick="selectPlanningRecette('${jour}','${repas}','${r.fichier}','${r.titre.replace(/'/g,"\\'")}')" style="cursor:pointer">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h3>${getEmoji(r.titre)} ${r.titre}</h3>
            <span style="font-size:14px;color:#4a7c5e">➕</span>
          </div>
        </div>`).join('')}</div>
    </div>
    <div id="planning-tab-frigo" style="display:none">
      <div style="font-size:13px;color:#8a8580;margin-bottom:8px">Ingrédients disponibles dans ton frigo :</div>
      ${!stock.length ? "<div style=\"font-size:13px;color:#c4bfb8;padding:10px;text-align:center\">🧊 Frigo vide — ajoute des ingrédients dans l'onglet Frigo</div>" :
        stock.map((s, i) => `<div class="recipe-card" onclick="selectPlanningIngredient('${jour}','${repas}',${i})" style="cursor:pointer">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h3>🧊 ${s.nom}</h3>
            <span style="font-size:13px;color:#8a8580">➕</span>
          </div>
        </div>`).join('')}
    </div>
  </div>`;
  document.body.appendChild(overlay);
}

function exportPlanning() {
  let texte = '📅 PLANNING HEBDOMADAIRE\n' + '═'.repeat(40) + '\n\n';
  for (const jour of JOURS) {
    const entries = Object.entries(planningSemaine[jour] || {}).filter(([, v]) => Array.isArray(v));
    if (!entries.some(([, v]) => v.length > 0)) continue;
    texte += `📆 ${jour.charAt(0).toUpperCase() + jour.slice(1)}\n`;
    for (const [repas, items] of entries) {
      texte += `  ${SLOT_ICONS[repas] || '🍽️'} ${SLOT_LABELS[repas] || repas} : `;
      texte += items.length ? items.map(i => i.type === 'recette' ? i.titre : `🧊 ${i.nom}`).join(' + ') : '—';
      texte += '\n';
    }
    texte += '\n';
  }
  navigator.clipboard.writeText(texte).then(() => {
    alert('📋 Planning copié dans le presse-papier !');
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = texte;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    alert('📋 Planning copié !');
  });
}

function renderPlanning() {
  const container = document.getElementById('semaine-content');
  if (!container) return;

  let html = `<div class="nutri-card" style="padding:10px 14px;display:flex;align-items:center;gap:6px;flex-wrap:wrap">
    <span style="font-size:16px;font-weight:700">📅 Planning semaine</span>
    <span onclick="if(confirm('Vider la semaine ?')){JOURS.forEach(j=>{planningSemaine[j]={};REPAS.forEach(r=>planningSemaine[j][r]=[])});savePlanning();renderPlanning()}" style="margin-left:auto;font-size:12px;color:#d97a5e;cursor:pointer">🗑️ Vider</span>
    <span onclick="exportPlanning()" style="font-size:12px;color:#4a7c5e;cursor:pointer;margin-left:4px">📋 Exporter</span>
    <span onclick="savePlanningToServer()" style="font-size:12px;color:#6b8fa3;cursor:pointer;margin-left:4px">💾 Sauvegarder</span>
  </div>`;

  for (const jour of JOURS) {
    const entries = Object.entries(planningSemaine[jour] || {}).filter(([, v]) => Array.isArray(v));
    const totalItems = entries.reduce((s, [, v]) => s + v.length, 0);

    html += `<div style="margin-bottom:12px">
      <div style="background:#2d4a3b;color:#fff;padding:8px 12px;border-radius:10px 10px 0 0;font-weight:600;font-size:14px;display:flex;justify-content:space-between;align-items:center">
        <span>📆 ${jour.charAt(0).toUpperCase() + jour.slice(1)}</span>
        <span style="font-size:12px;font-weight:400;opacity:0.8">${totalItems} élément(s)</span>
      </div>`;

    for (const [repas, items] of entries) {
      html += `<div style="border:1px solid #f0ede8;border-top:none;padding:6px 10px">
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:13px;font-weight:600;color:#4a7c5e;margin-bottom:4px">
          <span>${SLOT_ICONS[repas] || '🍽️'} ${SLOT_LABELS[repas] || repas}</span>
          <span style="font-size:11px;font-weight:400;color:#8a8580;cursor:pointer" onclick="addToPlanning('${jour}','${repas}')">➕ Ajouter</span>
        </div>`;
      if (!items.length) {
        html += `<div style="font-size:12px;color:#c4bfb8;font-style:italic;padding:4px 0">Vide</div>`;
      } else {
        for (let i = 0; i < items.length; i++) {
          const item = items[i];
          const label = item.type === 'recette' ? item.titre : '🧊 ' + item.nom;
          html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0;font-size:13px;border-bottom:1px solid #f8f6f2">
            <span>${label}</span>
            <span onclick="removeFromPlanning('${jour}','${repas}',${i})" style="cursor:pointer;font-size:14px;opacity:0.4">✕</span>
          </div>`;
        }
      }
      html += `</div>`;
    }
    const actif = planningSemaine[jour].activite || {};
    html += `<div style="border:1px solid #f0ede8;border-top:none;padding:8px 10px;display:flex;align-items:center;gap:8px;font-size:13px">
      <input type="checkbox" id="act-${jour}" ${actif.fait ? 'checked' : ''} onchange="toggleActivite('${jour}',this.checked)" style="width:18px;height:18px">
      <label for="act-${jour}" style="font-weight:500">🏃 Activité physique</label>
      <input type="number" id="dur-${jour}" value="${actif.duree || 30}" min="0" max="240" onchange="setDureeActivite('${jour}',this.value)" style="width:50px;padding:3px 5px;border:1px solid #ddd;border-radius:5px;font-size:13px;text-align:center">
      <span style="font-size:12px;color:#8a8580">min</span>
    </div>`;
    html += `</div>`;
  }

  container.innerHTML = html;
}
