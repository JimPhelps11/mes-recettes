// Compatibilité rapide: charger allRecettes depuis le endpoint /api/recettes existant
(async () => {
  try {
    const r = await fetch('/api/recettes');
    window.allRecettes = await r.json();
  } catch(e) {
    window.allRecettes = [];
  }
})();

// ====== NOUVEAU: Composant PlateAnalyzer (JS Module intégrable) ======
class PlateAnalyzer {
  static async init(targetTab = '#tab-plateanalyzer') {
    const html = `
<div>
  <div class="nutri-card">
    <h4>🍽️ Analyser mon assiette</h4>
    <p style="font-size:13px;color:#6b6560;margin-top:4px">
      Prends une photo de ton assiette : on détecte les ingrédients, quantités, et te propose des recettes similaires.
    </p>
  </div>

  <div class="plate-analyzer-container" style="padding:0 16px 60px">
    <input type="file" id="plate-upload" accept="image/*" capture="environment" style="display:none" />

    <div class="analyzer-card">
      <div class="analyzer-header">
        <button class="action-btn" onclick="document.getElementById('plate-upload').click()">📷 Importer une photo</button>
      </div>
      <p class="analyzer-tip">Glisser-déposer ou appuyer pour importer ta photo.</p>

      <div class="analyzer-preview" id="analyzer-preview">
        <img id="analyzer-image" style="max-width:100%;max-height:200px;border-radius:8px;display:none" />
      </div>

      <div class="analyzer-loading" id="analyzer-loading" style="display:none;">🔄 Analyse en cours…</div>

      <div class="analyzer-results" id="analyzer-results">
        <h5 style="margin-bottom:8px">📋 Résultat de l'analyse</h5>
        <div id="analyzer-ingredient-list"></div>

        <div id="analyzer-suggestions" style="margin-top:12px">
          <h5 style="margin-bottom:8px">🔥 Recettes similaires (Ciqual/FR)</h5>
          <div id="suggestions-carousel"></div>
        </div>

        <div class="error-box" id="analyzer-error" style="margin-top:10px;display:none"></div>
      </div>
    </div>
  </div>
</div>
`;
    document.querySelector(targetTab).innerHTML = html;

    // Gestionnaire de fichier
    document.getElementById('plate-upload').addEventListener('change', PlateAnalyzer.handleImage);

    // Fallback drag/drop sur la carte
    const card = document.querySelector('.plate-analyzer-container .analyzer-card');
    ['dragover','drop'].forEach(e => {
      card.addEventListener(e, (ev) => {
        ev.preventDefault();
        if (e==='dragover') { card.style.backgroundColor='rgba(0,0,0,.04)'; return; }
        card.style.backgroundColor=''; if (ev.dataTransfer.files && ev.dataTransfer.files[0]) {
          document.getElementById('plate-upload').files = ev.dataTransfer.files;
          PlateAnalyzer.handleImage({target:{files: ev.dataTransfer.files}});
        }
      });
    });
  }

  static async handleImage(evt) {
    const file = evt.target.files[0];
    if (!file) return;

    const preview = document.getElementById('analyzer-preview');
    const img = document.getElementById('analyzer-image');
    const loading = document.getElementById('analyzer-loading');
    const results = document.getElementById('analyzer-results');
    const error = document.getElementById('analyzer-error');

    // Reset UI
    img.style.display = 'none';
    results.style.display = 'none';
    loading.style.display = 'block';
    error.style.display = 'none';

    // Preview image
    const url = URL.createObjectURL(file);
    img.src = url; img.style.display = 'block';

    loading.textContent = '🔄 Analyse en cours…';

    const data = new FormData();
    data.append('image', file);

    // Appel au endpoint de vision existant /api/vision/estimate_portion (flask backend)
    try {
      const r = await fetch('/api/vision/estimate_portion', { method:'POST', body: data });
      const res = await r.json();

      if (res.error) throw new Error(res.error);

      // Affichage résultats
      PlateAnalyzer.renderIngredients(res);
      PlateAnalyzer.renderSuggestions(res);

      results.style.display = 'block';
      loading.style.display = 'none';
    } catch(err) {
      error.textContent = '⚠️ Echec de l’analyse: ' + (err.message||String(err));
      error.style.display = 'block';
      loading.style.display = 'none';
    } finally {
      // Cleanup
      if (url) URL.revokeObjectURL(url);
    }
  }

  static renderIngredients(res) {
    const list = document.getElementById('analyzer-ingredient-list');
    let html = '';
    for (const i of res.ingredient || []) {
      const cert = i.certitude || 'moyenne';
      const dotClass = {haute:'green',moyenne:'orange',basse:'red'}[cert] || 'gray';
      html += `
        <div class="ingr-item">
          <span class="dot ${dotClass}"></span>
          <span class="name">${i.nom}</span>
          <span class="qty">${i.quantite_g}g</span>
        </div>
      `;
    }
    list.innerHTML = html || '<p style="font-size:13px;color:#8a8580;">Aucun ingrédient détecté avec certitude.</p>';
  }

  static renderSuggestions(res) {
    if (!Array.isArray(res.suggestions_recettes) || res.suggestions_recettes.length === 0) {
      document.getElementById('suggestions-carousel').innerHTML = '';
      return;
    }
    const carousel = document.getElementById('suggestions-carousel');
    let html = '';
    for (const r of res.suggestions_recettes) {
      const kcal = r.kcal_100g ? `<small>🔥 ${r.kcal_100g}kcal/100g</small>` : '';
      html += `
        <div class="analyzer-item-card" onclick="openDetail('${r.fichier}')">
          <h6 style="margin:0;font-size:14px">${r.titre}</h6>
          <p style="margin:4px 0;font-size:11px;color:#5d5750"><small>${r.match_pct}%</small> ${kcal}</p>
        </div>
      `;
    }
    carousel.innerHTML = `<div style="display:flex;gap:8px;overflow-x:auto;padding:4px 0">${html}</div>`;
  }
}

// ====== Intégration app.js: ajout de l'onglet et initialisation ======
// On attend que l'UI charge

let didInjectTab = false;
const checkTabs = setInterval(() => {
  if (document.querySelector('.tabs')) {
    clearInterval(checkTabs);
    if (!didInjectTab) {
      didInjectTab = true;
      const tabsBar = document.querySelector('.tabs');
      const newTab = document.createElement('div');
      newTab.className = 'tab';
      newTab.dataset.tab = 'plateanalyzer';
      newTab.innerHTML = '🍽️ Plate · Anal';
      tabsBar.appendChild(newTab);
      
      const newTabContent = document.createElement('div');
      newTabContent.id = 'tab-plateanalyzer';
      newTabContent.className = 'tab-content';
      const container = document.getElementById('tab-recipes').parentNode;
      container.appendChild(newTabContent);
      
      // Ensures we don't leave duplicate listeners
    }
  }
}, 200);

// Après chargement de allRecettes (lazy), initialiser le composant
window.addEventListener('load', () => {
  setTimeout(async () => {
    await PlateAnalyzer.init();
    // Bind tab switching
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        if (tab.dataset.tab === 'plateanalyzer') {
          PlateAnalyzer.init();
        }
      });
    });
  }, 300);
});

// Expose global for dev console
window.PlateAnalyzer = PlateAnalyzer;
